"""Audit recorded wire messages independently of the Leader's decisions."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parent
output = Path((ROOT / 'LATEST.txt').read_text(encoding='utf-8'))
summary = json.loads((output / 'results.json').read_text(encoding='utf-8'))
events = [json.loads(line) for line in (output / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
responses = [e['body']['result'] for e in events if e['kind'] == 'aip_response' and e['body'].get('result')]
completed = [r for r in responses if r['status']['state'] == 'completed']
expected_states = ['accepted', 'working', 'awaiting-completion', 'completed']
checks = {
    '24_paired_runs': len(summary['results']) == 24,
    'all_outcomes_as_expected': all(r['passed'] for r in summary['results']),
    'database_content_preserved': all(r['data_unchanged'] for r in summary['results']),
    'aip_completion_has_full_history': bool(completed) and all(
        [s['state'] for s in r['statusHistory']] == expected_states for r in completed),
    'replacement_really_replied': any(r['senderId'] == 'LOCAL.DATABASE.REPLACEMENT' for r in completed),
    'replacement_registered_after_original_stopped': next(
        i for i, e in enumerate(events) if e['kind'] == 'local_registration'
        and e['id'] == 'LOCAL.DATABASE.REPLACEMENT') > next(
        i for i, e in enumerate(events) if e['kind'] == 'partner_stopped'),
    'process_cleanup_reported': summary['processes_stopped'],
    'stale_evidence_rejected': summary['guards']['stale_evidence_rejected'],
}
ports_closed = True
for event in events:
    if event['kind'] == 'process_started':
        port = int(event['endpoint'].rsplit(':', 1)[1])
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                ports_closed = False
checks['all_test_ports_closed'] = ports_closed
sdk = ROOT / 'vendor' / 'ACPs-community'
git = ['git', '-c', f'safe.directory={sdk.as_posix()}', '-C', str(sdk)]
actual_commit = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip()
sdk_diff = subprocess.check_output([*git, 'status', '--porcelain'], text=True).strip()
checks['sdk_commit_matches'] = actual_commit == summary['sdk_commit']
checks['sdk_source_unmodified'] = not sdk_diff
audit = {'checks': checks, 'completed_aip_tasks': len(completed), 'event_count': len(events),
         'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT / 'services.py', ROOT / 'run_pilot.py',
                              output / 'results.json', output / 'events.jsonl']}}
(output / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
print(json.dumps(audit, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
