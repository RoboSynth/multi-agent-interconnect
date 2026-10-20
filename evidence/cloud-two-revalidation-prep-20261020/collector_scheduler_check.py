"""Read-only post-batch source/offset/inspection receipt; no identities opened."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

root = Path('/opt/incident-pilot')
out = root / 'evidence/cloud-two-revalidation-20261020-r1' / 'collector-scheduler-restored.json'
batch = 'cloud-two-20261020-c6161b6b00'
directory = root / 'artifacts/cloud-collector-20261019'
load = lambda p: json.loads(Path(p).read_text())
held = load(directory / 'held-all-six.json')
plan = load(directory / 'collection-plan.json')
inspect = lambda *args: json.loads(subprocess.check_output(['docker', *args], text=True))
container = inspect('inspect', held['id'])[0]
mounts = {m['Destination']: m for m in container['Mounts']}
mount_options = {m['Target']:m for m in container['HostConfig']['Mounts']}
offset_mount = mounts['/collector-state']
offset_volume = inspect('volume', 'inspect', offset_mount['Name'])[0]
source_rows = []
for source in plan['sources']:
    mount = mounts[source['collector_mount']]
    if source['role'] == 'coordinator':
        correct = mount['Type'] == 'bind' and mount['Source'] == str(root / source['host_project_relative_directory'])
    else:
        correct = (mount['Type'] == 'volume' and mount.get('Name') == source['named_volume']
            and mount_options[source['collector_mount']].get('VolumeOptions',{}).get('Subpath') == source['volume_subpath'])
    source_rows.append({'role':source['role'], 'correct_original_source':correct,
        'read_only':mount['RW'] is False, 'source':mount['Source'], 'destination':mount['Destination']})
offsets = []
for database in sorted(Path(offset_mount['Source']).glob('*.db')):
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        records = connection.execute('select id,name,offset,inode,created,rotated from in_tail_files').fetchall()
    finally:
        connection.close()
    for identity, name, offset, inode, created, rotated in records:
        matches = [destination for destination in mounts if name == destination or name.startswith(destination + '/')]
        destination = max(matches, key=len)
        subpath = mount_options[destination].get('VolumeOptions',{}).get('Subpath','')
        source = Path(mounts[destination]['Source']) / subpath / name[len(destination):].lstrip('/')
        stat = source.stat()
        offsets.append({'db':database.name, 'id':identity, 'name':name, 'offset':offset,
            'inode':inode, 'created':created, 'rotated':rotated, 'source_size':stat.st_size,
            'lag_bytes':stat.st_size-offset, 'same_source_inode':stat.st_ino==inode,
            'offset_within_source':0<=offset<=stat.st_size})
events = [json.loads(line) for line in (root / 'runtime/private/cloud-new7-schedule/events.jsonl').read_text().splitlines()]
request = next(event for event in events if event['event']=='planned_pause_requested' and event.get('reason')==batch)
resume = next(event for event in events if event['event']=='planned_pause_finished' and event.get('request_id')==request['request_id'])
finished = [event for event in events if event['event']=='job_finished' and event.get('kind')=='inspect'
    and event['at']>resume['at'] and event.get('status')=='completed']
value = {'schema_version':'cloud-two-collector-scheduler/1','observed_at':datetime.now(timezone.utc).isoformat(),
    'batch_id':batch,'collector':{'id':container['Id'],'running':container['State']['Running'],
        'started_at':container['State']['StartedAt'],'held_started_at':held['started_at'],
        'restart_count':container['RestartCount'],'same_original_container':container['Id']==held['id'],
        'offset_volume':offset_mount['Name'],'offset_volume_created_at':offset_volume['CreatedAt']},
    'sources':source_rows,'offsets':offsets,'inspection_pause':request,'inspection_resumed':resume,
    'completed_inspections_after_resume':finished,
    'scope':'Read-only SQLite mode=ro reads and Docker inspect. Retained container/volume/row creation and current inode/offset evidence; no offsets reset or replay requested.'}
with out.open('x') as stream:
    json.dump(value,stream,indent=2);stream.write('\n')
print(json.dumps({'path':str(out),'same_collector':value['collector']['same_original_container'],
    'restart_count':value['collector']['restart_count'],'original_sources_match':all(r['correct_original_source'] and r['read_only'] for r in source_rows),
    'offset_rows':len(offsets),'offsets_valid':all(r['same_source_inode'] and r['offset_within_source'] for r in offsets),
    'post_resume_completed_inspections':finished}))
