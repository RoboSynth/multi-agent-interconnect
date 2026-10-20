"""Reviewed single-file maintenance; run as independent systemd build/activate jobs."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback

ROOT=Path('/opt/incident-pilot')
UPLOAD=Path('/home/ubuntu/.incident-observer-key-maintenance-20261020')
CONTEXT=UPLOAD/'context'
OUT=ROOT/'evidence/observer-key-maintenance-20261020'
PROFILE=ROOT/'runtime/private/cloud-new7-20261019'
CONTROL=ROOT/'runtime/private/cloud-longrun/control'
LEASES=ROOT/'runtime/private/cloud-longrun/leases'
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/ACPs-community/acps-sdk')]
load=lambda path:json.loads(Path(path).read_text(encoding='utf-8-sig'))
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
now=lambda:datetime.now(timezone.utc).isoformat()


def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n')


def command(args,timeout=300):
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        (OUT/'last-command-failure.txt').write_text(result.stdout+result.stderr)
        raise RuntimeError(args[0]+' failed with exit '+str(result.returncode))
    return result.stdout


def inspect_image(image):
    return json.loads(command(['docker','image','inspect',image]))[0]


def image_sources(image,names):
    check='import pathlib,hashlib,json; names='+repr(list(names))+'; print(json.dumps({n:hashlib.sha256((pathlib.Path("/srv")/n).read_bytes()).hexdigest() for n in names}))'
    return json.loads(command(['docker','run','--rm','--network','none','--read-only',image,'python','-B','-c',check]))


def manifest():
    value=load(CONTEXT/'manifest.json')
    assert value['runtime_file']=='business/load.py' and value['expected_tests']==27
    assert value['runtime_sha256']=='a15e87a1222906271d4ab39d68f213887f5775a856911a7dc3daa23947f9890c'
    assert sha(CONTEXT/value['runtime_file'])==value['runtime_sha256']
    assert all(sha(CONTEXT/name)==expected for name,expected in value['tests'].items())
    return value


def build():
    assert not (OUT/'build.json').exists(),'Do not consume the build twice'
    value=manifest();base=inspect_image(value['base_tag'])
    assert base['Id']==value['base_image_id']
    assert image_sources(base['Id'],value['baseline_sources'])==value['baseline_sources']
    assert {name:sha(ROOT/name) for name in value['baseline_sources']}==value['baseline_sources']
    save('pre-build-binding.json',dict(at=now(),base_image_id=base['Id'],host_sources=value['baseline_sources'],
        deployment_manifest_sha256=sha(PROFILE/'deployment.json')))
    (OUT/'build.log').write_text(command(['docker','build','--pull=false','--network=none','-t',value['patch_tag'],str(CONTEXT)]))
    new=inspect_image(value['patch_tag'])
    expected={**value['baseline_sources'],value['runtime_file']:value['runtime_sha256']}
    assert image_sources(new['Id'],expected)==expected
    for field in ('Cmd','Entrypoint','User','WorkingDir','Env','Labels','Volumes','ExposedPorts','StopSignal'):
        assert base['Config'].get(field)==new['Config'].get(field),field
    code='import sys,unittest; sys.path[:0]=["/srv","/srv/tests","/srv/vendor/ACPs-community/acps-sdk"]; r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames('+repr(value['test_modules'])+')); sys.exit(not r.wasSuccessful())'
    test=subprocess.run(['docker','run','--rm','--network=none','--read-only','--tmpfs','/tmp',
        '-v',str(CONTEXT/'tests')+':/srv/tests:ro','-v',str(ROOT/'eval')+':/srv/eval:ro',
        new['Id'],'python','-B','-c',code],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    (OUT/'linux-tests.txt').write_text(test.stdout)
    assert test.returncode==0 and 'Ran 27 tests' in test.stdout,'Linux tests failed; stop before activation'
    save('build.json',dict(status='built_linux_tests_passed',at=now(),image_id=new['Id'],
        source_sha256=expected,linux_tests_run=27,linux_tests_exit_code=test.returncode,manifest=value))
    print(json.dumps(dict(status='built_linux_tests_passed',image_id=new['Id'],tests=27)),flush=True)


def collector_snapshot():
    directory=ROOT/'artifacts/cloud-collector-20261019'
    held=load(directory/'held-all-six.json')
    item=json.loads(command(['docker','inspect',held['id']]))[0]
    mounts={m['Destination']:m for m in item['Mounts']}
    options={m['Target']:m for m in item['HostConfig']['Mounts']}
    source_checks=[]
    for source in load(directory/'collection-plan.json')['sources']:
        mount=mounts[source['collector_mount']]
        if source['role']=='coordinator':
            correct=mount['Type']=='bind' and mount['Source']==str(ROOT/source['host_project_relative_directory'])
        else:
            correct=(mount.get('Name')==source['named_volume'] and
                options[source['collector_mount']].get('VolumeOptions',{}).get('Subpath')==source['volume_subpath'])
        source_checks.append(dict(role=source['role'],source_matches=correct,read_only=not mount['RW']))
    offsets=[]
    for path in sorted(Path(mounts['/collector-state']['Source']).glob('*.db')):
        connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            offsets.extend(dict(db=path.name,id=row[0],name=row[1],offset=row[2],inode=row[3],created=row[4])
                for row in connection.execute('select id,name,offset,inode,created from in_tail_files'))
        finally:connection.close()
    return dict(at=now(),collector_id=item['Id'],running=item['State']['Running'],
        started_at=item['State']['StartedAt'],restart_count=item['RestartCount'],
        offset_volume=mounts['/collector-state']['Name'],sources=source_checks,offsets=offsets)


async def health(run_id,name):
    module=importlib.import_module('business.load');importlib.reload(module)
    result=await module.OrderObserver('http://127.0.0.1:38088',run_id=run_id,
        expected_api_version='v2').observe(duration=30,min_complete=10)
    save(name,result)
    assert (result['passed'] is True and result['success']==30 and result['completed_workflows']==10
        and result['failed']==result['unknown']==result['unresolved_intents']==0),'Business H00 failed'
    return result


async def activate():
    from ops.aic_lease import experiment_lease
    from deploy.prepare_deployment import load_deployment
    value=manifest();built=load(OUT/'build.json')
    assert built['status']=='built_linux_tests_passed' and built['linux_tests_run']==27
    assert inspect_image(value['base_tag'])['Id']==value['base_image_id']
    assert inspect_image(value['patch_tag'])['Id']==built['image_id']
    assert {name:sha(ROOT/name) for name in value['baseline_sources']}==value['baseline_sources']
    load_deployment(PROFILE/'deployment.json',root=ROOT)
    backup=UPLOAD/'source-backup-observer-key';backup.mkdir(exist_ok=False)
    shutil.copyfile(ROOT/value['runtime_file'],backup/'load.py')
    before=collector_snapshot();save('collector-before.json',before)
    state=load(CONTROL/'host.json');deployment_sha=sha(PROFILE/'deployment.json')
    dirty_names=command(['git','-c','safe.directory=/opt/incident-pilot','-C',str(ROOT),'diff','--name-only']).splitlines()
    untouched={name:sha(ROOT/name) for name in dirty_names if name!=value['runtime_file']}
    report=dict(status='starting',started_at=now(),fault_injections=0,model_calls=0,
        original_host_session=state['session_id'],old_image_id=value['base_image_id'],new_image_id=built['image_id'],
        old_runtime_sha256=value['old_runtime_sha256'],new_runtime_sha256=value['runtime_sha256'],untouched_dirty_sources=untouched)
    save('activation.json',report)
    async with experiment_lease(state['aics'],purpose='observer-key-maintenance-20261020',
            control_directory=CONTROL,directory=LEASES,timeout=840) as ownership:
        paused=load(CONTROL/'host.json')
        assert paused['status']=='paused' and paused['consumers_closed'] and paused['lease_released']
        report['pause_receipt']={k:paused[k] for k in ('status','session_id','consumers_closed','lease_released')}
        report['lease_id']=ownership.lease.owner['lease_id'];save('activation.json',report)
        changed=False
        try:
            command(['docker','tag',value['base_image_id'],'incident-pilot-pre-observer-key:20261020'])
            (ROOT/value['runtime_file']).write_bytes((CONTEXT/value['runtime_file']).read_bytes());changed=True
            command(['docker','tag',built['image_id'],value['base_tag']])
            assert sha(ROOT/value['runtime_file'])==value['runtime_sha256']
            load_deployment(PROFILE/'deployment.json',root=ROOT)
            original='cloud-four-20261020-7c082190d0-e1a-before_modification-r1'
            long_run_id=original+'-'+original+':1'
            assert len(long_run_id)==117
            h00=await health(long_run_id,'long-run-h00.json')
            assert all(len(item['request_key'])<=128 and len(item['operation_key'])<=128
                for item in h00['state']['completed'])
            assert {name:sha(ROOT/name) for name in untouched}==untouched
            assert sha(PROFILE/'deployment.json')==deployment_sha
            report.update(status='activated_resume_requested',h00_passed=True,source_binding=dict(
                host_source_sha256={name:sha(ROOT/name) for name in value['baseline_sources']},
                image_source_sha256=built['source_sha256'],deployment_manifest_sha256=deployment_sha,
                image_tag=value['base_tag'],image_id=built['image_id']))
            save('activation.json',report)
        except BaseException as error:
            report.update(status='activation_failed',error_class=type(error).__name__,traceback=traceback.format_exc())
            save('activation.json',report)
            if changed:
                assert sha(ROOT/value['runtime_file']) in (value['runtime_sha256'],value['old_runtime_sha256'])
                assert inspect_image(value['base_tag'])['Id'] in (value['base_image_id'],built['image_id'])
                (ROOT/value['runtime_file']).write_bytes((backup/'load.py').read_bytes())
                command(['docker','tag',value['base_image_id'],value['base_tag']])
                await health('observer-key-rollback-'+str(int(time.time())),'rollback-h00.json')
                report.update(status='failed_rolled_back_resume_requested',rollback_h00_passed=True)
                save('activation.json',report)
                ownership.mark_cleanup_verified(dict(resource_restored=True,h00_passed=True,
                    consumers_closed=True,remote_groups_closed=True,evidence='normal host close plus retained rollback H00; maintenance created no group'))
            raise
        ownership.mark_cleanup_verified(dict(resource_restored=True,h00_passed=True,consumers_closed=True,
            remote_groups_closed=True,evidence='normal managed host close and long-run H00; maintenance created no group'))
    text=await asyncio.to_thread(command,[str(ROOT/'.venv/bin/python'),'-B','/etc/incident-pilot/wait_cloud_workbench.py',
        '--project-root',str(ROOT),'--host-config',str(ROOT/'runtime/private/cloud-longrun/host.json'),'--execute'])
    report['wait_receipt']=json.loads(text);report['resumed_at']=now()
    assert report['wait_receipt']['host_session']==state['session_id']
    ids=command(['docker','ps','-q','--filter','label=com.docker.compose.project=incident-pilot-new7-cloud-20261019']).split()
    domains=[item for item in json.loads(command(['docker','inspect',*ids]))
        if item['Config']['Labels'].get('com.docker.compose.service','').endswith('-agent')]
    assert len(domains)==6 and all(item['Image']==built['image_id'] for item in domains)
    report['running_domains']=6;report['status']='running_waiting_scheduled_inspection';save('activation.json',report)
    print(json.dumps(dict(status=report['status'],image_id=built['image_id'],host_source_sha256=value['runtime_sha256'])),flush=True)
    resume=report['resumed_at']
    deadline=time.monotonic()+720
    while time.monotonic()<deadline:
        events=[json.loads(line) for line in (ROOT/'runtime/private/cloud-new7-schedule/events.jsonl').read_text().splitlines()]
        completed=[event for event in events if event.get('event')=='job_finished' and event.get('kind')=='inspect'
                   and event.get('status')=='completed' and event['at']>resume]
        if completed:break
        await asyncio.sleep(10)
    else:raise TimeoutError('No post-maintenance scheduled inspection completed')
    report['post_resume_inspections']=completed
    after=collector_snapshot();save('collector-after.json',after)
    keys=lambda rows:{(r['db'],r['id'],r['name'],r['inode']):r['offset'] for r in rows}
    a,b=keys(before['offsets']),keys(after['offsets'])
    checks=dict(same_collector=before['collector_id']==after['collector_id'],
        same_started_at=before['started_at']==after['started_at'],same_offset_volume=before['offset_volume']==after['offset_volume'],
        same_offset_rows=a.keys()==b.keys(),no_offset_decrease=a.keys()==b.keys() and all(b[k]>=a[k] for k in a),
        sources_match=all(r['source_matches'] and r['read_only'] for r in after['sources']),collector_running=after['running'])
    report['collector_checks']=checks;assert all(checks.values())
    report['offset_rows_advanced']=sum(b[k]>a[k] for k in a)
    command([str(ROOT/'.venv/bin/python'),'-B','/etc/incident-pilot/runtime_snapshot.py','--output',str(OUT/'runtime-after.json')])
    snapshot=load(OUT/'runtime-after.json')
    expected_checks={'services_active','services_enabled','host_running','same_workbench_pid','formal_connected',
        'resource_credentials_zero','model_disabled','seven_alive','inspect_every_600_seconds','no_auto_approvals','same_collector_running'}
    assert snapshot['status']=='passed' and set(snapshot['checks'])==expected_checks
    assert all(value is True for value in snapshot['checks'].values())
    report['runtime_checks']=snapshot['checks']
    report.update(status='completed',finished_at=now());save('activation.json',report)
    print(json.dumps(dict(status='completed',image_id=built['image_id'],post_resume_inspections=completed)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('build','activate'));args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    try:
        if args.action=='build':build()
        else:asyncio.run(activate())
    except BaseException as error:
        save(args.action+'-failure.json',dict(status='failed',at=now(),error_class=type(error).__name__,traceback=traceback.format_exc()))
        raise
