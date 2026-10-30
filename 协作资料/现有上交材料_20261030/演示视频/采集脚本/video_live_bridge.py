"""Capture-only adapter: one real runner, existing UI, actual approval futures.

Does not start a transport, acquire an identity, or change deployed source.
HTTP binds loopback only; reach it through the authenticated SSH tunnel.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlsplit


def now():
    return datetime.now(timezone.utc).isoformat()


class LiveBridge:
    def __init__(self, root, private, config, port=8879):
        self.root, self.private = Path(root), Path(private)
        self.private.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.aliases = {config['leader']['aic']: 'A01'}
        codes = {'application': 'A02', 'database': 'A03', 'ops': 'A05', 'verification': 'A06', 'onboarding': 'A07'}
        for role, identity in config.get('initial_participant_aics', {}).items():
            if role in codes:
                self.aliases[identity] = codes[role]
        for role, values in config.get('trusted_participant_aics', {}).items():
            for identity in values:
                self.aliases.setdefault(identity, 'A04' if role == 'database' else codes.get(role, 'AX'))
        self.state = None
        self.engine = None
        self.transport = None
        self.connected = False
        self.case = None
        self.phase = 'prepared'
        self.case_result = None
        self.events = []
        self.gate = asyncio.Event()
        self.loop = asyncio.get_running_loop()
        self.clock = {'utc': now(), 'epoch_seconds': time.time(), 'monotonic_seconds': time.monotonic()}
        self.persist('clock-anchor.json', self.clock)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def send(self, status, value, kind='application/json; charset=utf-8'):
                body = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', kind)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                route = urlsplit(self.path).path
                if route == '/api/state':
                    return self.send(200, bridge.snapshot())
                if route == '/api/capture':
                    return self.send(200, bridge.clean({'case': bridge.case, 'phase': bridge.phase,
                        'connected': bridge.connected, 'result': bridge.case_result, 'clock': bridge.clock,
                        'observed_at_utc': now(), 'events': bridge.events[-50:]}))
                assets = {'/': ('workbench.html', 'text/html; charset=utf-8'),
                    '/assets/workbench.css': ('workbench.css', 'text/css; charset=utf-8'),
                    '/assets/workbench.js': ('workbench.js', 'text/javascript; charset=utf-8'),
                    '/assets/workbench-access.js': ('workbench-access.js', 'text/javascript; charset=utf-8')}
                if route in assets:
                    filename, kind = assets[route]
                    content = (bridge.root / 'demo-ui' / filename).read_text(encoding='utf-8')
                    if filename == 'workbench.html':
                        content = content.replace('</head>', '<style>#incident-form,aside>details{display:none} .intro{padding-top:12px} .intro h1{font-size:28px} header{position:sticky;top:0;z-index:5} #capture-note{padding:9px 28px;background:#e7f2f7;color:#164f68;font-size:13px}</style></head>')
                        content = content.replace('<main>', '<div id="capture-note">本次真实云端运行的观察视图 · 发起入口关闭 · 审批按钮连接同一协调器</div><main>')
                        content = content.replace('</body>', '<script>setInterval(async()=>{try{const c=await(await fetch("/api/capture")).json();document.getElementById("capture-note").textContent=`${c.case||"等待案例"} · ${c.phase} · 同次云端运行 / 观察时间 ${c.observed_at_utc}`;}catch{}},800);</script></body>')
                    return self.send(200, content, kind)
                return self.send(404, {'detail': 'Not found'})

            def do_POST(self):
                route = urlsplit(self.path).path
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length > 4096:
                        raise ValueError('Body too large')
                    body = json.loads(self.rfile.read(length) or b'{}')
                    if route == '/api/capture/start':
                        self.loop_call(bridge.release(body.get('case')))
                    elif route.startswith('/api/approvals/'):
                        approval_id = unquote(route.rsplit('/', 1)[-1])
                        self.loop_call(bridge.approve(approval_id, body.get('approved')))
                    else:
                        return self.send(405, {'detail': 'Capture view cannot create incidents'})
                    self.send(200, {'ok': True})
                except Exception as error:
                    self.send(409, {'detail': type(error).__name__})

            def loop_call(self, coroutine):
                return asyncio.run_coroutine_threadsafe(coroutine, bridge.loop).result(timeout=10)

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def persist(self, name, value):
        (self.private / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')

    def record(self, event, **fields):
        row = {'captured_at_utc': now(), 'captured_monotonic': time.monotonic(), 'event': event, **fields}
        with (self.private / 'capture-events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        self.events.append(row)

    def clean(self, value):
        if isinstance(value, dict):
            return {self.clean(str(key)): ('[removed]' if re.search(r'(?i)(secret|password|signature|certificate|private_key|authorization)|^(?:token|access_token|refresh_token)$', str(key)) else self.clean(item))
                for key, item in value.items()}
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if not isinstance(value, str):
            return value
        for identity, alias in sorted(self.aliases.items(), key=lambda item: len(item[0]), reverse=True):
            value = value.replace(identity, alias)
        value = re.sub(r'1\.2\.156\.3088\.1\.[A-Za-z0-9.]+', '[external-role]', value)
        value = re.sub(r'(?i)(?:https?|amqps?)://[^\s\"<>]+', '[endpoint]', value)
        value = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', '[address]', value)
        value = re.sub(r'(?i)[A-Z]:[\\/][^\r\n\"<>]+|/(?:opt|home|Users|domain|runtime|tmp)/[^\s\"<>]+', '[path]', value)
        return value

    def snapshot(self):
        return self.clean({'connected': self.connected, 'mode': 'wutong-amqps',
            'participants': deepcopy(getattr(self.transport, 'participants', [])),
            'model_config': {'enabled': False}, 'model': 'rules',
            'artifacts': '本次新鲜采集；原始运行记录独立保存', 'incident': deepcopy(self.state)})

    async def wait_case(self, key):
        self.case, self.phase, self.state, self.case_result = key, 'ready_for_capture', None, None
        self.engine, self.transport, self.connected = None, None, False
        self.gate.clear()
        self.record('capture_case_ready', case=key)
        print(json.dumps({'event': 'capture_case_ready', 'case': key, 'at': now()}), flush=True)
        await asyncio.wait_for(self.gate.wait(), timeout=600)
        self.phase = 'running'
        self.record('capture_case_started', case=key)

    async def release(self, key):
        if key != self.case or self.phase != 'ready_for_capture':
            raise ValueError('Case gate mismatch')
        self.gate.set()

    async def approve(self, approval_id, approved):
        if type(approved) is not bool or self.engine is None or approval_id not in self.engine.approvals:
            raise ValueError('No matching real pending approval')
        entry = self.engine.approvals[approval_id][2]
        age = datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(entry['requested_at']).timestamp()
        if age < 2:
            raise ValueError('Approval must remain pending for at least two real seconds')
        self.engine.capture_real_decide(approval_id, approved)
        self.record('capture_operator_decision', approval_id=approval_id, approved=approved, pending_seconds=age,
            decision_applied=True, channel='existing IncidentCoordinator.decide real pending future')

    def coordinator_class(self, original):
        bridge = self
        class CaptureCoordinator(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                bridge.engine = self
                existing = self.on_update
                def update(state):
                    if existing:
                        existing(state)
                    bridge.state = deepcopy(state)
                self.on_update = update

            def decide(self, approval_id, approved):
                # Only suppress eval.run's 0.1s pre-authorization polling in this
                # isolated instance. The HTTP operator channel calls the original.
                return None

            def capture_real_decide(self, approval_id, approved):
                return super().decide(approval_id, approved)
        return CaptureCoordinator

    def instrument(self, transport, *, v2=False):
        self.transport = transport
        original_event, original_start, original_call, original_close = transport.on_event, transport.start, transport.call, transport.close
        def event(row):
            if original_event:
                original_event(row)
            self.record('transport_observed', source_event=row)
            if self.case and self.case.startswith('e1') and self.state:
                self.state['events'].append({'at': now(), **deepcopy(row), 'time_basis': 'capture arrival; original transport record has no native wall time'})
        transport.on_event = event
        cap = None
        capture_errors = []
        if v2:
            from v2_capture_adapter import V2Capture
            cap = V2Capture(self.private / 'v2', transport.config)
            cap.attach(transport)
            captured_event = transport.on_event
            def safe_capture_event(row):
                try:
                    captured_event(row)
                except Exception as error:
                    capture_errors.append(type(error).__name__)
                    self.record('v2_capture_callback_failed', error_class=type(error).__name__)
            transport.on_event = safe_capture_event

        async def start():
            try:
                result = await original_start()
            except BaseException as error:
                if cap:
                    transport.on_event = event
                    try:
                        cap.finish('failed', type(error).__name__)
                    except Exception:
                        cap.cast.close()
                raise
            self.connected = True
            if cap:
                capture_status, capture_error = 'completed', None
                try:
                    candidates = await transport._discover_candidates('database', transport.config['skills']['database'])
                    primary = transport.config['initial_participant_aics']['database']
                    backup = [aic for aic in transport.config['trusted_participant_aics']['database'] if aic != primary]
                    selected = [row for row in candidates if row.get('aic') in backup]
                    if len(selected) != 1:
                        raise ValueError('One exact trusted backup candidate required')
                    description = await transport._describe(selected[0])
                    cap.record_description('A04', description)
                    self.persist('v2-evidence.json', {'descriptions': transport.descriptions, 'backup': description,
                        'discovery': cap.discovery, 'captured_at_utc': now()})
                except Exception as error:
                    capture_status, capture_error = 'failed', type(error).__name__
                    self.record('v2_additional_capture_failed', error_class=capture_error)
                finally:
                    transport.on_event = event
                    if capture_errors:
                        capture_status, capture_error = 'failed', 'CaptureCallbackError'
                        self.persist('v2-callback-errors.json', capture_errors)
                    try:
                        cap.finish(capture_status, capture_error)
                    except Exception as error:
                        self.record('v2_capture_finish_failed', error_class=type(error).__name__)
                        cap.cast.close()
            return result

        async def call(payload):
            if not (self.case and self.case.startswith('e1')):
                return await original_call(payload)
            if self.state is None:
                self.state = {'id': payload['incident_id'], 'symptom': '主库中断后的可信接管 · 同次真实调用',
                    'status': 'running', 'tasks': [], 'facts': [], 'events': [], 'approvals': [], 'plan': [],
                    'hypotheses': [], 'result': None, 'model_source': 'rules', 'model_calls': 0, 'tokens': 0,
                    'capture_projection': 'transport payload/product; not IncidentCoordinator planning state'}
            row = {'logical_task_id': payload['logical_task_id'], 'tool': payload['tool'], 'kind': payload['kind'],
                'args': deepcopy(payload.get('args', {})), 'status': 'pending', 'started_at': now()}
            self.state['tasks'].append(row)
            started = time.monotonic()
            try:
                product = await original_call(payload)
                row.update(status=product.get('status'), product=deepcopy(product), elapsed_ms=round((time.monotonic()-started)*1000, 3))
                self.state['facts'].extend(deepcopy(product.get('facts', [])))
                if payload['kind'] == 'verify':
                    self.state['result'] = {fact['key']: fact['value'] for fact in product.get('facts', [])}
                return product
            except BaseException as error:
                row.update(status='failed', error=type(error).__name__)
                raise

        async def close():
            try:
                return await original_close()
            finally:
                self.connected = False
        transport.start, transport.call, transport.close = start, call, close
        return transport

    def complete_case(self, result):
        self.case_result, self.phase = result, 'case_finished'
        if self.state and self.case.startswith('e1'):
            self.state['status'] = 'completed' if result.get('task_phase_status') == 'completed' else 'needs_attention'
        self.record('capture_case_finished', case=self.case, status=result.get('status'))
        self.persist(self.case + '-snapshot.json', self.snapshot())

    async def stop(self):
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
