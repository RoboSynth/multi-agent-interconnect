"""Run one external task from the cloud coordinator via the official RPC client."""
import asyncio
import datetime
import json
from pathlib import Path
import ssl
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor/ACPs-community/acps-sdk')]
import httpx
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from acps_sdk.amp.access_emitter import AccessEmitter
import os

TARGET = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LIANSHU_EXTERNAL_TARGET_AIC", '1.2.156.3088.1.0000.000000.000000.000000.0101')
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output = ROOT / 'evidence' / ('external-rpc-once-' + stamp + '-' + uuid.uuid4().hex[:6])
output.mkdir(parents=True)
report = {'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'target_aic': TARGET, 'output_directory': str(output),
          'transport': 'HTTPS JSONRPC', 'status': 'started', 'results': []}


def save(name, value):
    (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


async def run():
    deployment = json.loads((ROOT / 'runtime/private/cloud-new7-20261019/deployment.json').read_text())
    config_path = Path(deployment['coordinator_config'])
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = json.loads(config_path.read_text())
    leader = config['leader']
    report['caller_aic'] = leader['aic']
    async with httpx.AsyncClient(trust_env=False, timeout=20) as public:
        response = await public.get('https://wt.ioa.pub/registry-server/acps-atr-v2/acs/' + TARGET)
        response.raise_for_status()
        acs = response.json()
        save('target-acs.json', acs)
        query = {'type': 'filtered', 'limit': 50,
                 'filter': {'logic': 'and', 'conditions': [{'field': 'aic', 'op': 'in', 'value': [TARGET]}]},
                 'extFilter': {'logic': 'and', 'conditions': [{'field': 'alive', 'op': 'in', 'value': ['online', 'offline', 'unknown']}]}}
        response = await public.post(config['discovery_url'], json=query)
        response.raise_for_status()
        save('discovery.json', response.json())

    endpoint = next(item['url'] for item in acs['endPoints']
                    if item.get('transport') == 'JSONRPC' and item['url'].startswith('https://'))
    report.update(target_name=acs['name'], endpoint=endpoint)
    skill = ('research.plan_template' if TARGET.endswith('RXO3OT.1AQ9') else acs['skills'][0]['id'])
    report['skill'] = skill
    context = ssl.create_default_context(cafile=config['trust_bundle'])
    context.load_cert_chain(leader['cert'], leader['key'])

    plan = json.loads((ROOT / 'artifacts/cloud-collector-20261019/collection-plan.json').read_text())
    source = next(item for item in plan['sources'] if item['role'] == 'coordinator')
    directory = ROOT / source['host_project_relative_directory']
    log_file = max(directory.glob('amp_access_*.jsonl'), key=lambda path: path.stat().st_mtime)
    report['access_log'] = str(log_file)
    emitter = AccessEmitter(log_file=log_file, aic=leader['aic'])
    client = AipRpcClient(endpoint, leader['aic'], ssl_context=context,
                          expected_partner_aic=TARGET, callee_aic=TARGET,
                          caller_service='incident-pilot-coordinator',
                          callee_service=skill, access_emitter=emitter)
    task = 'external-' + uuid.uuid4().hex
    session = task
    report.update(session_id=session, task_id=task)
    request = {
        'action': 'get_plan_template', 'skill': 'research.plan_template',
        'research_type': 'paired_comparison',
        'topic': '多智能体故障恢复：固定观察与证据调度的配对对照实验',
        'request': '请返回实验设计模板，用于完善已有实验的说明。比较固定观察M0与证据调度M2v2，'
                   '指标包括恢复成功率、观察成本、敏感观察次数和首次业务恢复耗时。',
    }
    message = sys.argv[2] if len(sys.argv) > 2 else json.dumps(request, ensure_ascii=False)
    save('request.json', {'caller_aic': leader['aic'], 'target_aic': TARGET,
                          'session_id': session, 'task_id': task, 'content': message})
    started = time.monotonic()
    try:
        result = await client.start_task(session, message, task_id=task)
        for index in range(11):
            raw = result.model_dump(mode='json', by_alias=True, exclude_none=True)
            report['results'].append(raw)
            save('result-' + str(index) + '.json', raw)
            state = result.status.state.value
            report['task_state'] = state
            if state == 'awaiting-completion':
                final = await client.complete_task(task, session)
                raw = final.model_dump(mode='json', by_alias=True, exclude_none=True)
                report['results'].append(raw)
                save('completion.json', raw)
                report['task_state'] = final.status.state.value
                break
            if state not in ('accepted', 'working'):
                break
            if index < 10:
                await asyncio.sleep(6)
                result = await client.get_task(task, session)
        if report['task_state'] in ('accepted', 'working', 'awaiting-input'):
            report['returned_state'] = report['task_state']
            final = await client.cancel_task(task, session)
            report['results'].append(final.model_dump(mode='json', by_alias=True, exclude_none=True))
            report['task_state'] = final.status.state.value
            report['status'] = 'needs_input' if report['returned_state'] == 'awaiting-input' else 'timeout'
        else:
            report['status'] = 'completed' if report['task_state'] == 'completed' else 'task_returned'
    except BaseException:
        if report.get('task_state') in ('accepted', 'working', 'awaiting-input'):
            try:
                cleanup = await asyncio.wait_for(client.cancel_task(task, session), timeout=8)
                raw = cleanup.model_dump(mode='json', by_alias=True, exclude_none=True)
                report['results'].append(raw)
                report['task_state'] = cleanup.status.state.value
                save('exception-cleanup.json', raw)
            except Exception as cleanup_error:
                report['cleanup_error'] = type(cleanup_error).__name__
        raise
    finally:
        await client.close()
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)


try:
    asyncio.run(asyncio.wait_for(run(), timeout=100))
except Exception as error:
    report.update(status='failed', error_type=type(error).__name__, error=str(error)[:1200])
report['finished_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
save('summary.json', report)
products = {}
for response in report['results']:
    for product in response.get('products', []):
        products[product['id']] = product
brief = {key: value for key, value in report.items() if key != 'results'}
brief.update(result_count=len(report['results']), product_count=len(products),
             products=list(products.values()),
             latest_status_data=report['results'][-1].get('status', {}).get('dataItems', []) if report['results'] else [])
print(json.dumps(brief, ensure_ascii=True))
