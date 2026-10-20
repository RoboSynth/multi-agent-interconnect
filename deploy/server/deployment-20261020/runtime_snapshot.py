"""Read-only NEW7 service, heartbeat and scheduler acceptance snapshot."""
import argparse
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

root=Path('/opt/incident-pilot')
sys.path.insert(0,str(root))
from tools.check_alive import request_for,summarize
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
spec=importlib.util.spec_from_file_location('snapshot_collector',root/'evidence/cloud-deployment-20261019/prepared-collector/cloud_collector.py')
collector=importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
aics,url=collector.identities(root)
host=collector.load(root/'runtime/private/cloud-longrun/control/host.json')
with urllib.request.urlopen('http://127.0.0.1:8877/api/state',timeout=15) as response:
    api=json.load(response)
units={}
for name in ('workbench','scheduler','collector'):
    unit='incident-'+name+'.service'
    values=subprocess.check_output(['systemctl','show',unit,'--property=MainPID,ActiveState,UnitFileState,ExecMainStatus'],text=True)
    units[name]=dict(line.split('=',1) for line in values.splitlines() if '=' in line)
schedule=collector.load(root/'runtime/private/cloud-longrun/schedule.json')
schedule_state=collector.load(root/'runtime/private/cloud-new7-schedule/schedule.json')
with httpx.Client(timeout=25,trust_env=False) as client:
    response=client.post(url,json=request_for(list(aics.values())))
    response.raise_for_status()
    alive=summarize(response.json(),list(aics.values()))
held=collector.load(root/'artifacts/cloud-collector-20261019/held-all-six.json')
container=collector.inspect_one('container',held['id'])
checks={'services_active':all(row['ActiveState']=='active' for row in units.values()),
        'services_enabled':all(row['UnitFileState']=='enabled' for row in units.values()),
        'host_running':host['status']=='running',
        'same_workbench_pid':host['pid']==api['pid']==int(units['workbench']['MainPID']),
        'formal_connected':api.get('connected') is True and api.get('mode')=='wutong-amqps',
        'resource_credentials_zero':api.get('resource_credential_count')==0,
        'model_disabled':api.get('model_config',{}).get('enabled') is False,
        'seven_alive':alive['all_online'] and alive['online_count']==7,
        'inspect_every_600_seconds':schedule['inspect_interval_seconds']==600,
        'no_auto_approvals':schedule['drill_auto_approvals']==[],
        'same_collector_running':container['Id']==held['id'] and container['State']['Running']}
events=root/'runtime/private/cloud-new7-schedule/events.jsonl'
event_counts={}
if events.exists():
    for line in events.read_text().splitlines():
        row=json.loads(line)
        event=row.get('event','unknown')
        event_counts[event]=event_counts.get(event,0)+1
result={'status':'passed' if all(checks.values()) else 'not_ready','observed_at':datetime.now(timezone.utc).isoformat(),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'checks':checks,'units':units,'host_session':host['session_id'],'aics':alive['aics'],
        'collector_id':held['id'],'scheduler_state':schedule_state,'scheduler_event_counts':event_counts,
        'timers':subprocess.check_output(['systemctl','list-timers','incident-daily-report.timer','incident-stage8-check.timer','--all','--no-pager'],text=True)}
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:
    json.dump(result,stream,indent=2)
    stream.write('\n')
print(json.dumps(result))
raise SystemExit(0 if result['status']=='passed' else 1)
