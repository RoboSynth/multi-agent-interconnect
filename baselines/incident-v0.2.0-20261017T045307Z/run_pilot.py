"""Run paired real-process feasibility tests using the official AIP SDK."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
from acps_sdk.aip import AipRpcClient, StructuredDataItem, TaskState

ROOT = Path(__file__).resolve().parent
SDK_COMMIT = '3985c1330209f075c124669cc9d31f0e75448140'
logging.basicConfig(level=logging.ERROR)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


class Lab:
    def __init__(self, output):
        self.output = output
        self.processes = []
        self.handles = []
        self.ports = set()
        self.audit = output / 'events.jsonl'
        self.case_id = 'setup'
        self.records = {}
        self.calls = 0
        self.fallbacks = 0

    def event(self, kind, **data):
        with self.audit.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                    'case': self.case_id, 'kind': kind, **data}, ensure_ascii=False) + '\n')

    def port(self):
        while True:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            if port not in self.ports:
                self.ports.add(port)
                return port

    async def launch(self, role, agent_id=''):
        port = self.port()
        base = f'http://127.0.0.1:{port}'
        args = [sys.executable, str(ROOT / 'services.py'), '--role', role, '--port', str(port),
                '--agent-id', agent_id, '--data-dir', str(self.output)]
        if hasattr(self, 'database'):
            args += ['--database', self.database]
        if hasattr(self, 'target'):
            args += ['--target', self.target]
        handle = (self.output / f'{role}-{port}.log').open('w', encoding='utf-8')
        self.handles.append(handle)
        process = subprocess.Popen(args, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.processes.append(process)
        async with httpx.AsyncClient(trust_env=False, timeout=0.5) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'{role} exited; see {handle.name}')
                try:
                    response = await client.get(base + '/health')
                    response.raise_for_status()
                    self.event('process_started', role=role, pid=process.pid, endpoint=base)
                    return base, process
                except httpx.TransportError:
                    await asyncio.sleep(0.1)
        raise RuntimeError(f'{role} did not become ready')

    async def http(self, method, url, **kwargs):
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    async def register(self, role, agent_id):
        endpoint, process = await self.launch(role + '-agent', agent_id)
        record = {'id': agent_id, 'capabilities': [role], 'endpoint': endpoint + '/rpc'}
        await self.http('POST', self.directory + '/register', json=record)
        self.event('local_registration', **record)
        return record, process

    async def setup(self):
        self.directory, _ = await self.launch('directory')
        self.database, _ = await self.launch('database')
        self.target, _ = await self.launch('target')
        for role in ['application', 'database', 'verification']:
            record, process = await self.register(role, 'LOCAL.' + role.upper())
            self.records[role] = record
            if role == 'database':
                self.primary_db = process

    async def rpc(self, record, payload):
        client = AipRpcClient(partner_url=record['endpoint'], leader_id='LOCAL.LEADER',
                              identity_binding_enabled=False)
        # Bypass ambient proxy only inside this local client's transport.
        await client.http_client.aclose()
        client.http_client = httpx.AsyncClient(trust_env=False)

        async def capture_request(request):
            self.event('aip_request', endpoint=str(request.url), body=json.loads(request.content))

        async def capture_response(response):
            await response.aread()
            self.event('aip_response', endpoint=str(response.url), body=response.json())

        client.http_client.event_hooks = {'request': [capture_request], 'response': [capture_response]}
        session = self.case_id
        task_id = 'task-' + uuid.uuid4().hex
        self.calls += 1
        try:
            task = await asyncio.wait_for(client.start_task(
                session_id=session, task_id=task_id, user_input=json.dumps(payload)), timeout=3)
            if task.senderId != record['id']:
                raise RuntimeError('Unexpected declared sender (not a TLS identity check)')
            if task.status.state != TaskState.AwaitingCompletion:
                raise RuntimeError(f'Partner state {task.status.state}: {task.status.dataItems}')
            output = next(item.data for product in task.products for item in product.dataItems
                          if isinstance(item, StructuredDataItem))
            finished = await asyncio.wait_for(client.complete_task(
                session_id=session, task_id=task_id), timeout=3)
            if finished.status.state != TaskState.Completed:
                raise RuntimeError('AIP task did not complete')
            return output
        finally:
            await client.close()

    async def call(self, mode, role, payload):
        if mode == 'fixed':
            return await self.rpc(self.records[role], payload)
        directory = await self.http('GET', self.directory + '/discover', params={'capability': role})
        self.event('local_discovery', capability=role, candidates=directory['agents'])
        for record in directory['agents']:
            try:
                return await self.rpc(record, payload)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Retry only failures before an action could be accepted.
                # A read timeout after a mutation is ambiguous and is NOT blindly retried.
                self.fallbacks += 1
                self.event('unreachable_partner', agent=record['id'], error=type(exc).__name__)
        raise RuntimeError('No reachable ' + role + ' agent')

    async def solve(self, mode):
        for _ in range(4):
            app = await self.call(mode, 'application', {'action': 'inspect'})
            if app['http_status'] == 200:
                verification = await self.call(mode, 'verification', {'action': 'verify'})
                return 'recovered' if verification['passed'] else 'verification_failed'
            error = app['response'].get('error')
            if error not in {'database_connection_failed', 'database_unavailable'}:
                self.event('human_review_required', evidence=app)
                return 'needs_human'
            database = await self.call(mode, 'database', {'action': 'inspect'})
            if app['config']['database_url'] != database['endpoint']:
                self.event('repair_decision', action='repair_endpoint', evidence=[app, database])
                await self.call(mode, 'application', {'action': 'repair_endpoint',
                    'database_url': database['endpoint'], 'expected_revision': app['config']['revision']})
            elif not database['available']:
                self.event('repair_decision', action='resume', evidence=[app, database])
                await self.call(mode, 'database', {'action': 'resume',
                                                  'expected_revision': database['revision']})
            else:
                return 'needs_human'
        return 'retry_budget_exhausted'

    def data_hash(self):
        with sqlite3.connect(self.output / 'orders.sqlite') as conn:
            rows = conn.execute('SELECT id, item FROM orders ORDER BY id').fetchall()
        return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

    async def run_case(self, mode, scenario, repeat):
        self.case_id = f'{scenario}-{mode}-{repeat}'
        self.calls = self.fallbacks = 0
        await self.http('POST', self.database + '/admin/reset', json={
            'available': scenario not in {'database_paused', 'combined'}})
        # This test owns the reserved socket; no unrelated local service is contacted.
        wrong_url = f'http://127.0.0.1:{self.closed_port}'
        await self.http('POST', self.target + '/admin/reset', json={
            'database_url': wrong_url if scenario in {'stale_endpoint', 'combined', 'agent_offline'} else self.database,
            'unsupported_fault': scenario == 'unknown_fault'})
        before_hash = self.data_hash()
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            before = await client.get(self.target + '/orders')
        self.event('fault_injected', scenario=scenario, before_status=before.status_code,
                   before_body=before.json())
        started = time.perf_counter()
        error = None
        try:
            outcome = await self.solve(mode)
        except Exception as exc:
            outcome, error = 'blocked', f'{type(exc).__name__}: {exc}'
            self.event('leader_blocked', error=error)
        duration = round(time.perf_counter() - started, 3)
        app_config = await self.http('GET', self.target + '/admin/config')
        db_status = await self.http('GET', self.database + '/admin/status')
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            after = await client.get(self.target + '/orders')
        mutations = app_config['mutations'] + db_status['mutations']
        expected = ('needs_human' if scenario == 'unknown_fault' else
                    'blocked' if scenario == 'agent_offline' and mode == 'fixed' else 'recovered')
        expected_mutations = {'healthy': 0, 'stale_endpoint': 1, 'database_paused': 1,
                              'combined': 2, 'unknown_fault': 0, 'agent_offline': 1}[scenario]
        if expected == 'blocked':
            expected_mutations = 0
        passed = (outcome == expected and before_hash == self.data_hash() and
                  mutations == expected_mutations and
                  (after.status_code == 200 if expected == 'recovered' else after.status_code != 200))
        result = {'case': self.case_id, 'scenario': scenario, 'mode': mode, 'outcome': outcome,
                  'before_status': before.status_code, 'after_status': after.status_code,
                  'seconds': duration, 'aip_tasks': self.calls, 'unreachable_attempts': self.fallbacks,
                  'mutations': mutations, 'data_unchanged': before_hash == self.data_hash(),
                  'expected': expected, 'passed': passed, 'error': error}
        self.event('case_result', **result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result

    async def guard_checks(self):
        self.case_id = 'guard-checks'
        config = await self.http('GET', self.target + '/admin/config')
        before_hash = self.data_hash()
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(self.target + '/admin/config', json={
                'database_url': self.database, 'expected_revision': config['revision'] - 1})
        after = await self.http('GET', self.target + '/admin/config')
        checks = {'stale_evidence_rejected': response.status_code == 409 and config == after,
                  'data_unchanged': before_hash == self.data_hash()}
        self.event('guard_results', **checks)
        return checks

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for handle in self.handles:
            handle.close()


async def main():
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = ROOT / 'artifacts' / stamp
    output.mkdir(parents=True)
    lab = Lab(output)
    results = []
    # Bound but not listening: guaranteed to be our own refused endpoint.
    reserved = socket.socket()
    reserved.bind(('127.0.0.1', 0))
    lab.closed_port = reserved.getsockname()[1]
    lab.ports.add(lab.closed_port)
    try:
        await lab.setup()
        for scenario in ['healthy', 'stale_endpoint', 'database_paused', 'combined', 'unknown_fault']:
            for repeat in [1, 2]:
                for mode in ['fixed', 'discovery']:
                    results.append(await lab.run_case(mode, scenario, repeat))
        lab.primary_db.terminate()
        lab.primary_db.wait(timeout=5)
        lab.event('partner_stopped', agent='LOCAL.DATABASE', pid=lab.primary_db.pid)
        # New address and ID, created AFTER the Leader's initial configuration.
        await lab.register('database', 'LOCAL.DATABASE.REPLACEMENT')
        for repeat in [1, 2]:
            for mode in ['fixed', 'discovery']:
                results.append(await lab.run_case(mode, 'agent_offline', repeat))
        guards = await lab.guard_checks()
    finally:
        reserved.close()
        lab.close()
    summary = {'sdk_version': '2.2.0', 'sdk_commit': SDK_COMMIT,
               'created_at': datetime.now(timezone.utc).isoformat(),
               'scope': 'Local real-process AIP RPC pilot; deterministic policy; no LLM or Wutong connection',
               'identity': 'Local test IDs only; HTTP loopback; mTLS binding disabled',
               'discovery': 'Custom in-memory capability directory, NOT official ADP or Wutong',
               'results': results, 'guards': guards,
               'processes_stopped': all(p.poll() is not None for p in lab.processes),
               'passed': all(r['passed'] for r in results) and all(guards.values())}
    save_json(output / 'results.json', summary)
    report = ['# 跨系统故障协作最小实验', '',
              f'运行时间：{summary["created_at"]}', '',
              f'官方 ACPs SDK v2.2.0，提交 `{SDK_COMMIT}`。', '',
              '**实验边界：本机独立进程、真实 HTTP 与 SQLite 查询；诊断为确定性规则。未接入大模型、梧桐、正式身份或证书；发现服务是本地简化实现。**', '',
              '## 实验结果', '',
              '| 场景 | 模式 | 结果 | HTTP 前→后 | 修改次数 | 秒 | 符合预期 |',
              '|---|---|---|---|---:|---:|---|']
    for row in results:
        report.append(f'| {row["scenario"]} | {row["mode"]} | {row["outcome"]} | '
                      f'{row["before_status"]}→{row["after_status"]} | {row["mutations"]} | '
                      f'{row["seconds"]} | {row["passed"]} |')
    report += ['', '## 结论与限制', '',
               '- fixed 与 discovery 使用完全相同的诊断与修复逻辑，只改变服务寻址和连接失败后的替代发现。',
               '- 普通故障两种模式都应修复；动态发现的收益仅由“原数据库智能体退出、新智能体加入”的受控场景检验。',
               '- 未知业务故障应停止并请求人工判断；服务健康时不修改配置；过期配置版本应被拒绝。',
               '- 原始 AIP 请求/响应、状态历史、发现结果及实际动作保存在 events.jsonl。',
               '- 这不能证明 AI 推理优势、行业创新性、真实生产效果或比赛平台接入成功。',
               '- 数据库暂停为测试端点模拟的不可用状态，连接错误是真实网络失败；只测试两类已知根因及其组合。',
               '- 同机进程不等于跨组织安全隔离；测试管理端点无认证，仅限本机临时实验。',
               '- 接下来应验证正式梧桐发现/证书、未见故障诊断，以及动态发现相对健壮传统编排的价值。', '',
               f'保护检查：{guards}', f'所有测试子进程已退出：{summary["processes_stopped"]}', '']
    (output / 'REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    (ROOT / 'LATEST.txt').write_text(str(output), encoding='utf-8')
    print(f'REPORT: {output / "REPORT.md"}', flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
