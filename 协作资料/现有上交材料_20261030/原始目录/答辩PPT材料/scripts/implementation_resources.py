"""Read-only resource inventory; SSH arguments are supplied privately at runtime."""
import argparse
import datetime
import json
import pathlib
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--ssh-target')
parser.add_argument('--ssh-key')
parser.add_argument('--known-hosts')
args = parser.parse_args()
result = {'captured_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
local_code = '''import importlib.metadata,json,platform,sys
packages={}
for name in ['aio-pika','httpx','pydantic','fastapi','uvicorn','mcp','cryptography','jcs','psycopg','acps-sdk']:
 try: packages[name]=importlib.metadata.version(name)
 except importlib.metadata.PackageNotFoundError: packages[name]=None
print(json.dumps({'system':platform.system(),'release':platform.release(),'version':platform.version(),'python':sys.version.split()[0],'packages':packages}))
'''
python = pathlib.Path(args.repo) / '.venv' / 'Scripts' / 'python.exe'
local = subprocess.run([str(python), '-B', '-c', local_code], capture_output=True, text=True, timeout=20)
result['local'] = json.loads(local.stdout) if local.returncode == 0 else {'status': 'unavailable', 'exit_code': local.returncode}
remote_code = '''import datetime,json,subprocess
commands={'cpu_logical':['nproc'],'memory':['free','-h'],'root_disk':['df','-h','/'],'os_release':['cat','/etc/os-release'],'docker_server':['sudo','-n','docker','version','--format','{{.Server.Version}}']}
out={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':{}}
for name,command in commands.items():
 r=subprocess.run(command,capture_output=True,text=True,timeout=15)
 out['commands'][name]={'exit_code':r.returncode,'stdout':r.stdout.strip() if r.returncode==0 else None}
print(json.dumps(out))
'''
if args.ssh_target and args.ssh_key and args.known_hosts:
    command = ['ssh.exe', '-i', args.ssh_key, '-o', 'UserKnownHostsFile=' + args.known_hosts,
               '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
               args.ssh_target, 'python3 -']
    try:
        remote = subprocess.run(command, input=remote_code, capture_output=True, text=True, timeout=45)
        result['cloud'] = json.loads(remote.stdout) if remote.returncode == 0 else {'status': 'unavailable', 'ssh_exit_code': remote.returncode}
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        result['cloud'] = {'status': 'unavailable', 'reason': 'timeout_or_unparseable_response'}
else:
    result['cloud'] = {'status': 'not_requested'}
pathlib.Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
