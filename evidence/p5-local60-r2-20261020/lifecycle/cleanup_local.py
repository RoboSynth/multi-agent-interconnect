"""Verify health and stop only this batch's registered local processes."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path('D:/AI + 开源/team-repository-multi-agent-interconnect')
BATCH=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from business import native_process as native
from business.load import OrderObserver
from tools.local_shutdown import fingerprint, supervisor_stop

def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def stop_model():
    expected=json.loads((BATCH/'model-process.json').read_text(encoding='utf-8'))
    kernel,ntdll=native._libraries()
    handle=kernel.OpenProcess(0x1000|0x100000|0x0001,False,expected['pid'])
    if not handle:
        if native.ctypes.get_last_error()==87:
            return {'status':'ALREADY_EXITED','pid':expected['pid']}
        raise OSError(native.ctypes.get_last_error(),'Cannot open owned model process')
    try:
        if kernel.WaitForSingleObject(handle,0)==0:
            return {'status':'ALREADY_EXITED','pid':expected['pid']}
        command=native._argv(native._command_line(ntdll,handle))
        if command!=expected['command']:
            raise ValueError('Model process command differs from the batch registration')
        if native._image_path(kernel,handle)!=native._normalized_path(expected['command'][0]):
            raise ValueError('Model process executable differs from the batch registration')
        if not kernel.TerminateProcess(handle,0) or kernel.WaitForSingleObject(handle,5000)!=0:
            raise OSError('Owned model process did not stop')
        return {'status':'EXACT_OWNED_PROCESS_STOPPED','pid':expected['pid'],'command_verified':True,'image_verified':True}
    finally:
        kernel.CloseHandle(handle)

def main():
    report={'started_at':datetime.now(timezone.utc).isoformat(),'stages':{},'unrelated_processes_untouched':True}
    try:
        final=asyncio.run(OrderObserver('http://127.0.0.1:8088',run_id='p5-r2-final-healthy').observe(duration=30,min_complete=10))
        save(BATCH/'final-h00.json',final)
        report['stages']['final_h00']={key:value for key,value in final.items() if key not in {'events','state'}}
    except Exception as error:
        report['stages']['final_h00']={'error_class':type(error).__name__,'error':str(error),'passed':False}
    try:
        registration=BATCH/'owned-supervisor.pid'
        if registration.exists():
            raise RuntimeError('Unexpected preexisting supervisor registration')
        supervisor=json.loads((BATCH/'supervisor-process.json').read_text(encoding='utf-8'))
        registration.write_text(str(supervisor['pid'])+'\n',encoding='ascii')
        report['stages']['supervisor']=supervisor_stop(registration,fingerprint(registration),60)
    except Exception as error:
        report['stages']['supervisor']={'status':'FAILED','error_class':type(error).__name__,'error':str(error)}
    try:
        command=['C:/Users/16080/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe',
            '-NoProfile','-File',str(ROOT/'deploy/native.ps1'),'-Action','stop','-RuntimeFile',str(ROOT/'deploy/native-runtime.json')]
        with (BATCH/'native-stop-output.txt').open('wb') as stream:
            process=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=120)
        report['stages']['native']={'exit_code':process.returncode,'status':'STOPPED' if process.returncode==0 else 'FAILED'}
    except Exception as error:
        report['stages']['native']={'status':'FAILED','error_class':type(error).__name__,'error':str(error)}
    try:
        report['stages']['model']=stop_model()
    except Exception as error:
        report['stages']['model']={'status':'FAILED','error_class':type(error).__name__,'error':str(error)}
    listeners=[]
    for _ in range(30):
        listeners=[]
        for port in [55432,8081,8082,8088,8089,8093]:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',port))==0:
                    listeners.append(port)
        if not listeners:
            break
        time.sleep(.25)
    report['remaining_batch_listeners']=listeners
    report['status']='STOPPED' if not listeners and report['stages']['native'].get('exit_code')==0 and report['stages']['supervisor'].get('status')=='NORMAL_CLOSED' and report['stages']['model'].get('status') in {'ALREADY_EXITED','EXACT_OWNED_PROCESS_STOPPED'} else 'INCOMPLETE'
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    save(BATCH/'cleanup-result.json',report)
    print(json.dumps({'status':report['status'],'final_h00_passed':report['stages']['final_h00'].get('passed'),
        'remaining_batch_listeners':listeners},ensure_ascii=False))
    return 0 if report['status']=='STOPPED' else 1

if __name__=='__main__':
    raise SystemExit(main())
