"""Broad local real-process resilience tests; never touches LATEST.txt.

Reuses the original Leader and service contracts unchanged. Expected safe blocking
is reported separately from recovery. No LLM, cloud, certificate, or Wutong claim.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
import uuid

import httpx

from run_pilot import Lab, ROOT, SDK_COMMIT, save_json

CHINA = timezone(timedelta(hours=8))


class ResilienceSuite:
    def __init__(self, output, seed):
        self.output = output
        self.lab = Lab(output)
        self.results = []
        self.rng = random.Random(seed)
        self.reserved = socket.socket()
        self.reserved.bind(('127.0.0.1', 0))
        self.lab.closed_port = self.reserved.getsockname()[1]
        self.lab.ports.add(self.lab.closed_port)
        self.serial = 0

    def stop(self, process, reason):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.lab.event('owned_process_stopped', pid=process.pid, reason=reason,
                       exit_code=process.poll())

    async def restart_at(self, role, endpoint):
        """Explicit operator restart on the original owned port, preserving data."""
        port = int(endpoint.rsplit(':', 1)[1])
        args = [sys.executable, str(ROOT / 'services.py'), '--role', role,
                '--port', str(port), '--database', self.lab.database,
                '--target', self.lab.target, '--data-dir', str(self.output)]
        handle = (self.output / f'{role}-{port}-restart-{uuid.uuid4().hex[:6]}.log').open(
            'w', encoding='utf-8')
        self.lab.handles.append(handle)
        process = subprocess.Popen(args, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.lab.processes.append(process)
        async with httpx.AsyncClient(trust_env=False, timeout=0.5) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'Restart exited: {handle.name}')
                try:
                    response = await client.get(endpoint + '/health')
                    response.raise_for_status()
                    self.lab.event('process_started', role=role, pid=process.pid,
                                   endpoint=endpoint, explicit_operator_restart=True)
                    return process
                except httpx.TransportError:
                    await asyncio.sleep(0.1)
        raise RuntimeError(f'Restart unavailable: {role}')

    async def reset(self, scenario='healthy'):
        await self.lab.http('POST', self.lab.database + '/admin/reset', json={
            'available': scenario not in {'database_paused', 'combined'}})
        await self.lab.http('POST', self.lab.target + '/admin/reset', json={
            'database_url': f'http://127.0.0.1:{self.lab.closed_port}'
                if scenario in {'stale_endpoint', 'combined'} else self.lab.database,
            'unsupported_fault': scenario == 'unknown_fault'})

    async def observe(self):
        observed = {}
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            for key, url in [('target', self.lab.target + '/orders'),
                             ('config', self.lab.target + '/admin/config'),
                             ('database', self.lab.database + '/admin/status')]:
                try:
                    response = await client.get(url)
                    observed[key] = {'status': response.status_code, 'body': response.json()}
                except Exception as exc:
                    observed[key] = {'status': 'unreachable',
                                     'error': type(exc).__name__ + ': ' + str(exc)}
        return observed

    async def case(self, name, mode, expected_outcome, expected_status,
                   expected_mutations, *, min_fallbacks=0, expected_order=None):
        self.serial += 1
        self.lab.case_id = f'r{self.serial:03d}-{name}-{mode}'
        self.lab.calls = self.lab.fallbacks = 0
        before_hash = self.lab.data_hash()
        before = await self.observe()
        self.lab.event('stress_case_started', name=name, mode=mode, before=before)
        started = time.perf_counter()
        error = None
        try:
            outcome = await self.lab.solve(mode)
        except Exception as exc:
            outcome = 'blocked'
            error = type(exc).__name__ + ': ' + str(exc)
            self.lab.event('leader_blocked', error=error)
        seconds = round(time.perf_counter() - started, 4)
        after = await self.observe()
        after_hash = self.lab.data_hash()
        available = [after[k]['body'] for k in ['config', 'database'] if 'body' in after[k]]
        known_mutations = sum(body.get('mutations', 0) for body in available)
        full_mutation_observation = len(available) == 2
        mutations = known_mutations if full_mutation_observation else None
        data_ok = before_hash == after_hash
        if expected_order is not None:
            data_ok = data_ok and after['target'].get('body', {}).get('orders') == expected_order
        expected = {'outcome': expected_outcome, 'target_status': expected_status,
                    'mutations': expected_mutations, 'data_unchanged': True,
                    'min_connection_fallbacks': min_fallbacks}
        checks = {'outcome': outcome == expected_outcome,
                  'target_status': after['target']['status'] == expected_status,
                  'mutations': mutations == expected_mutations,
                  'known_mutations_zero_when_partially_observed':
                      full_mutation_observation or known_mutations == 0,
                  'data_integrity': data_ok,
                  'fallbacks': self.lab.fallbacks >= min_fallbacks}
        row = {'case': self.lab.case_id, 'name': name, 'mode': mode,
               'expected': expected, 'outcome': outcome, 'error': error,
               'seconds': seconds, 'aip_tasks': self.lab.calls,
               'connection_fallbacks': self.lab.fallbacks, 'before': before, 'after': after,
               'mutations': mutations, 'known_mutations': known_mutations,
               'data_hash_before': before_hash, 'data_hash_after': after_hash,
               'checks': checks, 'passed': all(checks.values())}
        self.results.append(row)
        self.lab.event('stress_case_result', **row)
        with (self.output / 'cases.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(json.dumps({'case': row['case'], 'passed': row['passed'], 'outcome': outcome,
                          'seconds': seconds, 'failed_checks': [k for k, v in checks.items() if not v]},
                         ensure_ascii=False), flush=True)
        return row

    async def ordinary(self, repeats):
        scenarios = ['healthy', 'stale_endpoint', 'database_paused', 'combined', 'unknown_fault']
        jobs = [(scenario, repeat) for repeat in range(repeats) for scenario in scenarios]
        self.rng.shuffle(jobs)
        for scenario, repeat in jobs:
            modes = ['fixed', 'discovery']
            self.rng.shuffle(modes)
            for mode in modes:
                await self.reset(scenario)
                await self.case(f'paired-{scenario}-{repeat:02d}', mode,
                    'needs_human' if scenario == 'unknown_fault' else 'recovered',
                    500 if scenario == 'unknown_fault' else 200,
                    {'healthy': 0, 'stale_endpoint': 1, 'database_paused': 1,
                     'combined': 2, 'unknown_fault': 0}[scenario],
                    expected_order=None if scenario == 'unknown_fault' else
                        [[1, 'book'], [2, 'keyboard'], [3, 'monitor']])

    async def set_record(self, record, **changes):
        updated = {**record, **changes}
        await self.lab.http('POST', self.lab.directory + '/register', json=updated)
        self.lab.event('directory_test_record', **updated)

    async def directory_cases(self):
        for repeat in range(2):
            # No deletion endpoint exists: overwrite capabilities to make discovery empty.
            for record in self.lab.records.values():
                await self.set_record(record, capabilities=[])
            await self.reset('stale_endpoint')
            await self.case(f'empty-directory-{repeat}', 'discovery', 'blocked', 503, 0)
            for role, record in self.lab.records.items():
                await self.set_record(record, capabilities=['unrelated-capability'])
            await self.reset('stale_endpoint')
            await self.case(f'wrong-capability-{repeat}', 'discovery', 'blocked', 503, 0)
            for record in self.lab.records.values():
                await self.set_record(record)

        original = self.lab.records['database']
        await self.set_record(original, endpoint=f'http://127.0.0.1:{self.lab.closed_port}/rpc')
        await self.reset('database_paused')
        await self.case('first-candidate-dead-no-alternative', 'discovery', 'blocked', 503, 0,
                        min_fallbacks=1)
        replacement, replacement_process = await self.lab.register('database', 'LOCAL.STRESS.DB.ALTERNATIVE')
        for repeat in range(2):
            await self.reset('database_paused')
            await self.case(f'first-candidate-dead-live-alternative-{repeat}', 'discovery',
                            'recovered', 200, 1, min_fallbacks=2,
                            expected_order=[[1, 'book'], [2, 'keyboard'], [3, 'monitor']])
        await self.set_record(original)
        # A registry identity mismatch is refused, not silently treated as connection loss.
        await self.set_record(original, endpoint=replacement['endpoint'])
        await self.reset('database_paused')
        await self.case('directory-identity-mismatch', 'discovery', 'blocked', 503, 0)
        await self.set_record(original)
        await self.set_record(replacement, capabilities=[])
        self.stop(replacement_process, 'directory tests complete')

    async def partner_process_cases(self):
        # These are the live original processes created by Lab.setup.
        originals = {'application': self.lab.processes[3], 'database': self.lab.processes[4],
                     'verification': self.lab.processes[5]}
        replacements = {}
        for role in ['application', 'database', 'verification']:
            original_record = dict(self.lab.records[role])
            self.stop(originals[role], f'physical {role} Partner loss')
            scenario = 'database_paused' if role == 'database' else 'healthy'
            status = 503 if role == 'database' else 200
            for mode in ['fixed', 'discovery']:
                await self.reset(scenario)
                await self.case(f'{role}-partner-exited-no-alternative', mode, 'blocked', status, 0,
                                min_fallbacks=1 if mode == 'discovery' else 0)
            replacement, process = await self.lab.register(role, f'LOCAL.STRESS.{role.upper()}.REPLACEMENT')
            replacements[role] = (replacement, process)
            for mode in ['fixed', 'discovery']:
                await self.reset(scenario)
                await self.case(f'{role}-partner-exited-alternative-joined', mode,
                    'blocked' if mode == 'fixed' else 'recovered',
                    status if mode == 'fixed' else 200,
                    0 if mode == 'fixed' else (1 if role == 'database' else 0),
                    min_fallbacks=1 if mode == 'discovery' else 0)
            # Keep fixed-mode original address stale for the paired comparison above,
            # then restore both modes' useful services before testing the next role.
            self.lab.records[role] = replacement
            await self.set_record(original_record, capabilities=[])
        return replacements

    async def physical_service_cases(self):
        live = {'target': self.lab.processes[2], 'database': self.lab.processes[1]}
        for role in ['target', 'database']:
            await self.reset('healthy')
            self.stop(live[role], f'physical {role} service process crash')
            for mode in ['fixed', 'discovery']:
                await self.case(f'{role}-service-process-exited', mode, 'blocked',
                                'unreachable' if role == 'target' else 503, None)
            live[role] = await self.restart_at(role, getattr(self.lab, role))
            for mode in ['fixed', 'discovery']:
                await self.case(f'{role}-service-explicitly-restarted', mode,
                                'recovered', 200, 0,
                                expected_order=[[1, 'book'], [2, 'keyboard'], [3, 'monitor']])

    def close(self):
        self.reserved.close()
        self.lab.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeats', type=int, default=12,
                        help='Random paired repetitions per ordinary scenario (10 cases each).')
    parser.add_argument('--seed', type=int, default=20261017)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    stamp = datetime.now(CHINA).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = ROOT / 'artifacts' / ('resilience-' + stamp)
    output.mkdir(parents=True)
    source = output / 'source-snapshot'
    source.mkdir()
    source_hashes = {}
    for filename in ['services.py', 'run_pilot.py', 'resilience_stress.py', 'requirements-lock.txt']:
        path = ROOT / filename
        shutil.copy2(path, source / filename)
        source_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    save_json(output / 'manifest.json', {
        'started_at_utc8': datetime.now(CHINA).isoformat(), 'seed': args.seed,
        'repeats': args.repeats, 'python': sys.version, 'source_sha256': source_hashes,
        'sdk_commit': SDK_COMMIT, 'scope': 'Local owned real processes and original Lab.solve only',
        'not_tested': ['LLM diagnosis', 'Wutong', 'official ADP', 'mTLS', 'production systems']})
    print('OUTPUT: ' + str(output), flush=True)
    suite = ResilienceSuite(output, args.seed)
    fatal = None
    try:
        await suite.lab.setup()
        await suite.ordinary(args.repeats)
        await suite.directory_cases()
        await suite.partner_process_cases()
        await suite.physical_service_cases()
    except BaseException as exc:
        fatal = type(exc).__name__ + ': ' + str(exc)
        suite.lab.event('suite_aborted', error=fatal)
        raise
    finally:
        suite.close()
        source_unchanged = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                               for name, digest in source_hashes.items())
        ports_open = []
        port_probes = []
        for port in suite.lab.ports - {suite.lab.closed_port}:
            while True:
                # Explicit distinct source port avoids rare TCP self-connections
                # when a recently released listener port is reused ephemerally.
                probe = socket.socket()
                probe.bind(('127.0.0.1', 0))
                if probe.getsockname()[1] != port:
                    break
                probe.close()
            try:
                probe.settimeout(0.1)
                source_port = probe.getsockname()[1]
                code = probe.connect_ex(('127.0.0.1', port))
                port_probes.append({'port': port, 'source_port': source_port,
                                    'connect_ex': code})
                if code == 0:
                    ports_open.append(port)
            finally:
                probe.close()
        counts = Counter(row['outcome'] for row in suite.results)
        summary = {'finished_at_utc8': datetime.now(CHINA).isoformat(),
                   'total_cases': len(suite.results), 'passed_cases': sum(r['passed'] for r in suite.results),
                   'failed_cases': [r['case'] for r in suite.results if not r['passed']],
                   'actual_outcome_counts': dict(counts),
                   'recovered_cases': counts['recovered'], 'blocked_cases': counts['blocked'],
                   'confirmed_repair_cases': sum((r['mutations'] or 0) > 0 for r in suite.results),
                   'successful_zero_mutation_cases': sum(r['outcome'] == 'recovered'
                       and r['mutations'] == 0 for r in suite.results),
                   'human_review_cases': counts['needs_human'],
                   'fatal_error': fatal, 'sources_unchanged': source_unchanged,
                   'processes_stopped': all(p.poll() is not None for p in suite.lab.processes),
                   'owned_process_count': len(suite.lab.processes), 'ports_still_open': ports_open,
                   'cleanup_port_probes': port_probes,
                   'data_hash': suite.lab.data_hash() if (output / 'orders.sqlite').exists() else None,
                   'all_expected': bool(suite.results) and all(r['passed'] for r in suite.results)
                        and not fatal and source_unchanged and not ports_open
                        and all(p.poll() is not None for p in suite.lab.processes)}
        save_json(output / 'summary.json', summary)
        report = ['# 本机跨系统故障协作韧性压力测试', '',
                  '原始 Lab.solve 和 services.py 契约未改变。规则诊断、本地目录、无 LLM/梧桐/证书。', '',
                  f'结束时间（UTC+8）：{summary["finished_at_utc8"]}',
                  f'用例 {summary["total_cases"]}，符合预期 {summary["passed_cases"]}。',
                  f'任务成功完成或确认健康 {counts["recovered"]}；安全阻断 {counts["blocked"]}；转人工 {counts["needs_human"]}。',
                  f'实际执行修复的用例 {summary["confirmed_repair_cases"]}；成功且无修改 {summary["successful_zero_mutation_cases"]}。',
                  '“符合预期”包含应当阻断的故障，不能将其称为全部恢复成功。', '',
                  '| 用例 | 模式 | 期望结果 | 实际结果 | 秒 | 符合预期 |',
                  '|---|---|---|---|---:|---|']
        report += [f'| {r["name"]} | {r["mode"]} | {r["expected"]["outcome"]} | '
                   f'{r["outcome"]} | {r["seconds"]} | {r["passed"]} |' for r in suite.results]
        report += ['', '物理服务退出时系统只会阻断，显式人工重启后的恢复单独记录，不算自动重启能力。',
                   '某个服务不可达时修改次数为不可完整观测，记录 null；仍检查可达服务修改数和SQLite内容。',
                   f'源码未变：{source_unchanged}；子进程均退出：{summary["processes_stopped"]}；开放端口：{ports_open}。',
                   f'中断错误：{fatal}', '']
        (output / 'REPORT.md').write_text('\n'.join(report), encoding='utf-8')
        print('SUMMARY: ' + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary['all_expected'] else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
