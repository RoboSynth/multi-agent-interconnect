"""Bind this authorized batch, invoke the normal evaluator, retain all outcomes."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path('D:/AI + 开源/team-repository-multi-agent-interconnect')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from eval.run import build_parser, freeze_sources, run

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

def main():
    os.environ['INCIDENT_LLM_API_KEY']=''
    config_path=ROOT/'runtime/local-coordinator.json'
    config=json.loads(config_path.read_text(encoding='utf-8-sig'))
    if config.get('mode')!='local-aip-stdio' or not config['coordinator_aic'].startswith('local-'):
        raise RuntimeError('This batch must use local identities only')
    if any(not row['aic'].startswith('local-') for row in config['workers']):
        raise RuntimeError('Cloud identity in local batch configuration')
    config['automatic_takeover']=False
    save(config_path,config)
    scope=json.loads((ROOT/'evidence/technical-plan-local-20261019/p5/run-scope-60.json').read_text(encoding='utf-8-sig'))
    authorization=json.loads((BATCH/'authorization-recorded.json').read_text(encoding='utf-8'))
    initial_runtime=json.loads((ROOT/'deploy/native-runtime.json').read_text(encoding='utf-8-sig'))
    plan={**scope,'status':'BOUND_AUTHORIZED_NOT_EXECUTED','authorized':True,
        'bindings_pending':{},'authorization':authorization,'authorization_sha256':hashlib.sha256((BATCH/'authorization-recorded.json').read_bytes()).hexdigest(),
        'source_sha256':freeze_sources(BATCH/'binding'),'runtime_initial':initial_runtime,
        'coordinator_config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
        'model_process':json.loads((BATCH/'model-process.json').read_text(encoding='utf-8')),
        'preflight':json.loads((BATCH/'preflight.json').read_text(encoding='utf-8')),
        'source_frozen_at':datetime.now(timezone.utc).isoformat(),
        'native_lifecycle_fixes':['verification advertises existing symptom_check','stop verified app family before injection and ops restart',
            'fault locker is launched as actual base-interpreter process with its registered venv binding']}
    save(BATCH/'bound-plan.json',plan)
    args=build_parser().parse_args(['--config',str(config_path),'--runtime',str(ROOT/'deploy/native-runtime.json'),
        '--transport','local-aip-stdio','--backend','native','--scenarios','F01,F02,F06,F07,F10',
        '--methods','MR,M0,M1,M2v2','--repeats','3','--approve-high','--enable-llm',
        '--model-base-url','http://127.0.0.1:8089/v1','--model','Qwen3-1.7B-Q8_0','--seed','42',
        '--max-output-tokens','768','--model-call-budget','40','--model-token-budget','65536',
        '--task-budget','40','--deadline-seconds','600','--instance-seeds','101,202,303',
        '--order-url','http://127.0.0.1:8088','--output',str(BATCH/'matrix-r1')])
    start=datetime.now(timezone.utc).isoformat()
    save(BATCH/'execution-intent.json',{'started_at':start,'requested_cells':60,'bound_plan_sha256':hashlib.sha256((BATCH/'bound-plan.json').read_bytes()).hexdigest(),
        'transport':'local-aip-stdio','platform_calls':0,'paid_apis':0,'normal_evaluator':'eval.run.run','arguments':vars(args)},)
    try:
        code=asyncio.run(run(args))
        result={'status':'EVALUATOR_FINISHED','exit_code':code,'started_at':start,'finished_at':datetime.now(timezone.utc).isoformat()}
    except BaseException as error:
        result={'status':'EVALUATOR_FAILED','error_class':type(error).__name__,'error':str(error),
            'started_at':start,'finished_at':datetime.now(timezone.utc).isoformat(),'exit_code':1}
        traceback.print_exc()
        code=1
    save(BATCH/'execution-result.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return code

if __name__=='__main__':
    raise SystemExit(main())
