"""Read current server logs from the project cwd; never changes services or consumers."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
from eval.stability_bundle import _scheduler

now=datetime.now(timezone.utc)
start=datetime.fromisoformat('2026-10-20T07:00:00+08:00').timestamp()
end=now.timestamp()
interval=15

def command(args):
    proc=subprocess.run(args,capture_output=True,text=True,timeout=25)
    return proc.returncode,proc.stdout

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def when(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def tag(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]

class Snapshot:
    def __init__(self,raw): self.raw=raw
    def open(self,**kwargs): return io.StringIO(self.raw.decode('utf-8-sig'))

deployment=load(ROOT/'runtime/private/cloud-new7-20261019/deployment.json')
config_path=Path(deployment['coordinator_config'])
if not config_path.is_absolute(): config_path=ROOT/config_path
config=load(config_path)
role_codes={'coordinator':'A01','application':'A02','database':'A03','database-backup':'A04','ops':'A05','verification':'A06','onboarding':'A07'}
identities={'coordinator':config['leader']['aic']}
for role,values in config['trusted_participant_aics'].items():
    for i,aic in enumerate(values): identities['database-backup' if role=='database' and i else role]=aic

services={}
for name in ('workbench','scheduler','collector'):
    code,text=command(['systemctl','show','incident-'+name+'.service','--property=ActiveState,SubState,NRestarts,ExecMainStatus,ActiveEnterTimestamp,UnitFileState','--no-pager'])
    services[name]={'command_exit_code':code,**dict(line.split('=',1) for line in text.splitlines() if '=' in line)}
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8877/api/state',timeout=15) as response:
        state=json.load(response)
    workbench={'connected':state.get('connected'),'mode':state.get('mode'),'participant_count':len(state.get('participants',[])),
        'incident_status_counts':dict(Counter(item.get('status') for item in state.get('incidents',[]))),
        'latest_incident_status':(state.get('incident') or {}).get('status'),
        'connection_error_present':bool(state.get('connection_error'))}
except Exception as exc:
    workbench={'connected':None,'error_class':type(exc).__name__}

event_path=ROOT/'runtime/private/cloud-new7-schedule/events.jsonl'
event_raw=event_path.read_bytes()
scheduler=_scheduler([Snapshot(event_raw)],start,end)
events=[]
for line in event_raw.splitlines():
    try:
        item=json.loads(line)
        if start<=when(item['at'])<end: events.append(item)
    except (ValueError,KeyError,TypeError): pass
finished=[item for item in events if item.get('event')=='job_finished']
def job_projection(item):
    return {**{key:item.get(key) for key in ('at','event','kind','status','seconds')},
        'run_alias':'RUN-'+tag(item['run_id']) if item.get('run_id') else None}
for row in scheduler['jobs']:
    row['run_id']='RUN-'+tag(row['run_id'])
inspection=next(item for item in scheduler['by_kind'] if item['kind']=='inspect')
inspection['completed_fraction_of_recorded_jobs']=inspection['completed']/inspection['recorded_jobs'] if inspection['recorded_jobs'] else None

plan=load(ROOT/'artifacts/cloud-collector-20261019/collection-plan.json')
heartbeats=[]
sources=[]
for source in plan['sources']:
    role=source['role']
    if role not in role_codes: continue
    if source.get('host_project_relative_directory'):
        directory=ROOT/source['host_project_relative_directory']
    else:
        code,mount=command(['docker','volume','inspect',source['named_volume'],'--format','{{.Mountpoint}}'])
        if code: raise RuntimeError('Could not inspect current role state volume')
        directory=Path(mount.strip())/source['volume_subpath']
    timestamps=[]
    invalid=0
    seen=set()
    for index,path in enumerate(sorted(directory.glob('amp_heartbeat_*.jsonl'))):
        raw=path.read_bytes()
        sources.append({'source_id':role_codes[role]+'-heartbeat-'+str(index+1),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        for line in raw.splitlines():
            try:
                row=json.loads(line)
                stamp=when(row['timestamp'])
                if row.get('aic')!=identities[role] or not start<=stamp<end: continue
                key=row.get('log_id') or row['timestamp']
                if key in seen: continue
                seen.add(key)
                timestamps.append(stamp)
            except (ValueError,TypeError,KeyError): invalid+=1
    timestamps=sorted(set(timestamps))
    occupied={int((stamp-start)//interval) for stamp in timestamps}
    expected=math.ceil((end-start)/interval)
    heartbeats.append({'role':role_codes[role],'interval_seconds':interval,'expected_slots':expected,'observed_slots':len(occupied),
        'missing_slots':expected-len(occupied),'coverage_percent':100*len(occupied)/expected,
        'recorded_unique_heartbeat_timestamps':len(timestamps),'invalid_records':invalid,
        'first_heartbeat_utc':datetime.fromtimestamp(timestamps[0],timezone.utc).isoformat() if timestamps else None,
        'last_heartbeat_utc':datetime.fromtimestamp(timestamps[-1],timezone.utc).isoformat() if timestamps else None,
        'maximum_observed_gap_seconds':max((b-a for a,b in zip(timestamps,timestamps[1:])),default=None)})

boot_epoch=int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
post_boot=[item for item in finished if item.get('status')=='completed' and when(item['at'])>=boot_epoch]
memory={}
for line in Path('/proc/meminfo').read_text().splitlines():
    key,value=line.split(':',1)
    if key in ('MemTotal','MemAvailable'): memory[key+'_kib']=int(value.split()[0])
disk=shutil.disk_usage(ROOT)
result={'schema_version':1,'status':'collected','source_mode':'fresh_read_of_current_runtime_logs',
    'observed_at_utc':now.isoformat(),'window':{'startAt':'2026-10-20T07:00:00+08:00','endAt':now.isoformat(),'duration_hours':(end-start)/3600},
    'services':services,'workbench':workbench,'scheduler':scheduler,
    'recent_completed_inspections':[job_projection(item) for item in finished if item.get('status')=='completed'][-5:],
    'recent_failed_inspections':[job_projection(item) for item in finished if item.get('status')!='completed'][-5:],
    'recent_unknown_signals':[job_projection(item) for item in events if item.get('event') in ('dispatch_unknown','job_timeout','operator_required')][-5:],
    'heartbeat_sampling':{'method':'Occupied 15-second slots in the explicit full time window; maintenance and missing logs remain in the denominator. Not service uptime.', 'agents':heartbeats},
    'current_boot_observation':{'boot_time_utc':datetime.fromtimestamp(boot_epoch,timezone.utc).isoformat(),
        'host_uptime_seconds':float(Path('/proc/uptime').read_text().split()[0]),'reboot_performed_this_batch':False,
        'first_recorded_completion_after_boot':job_projection(post_boot[0]) if post_boot else None,
        'seconds_from_boot_to_first_recorded_completion':when(post_boot[0]['at'])-boot_epoch if post_boot else None,
        'automatic_recovery_independently_verified_this_batch':False},
    'host_resources':{'load_average':os.getloadavg(),'memory':memory,'disk_free_bytes':disk.free},
    'source_snapshots':[{'source_id':'scheduler-events','sha256':hashlib.sha256(event_raw).hexdigest(),'bytes':len(event_raw)},*sources],
    'limitations':['The scheduler reports task completion; this does not independently prove successful resource recovery.',
        'Heartbeat sampling coverage is not uptime or 7x24 uninterrupted operation.',
        'No reboot or fault was triggered; automatic restart recovery was not re-tested.',
        'This is a new read of current runtime files, not a reused prior report.']}
print(json.dumps(result,ensure_ascii=False))
