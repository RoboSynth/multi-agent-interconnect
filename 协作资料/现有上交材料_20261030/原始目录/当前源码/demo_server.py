"""Loopback-only, evidence-driven walkthrough of the incident pilot.

Each Partner and the disposable order application run as a separate process.
Progress comes from completed operations and captured AIP traffic, never timers.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import logging
from pathlib import Path
import socket
import subprocess
from typing import Literal
from urllib.parse import urlsplit
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
import uvicorn

from run_pilot import Lab, ROOT, SDK_COMMIT, save_json


SCENARIOS = Literal['stale_endpoint', 'database_paused', 'combined',
                    'agent_offline', 'unknown_fault']
SCENARIO_NAMES = {
    'stale_endpoint': '数据库连接地址错误',
    'database_paused': '数据库暂停',
    'combined': '连接地址错误与数据库暂停',
    'agent_offline': '数据库智能体退出与替代者加入',
    'unknown_fault': '未知业务故障',
}
STEP_TITLES = ['注入故障', '发现能力', '收集证据', '协调修复', '独立复核', '交付结果']
ROLE_NAMES = {'application': '应用智能体', 'database': '数据库智能体',
              'verification': '验证智能体'}


def now():
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: SCENARIOS


class DemoLab(Lab):
    def __init__(self, output):
        super().__init__(output)
        self.current = None
        self.runs = {}
        self.agent_processes = {}
        self.retired_agents = []
        self.db_generation = 0
        self.closed_socket = socket.socket()
        self.closed_socket.bind(('127.0.0.1', 0))
        self.closed_port = self.closed_socket.getsockname()[1]
        self.ports.add(self.closed_port)
        self.rpc_observations = []

    def advance(self, index, status, detail, agent=None, evidence=None):
        if not self.current or self.current['status'] != 'running':
            return
        step = self.current['steps'][index]
        step.update(status=status, detail=detail)
        if agent:
            step['agent'] = agent
        if evidence is not None:
            step['evidence'] = evidence
        step['updated_at'] = now()

    def event(self, kind, **data):
        super().event(kind, **data)
        if not self.current or self.current['status'] != 'running':
            return
        if kind == 'fault_injected':
            self.advance(0, 'completed', f"故障已实际注入，订单接口返回 HTTP {data['before_status']}。",
                         'LOCAL.LEADER', data)
            self.advance(1, 'running', '协调者正在向本地目录查询应用检查能力。', 'LOCAL.LEADER')
        elif kind == 'local_discovery':
            record = {'capability': data['capability'], 'candidates': data['candidates']}
            self.current['discoveries'].append(record)
            self.advance(1, 'completed', f"已按能力查询目录；累计 {len(self.current['discoveries'])} 次真实发现。",
                         'LOCAL.LEADER', self.current['discoveries'])
            if self.current['steps'][2]['status'] == 'pending':
                self.advance(2, 'running', '等待独立 Partner 通过 AIP 返回检查证据。')
        elif kind == 'unreachable_partner':
            self.current['unreachable'].append(data)
            self.advance(1, 'completed',
                         f"发现候选者后实际连接；{data['agent']} 已失联，继续寻找可用替代者。",
                         'LOCAL.LEADER', self.current['discoveries'])
        elif kind == 'repair_decision':
            self.advance(2, 'completed', '已对照应用配置与数据库状态，取得修复所需证据。',
                         'LOCAL.LEADER', data['evidence'])
            self.current['repair_decisions'].append(data)
            action = '更新应用的数据库地址' if data['action'] == 'repair_endpoint' else '恢复暂停的数据库'
            self.advance(3, 'running', f'根据证据决定：{action}。执行时检查配置版本。',
                         'LOCAL.LEADER', self.current['repair_decisions'])
        elif kind == 'human_review_required':
            self.advance(2, 'completed', '应用智能体确认故障不在当前可自动修复范围内。',
                         'LOCAL.APPLICATION', data['evidence'])
            self.advance(3, 'skipped', '停止自动修复，转人工；未执行任何修复写入。', 'LOCAL.LEADER', data)
        elif kind == 'partner_output':
            self.current['observations'].append(data)
            if data['action'] == 'verify':
                self.advance(4, 'completed',
                             '验证智能体已实际请求订单接口三次。' +
                             ('业务检查通过。' if data['output']['passed'] else '业务仍异常，已保留检查结果。'),
                             data['agent'], data['output'])
            elif data['action'] in {'inspect'}:
                self.advance(2, self.current['steps'][2]['status'],
                             f"已收到 {data['agent']} 的检查结果。", data['agent'],
                             [x for x in self.current['observations'] if x['action'] == 'inspect'])
            else:
                self.advance(3, 'running', f"{data['agent']} 已实际执行 {data['action']}，等待独立复核。",
                             data['agent'], self.current['repair_decisions'])

    async def register(self, role, agent_id):
        record, process = await super().register(role, agent_id)
        self.agent_processes[agent_id] = process
        return record, process

    async def rpc(self, record, payload):
        if self.current and payload['action'] == 'verify':
            if self.current['steps'][3]['status'] != 'skipped':
                self.advance(3, 'completed', '协调修复结束，交给独立验证智能体复查。', 'LOCAL.LEADER')
            self.advance(4, 'running', '验证智能体通过 AIP 接收任务，并实际访问订单接口。', record['id'])
        output = await super().rpc(record, payload)
        self.event('partner_output', agent=record['id'], action=payload['action'],
                   endpoint=record['endpoint'], output=output)
        return output

    def agents(self):
        agents = [{'id': 'LOCAL.LEADER', 'name': '协调智能体', 'role': 'leader',
                   'status': 'online', 'endpoint': '本机协调器（规则决策）'}]
        for role, record in self.records.items():
            process = self.agent_processes.get(record['id'])
            agents.append({'id': record['id'], 'name': ROLE_NAMES[role], 'role': role,
                           'status': 'online' if process and process.poll() is None else 'offline',
                           'endpoint': record['endpoint']})
        for record in self.retired_agents:
            agents.append({'id': record['id'], 'name': '已退出的数据库智能体', 'role': 'database',
                           'status': 'offline', 'endpoint': record['endpoint']})
        return agents

    async def replace_database_partner(self):
        old = deepcopy(self.records['database'])
        process = self.agent_processes[old['id']]
        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)
        if process.poll() is None:
            raise RuntimeError('Database Partner did not exit')
        self.retired_agents.append(old)
        self.event('partner_stopped', agent=old['id'], pid=process.pid, exit_code=process.returncode,
                   endpoint=old['endpoint'])
        self.db_generation += 1
        replacement, replacement_process = await self.register(
            'database', f'LOCAL.DATABASE.REPLACEMENT.{self.db_generation}')
        self.records['database'] = replacement
        self.primary_db = replacement_process
        self.event('partner_replaced', previous=old, replacement=replacement)

    async def execute_run(self, run):
        self.case_id = run['id']
        self.calls = self.fallbacks = 0
        scenario = run['scenario']
        self.advance(0, 'running', '仅操作本次启动的一次性订单应用与数据库。', 'LOCAL.LEADER')
        try:
            await self.http('POST', self.database + '/admin/reset', json={
                'available': scenario not in {'database_paused', 'combined'}})
            await self.http('POST', self.target + '/admin/reset', json={
                'database_url': f'http://127.0.0.1:{self.closed_port}'
                if scenario in {'stale_endpoint', 'combined', 'agent_offline'} else self.database,
                'unsupported_fault': scenario == 'unknown_fault'})
            if scenario == 'agent_offline':
                await self.replace_database_partner()
            before_hash = self.data_hash()
            async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
                before = await client.get(self.target + '/orders')
            self.event('fault_injected', scenario=scenario, before_status=before.status_code,
                       before_body=before.json())
            outcome = await self.solve('discovery')
            if outcome == 'needs_human':
                # Independently confirm the unresolved business fault and preserve raw samples.
                await self.call('discovery', 'verification', {'action': 'verify'})
            self.advance(5, 'running', '汇总真实接口状态、修复次数与订单数据哈希。', 'LOCAL.LEADER')
            app_config = await self.http('GET', self.target + '/admin/config')
            db_status = await self.http('GET', self.database + '/admin/status')
            async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
                after = await client.get(self.target + '/orders')
            after_hash = self.data_hash()
            mutations = app_config['mutations'] + db_status['mutations']
            expected_outcome = 'needs_human' if scenario == 'unknown_fault' else 'recovered'
            expected_mutations = {'stale_endpoint': 1, 'database_paused': 1, 'combined': 2,
                                  'agent_offline': 1, 'unknown_fault': 0}[scenario]
            passed = (outcome == expected_outcome and mutations == expected_mutations and
                      before_hash == after_hash and
                      (after.status_code == 200 if outcome == 'recovered' else after.status_code != 200))
            result = {'outcome': outcome, 'before_status': before.status_code,
                      'after_status': after.status_code, 'mutations': mutations,
                      'data_unchanged': before_hash == after_hash,
                      'before_hash': before_hash, 'after_hash': after_hash,
                      'aip_tasks': self.calls, 'unreachable_attempts': self.fallbacks,
                      'passed': passed, 'expected': expected_outcome}
            run['result'] = result
            self.event('case_result', **result)
            self.advance(5, 'completed' if passed else 'failed',
                         '已生成本轮证据；订单数据保持一致。' if passed else '本轮结果不符合预期，请查看证据。',
                         'LOCAL.LEADER', result)
            run['status'] = 'completed' if passed else 'failed'
            if not passed:
                run['error'] = '结果不符合场景预期，已保留原始证据。'
        except asyncio.CancelledError:
            run['status'], run['error'] = 'canceled', '演示服务关闭，任务被取消。'
            for step in run['steps']:
                if step['status'] == 'running':
                    step['status'] = 'failed'
                    step['detail'] = run['error']
            raise
        except Exception as exc:
            self.event('leader_blocked', error=f'{type(exc).__name__}: {exc}')
            for step in run['steps']:
                if step['status'] == 'running':
                    step['status'] = 'failed'
                    step['detail'] = '本步骤未完成，已保留原始错误。'
            run['status'], run['error'] = 'failed', f'{type(exc).__name__}: {exc}'
        finally:
            run['finished_at'] = now()
            save_json(self.output / (run['id'] + '.json'), run)


def platform_state():
    default = {'registered': False, 'aic': None, 'certificate': False,
               'discovery': 'local', 'connection': False,
               'note': '当前为本地官方 AIP 互联；梧桐注册、正式 AIC、证书和平台发现尚未验证。'}
    status_path = ROOT / 'integration' / 'platform-status.json'
    if not status_path.exists():
        return default
    try:
        raw = json.loads(status_path.read_text(encoding='utf-8-sig'))
        source = raw.get('platform', raw)
        evidence = raw.get('evidence', source.get('evidence', {}))

        def has_evidence(kind):
            references = evidence.get(kind, [])
            if isinstance(references, str):
                references = [references]
            if not isinstance(references, list) or not references:
                return False
            integration_root = status_path.parent.resolve()
            for reference in references:
                if not isinstance(reference, str):
                    return False
                resolved = (integration_root / reference).resolve()
                if not resolved.is_relative_to(integration_root) or not resolved.is_file():
                    return False
            return True

        registered = source.get('registered') is True and has_evidence('registration')
        certificate = source.get('certificate') is True and has_evidence('certificate')
        connection = (registered and certificate and source.get('connection') is True
                      and has_evidence('connection'))
        return {**default, 'registered': registered,
                'aic': source.get('aic') if registered and isinstance(source.get('aic'), str) else None,
                'certificate': certificate,
                'discovery': source.get('discovery', 'local') if connection else 'local',
                'connection': connection,
                'note': source.get('note', default['note'])}
    except (ValueError, TypeError, AttributeError, OSError):
        return {**default, 'note': '平台状态文件无法读取；正式接入状态保持未验证。'}


def create_app(output=None):
    if output is None:
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
        output = ROOT / 'artifacts' / f'demo-{stamp}-{uuid.uuid4().hex[:6]}'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    @asynccontextmanager
    async def lifespan(app):
        lab = DemoLab(output)
        app.state.lab = lab
        app.state.run_task = None
        try:
            await lab.setup()
            lab.event('demo_ready', sdk_commit=SDK_COMMIT, directory=lab.directory,
                      target=lab.target, database=lab.database)
            save_json(output / 'startup.json', {'started_at': now(), 'sdk_commit': SDK_COMMIT,
                      'agents': lab.agents(), 'target': lab.target, 'database': lab.database,
                      'directory': lab.directory, 'platform': platform_state()})
            yield
        finally:
            task = app.state.run_task
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await asyncio.to_thread(lab.close)
            lab.closed_socket.close()
            save_json(output / 'shutdown.json', {'finished_at': now(),
                      'all_children_stopped': all(p.poll() is not None for p in lab.processes),
                      'processes': [{'pid': p.pid, 'returncode': p.returncode} for p in lab.processes]})

    app = FastAPI(title='多智能体协同恢复 · 最小流程演示', lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.output = output

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        try:
            local_client = request.client and ipaddress.ip_address(request.client.host).is_loopback
            host = urlsplit('http://' + request.headers.get('host', '')).hostname
            local_host = host in {'127.0.0.1', 'localhost', '::1'}
            origin = request.headers.get('origin')
            local_origin = not origin or urlsplit(origin).hostname in {'127.0.0.1', 'localhost', '::1'}
        except ValueError:
            local_client = local_host = local_origin = False
        if not (local_client and local_host and local_origin):
            return JSONResponse({'detail': '仅允许本机访问此一次性实验。'}, status_code=403)
        if request.method == 'POST' and request.url.path.startswith('/api/'):
            if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
                return JSONResponse({'detail': '请使用 application/json。'}, status_code=415)
            try:
                content_length = int(request.headers.get('content-length', 0) or 0)
            except ValueError:
                return JSONResponse({'detail': '无效的 Content-Length。'}, status_code=400)
            if content_length > 4096 or len(await request.body()) > 4096:
                return JSONResponse({'detail': '请求过大。'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:"
        return response

    @app.get('/api/state')
    async def state():
        lab = app.state.lab
        return {'platform': platform_state(), 'agents': lab.agents(), 'run': lab.current,
                'runtime': {'mode': 'local', 'discovery': 'local-directory', 'model': 'rule-based',
                            'sdk_commit': SDK_COMMIT, 'artifacts': str(output), 'target': lab.target}}

    @app.post('/api/runs', status_code=202)
    async def start_run(body: RunRequest):
        lab = app.state.lab
        if app.state.run_task and not app.state.run_task.done():
            raise HTTPException(409, '已有演示任务正在运行，请等待当前任务结束。')
        run_id = 'run-' + uuid.uuid4().hex[:12]
        run = {'id': run_id, 'status': 'running', 'scenario': body.scenario,
               'scenario_name': SCENARIO_NAMES[body.scenario], 'started_at': now(),
               'steps': [{'id': f'step-{index + 1}', 'title': title, 'status': 'pending',
                          'detail': '等待执行', 'agent': None} for index, title in enumerate(STEP_TITLES)],
               'result': None, 'error': None, 'discoveries': [], 'unreachable': [],
               'repair_decisions': [], 'observations': []}
        lab.current = run
        lab.runs[run_id] = run
        app.state.run_task = asyncio.create_task(lab.execute_run(run))
        return {'id': run_id, 'status': 'running'}

    @app.get('/api/runs/{run_id}')
    async def get_run(run_id: str):
        run = app.state.lab.runs.get(run_id)
        if run is None:
            raise HTTPException(404, '未找到本次服务中的演示记录。')
        return run

    app.mount('/', StaticFiles(directory=str(ROOT / 'demo-ui'), html=True, check_dir=False), name='demo-ui')
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    application = create_app()
    file_handler = logging.FileHandler(application.state.output / 'server.log', encoding='utf-8')
    logging.getLogger().addHandler(file_handler)
    print(f'Demo evidence: {application.state.output}', flush=True)
    uvicorn.run(application, host='127.0.0.1', port=options.port, log_level='info')
