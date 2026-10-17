"""Small real-HTTP acceptance test for the demo server; no stress campaign."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import uuid

import httpx
import uvicorn

from demo_server import create_app
from run_pilot import ROOT, save_json


async def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    output = ROOT / 'artifacts' / f'demo-acceptance-{stamp}-{uuid.uuid4().hex[:6]}'
    application = create_app(output)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=port,
                                          log_level='warning', access_log=False))
    server_task = asyncio.create_task(server.serve())
    base = f'http://127.0.0.1:{port}'
    results = []
    checks = {}
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
            for _ in range(300):
                if server_task.done():
                    await server_task
                    raise RuntimeError('Demo server exited before ready')
                try:
                    response = await client.get(base + '/api/state')
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError('Demo server did not become ready')
            initial = response.json()
            checks['startup_four_online_agents'] = (len(initial['agents']) == 4 and
                                                    all(x['status'] == 'online' for x in initial['agents']))
            checks['no_false_platform_connection'] = initial['platform']['connection'] is False
            invalid = await client.post(base + '/api/runs', json={'scenario': 'not-a-scenario'})
            checks['invalid_scenario_422'] = invalid.status_code == 422
            extra = await client.post(base + '/api/runs', json={'scenario': 'combined', 'target': 'elsewhere'})
            checks['extra_fields_422'] = extra.status_code == 422
            form = await client.post(base + '/api/runs', data={'scenario': 'combined'})
            checks['non_json_415'] = form.status_code == 415
            foreign = await client.get(base + '/api/state', headers={'Origin': 'https://foreign.invalid'})
            checks['foreign_origin_403'] = foreign.status_code == 403
            rebound = await client.get(base + '/api/state', headers={'Host': 'foreign.invalid'})
            checks['foreign_host_403'] = rebound.status_code == 403
            unknown = await client.get(base + '/api/runs/unknown')
            checks['unknown_run_404'] = unknown.status_code == 404
            scenarios = ['stale_endpoint', 'database_paused', 'combined', 'agent_offline',
                         'unknown_fault', 'agent_offline', 'combined']
            for index, scenario in enumerate(scenarios):
                started = await client.post(base + '/api/runs', json={'scenario': scenario})
                started.raise_for_status()
                assert started.status_code == 202, started.text
                run_id = started.json()['id']
                if index == 0:
                    collision = await client.post(base + '/api/runs', json={'scenario': 'combined'})
                    checks['concurrent_run_409'] = collision.status_code == 409
                statuses = set()
                for _ in range(1000):
                    run_response = await client.get(base + '/api/runs/' + run_id)
                    run_response.raise_for_status()
                    run = run_response.json()
                    statuses.add(tuple(s['status'] for s in run['steps']))
                    if run['status'] != 'running':
                        break
                    await asyncio.sleep(0.05)
                else:
                    raise RuntimeError('Run did not finish: ' + run_id)
                assert run['status'] == 'completed', run
                assert run['result']['passed'], run
                assert run['result']['data_unchanged'], run
                assert len(run['steps']) == 6, run
                expected_states = ['completed'] * 6
                if scenario == 'unknown_fault':
                    expected_states[3] = 'skipped'
                assert [s['status'] for s in run['steps']] == expected_states, run
                if scenario == 'agent_offline':
                    assert run['result']['unreachable_attempts'] >= 1, run
                    assert run['unreachable'], run
                if scenario == 'unknown_fault':
                    assert run['result']['outcome'] == 'needs_human', run
                    assert run['result']['mutations'] == 0, run
                    assert run['result']['after_status'] == 500, run
                results.append({'run_id': run_id, 'scenario': scenario, 'result': run['result'],
                                'observed_progress_states': [list(s) for s in statuses]})
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            final = (await client.get(base + '/api/state')).json()
            checks['two_retired_partners_preserved'] = sum(
                a['status'] == 'offline' for a in final['agents']) == 2
            checks['replacement_online'] = any(a['id'] == 'LOCAL.DATABASE.REPLACEMENT.2'
                                              and a['status'] == 'online' for a in final['agents'])
            checks['observed_real_intermediate_progress'] = all(
                len(r['observed_progress_states']) > 1 for r in results)
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=30)
    shutdown = json.loads((output / 'shutdown.json').read_text(encoding='utf-8'))
    checks['all_children_stopped'] = shutdown['all_children_stopped']
    all_passed = all(checks.values()) and len(results) == 7
    report = {'output': str(output), 'passed': all_passed, 'checks': checks, 'runs': results}
    save_json(output / 'acceptance.json', report)
    print(json.dumps({'output': str(output), 'passed': all_passed, 'checks': checks}, ensure_ascii=False), flush=True)
    if not all_passed:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
