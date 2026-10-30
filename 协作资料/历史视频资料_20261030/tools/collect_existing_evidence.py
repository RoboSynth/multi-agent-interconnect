"""Collect traceable historical video inputs; no live UI or executions are simulated."""
from pathlib import Path
import collections
import datetime
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent / 'team-repository-multi-agent-interconnect'
OUT = ROOT / '素材'
OUT.mkdir(exist_ok=True)
manifest = []

def load(relative):
    return json.loads((REPO / relative).read_text(encoding='utf-8-sig'))

def save(relative, data, sources, note):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != content:
        raise FileExistsError(path)
    if not path.exists():
        path.write_text(content, encoding='utf-8')
    manifest.append({'file': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'sources': [{'path': '[project]/' + str(p.relative_to(REPO)).replace('\\', '/'),
                     'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources], 'note': note})

def copy(relative, source, note):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != source.read_bytes(): raise FileExistsError(path)
    if not path.exists(): shutil.copyfile(source, path)
    manifest.append({'file': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'sources': [{'path': '[project]/' + source.relative_to(REPO).as_posix(),
                     'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}], 'note': note})

for folder in ('V1-registry','V2-discovery','V3-f10','V4-takeover','V5-access','V6-safety','V7-opensource'):
    (OUT / folder).mkdir(exist_ok=True)

# Historical F10 access pairs; never represent them as newly recorded footage.
base = REPO / 'evidence/cloud-four-revalidation-20261020'
f10_sources = sorted((base / 'audit/f10-m0-r1/access').glob('*.jsonl'))
sys.path.insert(0, str(ROOT / 'tools'))
import extract_replay
extract_replay.main(REPO, OUT / 'V3-f10/replay-historical.json')
replay = json.loads((OUT / 'V3-f10/replay-historical.json').read_text())
manifest.append({'file':'V3-f10/replay-historical.json','sha256':hashlib.sha256((OUT/'V3-f10/replay-historical.json').read_bytes()).hexdigest(),
    'sources':[{'path':'[project]/'+p.relative_to(REPO).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in f10_sources],
    'note':'Historical 2026-10-20 F10/M0; no matching video currently available.'})
for path in f10_sources:
    copy('V3-f10/access/' + path.name, path, 'Exact historical access bytes; platform AICs retained for pairing.')
f10_result = base / 'cases/f10-m0-r1/results.json'
save('V3-f10/results-historical.json', json.loads(f10_result.read_text()), [f10_result], 'Historical cloud F10/M0 result.')
wrapper = base / 'cases/f10-m0-r1/wrapper-result.json'
w = json.loads(wrapper.read_text())
save('V3-f10/order-samples-final-h00.json', {'scope':'independent final H00 AFTER the F10 case; not the same run as the replay',
    'events':w['independent_final_H00']['events'], 'summary':{k:v for k,v in w['independent_final_H00'].items() if k not in ('events','state')}},
    [wrapper], 'Separate post-case H00. Never synchronize this to the F10 run as if concurrent.')
save('V3-f10/run.json', {'scope':'historical_run_data_only','batch':'cloud-four-revalidation-20261020',
    'case':'F10','method':'M0','incident_id':json.loads(f10_result.read_text())[0]['incident_id'],
    'access_t0_utc':replay['t0_utc'],'matching_video_available':False,'video_start_delta_seconds':None,
    'events_jsonl_available':False,'approvals_available':False}, [f10_result,*f10_sources], 'Missing synchronization evidence is explicit.')

# E1-a after_applied: actual access timestamps and untimed exit receipt are kept separate.
path = base / 'cases/e1a-after_applied-r1/results.json'
d = json.loads(path.read_text())
timeline = []
access_sources = sorted((base / 'audit/e1a-after_applied-r1/access').glob('*.jsonl'))
for source in access_sources:
    for line in source.read_text().splitlines():
        row = json.loads(line);body = row['body']
        timeline.append({'at':row['timestamp'],'event':'access_record','task_id':row['correlation_id'],
            'emitter_aic':row['aic'],'route':body['request'].get('route'),'method':body['request'].get('method'),
            'http_status':(body.get('response') or {}).get('statusCode'), 'error':body.get('error')})
timeline.sort(key=lambda row:row['at'])
products = [{'kind':p['payload'].get('kind'),'tool':p['payload'].get('tool'),
    'logical_task_id':p['payload'].get('logical_task_id'),'executor_aic':p['product'].get('executor_aic'),
    'status':p['product'].get('status'),'operation':p['product'].get('operation')} for p in d['products']]
save('V4-takeover/takeover-timeline.json', {'scope':'historical cloud E1-a after_applied, 2026-10-20',
    'incident_id':d['incident_id'],'started_at':d['started_at'],'finished_at':d['finished_at'],
    'events':timeline,'products':products,'untimed_worker_exit_receipt':d['worker_exit_and_mcp'],
    'journal_resolution':d['journal_resolution'],
    'business_verification':{k:v for k,v in d['business_verification'].items() if k not in ('events','state')},
    'limits':['Access log timestamps are retained as access events; no crash/discovery timestamps inferred.',
              'Old-primary revival/fence rejection is not established by this case.', 'No matching screen recording.']},
    [path,*access_sources], 'Do not label this historical timeline as a new live recording.')

# Safety: local component experiment, not a production-platform security claim.
source = REPO / 'evidence/gateway-policy-e2c-20261019/run-attempt-1/results.json'
d = json.loads(source.read_text())
save('V6-safety/policy-denials.json', {k:d[k] for k in ('schema_version','status','started_at','completed_at','scope',
    'case_count','rejection_cases','positive_controls','positive_controls_passed','rejected_policy_execution_mcp_calls',
    'policy_execution_mcp_calls','independent_verification_probe_calls','cases','limits')}, [source],
    'Local stdio fixture, self-signed audit certificate; not Wutong production-CA acceptance.')
source=REPO/'evidence/eval/results/local/E1c-container-20261017-retry/credential-scan.json'
save('V6-safety/credential-scan.json',json.loads(source.read_text()),[source], 'Historical scan of exactly two supplied files; not a scan of the current full deployment.')

# Historical contribution status only; no publication or API write.
source=REPO/'evidence/upstream-status-20261019/recheck-1651/summary.json'
d=json.loads(source.read_text())
keys=('number','title','state','kind','html_url','draft','merged','merged_at','updated_at','additions','deletions','changed_files')
save('V7-opensource/contributions-historical.json', {'observed_at':d.get('checked_at_utc'),
    'status_is_current':False,'repository':d['repository'],
    'threads':[{k:x[k] for k in keys if k in x} for x in d['threads']]},[source], 'Refresh PR/Issue state before final filming; no author account exported.')

# Genuine stored ranking points, with gaps, not reconstructed hourly samples.
folder=REPO/'artifacts/leaderboard-investigation-20261022'
points=[];sources=[]
for p in sorted(folder.glob('live_four_boards-*.json')):
    try: x=json.loads(p.read_text(encoding='utf-8-sig'))
    except (ValueError,UnicodeError):continue
    points.append({k:x[k] for k in ('observed_at_utc','timeRange','headers','boards') if k in x});sources.append(p)
save('V5-access/ranking-snapshots-historical.json', {'scope':'saved historical cumulative snapshots; not an hourly-complete curve',
    'interpolated':False,'points':points},sources,'Leave gaps. Querying old windows now is a retrospective recomputation, not an old captured snapshot.')
source=REPO/'artifacts/score-audit-20261023/cloud-24h-summary.json'
d=json.loads(source.read_text())
save('V5-access/longrun-24h-historical.json',d,[source], 'Historical fixed 24-hour window includes maintenance; heartbeat sample coverage is not exact availability.')
source=REPO/'artifacts/runtime-repair-20261028/final-status.json'
save('V5-access/recovery-20261028.json',json.loads(source.read_text()),[source],'Verified 09:42 recovery snapshot; not current status or uninterrupted 7x24 proof.')

(OUT/'source-manifest.json').write_text(json.dumps({'collected_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'entries':manifest,'live_recordings_created':0,'publications_or_messages_sent':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(manifest),'root':str(OUT),'pending':'live video, synchronized events/actions, current ranking, registry login'},ensure_ascii=False))
