"""Controlled feasibility probes, not a product or an AI repair benchmark.

Uses synthetic files/processes and a separate headless browser profile. Does not
call model APIs, read user log contents, change real app settings, or install hooks.
"""
from __future__ import annotations
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
RUN = HERE / '运行记录' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
RUN.mkdir(parents=True, exist_ok=False)
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
RESULTS = {}

def execute(args, *, cwd=RUN, timeout=20):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=CREATION_FLAGS)

# The PowerShell probe only registers a future event subscription and activates UIA.
try:
    ps = shutil.which('pwsh') or shutil.which('powershell')
    p = execute([ps, '-NoProfile', '-File', str(HERE / '原生能力探针.ps1'), '-OutputDirectory', str(RUN / 'native')])
    RESULTS['native'] = json.loads((RUN / 'native' / 'native-results.json').read_text(encoding='utf-8-sig'))
    RESULTS['native']['process_exit_code'] = p.returncode
except Exception as exc:
    RESULTS['native'] = {'error': str(exc)}

# Capture a subprocess failure, repair only its synthetic config, replay and verify.
# The repair candidate is deterministic; no model quality is tested.
try:
    task_dir = RUN / 'synthetic-task'
    task_dir.mkdir()
    config = task_dir / 'config.json'
    good_input = task_dir / 'input.txt'
    good_input.write_text('controlled task content', encoding='utf-8')
    config.write_text(json.dumps({'input': 'missing.txt'}), encoding='utf-8')
    original = config.read_bytes()
    task_code = "import json,pathlib; p=pathlib.Path('.'); c=json.loads((p/'config.json').read_text()); text=(p/c['input']).read_text(); (p/'output.txt').write_text(text.upper()); print('TASK_OK')"
    args = [sys.executable, '-X', 'utf8', '-c', task_code]
    before = execute(args, cwd=task_dir)
    backup = task_dir / 'config.before.json'
    backup.write_bytes(original)
    replacement = task_dir / 'config.pending.json'
    replacement.write_text(json.dumps({'input': 'input.txt'}), encoding='utf-8')
    os.replace(replacement, config)
    after = execute(args, cwd=task_dir)
    output = task_dir / 'output.txt'
    independently_verified = after.returncode == 0 and output.read_text() == 'CONTROLLED TASK CONTENT'
    config.write_bytes(backup.read_bytes())
    restored = config.read_bytes() == original
    failed_again = execute(args, cwd=task_dir)
    RESULTS['controlled_repair'] = {
        'passed': before.returncode != 0 and independently_verified and restored and failed_again.returncode != 0,
        'failure_captured': 'FileNotFoundError' in before.stderr,
        'before_exit_code': before.returncode, 'after_exit_code': after.returncode,
        'task_result_verified': independently_verified, 'original_config_restored': restored,
        'fault_reproduced_after_restore': failed_again.returncode != 0,
        'original_config_sha256': hashlib.sha256(original).hexdigest(),
        'scope': 'Only a synthetic config in this run directory; deterministic fix, not real software or model evaluation',
    }
except Exception as exc:
    RESULTS['controlled_repair'] = {'passed': False, 'error': str(exc)}

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            body = b'''<!doctype html><title>Isolated feasibility fixture</title><script>
console.error("EA_SYNTHETIC_CONSOLE");
fetch('/missing');
setTimeout(() => { throw new Error("EA_SYNTHETIC_EXCEPTION"); }, 100);
</script>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args): pass

chrome = None
server = None
try:
    browser = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    if not browser.exists():
        browser = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test_url = f'http://127.0.0.1:{server.server_port}/'
    profile = RUN / 'isolated-browser-profile'
    browser_log = open(RUN / 'isolated-browser.log', 'wb')
    chrome = subprocess.Popen([str(browser), '--headless=new', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', f'--user-data-dir={profile}', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-sync', '--disable-extensions', 'about:blank'], stdin=subprocess.DEVNULL, stdout=browser_log, stderr=browser_log, creationflags=CREATION_FLAGS)
    active_port = profile / 'DevToolsActivePort'
    deadline = time.monotonic() + 15
    while not active_port.exists() and time.monotonic() < deadline and chrome.poll() is None:
        time.sleep(0.1)
    lines = active_port.read_text().splitlines()
    endpoint = f'ws://127.0.0.1:{lines[0]}{lines[1]}'
    browser_result_path = RUN / 'browser-results.json'
    browser_probe = execute([shutil.which('node'), str(HERE / 'browser-probe.mjs'), endpoint, test_url, str(browser_result_path)], timeout=20)
    RESULTS['browser_cdp'] = json.loads(browser_result_path.read_text())
    RESULTS['browser_cdp']['probe_exit_code'] = browser_probe.returncode
    if browser_probe.returncode:
        RESULTS['browser_cdp']['error'] = browser_probe.stderr[-1200:]
except Exception as exc:
    RESULTS['browser_cdp'] = {'passed': False, 'error': str(exc)}
finally:
    if chrome is not None:
        try:
            chrome.wait(timeout=5)
            RESULTS['owned_browser_cleanup'] = {'passed': True, 'method': 'Browser.close and process wait'}
        except subprocess.TimeoutExpired:
            cleanup = execute(['taskkill', '/PID', str(chrome.pid), '/T', '/F'], timeout=10)
            RESULTS['owned_browser_cleanup'] = {'passed': cleanup.returncode == 0, 'method': 'Terminate only the owned probe PID and descendants'}
        browser_log.close()
    if server is not None:
        server.shutdown()
        server.server_close()

RESULTS['metadata'] = {
    'local_date': '2026-10-15', 'python': sys.version.split()[0],
    'model_api_calls': 0, 'external_accounts_changed': False,
    'user_browser_profile_used': False, 'real_app_configs_modified': False,
    'run_directory': str(RUN),
}
(RUN / 'results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')
(HERE / 'latest-run.json').write_text(json.dumps({'results': str(RUN / 'results.json')}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
