"""Read-only Docker/source evidence audit plus filtered taskId access snapshots.

Run on the authorized cloud after the consumed four-case batch. This does not
open an identity transport, alter a lease, inject faults, or repair a resource.
Only the fresh evidence directory is written.
"""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/opt/incident-pilot')
PREP = ROOT / 'runtime/private/cloud-four-revalidation-20261020-r1'
OUTPUT = ROOT / 'evidence/cloud-four-revalidation-20261020-r1'
PLAN = json.loads((PREP / 'batch-plan.json').read_text())
RESULTS = ROOT / PLAN['results']
sys.path.insert(0, str(ROOT))
from eval.reconcile_access import reconcile


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def docker(*command):
    return json.loads(subprocess.check_output(['docker', *command], text=True))


def health_summary(value):
    return {name: value.get(name) for name in ('duration_seconds', 'requests', 'success',
        'failed', 'unknown', 'completed_workflows', 'unresolved_intents', 'passed')}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    ids = subprocess.check_output(['docker', 'ps', '-a', '-q', '--filter',
        'label=com.docker.compose.project=' + PLAN['project']], text=True).split()
    containers = docker('inspect', *ids)
    volumes = set()
    for item in containers:
        role = (item['Config'].get('Labels') or {}).get('com.docker.compose.service', '')
        if role.endswith('-agent'):
            volumes.update(m['Name'] for m in item['Mounts']
                if m['Destination'] == '/state' and m['Type'] == 'volume')
    domain_access = set()
    for name in volumes:
        volume = docker('volume', 'inspect', name)[0]
        domain_access.update(Path(volume['Mountpoint']).rglob('amp_access_*.jsonl'))
    report = load(RESULTS / 'batch/summary.json')
    rows = []
    for case in PLAN['cases']:
        directory = ROOT / case['output']
        transport = directory / ('transport' if case['case'] == 'F10' else 'coordinator')
        messages = transport / 'messages.jsonl'
        starts = set()
        for line in messages.read_text().splitlines():
            record = json.loads(line)
            message = record['message']
            if record['direction'] == 'send' and message.get('type') == 'task-command' and message.get('command') == 'start':
                starts.add(message['taskId'])
        snapshot = OUTPUT / case['key'] / 'access'
        snapshot.mkdir(parents=True)
        source_counts = []
        for index, path in enumerate(sorted(domain_access | set((transport / 'amp').rglob('amp_access_*.jsonl')))):
            selected = []
            for line in path.read_text().splitlines():
                record = json.loads(line)
                if record.get('correlation_id', record.get('correlationId')) in starts:
                    selected.append(line)
            if selected:
                destination = snapshot / ('amp_access_' + str(index) + '.jsonl')
                destination.write_text('\n'.join(selected) + '\n')
                source_counts.append({'source':str(path),'selected_records':len(selected),'snapshot':destination.name})
        access = reconcile(messages, snapshot, transport='wutong-amqps')
        access['snapshot_sources'] = source_counts
        access['access_counting_passed'] = bool(access['captured_start_tasks']) and access['missing_records'] == 0 and access['extra_records'] == 0 and access['platform_pairing']['passed']
        access['lifecycle_scope'] = 'Original interrupted tasks may lack terminal lifecycle; access pairing is judged separately from task success and platform ingestion.'
        save(OUTPUT / case['key'] / 'access-accounting.json', access)
        batch_case = next(r for r in report['cases'] if r['key'] == case['key'])
        result = batch_case['result']
        rows.append({'key':case['key'],'status':batch_case['status'],
            'safe_to_continue':batch_case.get('safe_to_continue'),
            'errors':{k:v for k,v in result.items() if k.endswith('error_class')},
            'resource_and_worker_restore':result.get('resource_and_worker_restore'),
            'independent_final_H00':health_summary(result.get('independent_final_H00',{})),
            'business_verification':health_summary(result.get('business_verification',{})),
            'close_checks':result.get('close_checks'),
            'batch_consumer_cleanup':result.get('batch_consumer_cleanup',{}).get('status'),
            'access_recovery':result.get('access_recovery'),
            'access_accounting':{name:access[name] for name in ('captured_start_tasks','expected_access_records',
                'actual_access_records','missing_records','extra_records','incomplete_task_lifecycles','access_counting_passed')},
            'platform_pairing':{name:access['platform_pairing'][name] for name in ('task_count','paired_task_count',
                'pairing_rate','missing_endpoint_task_ids','duplicate_endpoint_task_ids','conflicting_task_ids','passed')}})
    value = {'schema_version':'cloud-four-audit/1','batch_id':PLAN['batch_id'],
        'observed_at':datetime.now(timezone.utc).isoformat(),'batch_status':report['status'],
        'lease':report.get('lease'),'cases':rows,'model_calls':0,
        'scope':'Read-only audit of the consumed four cases. Source logs are filtered by their captured taskId; no historical unrelated rows or Monitor ingestion inferred.'}
    save(OUTPUT / 'summary.json', value)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
