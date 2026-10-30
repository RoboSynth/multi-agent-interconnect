"""Continue the original frozen matrix, keeping interrupted and completed attempts."""
import ast
import asyncio
from datetime import datetime, timezone
import difflib
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path('D:/AI + 开源/team-repository-multi-agent-interconnect')
BATCH=Path(__file__).resolve().parent
R1=BATCH/'matrix-r1'
R2=BATCH/'matrix-r2'
sys.path.insert(0,str(ROOT))
import eval.run as evaluator
from business.load import OrderObserver

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plan():
    original=json.loads((R1/'results.json').read_text(encoding='utf-8'))
    done={(row['scenario'],row['method'],row['repeat']) for row in original}
    if len(original)!=29 or len(done)!=29:
        raise RuntimeError('Continuation expects the preserved 29 unique terminal rows')
    methods=['MR','M0','M1','M2v2']
    ordered=[(scenario,method,repeat+1) for scenario in ['F01','F02','F06','F07','F10']
        for repeat in range(3) for method in methods[repeat%4:]+methods[:repeat%4]]
    if {(row['scenario'],row['method'],row['repeat']) for row in original}!=set(ordered[:29]):
        raise RuntimeError('Original terminal rows do not match the first 29 planned cells')
    for row in original:
        if row['workload_seed']!=[101,202,303][row['repeat']-1] or row['precondition_pool_rebuilds']!=(row['repeat']-1)%3:
            raise RuntimeError('Original held-out bindings differ')
    frozen=json.loads((R1/'experiment.json').read_text(encoding='utf-8'))['source_sha256']
    evaluator.check_sources(frozen)
    source=inspect.getsource(evaluator.run)
    marker='                for method in ordered_methods:\n'
    if source.count(marker)!=1:
        raise RuntimeError('Frozen loop shape does not match the reviewed continuation guard')
    guarded=source.replace(marker,marker+'                    if (scenario, method, repeat + 1) in completed_cell_keys:\n                        continue\n')
    before=ast.parse(source);after=ast.parse(guarded)
    loops=[node for node in ast.walk(after) if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='method']
    if len(loops)!=1 or not isinstance(loops[0].body[0],ast.If):
        raise RuntimeError('Unexpected orchestration transformation')
    del loops[0].body[0]
    if ast.dump(before)!=ast.dump(after):
        raise RuntimeError('Continuation changed more than the reviewed skip guard')
    (BATCH/'resume-guarded-run.py').write_text(guarded,encoding='utf-8')
    (BATCH/'resume-guard.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True),guarded.splitlines(True),
        fromfile='frozen eval.run.run',tofile='external continuation orchestration')),encoding='utf-8')
    namespace=dict(vars(evaluator),completed_cell_keys=done)
    exec(compile(guarded,str(BATCH/'resume-guarded-run.py'),'exec'),namespace)
    revision={'status':'CONTINUATION_BOUND','original_plan_sha256':sha(BATCH/'bound-plan.json'),
        'original_results_sha256':sha(R1/'results.json'),'original_source_sha256':frozen,
        'authorization':'Original user-authorized local 60 cells; continue remaining cells after interrupted executor',
        'planned_order':ordered,'completed_cell_keys':ordered[:29],'remaining_cell_keys':ordered[29:],
        'interrupted_attempt':{'cell':ordered[29],'incident_id':'inc-f37914601a4341f6','classification':'EXECUTOR_INTERRUPTED',
            'algorithm_failure':False,'last_apply_at':'2026-10-20T03:16:50.920560+00:00','terminal_row':False},
        'orchestration_change':'Only skip the original 29 completed cell keys; all original repeat indices/order/seed/pool preconditions retained',
        'guard_semantic_diff_verified':True,'guarded_runner_sha256':sha(BATCH/'resume-guarded-run.py'),
        'controller_sha256':sha(Path(__file__)),'original_output':str(R1),'continuation_output':str(R2),
        'recorded_at':datetime.now(timezone.utc).isoformat()}
    save(BATCH/'continuation-revision-1.json',revision)
    return original,revision,namespace['run']

