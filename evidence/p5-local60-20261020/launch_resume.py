"""Start the owned continuation independently of a tool console/process group."""
import ctypes
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

BATCH=Path(__file__).resolve().parent
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetCurrentProcess.restype=ctypes.c_void_p
kernel.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
in_job=ctypes.c_int()
if not kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(in_job)):
    raise ctypes.WinError(ctypes.get_last_error())
command=[sys._base_executable,str(BATCH/'resume_local60.py')]
environment={**os.environ,'__PYVENV_LAUNCHER__':sys.executable,'PYTHONUTF8':'1'}
flags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_BREAKAWAY_FROM_JOB
with (BATCH/'continuation-output.txt').open('xb') as stream:
    process=subprocess.Popen(command,cwd=BATCH,env=environment,stdin=subprocess.DEVNULL,
        stdout=stream,stderr=subprocess.STDOUT,creationflags=flags,close_fds=True)
child_in_job=ctypes.c_int()
if not kernel.IsProcessInJob(ctypes.c_void_p(int(process._handle)),None,ctypes.byref(child_in_job)):
    raise ctypes.WinError(ctypes.get_last_error())
record={'pid':process.pid,'command':command,'owned_by_batch':str(BATCH),'started_at':datetime.now(timezone.utc).isoformat(),
    'creation_flags':flags,'detached_process':True,'new_process_group':True,'breakaway_from_job':True,
    'launcher_in_job':bool(in_job.value),'child_in_job':bool(child_in_job.value)}
(BATCH/'continuation-process.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
