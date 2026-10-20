"""Publish a compact, credential-free ledger; retain full local artifacts separately."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

BATCH=Path(__file__).resolve().parent
RUN=BATCH/('matrix-combined' if (BATCH/'matrix-combined').exists() else 'matrix-r1')
DEST=Path('D:/AI + 开源/team-repository-multi-agent-interconnect/evidence/p5-local60-20261020')

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def concise_value(key,value):
    if key in {'order_observation','symptom_observation'} and isinstance(value,dict):
        return {k:v for k,v in value.items() if k not in {'events','state'}}
    return value

def scan_publication():
    """Apply the frozen project scanner to every published text type."""
    scanner=SimpleNamespace(**runpy.run_path(str(BATCH/'binding/source/eval/secret_scan.py')))
    env_path=DEST.parents[1]/'deploy/.env'
    known_secrets=[]
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1)
            if any(word in key for word in ['PASSWORD','TOKEN','SECRET','DATABASE_URL','DATABASE_URI','DSN']) and value:
                known_secrets.append(value)
    base=scanner.scan([DEST],known_secrets)
    findings=[]
    scanned=[]
    omitted_binary=[]
    forbidden=[]
    for item in sorted(DEST.iterdir()):
        if not item.is_file() or item.name in {'artifact-manifest.json','publication-scan.json'}:
            continue
        if item.suffix.lower() in {'.env','.sqlite','.db','.gguf'} or item.name.startswith('.env'):
            forbidden.append(item.name)
            continue
        if item.suffix.lower()=='.png':
            omitted_binary.append(item.name)
            continue
        content=item.read_text(encoding='utf-8-sig')
        scanned.append(item.name)
        for number,line in enumerate(content.splitlines(),1):
            categories={name for name,pattern in scanner.PATTERNS.items() if pattern.search(line)}
            if any(secret in line for secret in known_secrets):
                categories.add('known_resource_secret')
            findings.extend({'file':item.name,'line':number,'category':category} for category in sorted(categories))
    result={'status':'PASSED' if not findings and not forbidden and base['machine_checks_passed'] else 'FAILED',
        'scope':'All published text files checked against frozen project credential patterns and live local resource secret values; all JSON parsed',
        'text_files_scanned':len(scanned),'files':scanned,'binary_files_not_text_scanned':omitted_binary,
        'known_secret_values_checked':len(known_secrets),'hits':len(findings),'findings':findings,
        'forbidden_resource_files':forbidden,'json_records_parsed':base['json_records'],
        'parse_errors':base['parse_errors'],'read_errors':base['read_errors'],
        'machine_checks_passed':not findings and not forbidden and base['machine_checks_passed']}
    save(DEST/'publication-scan.json',result)
    if not result['machine_checks_passed']:
        raise RuntimeError('Publication credential or file-scope scan failed; inspect publication-scan.json categories')

def main():
    rows=json.loads((RUN/'results.json').read_text(encoding='utf-8'))
    if len(rows)!=60 or len({(r['scenario'],r['method'],r['repeat']) for r in rows})!=60:
        raise RuntimeError('Only a completed 60-cell batch can be packaged')
    cleanup=json.loads((BATCH/'cleanup-result.json').read_text(encoding='utf-8'))
    if cleanup.get('status')!='STOPPED':
        raise RuntimeError('Publish only after owned-process cleanup completes')
    DEST.mkdir(parents=True,exist_ok=True)
    for item in (BATCH/'publication').iterdir():
        if item.is_file():
            shutil.copy2(item,DEST/item.name)
    names=['authorization-recorded.json','bound-plan.json','execution-intent.json',
        'environment.json','preflight.json','final-h00.json','cleanup-result.json',
        'tests-native-stop.txt','tests-eval.txt','tests-p5.txt','run_local60.py','cleanup_local.py',
        'report.py','plot_report.py','package_evidence.py','verify_evidence.py','native-lifecycle-fixes.patch']
    names+=['continuation-revision-1.json','continuation-execution-intent.json','continuation-execution-result.json',
        'resume_local60.py','resume-guarded-run.py','resume-guard.diff','launch_resume.py','continuation-process.json',
        'continuation-process-self.json','continuation-h00.json','continuation-restore-F06.json']
    for name in names:
        shutil.copy2(BATCH/name,DEST/name)
    shutil.copy2(RUN/'experiment.json',DEST/'experiment.json')
    shutil.copy2(RUN/'continuation.json',DEST/'continuation.json')
    for part in ['r1','r2']:
        for name in ['results.json','experiment.json']:
            shutil.copy2(BATCH/f'matrix-{part}'/name,DEST/f'matrix-{part}-{name}')
    shutil.copy2(BATCH/'interruption-20261020T0333/interruption.json',DEST/'interrupted-attempt.json')
    shutil.copy2(BATCH/'interruption-20261020T0333/inc-f37914601a4341f6.json',DEST/'interrupted-attempt-raw.json')
    interrupted=json.loads((BATCH/'interruption-20261020T0333/inc-f37914601a4341f6.json').read_text(encoding='utf-8'))
    save(DEST/'interrupted-attempt-summary.json',{
        'cell':['F06','M1',2],'classification':'EXECUTOR_INTERRUPTED','algorithm_failure':False,
        'id':interrupted['id'],'original_status':interrupted['status'],'started_at':interrupted['started_at'],
        'tasks':[{key:task.get(key) for key in ['logical_task_id','kind','tool','status']} for task in interrupted['tasks']],
        'source_sha256':hashlib.sha256((BATCH/'interruption-20261020T0333/inc-f37914601a4341f6.json').read_bytes()).hexdigest()})
    ledger=[]
    for row in rows:
        state=json.loads((RUN/'incidents'/f"{row['incident_id']}.json").read_text(encoding='utf-8'))
        tasks=[]
        for task in state.get('tasks',[]):
            product=task.get('product') or {}
            tasks.append({
                **{k:v for k,v in task.items() if k not in {'product','args'}},
                'operation':product.get('operation'),
                'facts':[{**fact,'value':concise_value(fact.get('key'),fact.get('value'))} for fact in product.get('facts',[])],
                'product_status':product.get('status'),
            })
        ledger.append({
            'scenario':row['scenario'],'method':row['method'],'repeat':row['repeat'],
            'incident_id':row['incident_id'],'status':state['status'],'error':state.get('error'),
            'facts':[{**fact,'value':concise_value(fact.get('key'),fact.get('value'))} for fact in state['facts']],
            'diagnosed_causes':state.get('diagnosed_causes'),
            'hypotheses':state.get('hypotheses'),
            'planning_history':state.get('planning_history'),
            'tasks':tasks,
            'model_requests':[{k:v for k,v in request.items() if k not in {'context','schema'}} for request in state.get('model_requests',[])],
            'raw_incident_sha256':hashlib.sha256((RUN/'incidents'/f"{row['incident_id']}.json").read_bytes()).hexdigest(),
        })
    save(DEST/'incident-ledger.json',ledger)
    scan_publication()
    manifest={
        'scope':'60 terminal cells and selected non-secret evidence; no private credentials, model binaries or SQLite copied',
        'full_local_artifact_directory':str(BATCH),
        'compact_ledger_omits':['model input contexts and schemas','task arguments','per-order workflow events and state'],
        'all_failure_rows_retained':True,
        'files':{item.name:{'bytes':item.stat().st_size,'sha256':hashlib.sha256(item.read_bytes()).hexdigest()}
                 for item in sorted(DEST.iterdir()) if item.is_file() and item.name!='artifact-manifest.json'},
    }
    save(DEST/'artifact-manifest.json',manifest)
    print(json.dumps({'destination':str(DEST),'files':len(manifest['files'])+1,
        'terminal_cells':len(rows),'status':'PACKAGED'},ensure_ascii=False))

if __name__=='__main__':
    main()
