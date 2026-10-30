"""Independent loopback AIP protocol stress tests; never modifies vendor code.

The official in-memory SDK supplies protocol semantics. Session-owner isolation is
an additional product property, explicitly NOT claimed to be an AIP spec MUST.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
import traceback
import uuid

import httpx
from acps_sdk.aip import AipRpcClient
from run_pilot import Lab, ROOT, SDK_COMMIT


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def command(action, task_id, session='protocol-session', payload=None, **overrides):
    body = {
        'jsonrpc': '2.0', 'method': 'rpc', 'id': 'rpc-' + uuid.uuid4().hex,
        'params': {'command': {
            'type': 'task-command', 'id': 'cmd-' + uuid.uuid4().hex,
            'sentAt': datetime.now(timezone.utc).isoformat(),
            'senderRole': 'leader', 'senderId': 'LOCAL.PROTOCOL.LEADER',
            'sessionId': session, 'command': action, 'taskId': task_id,
        }},
    }
    if payload is not None:
        body['params']['command']['dataItems'] = [{'type': 'text', 'text': json.dumps(payload)}]
    body['params']['command'].update(overrides)
    return body


def result(response):
    body = response.get('json')
    return body.get('result') if isinstance(body, dict) else None


def state(response):
    task = result(response)
    return task.get('status', {}).get('state') if isinstance(task, dict) else None


def rpc_result_history(response):
    task=result(response)
    return (task.get('statusHistory') or []) if isinstance(task,dict) else []


def controlled_error(response):
    body = response.get('json')
    return response.get('status') == 200 and isinstance(body, dict) and isinstance(body.get('error'), dict)


class Suite:
    def __init__(self, output):
        self.output = output
        self.lab = Lab(output)
        self.records = []
        self.checks = []
        self.client = None
        self.category = 'setup'
        self.case = 'setup'

    def record(self, value):
        value = {'number': len(self.records) + 1, 'category': self.category, 'case': self.case, **value}
        self.records.append(value)
        with (self.output / 'raw_requests_responses.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')
        return value

    async def request(self, url, body=None, text=None, method='POST'):
        assert url.startswith('http://127.0.0.1:'), 'Only this disposable loopback lab is allowed'
        started = time.perf_counter()
        request_started_at = datetime.now(timezone.utc).isoformat()
        request_text = text if text is not None else json.dumps(body, ensure_ascii=False)
        try:
            response = await self.client.request(method, url, content=request_text if method == 'POST' else None,
                                                  headers={'Content-Type': 'application/json'})
            try:
                parsed = response.json()
            except ValueError:
                parsed = None
            return self.record({'method': method, 'url': url, 'request': request_text,
                                'request_started_at': request_started_at,
                                'response_received_at': datetime.now(timezone.utc).isoformat(),
                                'status': response.status_code, 'response': response.text, 'json': parsed,
                                'seconds': round(time.perf_counter() - started, 6)})
        except Exception as exc:
            return self.record({'method': method, 'url': url, 'request': request_text, 'status': None,
                                'request_started_at': request_started_at,
                                'response_received_at': datetime.now(timezone.utc).isoformat(),
                                'response': None, 'json': None,
                                'transport_error': f'{type(exc).__name__}: {exc}',
                                'seconds': round(time.perf_counter() - started, 6)})

    async def raw(self, body=None, text=None, role='database'):
        return await self.request(self.lab.records[role]['endpoint'], body=body, text=text)

    def check(self, label, passed, references, expected, contract='official_sdk_and_spec'):
        check = {'category': self.category, 'case': self.case, 'label': label,
                 'passed': bool(passed), 'contract': contract, 'expected': expected,
                 'request_numbers': [r['number'] for r in references]}
        self.checks.append(check)
        if not passed:
            filename = f'failure-{len([c for c in self.checks if not c["passed"]]):03d}.json'
            dump(self.output / filename, {'check': check, 'reproduction': references})
        return bool(passed)

    async def sdk_lifecycle(self, n):
        self.category = 'sdk_idempotency_and_terminal_states'
        client = AipRpcClient(self.lab.records['database']['endpoint'], 'LOCAL.PROTOCOL.LEADER',
                              identity_binding_enabled=False)
        await client.http_client.aclose()
        async def response_hook(response):
            await response.aread()
            self.record({'method': response.request.method, 'url': str(response.url),
                         'request': response.request.content.decode(), 'status': response.status_code,
                         'response': response.text, 'json': response.json(), 'via': 'official_AipRpcClient'})
        client.http_client = httpx.AsyncClient(trust_env=False, timeout=10,
                                              event_hooks={'response': [response_hook]})
        try:
            for i in range(n):
                self.case = f'sdk-lifecycle-{i}'
                start_idx = len(self.records)
                task_id = f'sdk-{i}-' + uuid.uuid4().hex
                session = 'sdk-' + str(i)
                a = await client.start_task(session_id=session, task_id=task_id,
                                            user_input='{"action":"inspect"}')
                b = await client.start_task(session_id=session, task_id=task_id,
                                            user_input='{"action":"unsupported-action"}')
                c = await client.get_task(task_id=task_id, session_id=session)
                d = await client.complete_task(task_id=task_id, session_id=session)
                e = await client.complete_task(task_id=task_id, session_id=session)
                f = await client.cancel_task(task_id=task_id, session_id=session)
                g = await client.continue_task(task_id=task_id, session_id=session, user_input='retry')
                h = await client.start_task(session_id=session, task_id=task_id,
                                            user_input='{"action":"inspect"}')
                refs = self.records[start_idx:]
                self.check('duplicate_start_returns_existing_result', a.id == b.id == c.id and
                           str(b.status.state.value) == 'awaiting-completion' and a.products == b.products,
                           refs[:3], 'Duplicate Start ignores different payload and returns the original task/products')
                self.check('completed_is_terminal', all(x.status.state.value == 'completed' for x in [d,e,f,g,h])
                           and len(d.statusHistory) == len(h.statusHistory), refs[3:],
                           'Repeated Complete, Cancel, Continue and Start never leave Completed')
                self.check('response_identity_and_correlation', all(
                    x.senderId == self.lab.records['database']['id'] and x.taskId == task_id and
                    x.sessionId == session for x in [a,b,c,d,e,f,g,h]), refs,
                    'Every response preserves senderId/taskId/sessionId (declared identity only; no mTLS)')
        finally:
            await client.close()

    async def raw_lifecycle(self, n):
        self.category = 'cancel_continue_failed_terminal'
        for i in range(n):
            self.case = f'raw-terminal-{i}'
            task_id = 'terminal-' + uuid.uuid4().hex
            a = await self.raw(command('start', task_id, payload={'action':'inspect'}))
            b = await self.raw(command('continue', task_id, payload={'action':'inspect'}))
            c = await self.raw(command('cancel', task_id))
            d = await self.raw(command('cancel', task_id))
            e = await self.raw(command('complete', task_id))
            f = await self.raw(command('continue', task_id, payload={'action':'inspect'}))
            g = await self.raw(command('start', task_id, payload={'action':'inspect'}))
            self.check('default_continue_is_business_noop', state(a) == state(b) == 'awaiting-completion',
                       [a,b], 'SDK default Continue records input but requires an agent handler for new work')
            self.check('canceled_is_terminal', all(state(x) == 'canceled' for x in [c,d,e,f,g]),
                       [a,b,c,d,e,f,g], 'Cancel enters Canceled and all following commands preserve it')
            failed_id = 'failed-' + uuid.uuid4().hex
            refs = [await self.raw(command('start', failed_id, payload={'action':'unsupported-action'}))]
            for action in ['complete','cancel','continue','start','get']:
                refs.append(await self.raw(command(action, failed_id, payload={'action':'inspect'})))
            self.check('unsupported_action_is_controlled_failed', all(state(x) == 'failed' for x in refs)
                       and all(x['status'] == 200 for x in refs), refs,
                       'Unsupported business actions return a Failed task; terminal state remains Failed')

    async def missing_tasks(self, n):
        self.category = 'unknown_and_missing_task_ids'
        for i in range(n):
            self.case = f'missing-task-{i}'
            for action in ['get','complete','cancel','continue']:
                missing = await self.raw(command(action, 'not-created-' + uuid.uuid4().hex))
                self.check('unknown_task_' + action, controlled_error(missing) and
                           missing['json']['error']['code'] == -32001, [missing], 'Unknown task returns -32001')
                noid = command(action, None)
                noid['params']['command'].pop('taskId')
                response = await self.raw(noid)
                self.check('missing_id_' + action, controlled_error(response) and
                           response['json']['error']['code'] == -32602, [response],
                           'Non-Start without taskId returns -32602; never HTTP 500')

    async def malformed(self, n):
        self.category = 'malformed_envelope_and_start_payload'
        specimens = []
        for text in ['{', '', '[1,2,3]', 'null', '"hello"']:
            specimens.append(('malformed_json_or_envelope', text, 'structured_error'))
        for body in [{}, {'method':'rpc'}, {'jsonrpc':'1.0','method':'rpc','params':{}},
                     {'jsonrpc':'2.0','method':'unsupported','id':1,'params':{'command':{}}}]:
            specimens.append(('missing_or_invalid_envelope_fields', json.dumps(body), 'structured_error'))
        for action in ['start','unsupported-action']:
            body = command(action, 'bad-' + uuid.uuid4().hex)
            if action == 'start':
                body['params']['command'].pop('senderId')
            specimens.append(('missing_sender_or_invalid_command', json.dumps(body), 'structured_error'))
        for variant in ['missing_task_id','no_data_items','invalid_payload_json','missing_action','null_payload']:
            body = command('start', 'payload-' + uuid.uuid4().hex, payload={'action':'inspect'})
            if variant == 'missing_task_id':
                body['params']['command'].pop('taskId')
            elif variant == 'no_data_items':
                body['params']['command'].pop('dataItems')
            elif variant == 'invalid_payload_json':
                body['params']['command']['dataItems'][0]['text'] = '{'
            elif variant == 'missing_action':
                body['params']['command']['dataItems'][0]['text'] = '{}'
            else:
                body['params']['command']['dataItems'][0]['text'] = 'null'
            specimens.append((variant,json.dumps(body),'graceful_failure_or_error'))
        for i in range(n):
            for name, body, expectation in specimens:
                self.case = f'{name}-{i}'
                # Every repetition uses a fresh task/message ID so bad input is not hidden by idempotency.
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed,dict) and isinstance(parsed.get('params'),dict) and isinstance(parsed['params'].get('command'),dict):
                        cmd = parsed['params']['command']
                        if 'taskId' in cmd:
                            cmd['taskId'] = 'malformed-' + uuid.uuid4().hex
                        cmd['id'] = 'cmd-' + uuid.uuid4().hex
                        body = json.dumps(parsed)
                except ValueError:
                    pass
                response = await self.raw(text=body)
                acceptable = controlled_error(response)
                if expectation == 'graceful_failure_or_error':
                    acceptable = acceptable or (response['status'] == 200 and state(response) in {'failed','rejected'})
                    if name == 'missing_task_id':
                        acceptable = acceptable or (response['status'] == 200 and bool(result(response)) and
                                                     bool(result(response).get('taskId')))
                self.check(name, acceptable, [response],
                           'Malformed request must return a structured protocol error or controlled Failed/Rejected task; '
                           'Start without ID may generate an ID; HTTP 500 is a failure',
                           'input_robustness_product_contract')
                if name in {'no_data_items','invalid_payload_json','missing_action','null_payload'}:
                    history=[status.get('state') for status in rpc_result_history(response)]
                    self.check('invalid_start_is_initially_rejected',state(response)=='rejected' and history==['rejected'],
                               [response],'Malformed business Start is created directly in Rejected; the specification '
                               'explicitly forbids Accepted then Rejected','official_sdk_and_spec')

    async def concurrent_duplicates(self, n):
        self.category = 'concurrent_same_task_id'
        for i in range(n):
            self.case = f'concurrent-duplicate-start-{i}'
            before = await self.request(self.lab.database + '/admin/status', method='GET')
            reset = await self.request(self.lab.database + '/admin/reset', body={'available':False})
            revision = reset['json']['revision']
            task_id = 'concurrent-' + uuid.uuid4().hex
            starts = await asyncio.gather(*[self.raw(command('start', task_id,
                          payload={'action':'resume','expected_revision':revision})) for _ in range(12)])
            final = await self.raw(command('get', task_id))
            completed = await self.raw(command('complete', task_id))
            after = await self.request(self.lab.database + '/admin/status', method='GET')
            ids = {result(r).get('id') for r in starts if result(r)}
            self.check('concurrent_start_is_single_task_and_single_mutation',
                       all(r['status']==200 and result(r) for r in starts) and len(ids)==1 and
                       state(final)=='awaiting-completion' and state(completed)=='completed' and
                       after['json']['mutations']==1 and after['json']['revision']==revision+1,
                       [before,reset,*starts,final,completed,after],
                       '12 concurrent identical Starts create one task and exactly one database resume mutation')

    async def cancellation_races(self, n):
        self.category = 'cancel_during_work'
        for i in range(n):
            self.case = f'cancel-working-start-{i}'
            task_id = 'race-' + uuid.uuid4().hex
            start = asyncio.create_task(self.raw(command('start', task_id, payload={'action':'inspect'}),role='application'))
            probes = []
            working = False
            for _ in range(30):
                probe = await self.raw(command('get', task_id),role='application')
                probes.append(probe)
                if state(probe)=='working':
                    working = True
                    break
                if start.done():
                    break
                await asyncio.sleep(0.002)
            cancel = await self.raw(command('cancel', task_id),role='application')
            start_result = await start
            final = await self.raw(command('get', task_id),role='application')
            self.check('canceled_cannot_be_overwritten_by_inflight_start',
                       working and state(cancel)=='canceled' and state(final)=='canceled',
                       [*probes,cancel,start_result,final],
                       'After observing Working and a Canceled response, the in-flight handler must never leave Canceled')

    async def session_collisions(self, n):
        self.category = 'cross_session_task_id_collision'
        for i in range(n):
            self.case = f'cross-session-{i}'
            task_id = 'session-collision-' + uuid.uuid4().hex
            owner = await self.raw(command('start',task_id,session='session-A',payload={'action':'inspect'}))
            read = await self.raw(command('get',task_id,session='session-B'))
            cancel = await self.raw(command('cancel',task_id,session='session-B'))
            after = await self.raw(command('get',task_id,session='session-A'))
            self.check('conflicting_session_read_rejected', controlled_error(read), [owner,read],
                       'Product isolation: a conflicting session must not silently read another session task. '
                       'AIP requires globally unique taskId; this is extra defensive validation, not an explicit spec MUST.',
                       'additional_product_session_isolation')
            self.check('conflicting_session_cannot_cancel_owner_task',
                       controlled_error(cancel) and state(after)==state(owner), [owner,cancel,after],
                       'Product isolation: reject session mismatch and preserve owner state. Identity binding is disabled '
                       'for this local pilot; no production authentication claim is made.',
                       'additional_product_session_isolation')

    async def canceled_business_exception(self, n):
        """A real local HTTP peer drops a held request only after Cancel succeeds.

        This deterministic transport fault exercises the handler's exception path,
        while avoiding timing-dependent process termination or any external host.
        """
        self.category='cancel_before_business_transport_exception'
        original_target=self.lab.target
        fault_port=self.lab.port()
        context={}

        async def drop_request(reader,writer):
            local=dict(context)
            try:
                request=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),timeout=5)
                self.lab.event('fault_target_http_received',request=request.decode('ascii',errors='replace'),
                               endpoint=f'http://127.0.0.1:{fault_port}',test_case=local['case'])
                local['received'].set()
                await asyncio.wait_for(local['release'].wait(),timeout=5)
                # A real HTTP connection closes without a response after task cancellation.
                self.lab.event('fault_target_closed_without_http_response',test_case=local['case'])
            finally:
                writer.close()
                await writer.wait_closed()
                local['closed'].set()

        server=await asyncio.start_server(drop_request,'127.0.0.1',fault_port)
        self.lab.event('owned_fault_server_started',endpoint=f'http://127.0.0.1:{fault_port}')
        self.lab.target=f'http://127.0.0.1:{fault_port}'
        try:
            endpoint,_=await self.lab.launch('application-agent','LOCAL.PROTOCOL.TRANSPORT.EXCEPTION')
            self.lab.target=original_target
            for i in range(n):
                self.case=f'cancel-then-http-disconnect-{i}'
                self.lab.case_id=self.case
                context.clear()
                context.update(case=self.case,received=asyncio.Event(),release=asyncio.Event(),closed=asyncio.Event())
                task_id='cancel-exception-'+uuid.uuid4().hex
                start=asyncio.create_task(self.request(endpoint+'/rpc',body=command('start',task_id,payload={'action':'inspect'})))
                try:
                    await asyncio.wait_for(context['received'].wait(),timeout=5)
                    working=await self.request(endpoint+'/rpc',body=command('get',task_id))
                    cancel=await self.request(endpoint+'/rpc',body=command('cancel',task_id))
                    context['release'].set()
                    await asyncio.wait_for(context['closed'].wait(),timeout=5)
                    start_result=await asyncio.wait_for(start,timeout=5)
                    final=await self.request(endpoint+'/rpc',body=command('get',task_id))
                    self.check('canceled_survives_actual_business_http_exception',
                               state(working)=='working' and state(cancel)=='canceled' and
                               state(start_result)=='canceled' and state(final)=='canceled' and
                               [x.get('state') for x in rpc_result_history(final)]==['accepted','working','canceled'],
                               [working,cancel,start_result,final],
                               'A held real HTTP request is disconnected only after Cancel; the business exception '
                               'must preserve Canceled and never append Failed or AwaitingCompletion')
                finally:
                    context['release'].set()
                    if not start.done():
                        await asyncio.wait_for(start,timeout=5)
        finally:
            self.lab.target=original_target
            server.close()
            await server.wait_closed()
            self.lab.event('owned_fault_server_closed',endpoint=f'http://127.0.0.1:{fault_port}')

    async def sender_collisions(self, n):
        self.category='different_declared_sender_same_session'
        for i in range(n):
            self.case=f'different-declared-sender-{i}'
            task_id='sender-collision-'+uuid.uuid4().hex
            owner=await self.raw(command('start',task_id,session='same-session',payload={'action':'inspect'}))
            read=await self.raw(command('get',task_id,session='same-session',senderId='LOCAL.OTHER.DECLARED.SENDER'))
            cancel=await self.raw(command('cancel',task_id,session='same-session',senderId='LOCAL.OTHER.DECLARED.SENDER'))
            after=await self.raw(command('get',task_id,session='same-session'))
            self.check('conflicting_declared_sender_read_rejected',controlled_error(read),[owner,read],
                       'A different declared sender in the same session is rejected by the local consistency guard; '
                       'this is not authenticated identity or mTLS verification','additional_product_declared_sender_consistency')
            self.check('conflicting_declared_sender_cannot_cancel_owner_task',
                       controlled_error(cancel) and state(after)==state(owner),[owner,cancel,after],
                       'A different declared sender cannot change the owner task state; declaration consistency is '
                       'not proof of who the caller actually is','additional_product_declared_sender_consistency')

    async def run(self, iterations):
        fatal = None
        before = time.perf_counter()
        try:
            await self.lab.setup()
            self.client = httpx.AsyncClient(trust_env=False, timeout=15,
                                           limits=httpx.Limits(max_connections=30,max_keepalive_connections=20))
            for name, fn, n in [
                ('sdk_lifecycle',self.sdk_lifecycle,iterations),
                ('raw_lifecycle',self.raw_lifecycle,iterations),
                ('missing_tasks',self.missing_tasks,max(2,iterations//2)),
                ('malformed',self.malformed,max(2,iterations//2)),
                ('concurrent_duplicates',self.concurrent_duplicates,max(3,iterations//2)),
                ('cancellation_races',self.cancellation_races,iterations),
                ('session_collisions',self.session_collisions,max(3,iterations//2)),
                ('sender_collisions',self.sender_collisions,max(3,iterations//2)),
                ('canceled_business_exception',self.canceled_business_exception,max(3,iterations//2)),
            ]:
                await fn(n)
                print(json.dumps({'finished':name,'requests':len(self.records),'checks':len(self.checks),
                                  'failed':sum(not x['passed'] for x in self.checks)},ensure_ascii=False),flush=True)
        except Exception as exc:
            fatal = {'error':f'{type(exc).__name__}: {exc}','traceback':traceback.format_exc()}
        finally:
            if self.client:
                await self.client.aclose()
            self.lab.close()
        categories = defaultdict(lambda:{'requests':0,'checks':0,'passed':0,'failed':0})
        for record in self.records:
            categories[record['category']]['requests'] += 1
        for check in self.checks:
            categories[check['category']]['checks'] += 1
            categories[check['category']]['passed' if check['passed'] else 'failed'] += 1
        status_counts = Counter(str(x['status']) for x in self.records)
        summary = {
            'suite':'protocol_stress','time_zone':'UTC+08:00','sdk_commit':SDK_COMMIT,
            'started_directory':str(self.output),'requests':len(self.records),'checks':len(self.checks),
            'passed':sum(x['passed'] for x in self.checks),'failed':sum(not x['passed'] for x in self.checks),
            'http_status_counts':dict(status_counts),'categories':dict(categories),
            'seconds':round(time.perf_counter()-before,3),'fatal':fatal,
            'processes':[{'pid':p.pid,'exit_code':p.poll()} for p in self.lab.processes],
            'all_child_processes_exited':all(p.poll() is not None for p in self.lab.processes),
            'scope':'Actual loopback HTTP to independent service processes using official SDK and raw HTTP. '
                    'No paid API, Wutong, formal certificate, production authentication, LLM reasoning or multi-host result.',
            'pass_gate':fatal is None and len(self.records)>=150 and all(x['passed'] for x in self.checks),
        }
        dump(self.output/'results.json',{'summary':summary,'checks':self.checks})
        dump(self.output/'summary.json',summary)
        failures=[c for c in self.checks if not c['passed']]
        counts=Counter(c['label'] for c in failures)
        report=['# Protocol stress test report','',
                f'Output: {self.output}',f'Actual recorded requests: {len(self.records)}',
                f'Checks: {len(self.checks)}; passed: {summary["passed"]}; failed: {summary["failed"]}',
                f'HTTP status counts: {dict(status_counts)}',f'All owned child processes exited: {summary["all_child_processes_exited"]}',
                '', '## Failures retained','']
        for label,count in counts.items():
            report.append(f'- {label}: {count}; see failure-*.json and raw_requests_responses.jsonl.')
        report += ['', '## Interpretation and repair recommendations','',
            '- HTTP 500 for missing Start taskId, missing dataItems or malformed JSON text is an input handling bug. '
              'Validate before dispatch, create a controlled Failed/Rejected task or structured error, and never attempt '
              'TaskManager.update_task_status for a task that was not created. Generate an ID or reject missing Start taskId explicitly.',
            '- If Cancel while Working is later overwritten, the awaited start handler needs a terminal-state guard '
              'after each await and immediately before publishing products/state. Do not mutate Canceled/Failed/Completed.',
            '- Cross-session collision checks are an additional product isolation property. The AIP specification '
              'requires task IDs to be globally unique; it does not by itself establish this test as an explicit normative '
              'session-authorization requirement. For a usable recovery service, bind the task to session and authenticated '
              'leader identity, reject mismatches, and enable formal identity binding before external deployment.',
            '- Passing duplicate Start tests demonstrates one-task/one-effect behavior only for tested in-memory cases. '
              'Process restart, persistent deduplication, mTLS, Wutong interconnection and LLM diagnosis remain outside this suite.',
            '', '## Reproduce','',f'`{sys.executable} protocol_stress.py --iterations {iterations}`',
            '', 'Original source snapshots and SHA-256 hashes are in source_snapshot/ and source_manifest.json.',
            'Each failure JSON contains its expected contract and exact minimal sequence of request/response records.']
        if fatal:
            report += ['', '## Harness fatal error','',fatal['traceback']]
        (self.output/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        return 0 if summary['pass_gate'] else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--iterations',type=int,default=8)
    parser.add_argument('--label',default='',help='Optional descriptive run label; never overwrites an earlier run')
    args=parser.parse_args()
    if args.iterations<4:
        parser.error('At least 4 iterations are required for meaningful repetition')
    if args.label and not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',args.label):
        parser.error('Label must contain 1-32 ASCII letters, digits, underscores or hyphens')
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    prefix='protocol-' + (args.label+'-' if args.label else '')
    output=ROOT/'artifacts'/f'{prefix}{stamp}-{uuid.uuid4().hex[:6]}'
    output.mkdir(parents=True)
    snapshot=output/'source_snapshot'
    snapshot.mkdir()
    manifest={}
    for name in ['protocol_stress.py','services.py','run_pilot.py','requirements-lock.txt']:
        source=ROOT/name
        shutil.copy2(source,snapshot/name)
        manifest[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ['aip_rpc_server.py','aip_rpc_client.py','aip_rpc_model.py','aip_base_model.py']:
        source=ROOT/'vendor'/'ACPs-community'/'acps-sdk'/'acps_sdk'/'aip'/name
        shutil.copy2(source,snapshot/name)
        manifest['vendor/'+name]=hashlib.sha256(source.read_bytes()).hexdigest()
    dump(output/'source_manifest.json',manifest)
    print('OUTPUT='+str(output),flush=True)
    return asyncio.run(Suite(output).run(args.iterations))


if __name__=='__main__':
    raise SystemExit(main())
