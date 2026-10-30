"""Real AIP and HTTP tests of concurrent repairs and exactly-once effects."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import socket
import sys
import time
import uuid

import httpx
from acps_sdk.aip import AipRpcClient
from run_pilot import Lab, ROOT, SDK_COMMIT, save_json


class ConsistencySuite:
    def __init__(self, lab, seed):
        self.lab = lab
        self.rng = random.Random(seed)
        self.rows = []
        self.requests = 0
        original_http = lab.http

        async def observed_http(method, url, **kwargs):
            lab.event('test_http_request', method=method, url=url, arguments=kwargs)
            try:
                result = await original_http(method, url, **kwargs)
                lab.event('test_http_response', method=method, url=url, body=result)
                return result
            except Exception as exc:
                lab.event('test_http_error', method=method, url=url, error=f'{type(exc).__name__}: {exc}')
                raise

        lab.http = observed_http

    async def command(self, role, command, payload=None, task_id=None):
        record = self.lab.records[role]
        client = AipRpcClient(record['endpoint'], leader_id='LOCAL.CONSISTENCY', identity_binding_enabled=False)
        await client.http_client.aclose()
        client.http_client = httpx.AsyncClient(trust_env=False, timeout=6)

        async def request_hook(request):
            self.requests += 1
            self.lab.event('aip_request', endpoint=str(request.url), body=json.loads(request.content))

        async def response_hook(response):
            await response.aread()
            self.lab.event('aip_response', endpoint=str(response.url), body=response.json())

        client.http_client.event_hooks = {'request': [request_hook], 'response': [response_hook]}
        task_id = task_id or uuid.uuid4().hex
        try:
            if command == 'start':
                return await client.start_task(session_id=self.lab.case_id, task_id=task_id,
                                               user_input=json.dumps(payload))
            if command == 'get':
                return await client.get_task(session_id=self.lab.case_id, task_id=task_id)
            return await client.complete_task(session_id=self.lab.case_id, task_id=task_id)
        finally:
            await client.close()

    async def reset(self, available=True):
        await self.lab.http('POST', self.lab.database + '/admin/reset', json={'available': available})
        return await self.lab.http('POST', self.lab.target + '/admin/reset', json={
            'database_url': self.lab.directory, 'unsupported_fault': False})

    async def config(self):
        return await self.lab.http('GET', self.lab.target + '/admin/config')

    async def single(self, kind, index, body):
        self.lab.case_id = f'{kind}-{index}'
        started = time.perf_counter()
        before = self.lab.data_hash()
        try:
            detail = await body()
            preserved = before == self.lab.data_hash()
            passed = all(detail['checks'].values()) and preserved
            error = None
        except Exception as exc:
            passed, preserved = False, before == self.lab.data_hash()
            detail, error = {}, f'{type(exc).__name__}: {exc}'
        row = {'case': self.lab.case_id, 'category': kind, 'passed': passed,
               'data_hash_before': before, 'data_hash_after': self.lab.data_hash(),
               'data_unchanged': preserved, 'seconds': round(time.perf_counter() - started, 4),
               'error': error, **detail}
        self.rows.append(row)
        self.lab.event('consistency_result', **row)

    async def repeat_start(self):
        cfg = await self.reset()
        task_id = uuid.uuid4().hex
        payload = {'action': 'repair_endpoint', 'database_url': self.lab.database,
                   'expected_revision': cfg['revision']}
        one = await self.command('application', 'start', payload, task_id)
        two = await self.command('application', 'start', payload, task_id)
        three = await self.command('application', 'complete', task_id=task_id)
        four = await self.command('application', 'complete', task_id=task_id)
        current = await self.config()
        return {'checks': {'first_waits': one.status.state.value == 'awaiting-completion',
                           'duplicate_preserves_products': one.products == two.products,
                           # Complete may append an audit command; its business result must not change.
                           'terminal_idempotence': (three.status == four.status and
                                                    three.products == four.products and
                                                    three.taskId == four.taskId and
                                                    three.sessionId == four.sessionId),
                           'one_effect': current['mutations'] == 1,
                           'revision_once': current['revision'] == cfg['revision'] + 1}}

    async def same_id_race(self):
        cfg = await self.reset()
        task_id = uuid.uuid4().hex
        payload = {'action': 'repair_endpoint', 'database_url': self.lab.database,
                   'expected_revision': cfg['revision']}
        replies = await asyncio.gather(*[self.command('application', 'start', payload, task_id) for _ in range(6)])
        final = await self.command('application', 'get', task_id=task_id)
        await self.command('application', 'complete', task_id=task_id)
        current = await self.config()
        return {'states': Counter(r.status.state.value for r in replies), 'checks': {
            'valid_nonterminal': all(r.status.state.value in {'accepted', 'working', 'awaiting-completion'} for r in replies),
            'final_waits': final.status.state.value == 'awaiting-completion',
            'one_effect': current['mutations'] == 1,
            'one_revision': current['revision'] == cfg['revision'] + 1}}

    async def competing_repairs(self, role):
        cfg = await self.reset(available=False)
        if role == 'application':
            payload = {'action': 'repair_endpoint', 'database_url': self.lab.database,
                       'expected_revision': cfg['revision']}
        else:
            cfg = await self.lab.http('GET', self.lab.database + '/admin/status')
            payload = {'action': 'resume', 'expected_revision': cfg['revision']}
        ids = [uuid.uuid4().hex for _ in range(6)]
        replies = await asyncio.gather(*[self.command(role, 'start', payload, task_id) for task_id in ids])
        successes = [r for r in replies if r.status.state.value == 'awaiting-completion']
        for task in successes:
            await self.command(role, 'complete', task_id=task.taskId)
        current = await self.config() if role == 'application' else await self.lab.http('GET', self.lab.database + '/admin/status')
        return {'states': Counter(r.status.state.value for r in replies), 'checks': {
            'one_winner': len(successes) == 1,
            'others_fail': sum(r.status.state.value == 'failed' for r in replies) == 5,
            'one_effect': current['mutations'] == 1,
            'one_revision': current['revision'] == cfg['revision'] + 1}}

    async def stale_revision(self):
        cfg = await self.reset()
        delta = self.rng.choice([-10, -2, -1, 1, 2, 10])
        reply = await self.command('application', 'start', {
            'action': 'repair_endpoint', 'database_url': self.lab.database,
            'expected_revision': cfg['revision'] + delta})
        return {'delta': delta, 'checks': {'task_failed': reply.status.state.value == 'failed',
                                         'no_change': cfg == await self.config()}}

    async def forbidden_destination(self):
        cfg = await self.reset()
        destination = self.rng.choice([self.lab.directory, self.lab.target, self.lab.database + '/',
                                       'http://127.0.0.1:1', 'https://example.invalid', 'file:///test'])
        reply = await self.command('application', 'start', {'action': 'repair_endpoint',
            'database_url': destination, 'expected_revision': cfg['revision']})
        return {'destination': destination, 'checks': {'task_failed': reply.status.state.value == 'failed',
                                                      'no_change': cfg == await self.config()}}

    async def no_op(self):
        await self.reset()
        cfg = await self.lab.http('POST', self.lab.target + '/admin/reset', json={'database_url': self.lab.database})
        task = await self.command('application', 'start', {'action': 'repair_endpoint',
            'database_url': self.lab.database, 'expected_revision': cfg['revision']})
        await self.command('application', 'complete', task_id=task.taskId)
        return {'checks': {'no_change': cfg == await self.config()}}

    async def parallel_reads(self):
        await self.reset()
        cfg = await self.lab.http('POST', self.lab.target + '/admin/reset', json={'database_url': self.lab.database})
        tasks = await asyncio.gather(*[self.command('verification', 'start', {'action': 'verify'}) for _ in range(12)])
        valid = []
        for task in tasks:
            valid.append(task.status.state.value == 'awaiting-completion' and task.products[0].dataItems[0].data['passed'])
            await self.command('verification', 'complete', task_id=task.taskId)
        return {'checks': {'all_12_verified': all(valid), 'no_change': cfg == await self.config()}}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='baseline')
    parser.add_argument('--seed', type=int, default=20261017)
    parser.add_argument('--scale', type=int, default=1)
    args = parser.parse_args()
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    output = ROOT / 'artifacts' / f'consistency-{timestamp}-{args.label}-{uuid.uuid4().hex[:6]}'
    output.mkdir(parents=True)
    for name in ['services.py', 'run_pilot.py', 'consistency_stress.py']:
        (output / name).write_bytes((ROOT / name).read_bytes())
    lab = Lab(output)
    suite = ConsistencySuite(lab, args.seed)
    setup_error = None
    started = time.perf_counter()
    try:
        await lab.setup()
        categories = [('repeat_start_complete', 30, suite.repeat_start),
                      ('same_task_id_race', 20, suite.same_id_race),
                      ('competing_application_repairs', 20, lambda: suite.competing_repairs('application')),
                      ('competing_database_repairs', 20, lambda: suite.competing_repairs('database')),
                      ('stale_or_future_revision', 40, suite.stale_revision),
                      ('forbidden_destination', 30, suite.forbidden_destination),
                      ('healthy_no_op', 30, suite.no_op),
                      ('parallel_verification', 5, suite.parallel_reads)]
        for kind, count, body in categories:
            for i in range(count * args.scale):
                await suite.single(kind, i, body)
            rows = [r for r in suite.rows if r['category'] == kind]
            print(json.dumps({'category': kind, 'runs': len(rows), 'passed': sum(r['passed'] for r in rows)}, ensure_ascii=False), flush=True)
    except Exception as exc:
        setup_error = f'{type(exc).__name__}: {exc}'
    finally:
        lab.close()
    port_checks = []
    for line in lab.audit.read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        if event['kind'] == 'process_started':
            with socket.socket() as sock:
                sock.settimeout(.2)
                port_checks.append(sock.connect_ex(('127.0.0.1', int(event['endpoint'].rsplit(':', 1)[1]))) != 0)
    summary = {'suite': 'consistency', 'label': args.label, 'seed': args.seed,
               'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
               'seconds': round(time.perf_counter() - started, 3), 'sdk_commit': SDK_COMMIT,
               'source_hashes': {n: hashlib.sha256((output / n).read_bytes()).hexdigest()
                                 for n in ['services.py', 'run_pilot.py', 'consistency_stress.py']},
               'total': len(suite.rows), 'passed': sum(r['passed'] for r in suite.rows),
               'failed': [r for r in suite.rows if not r['passed']], 'requests': suite.requests,
               'results': suite.rows, 'setup_error': setup_error,
               'processes_stopped': all(p.poll() is not None for p in lab.processes),
               'test_ports_closed': bool(port_checks) and all(port_checks)}
    save_json(output / 'summary.json', summary)
    print(f'SUMMARY: {output / "summary.json"}', flush=True)
    print(json.dumps({k: v for k, v in summary.items() if k not in {'results', 'source_hashes', 'failed'}}), flush=True)
    return 0 if summary['total'] and not summary['failed'] and not setup_error and summary['test_ports_closed'] else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
