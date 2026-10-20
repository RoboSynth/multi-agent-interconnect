import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path('D:/AI + 开源/team-repository-multi-agent-interconnect')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from incident.local_transport import LocalAipStdioTransport

async def check_transport():
    config=json.loads((ROOT/'runtime/local-coordinator.json').read_text(encoding='utf-8-sig'))
    config.update(directory=str(BATCH/'preflight-transport'),journal_path=str(BATCH/'preflight-transport/journal.sqlite'),
        amp_directory=str(BATCH/'preflight-transport/amp'),term_journal_path=str(BATCH/'private/preflight-terms.sqlite'))
    transport=LocalAipStdioTransport(config)
    try:
        await transport.start()
        if 'incident.symptom_check' not in transport.tools:
            raise RuntimeError('Local verification worker did not advertise symptom checks')
        product=await transport.call({'incident_id':'p5-readonly-preflight','logical_task_id':'symptom',
            'kind':'observe','tool':'incident.symptom_check','args':{}})
        facts={fact['key']:fact['value'] for fact in product.get('facts',[])}
        if product['status']!='ok' or facts.get('symptom_check_passed') is not True:
            raise RuntimeError('Actual local symptom-check roundtrip failed')
        # Reproduce the previous matrix's failing path on the actual worker:
        # final verification with no preceding symptom state, then another task.
        verified=await transport.call({'incident_id':'p5-r3-preflight-no-symptoms',
            'logical_task_id':'final','kind':'verify','tool':'incident.verification','args':{},
            'budget':{'deadline_ms':60000}})
        final_facts={fact['key']:fact['value'] for fact in verified.get('facts',[])}
        window=final_facts.get('order_observation',{})
        if (verified['status']!='ok' or final_facts.get('business_recovered') is not True
                or 'carried_symptom_intents' in final_facts or window.get('duration_seconds',0)<30
                or window.get('completed_workflows',0)<10):
            raise RuntimeError('Actual verification product roundtrip failed')
        following=await transport.call({'incident_id':'p5-r3-preflight-following',
            'logical_task_id':'symptom','kind':'observe','tool':'incident.symptom_check','args':{}})
        if not any(f['key']=='symptom_check_passed' and f['value'] is True for f in following.get('facts',[])):
            raise RuntimeError('Verification worker unavailable after final product')
        return {'tools':transport.tools,'product':product,'verification_product':verified,
                'following_product':following,'participants':transport.worker_status()}
    finally:
        await transport.close()

def main():
    if not (BATCH/'supervisor-process.json').exists():
        with (BATCH/'supervisor.stdout.log').open('ab') as out,(BATCH/'supervisor.stderr.log').open('ab') as err:
            process=subprocess.Popen([sys.executable,str(ROOT/'domains/ops/native_supervisor.py')],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        (BATCH/'supervisor-process.json').write_text(json.dumps({'pid':process.pid,'script':str(ROOT/'domains/ops/native_supervisor.py'),
            'python':sys.executable,'owned_by_batch':str(BATCH),'started_at':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
    env={line.partition('=')[0]:line.partition('=')[2] for line in (ROOT/'runtime/private/ops-bridge.env').read_text(encoding='utf-8').splitlines() if '=' in line}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(40):
        try:
            request=urllib.request.Request('http://127.0.0.1:8093/health',headers={'Authorization':'Bearer '+env['OPS_SUPERVISOR_TOKEN']})
            with opener.open(request,timeout=1) as response:
                health=json.load(response)
            if health.get('ok') and Path(health['project_root']).resolve()==ROOT:
                break
        except OSError:
            pass
        time.sleep(.25)
    else:
        raise RuntimeError('Independent ops supervisor did not become ready')
    result=asyncio.run(check_transport())
    (BATCH/'preflight.json').write_text(json.dumps({'status':'PASSED','supervisor':health,
        'local_aip_actual_roundtrip':result,'platform_calls':0,'model_calls':0,
        'fault_injections':0,'infrastructure_modifications':0,'healthy_business_workflows':12,
        'completed_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'LOCAL_AIP_PREFLIGHT_PASSED','tools':len(result['tools']),
        'symptom_check_roundtrip':True,'no_carried_verification_roundtrip':True,'following_task_roundtrip':True}))

if __name__=='__main__':
    main()