async def restore_and_check():
    restore=await evaluator.inject('F06','restore',ROOT/'deploy/native-runtime.json',BATCH/'continuation-private/injections.jsonl',backend='native')
    save(BATCH/'continuation-restore-F06.json',restore)
    command=['C:/Users/shared-user/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe',
        '-NoProfile','-File',str(ROOT/'deploy/native.ps1'),'-Action','start','-RuntimeFile',str(ROOT/'deploy/native-runtime.json')]
    with (BATCH/'continuation-native-start.txt').open('wb') as stream:
        process=await asyncio.create_subprocess_exec(*command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        code=await asyncio.wait_for(process.wait(),timeout=100)
    if code:
        raise RuntimeError(f'Owned native resource restoration failed: {code}')
    health=await OrderObserver('http://127.0.0.1:8088',run_id='p5-resume-healthy').observe(duration=30,min_complete=10)
    save(BATCH/'continuation-h00.json',health)
    if health.get('passed') is not True:
        raise RuntimeError('Restored resources failed 30-second / 10-workflow health check')

async def execute(original,revision,resume_run):
    await restore_and_check()
    evaluator.check_sources(revision['original_source_sha256'])
    original_args=json.loads((BATCH/'execution-intent.json').read_text(encoding='utf-8'))['arguments']
    args=evaluator.build_parser().parse_args([])
    for key,value in original_args.items():
        setattr(args,key,Path(value) if key in {'config','runtime','output','target_config'} and value is not None else value)
    args.output=R2
    os.environ['INCIDENT_LLM_API_KEY']=''
    save(BATCH/'continuation-execution-intent.json',{'started_at':datetime.now(timezone.utc).isoformat(),
        'revision_sha256':sha(BATCH/'continuation-revision-1.json'),'arguments':vars(args),'remaining_cells':31})
    code=await resume_run(args)
    subsequent=json.loads((R2/'results.json').read_text(encoding='utf-8'))
    subsequent_keys=[(row['scenario'],row['method'],row['repeat']) for row in subsequent]
    if len(subsequent)!=31 or subsequent_keys!=[tuple(key) for key in revision['remaining_cell_keys']]:
        raise RuntimeError('Continuation did not record exactly the 31 remaining cells in the original order')
    aggregate=BATCH/'matrix-combined'
    aggregate.mkdir(exist_ok=False)
    (aggregate/'incidents').mkdir()
    save(aggregate/'results.json',original+subsequent)
    for directory in [R1,R2]:
        for row in json.loads((directory/'results.json').read_text(encoding='utf-8')):
            path=directory/'incidents'/f"{row['incident_id']}.json"
            (aggregate/'incidents'/path.name).write_bytes(path.read_bytes())
    (aggregate/'experiment.json').write_bytes((R1/'experiment.json').read_bytes())
    save(aggregate/'continuation.json',{'original_terminal_cells':29,'continued_terminal_cells':31,
        'interrupted_attempts':1,'unique_terminal_cells':60,'r1_result_sha256':sha(R1/'results.json'),
        'r2_result_sha256':sha(R2/'results.json'),'revision_sha256':sha(BATCH/'continuation-revision-1.json'),
        'same_frozen_source':json.loads((R2/'experiment.json').read_text(encoding='utf-8'))['source_sha256']==revision['original_source_sha256']})
    return code

def main():
    outcome={'status':'PREPARING_CONTINUATION','pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat()}
    save(BATCH/'continuation-process-self.json',{'pid':os.getpid(),'parent_pid':os.getppid(),
        'sys_executable':sys.executable,'sys_base_executable':sys._base_executable,'command_line':sys.argv,
        'owned_by_batch':str(BATCH),'started_at':outcome['started_at']})
    try:
        original,revision,resume_run=plan()
        code=asyncio.run(execute(original,revision,resume_run))
        outcome.update(status='EVALUATOR_FINISHED',evaluator_exit_code=code,terminal_cells=60)
    except BaseException as error:
        traceback.print_exc()
        outcome.update(status='CONTINUATION_FAILED',error_class=type(error).__name__,error=str(error))
    finally:
        with (BATCH/'continuation-cleanup-output.txt').open('wb') as stream:
            cleanup=subprocess.run([sys.executable,str(BATCH/'cleanup_local.py')],cwd=BATCH,
                stdout=stream,stderr=subprocess.STDOUT,timeout=240)
        outcome['cleanup_exit_code']=cleanup.returncode
        outcome['finished_at']=datetime.now(timezone.utc).isoformat()
        save(BATCH/'continuation-execution-result.json',outcome)
    print(json.dumps(outcome),flush=True)
    return 0 if outcome['status']=='EVALUATOR_FINISHED' else 1

if __name__=='__main__':
    raise SystemExit(main())
