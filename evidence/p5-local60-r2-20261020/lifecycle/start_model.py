from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

BATCH=Path(__file__).resolve().parent
ROOT=Path('D:/AI + 开源/team-repository-multi-agent-interconnect')
MODEL=Path('D:/AI + 开源/incident-pilot/tools/runtime/local-model')
binary=MODEL/'b11707/llama-server.exe'
command=[str(binary),'--model',str(MODEL/'Qwen3-1.7B-Q8_0.gguf'),'--alias','Qwen3-1.7B-Q8_0',
    '--host','127.0.0.1','--port','8089','--ctx-size','32768','--n-gpu-layers','99','--parallel','1',
    '--jinja','--reasoning','off','--no-webui','--cors-origins','http://127.0.0.1:8089']
with (BATCH/'model-server.log').open('ab') as output:
    process=subprocess.Popen(command,cwd=MODEL,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
record={'pid':process.pid,'command':command,'started_at':datetime.now(timezone.utc).isoformat(),
    'base_url':'http://127.0.0.1:8089/v1','model':'Qwen3-1.7B-Q8_0','context_size_requested':32768,
    'owned_by_batch':str(BATCH),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
(BATCH/'model-process.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(90):
    if process.poll() is not None:
        raise RuntimeError(f'Owned model exited {process.returncode}')
    try:
        with opener.open('http://127.0.0.1:8089/health',timeout=2) as response:
            health=json.load(response)
        if health.get('status')=='ok':
            record['health']=health
            for target in [BATCH/'model-process.json', ROOT/'tools/runtime/local-model/server.json']:
                target.write_text(json.dumps(record,indent=2),encoding='utf-8')
            print(json.dumps({'status':'MODEL_READY','pid':process.pid,'base_url':record['base_url'],'context_size':32768}))
            break
    except (OSError,ValueError):
        pass
    time.sleep(1)
else:
    raise RuntimeError('Owned model did not become ready')
