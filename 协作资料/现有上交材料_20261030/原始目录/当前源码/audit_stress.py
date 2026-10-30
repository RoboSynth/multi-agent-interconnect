"""Independent read-only audit of protocol, consistency and resilience artifacts.

Exit 0: no verified contradiction, product failure or critical unverified item.
Exit 1: verified mismatch, failed product assertion, open owned port or live PID.
Exit 2: required evidence is missing, unreadable or not independently verifiable.
No suite input file is written. AUDIT.json is only created in a separate output.
"""
import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import ctypes
from datetime import datetime, timezone, timedelta
import errno
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from urllib.parse import urlsplit


STATES = {'accepted','working','awaiting-input','awaiting-completion','completed','failed','rejected','canceled'}
TRANSITIONS = {
    'accepted': {'working','canceled'},
    'working': {'awaiting-input','awaiting-completion','failed','canceled'},
    'awaiting-input': {'working','canceled'},
    'awaiting-completion': {'completed','working','canceled'},
    'completed': set(), 'failed': set(), 'rejected': set(), 'canceled': set(),
}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_state(body):
    task = body.get('result') if isinstance(body,dict) else None
    return task.get('status',{}).get('state') if isinstance(task,dict) else None


def rpc_result(row):
    body=row.get('json')
    return (body.get('result') or {}) if isinstance(body,dict) else {}


def rpc_error(row, code=None):
    body=row.get('json')
    error=body.get('error') if isinstance(body,dict) else None
    return row.get('status')==200 and isinstance(error,dict) and (code is None or error.get('code')==code)


class Audit:
    def __init__(self):
        self.checks = []
        self.details = {}

    def check(self, suite, label, actual, expected=True, *, evidence=None, critical=True):
        passed = actual == expected
        self.checks.append({'suite':suite,'label':label,'status':'verified' if passed else 'failed',
                            'actual':actual,'expected':expected,'critical':critical,'evidence':evidence})
        return passed

    def unverified(self, suite, label, reason, *, critical=True, evidence=None):
        self.checks.append({'suite':suite,'label':label,'status':'unverified','critical':critical,
                            'reason':reason,'evidence':evidence})

    def sources(self, name, directory, summary, manifest):
        if name=='protocol':
            hashes=read_json(directory/'source_manifest.json')
            sources={key:directory/'source_snapshot'/Path(key).name for key in hashes}
        elif name=='consistency':
            hashes=summary.get('source_hashes',{})
            sources={key:directory/key for key in hashes}
        else:
            hashes=manifest.get('source_sha256',{})
            sources={key:directory/'source-snapshot'/key for key in hashes}
        self.check(name,'nonempty_source_manifest',bool(hashes))
        actual={}
        for key, expected in hashes.items():
            path=sources[key]
            if not path.exists():
                self.unverified(name,'source_snapshot:'+key,'Snapshot file is missing',evidence=str(path))
                continue
            actual[key]=digest(path)
            self.check(name,'source_sha256:'+key,actual[key],expected,evidence=str(path))
        self.details[name]['source_sha256']=actual

    def lifecycle(self, name, events, summary):
        starts=[e for e in events if e.get('kind')=='process_started']
        self.check(name,'nonempty_owned_process_evidence',bool(starts))
        if name=='protocol':
            declaration=summary.get('all_child_processes_exited')
            processes=summary.get('processes',[])
            self.check(name,'reported_exit_code_for_every_process',bool(processes) and
                       all(p.get('exit_code') is not None for p in processes))
            self.check(name,'process_pid_list_matches_start_events',
                       sorted(p['pid'] for p in processes),sorted(e['pid'] for e in starts))
        else:
            declaration=summary.get('processes_stopped')
        self.check(name,'suite_declares_owned_processes_stopped',declaration)
        pids=sorted({e['pid'] for e in starts if isinstance(e.get('pid'),int)})
        pid_results=[]
        for pid in pids:
            original_ready_at=next((e.get('at') for e in starts if e.get('pid')==pid),None)
            stopped,reason=self.pid_stopped(pid,original_ready_at)
            pid_results.append({'pid':pid,'stopped_now':stopped,'reason':reason})
            if stopped is None:
                self.unverified(name,'current_pid_stopped:'+str(pid),reason)
            else:
                self.check(name,'current_pid_stopped:'+str(pid),stopped,
                           evidence=reason)
        port_events=starts+[e for e in events if e.get('kind')=='owned_fault_server_started']
        ports=sorted({urlsplit(e['endpoint']).port for e in port_events if e.get('endpoint')})
        port_results=[]
        with ThreadPoolExecutor(max_workers=max(1,min(12,len(ports)))) as pool:
            observations=list(pool.map(self.probe_port,ports))
        for observation in observations:
            port,source_port,code=observation
            if code is None:
                self.unverified(name,'owned_port_closed:'+str(port),'Ephemeral source port unexpectedly equals destination; probe deliberately skipped')
                continue
            closed=code in {errno.ECONNREFUSED,10061}
            row={'host':'127.0.0.1','source_port':source_port,'destination_port':port,'connect_ex':code,'closed_now':closed}
            port_results.append(row)
            if code==0:
                self.check(name,'owned_port_closed:'+str(port),False,evidence=row)
            elif closed:
                self.check(name,'owned_port_closed:'+str(port),True,evidence=row)
            else:
                self.unverified(name,'owned_port_closed:'+str(port),'Connection did not succeed but refusal was not observed',evidence=row)
        self.details[name]['process_checks']=pid_results
        self.details[name]['port_checks']=port_results

    @staticmethod
    def probe_port(port):
        with socket.socket() as probe:
            probe.settimeout(3)
            probe.bind(('127.0.0.1',0))
            source=probe.getsockname()[1]
            if source==port:
                return port,source,None
            return port,source,probe.connect_ex(('127.0.0.1',port))

    @staticmethod
    def pid_stopped(pid, original_ready_at=None):
        if os.name=='nt':
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
            kernel.OpenProcess.restype=ctypes.c_void_p
            kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
            kernel.GetExitCodeProcess.restype=ctypes.c_int
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            kernel.GetProcessTimes.argtypes=[ctypes.c_void_p,*([ctypes.POINTER(ctypes.c_uint64)]*4)]
            kernel.GetProcessTimes.restype=ctypes.c_int
            kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
            kernel.QueryFullProcessImageNameW.restype=ctypes.c_int
            handle=kernel.OpenProcess(0x1000,False,pid)
            if not handle:
                error=ctypes.get_last_error()
                return (True,'PID no longer exists') if error==87 else (None,f'OpenProcess error {error}')
            try:
                code=ctypes.c_uint32()
                if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):
                    return None,f'GetExitCodeProcess error {ctypes.get_last_error()}'
                reason={'audit_pid':os.getpid(),'observed_pid':pid,'current_exit_code':code.value,
                        'original_service_ready_at':original_ready_at}
                creation,exit_time,kernel_time,user_time=[ctypes.c_uint64() for _ in range(4)]
                created_at=None
                if kernel.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit_time),ctypes.byref(kernel_time),ctypes.byref(user_time)):
                    created_at=datetime.fromtimestamp((creation.value-116444736000000000)/10000000,timezone.utc)
                    reason['current_creation_utc']=created_at.isoformat()
                else:
                    reason['creation_time_error']=ctypes.get_last_error()
                length=ctypes.c_uint32(32768)
                image=ctypes.create_unicode_buffer(length.value)
                if kernel.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(length)):
                    reason['current_image_path']=image.value
                else:
                    reason['image_path_error']=ctypes.get_last_error()
                if code.value!=259:
                    return True,reason
                if created_at is not None and original_ready_at:
                    ready=datetime.fromisoformat(original_ready_at)
                    if created_at>ready:
                        reason['pid_reuse_proven']=True
                        reason['explanation']='Current process was created after the original service was already ready; it cannot be the original owned process.'
                        return True,reason
                    reason['pid_reuse_proven']=False
                    return False,reason
                reason['explanation']='PID is active but its lifetime cannot be compared with the original process event.'
                return None,reason
            finally:
                kernel.CloseHandle(handle)
        try:
            os.kill(pid,0)
            return False,'PID is currently active (or reused)'
        except ProcessLookupError:
            return True,'PID no longer exists'
        except PermissionError:
            return None,'Permission denied while checking PID'

    def pair_aip(self, name, events=None, raw=None):
        pairs=[]
        if raw is not None:
            for row in raw:
                if urlsplit(row.get('url','')).path!='/rpc':
                    continue
                try:
                    request=json.loads(row['request'])
                except (ValueError,TypeError):
                    continue
                if not isinstance(request,dict) or not isinstance(request.get('params'),dict):
                    continue
                if not isinstance(request['params'].get('command'),dict):
                    continue
                pairs.append({'case':row.get('case'),'endpoint':row.get('url'),'request':request,
                              'response':row.get('json'),'http_status':row.get('status'),'raw_number':row.get('number')})
        else:
            requests=[e for e in events if e.get('kind')=='aip_request']
            responses=[e for e in events if e.get('kind')=='aip_response']
            by_id=defaultdict(list)
            for event in responses:
                by_id[(event.get('endpoint'),event.get('body',{}).get('id'))].append(event)
            seen=Counter()
            transport_budget=Counter()
            for event in events:
                if event.get('kind')=='unreachable_partner':
                    transport_budget[event.get('case')]+=1
                elif event.get('kind')=='leader_blocked' and any(token in event.get('error','') for token in ['ConnectError','ConnectTimeout']):
                    transport_budget[event.get('case')]+=1
            consumed_transport=Counter()
            for request in requests:
                key=(request.get('endpoint'),request.get('body',{}).get('id'))
                matched=by_id.get(key,[])
                seen[key]+=1
                if len(matched)!=1:
                    case=request.get('case')
                    if name=='resilience' and not matched and consumed_transport[case]<transport_budget[case]:
                        consumed_transport[case]+=1
                        pairs.append({'case':case,'endpoint':request.get('endpoint'),'request':request['body'],
                                      'response':None,'http_status':None,'expected_transport_failure':True})
                        self.check(name,'missing_rpc_response_explained_by_transport_failure:'+str(key),True,
                                   evidence='Matching case has an explicit ConnectError/ConnectTimeout or unreachable_partner record')
                        continue
                    self.check(name,'one_response_per_rpc:'+str(key),len(matched),1,evidence=request)
                    continue
                response=matched[0]
                self.check(name,'rpc_request_response_case_match:'+str(key),response.get('case'),request.get('case'))
                pairs.append({'case':request.get('case'),'endpoint':request.get('endpoint'),'request':request['body'],
                              'response':response['body'],'http_status':response.get('http_status')})
            duplicates=[str(key) for key,n in seen.items() if n!=1]
            self.check(name,'unique_rpc_request_ids',duplicates,[])
            orphan=[str(key) for key in by_id if key not in seen]
            self.check(name,'no_orphan_rpc_responses',orphan,[])
            self.details[name]['recorded_aip_requests']=len(requests)
            self.details[name]['recorded_aip_responses']=len(responses)
            if responses and any('http_status' not in event for event in responses):
                self.unverified(name,'exact_numeric_http_status_for_saved_rpc_events',
                                'Saved events contain real request/response JSON and correlation IDs, but omit the numeric HTTP status. '
                                'Task states and request/response linkage are audited; exact transport status codes cannot be independently reconstructed.',
                                critical=False)
        self.check(name,'nonempty_end_to_end_rpc_pairs',bool(pairs))
        states=Counter()
        by_case=defaultdict(list)
        for pair in pairs:
            request=pair['request']
            response=pair['response']
            command=request['params']['command']
            by_case[pair['case']].append(pair)
            if not isinstance(response,dict):
                # Malformed-input rejection is evaluated by the protocol checks separately.
                continue
            task=response.get('result')
            if not isinstance(task,dict):
                continue
            key=str(pair.get('raw_number',request.get('id')))
            self.check(name,'rpc_response_id:'+key,response.get('id'),request.get('id'))
            if command.get('taskId'):
                self.check(name,'rpc_response_task_id:'+key,task.get('taskId'),command['taskId'])
            if command.get('sessionId') is not None:
                self.check(name,'rpc_response_session_id:'+key,task.get('sessionId'),command['sessionId'])
            current=task.get('status',{}).get('state')
            states[current]+=1
            self.check(name,'valid_task_state:'+key,current in STATES)
            history=[x.get('state') for x in task.get('statusHistory') or []]
            invalid=[{'from':a,'to':b} for a,b in zip(history,history[1:]) if b not in TRANSITIONS.get(a,set())]
            self.check(name,'legal_task_status_history:'+key,invalid,[])
            if history:
                self.check(name,'status_matches_history_tail:'+key,current,history[-1])
        self.details[name]['task_state_snapshot_counts']=dict(states)
        self.details[name]['matched_rpc_pairs']=sum(isinstance(pair.get('response'),dict) for pair in pairs)
        self.details[name]['recorded_transport_failures']=sum(pair.get('expected_transport_failure',False) for pair in pairs)
        return by_case

    def protocol(self, directory):
        name='protocol'
        summary=read_json(directory/'summary.json')
        checks=read_json(directory/'results.json')['checks']
        raw=read_lines(directory/'raw_requests_responses.jsonl')
        events=read_lines(directory/'events.jsonl')
        self.details[name]={'directory':str(directory)}
        self.sources(name,directory,summary,{})
        self.check(name,'nonempty_requests_and_assertions',bool(raw) and bool(checks))
        self.check(name,'summary_request_count',summary.get('requests'),len(raw))
        self.check(name,'summary_assertion_count',summary.get('checks'),len(checks))
        self.check(name,'summary_passed_count',summary.get('passed'),sum(c.get('passed') is True for c in checks))
        failed=[c for c in checks if c.get('passed') is not True]
        self.check(name,'summary_failed_count',summary.get('failed'),len(failed))
        self.check(name,'product_assertion_failures',len(failed),0,evidence=failed)
        self.check(name,'no_fatal_error',summary.get('fatal'),None)
        self.check(name,'sequential_raw_record_numbers',[r.get('number') for r in raw],list(range(1,len(raw)+1)))
        self.check(name,'all_actual_requests_loopback',all(urlsplit(r.get('url','')).hostname=='127.0.0.1' for r in raw))
        self.check(name,'http_status_count',summary.get('http_status_counts'),dict(Counter(str(r.get('status')) for r in raw)))
        by_number={r.get('number'):r for r in raw}
        categories=defaultdict(lambda:{'requests':0,'checks':0,'passed':0,'failed':0})
        for row in raw:
            categories[row.get('category')]['requests']+=1
        for check in checks:
            category=categories[check.get('category')]
            category['checks']+=1
            category['passed' if check.get('passed') is True else 'failed']+=1
            refs=check.get('request_numbers',[])
            self.check(name,'assertion_has_real_evidence:'+check['case']+':'+check['label'],bool(refs) and all(n in by_number for n in refs))
            self.check(name,'assertion_references_own_case:'+check['case']+':'+check['label'],
                       all(by_number.get(n,{}).get('case')==check.get('case') for n in refs))
            evidence=[by_number[n] for n in refs if n in by_number]
            observed=self.protocol_assertion(check['label'],evidence,events)
            if observed is None:
                self.unverified(name,'recompute_assertion:'+check['case']+':'+check['label'],'Unknown assertion label or missing prerequisite raw records')
            else:
                self.check(name,'assertion_boolean_recomputed:'+check['case']+':'+check['label'],check.get('passed'),observed)
            if check.get('passed') is True:
                statuses=[by_number[n].get('status') for n in refs if n in by_number]
                self.check(name,'passing_assertion_never_accepts_http500:'+check['case']+':'+check['label'],
                           not any(status is None or status>=500 for status in statuses),evidence=refs)
        self.check(name,'summary_category_counts',summary.get('categories'),dict(categories))
        self.check(name,'every_category_has_requests_and_checks',all(x['requests'] and x['checks'] for x in categories.values()))
        self.pair_aip(name,raw=raw)
        self.lifecycle(name,events,summary)
        self.details[name].update({'requests':len(raw),'assertions':len(checks),'product_failures':len(failed),
                                  'recovery_claims':0,'category_counts':dict(categories)})

    @staticmethod
    def protocol_assertion(label, refs, events):
        if not refs:
            return None
        states=[task_state(row.get('json')) for row in refs]
        if label=='duplicate_start_returns_existing_result':
            tasks=[rpc_result(row) for row in refs]
            return len(tasks)==3 and bool(tasks[0]) and len({t.get('id') for t in tasks})==1 and states[1]=='awaiting-completion' and tasks[0].get('products')==tasks[1].get('products')
        if label=='completed_is_terminal':
            return all(s=='completed' for s in states) and len(rpc_result(refs[0]).get('statusHistory') or [])==len(rpc_result(refs[-1]).get('statusHistory') or [])
        if label=='response_identity_and_correlation':
            identity={e['endpoint']:e['id'] for e in events if e.get('kind')=='local_registration'}
            for row in refs:
                task=rpc_result(row)
                try:
                    command=json.loads(row['request'])['params']['command']
                except (ValueError,KeyError,TypeError):
                    return False
                if not task or task.get('senderId')!=identity.get(row['url']) or task.get('taskId')!=command.get('taskId') or task.get('sessionId')!=command.get('sessionId'):
                    return False
            return True
        if label=='default_continue_is_business_noop':
            return len(states)==2 and all(s=='awaiting-completion' for s in states)
        if label=='canceled_is_terminal':
            return len(states)==7 and all(s=='canceled' for s in states[2:])
        if label=='unsupported_action_is_controlled_failed':
            return all(s=='failed' for s in states) and all(row.get('status')==200 for row in refs)
        if label.startswith('unknown_task_'):
            return rpc_error(refs[0],-32001)
        if label in {'missing_id_get','missing_id_complete','missing_id_cancel','missing_id_continue'}:
            return rpc_error(refs[0],-32602)
        if label=='concurrent_start_is_single_task_and_single_mutation':
            if len(refs)!=17:
                return None
            reset=refs[1].get('json') or {}
            starts=refs[2:14]
            final,completed,after=refs[14:17]
            ids={rpc_result(row).get('id') for row in starts if rpc_result(row)}
            final_status=after.get('json') or {}
            return (all(row.get('status')==200 and bool(rpc_result(row)) for row in starts) and len(ids)==1 and
                    task_state(final.get('json'))=='awaiting-completion' and task_state(completed.get('json'))=='completed' and
                    final_status.get('mutations')==1 and final_status.get('revision')==reset.get('revision',-99)+1)
        if label=='canceled_cannot_be_overwritten_by_inflight_start':
            return len(refs)>=4 and 'working' in states[:-3] and states[-3]=='canceled' and states[-1]=='canceled'
        if label=='invalid_start_is_initially_rejected':
            return states[0]=='rejected' and [x.get('state') for x in rpc_result(refs[0]).get('statusHistory') or []]==['rejected']
        if label=='canceled_survives_actual_business_http_exception':
            case=refs[0].get('case')
            markers={e.get('kind') for e in events if e.get('test_case')==case}
            return (len(states)==4 and states==['working','canceled','canceled','canceled'] and
                    [x.get('state') for x in rpc_result(refs[-1]).get('statusHistory') or []]==['accepted','working','canceled'] and
                    {'fault_target_http_received','fault_target_closed_without_http_response'}<=markers)
        if label in {'conflicting_session_read_rejected','conflicting_declared_sender_read_rejected'}:
            return len(refs)==2 and rpc_error(refs[-1])
        if label in {'conflicting_session_cannot_cancel_owner_task','conflicting_declared_sender_cannot_cancel_owner_task'}:
            return len(refs)==3 and rpc_error(refs[1]) and states[0]==states[-1]
        malformed={'malformed_json_or_envelope','missing_or_invalid_envelope_fields','missing_sender_or_invalid_command',
                   'missing_task_id','no_data_items','invalid_payload_json','missing_action','null_payload'}
        if label in malformed:
            row=refs[0]
            if rpc_error(row):
                return True
            if label in {'missing_task_id','no_data_items','invalid_payload_json','missing_action','null_payload'}:
                return row.get('status')==200 and (states[0] in {'failed','rejected'} or
                       (label=='missing_task_id' and bool(rpc_result(row).get('taskId'))))
            return False
        return None

    def test_http_pairs(self, name, events):
        pending=defaultdict(deque)
        pairs=[]
        errors=[]
        for event in events:
            kind=event.get('kind')
            if kind=='test_http_request':
                pending[(event.get('method'),event.get('url'))].append(event)
            elif kind in {'test_http_response','test_http_error'}:
                key=(event.get('method'),event.get('url'))
                if not pending[key]:
                    errors.append({'reason':'orphan HTTP response','event':event})
                else:
                    request=pending[key].popleft()
                    pairs.append({'request':request,'response':event})
        errors.extend({'reason':'request without response','event':request} for queue in pending.values() for request in queue)
        if not pairs:
            self.unverified(name,'management_http_evidence','No test_http_request/test_http_response events; raw configuration observations are unavailable')
        else:
            self.check(name,'management_http_request_response_pairing',errors,[])
        self.details[name]['management_http_pairs']=len(pairs)
        by_case=defaultdict(list)
        for pair in pairs:
            by_case[pair['request'].get('case')].append(pair)
        return by_case

    def final_sqlite_hash(self, name, directory, expected):
        path=directory/'orders.sqlite'
        if not path.exists() or not expected:
            self.unverified(name,'actual_final_sqlite_hash','Frozen database or expected content hash is unavailable')
            return
        connection=sqlite3.connect('file:'+path.as_posix()+'?mode=ro&immutable=1',uri=True)
        try:
            rows=connection.execute('SELECT id,item FROM orders ORDER BY id').fetchall()
        finally:
            connection.close()
        actual=hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        self.check(name,'actual_final_sqlite_hash_matches_recorded',actual,expected,evidence=str(path))
        self.details[name]['actual_final_sqlite_sha256']=actual

    def consistency(self, directory):
        name='consistency'
        summary=read_json(directory/'summary.json')
        rows=summary.get('results',[])
        events=read_lines(directory/'events.jsonl')
        result_events=[e for e in events if e.get('kind')=='consistency_result']
        self.details[name]={'directory':str(directory)}
        self.sources(name,directory,summary,{})
        self.check(name,'nonempty_cases',bool(rows))
        self.check(name,'summary_case_count',summary.get('total'),len(rows))
        self.check(name,'summary_passed_count',summary.get('passed'),sum(r.get('passed') is True for r in rows))
        failed=[r for r in rows if r.get('passed') is not True]
        self.check(name,'summary_failed_rows',summary.get('failed'),failed)
        self.check(name,'product_case_failures',len(failed),0,evidence=failed)
        self.check(name,'no_setup_error',summary.get('setup_error'),None)
        self.check(name,'one_result_event_per_case',len(result_events),len(rows))
        self.check(name,'event_case_ids_match_summary',[e['case'] for e in result_events],[r['case'] for r in rows])
        for row,event in zip(rows,result_events):
            self.check(name,'summary_result_matches_raw_event:'+row['case'],
                       {k:event.get(k) for k in row},row)
        self.check(name,'unique_case_ids',len({r['case'] for r in rows}),len(rows))
        rpc=self.pair_aip(name,events=events)
        self.check(name,'summary_request_count',summary.get('requests'),self.details[name]['recorded_aip_requests'])
        management=self.test_http_pairs(name,events)
        categories=Counter()
        classifications=Counter()
        for row in rows:
            case=row['case']
            category=row.get('category')
            categories[category]+=1
            pairs=rpc.get(case,[])
            self.check(name,'case_has_rpc_evidence:'+case,bool(pairs))
            expected_pass=bool(row.get('checks')) and all(value is True for value in row.get('checks',{}).values()) and row.get('data_unchanged') is True
            self.check(name,'case_pass_boolean_recomputed:'+case,row.get('passed'),expected_pass)
            before=row.get('data_hash_before')
            after=row.get('data_hash_after')
            if before is None or after is None:
                self.unverified(name,'sqlite_data_hash:'+case,'Only a boolean was retained; before/after content hashes are unavailable')
            else:
                self.check(name,'sqlite_data_preservation:'+case,before,after)
                self.check(name,'sqlite_data_unchanged_boolean:'+case,row.get('data_unchanged'),before==after)
            start_pairs=[p for p in pairs if p['request']['params']['command'].get('command')=='start']
            states=Counter(task_state(p['response']) for p in start_pairs)
            if category in {'competing_application_repairs','competing_database_repairs'}:
                self.check(name,'one_winner_five_expected_conflicts:'+case,
                           {'awaiting-completion':states['awaiting-completion'],'failed':states['failed']},
                           {'awaiting-completion':1,'failed':5})
            if category in {'stale_or_future_revision','forbidden_destination'}:
                self.check(name,'guard_rejection_has_failed_task:'+case,
                           bool(start_pairs) and all(task_state(p['response'])=='failed' for p in start_pairs))
            if category=='parallel_verification':
                verified=[]
                for pair in start_pairs:
                    task=pair['response'].get('result') or {}
                    products=task.get('products') or []
                    payloads=[item.get('data') for product in products for item in product.get('dataItems',[]) if item.get('type')=='data']
                    verified.append(any(isinstance(payload,dict) and payload.get('passed') is True for payload in payloads))
                self.check(name,'12_actual_verification_products:'+case,len(verified)==12 and all(verified))
            http=management.get(case,[])
            configs=[p['response'].get('body') for p in http if urlsplit(p['request'].get('url','')).path in {'/admin/config','/admin/status','/admin/reset'}]
            configs=[x for x in configs if isinstance(x,dict)]
            if not configs:
                self.unverified(name,'business_mutations:'+case,'No raw management configuration responses for this case')
            else:
                final=configs[-1]
                if row.get('checks',{}).get('one_effect') is not None:
                    self.check(name,'raw_configuration_one_mutation:'+case,final.get('mutations'),1)
                if any(key in row.get('checks',{}) for key in ['revision_once','one_revision']):
                    final_http=[p for p in http if p['response'].get('body') is final][-1]
                    target=urlsplit(final_http['request']['url']).netloc
                    baselines=[p['response'].get('body') for p in http if urlsplit(p['request'].get('url','')).netloc==target
                               and isinstance(p['response'].get('body'),dict) and 'revision' in p['response']['body']]
                    if baselines:
                        self.check(name,'raw_configuration_one_revision:'+case,final.get('revision'),baselines[0]['revision']+1)
                    else:
                        self.unverified(name,'raw_configuration_one_revision:'+case,'No raw baseline revision exists for the mutated service')
                if row.get('checks',{}).get('no_change') is not None:
                    # Locate the application config immediately before task work from the reset result.
                    resets=[p['response'].get('body') for p in http if p['request'].get('method')=='POST' and
                            urlsplit(p['request'].get('url','')).path=='/admin/reset' and
                            isinstance(p['response'].get('body'),dict) and 'database_url' in p['response']['body']]
                    if resets:
                        self.check(name,'raw_no_change_config:'+case,final,resets[-1])
                    else:
                        self.unverified(name,'raw_no_change_config:'+case,'No application reset baseline was recorded')
            if not row.get('passed'):
                classifications['product_failure']+=1
            elif category in {'stale_or_future_revision','forbidden_destination'}:
                classifications['expected_guard_rejection']+=1
            elif category.startswith('competing_'):
                classifications['single_winner_with_expected_conflicts']+=1
            elif category in {'healthy_no_op','parallel_verification'}:
                classifications['verification_or_noop']+=1
            else:
                classifications['idempotency_or_single_effect_test']+=1
        expected_categories={'repeat_start_complete','same_task_id_race','competing_application_repairs','competing_database_repairs',
                             'stale_or_future_revision','forbidden_destination','healthy_no_op','parallel_verification'}
        self.check(name,'every_expected_category_nonempty',sorted(categories),sorted(expected_categories))
        self.check(name,'classification_count_does_not_double_count',sum(classifications.values()),len(rows))
        self.final_sqlite_hash(name,directory,rows[-1].get('data_hash_after') if rows else None)
        self.lifecycle(name,events,summary)
        self.details[name].update({'cases':len(rows),'product_failures':len(failed),'category_counts':dict(categories),
                                  'disjoint_case_classification':dict(classifications),'recovery_claims':0})

    def resilience(self, directory):
        name='resilience'
        summary=read_json(directory/'summary.json')
        manifest=read_json(directory/'manifest.json')
        rows=read_lines(directory/'cases.jsonl')
        events=read_lines(directory/'events.jsonl')
        result_events=[e for e in events if e.get('kind')=='stress_case_result']
        self.details[name]={'directory':str(directory)}
        self.sources(name,directory,summary,manifest)
        self.check(name,'nonempty_cases',bool(rows))
        self.check(name,'unique_case_ids',len({r['case'] for r in rows}),len(rows))
        self.check(name,'summary_case_count',summary.get('total_cases'),len(rows))
        self.check(name,'summary_passed_count',summary.get('passed_cases'),sum(r.get('passed') is True for r in rows))
        failed=[r['case'] for r in rows if r.get('passed') is not True]
        self.check(name,'summary_failed_cases',summary.get('failed_cases'),failed)
        self.check(name,'product_case_failures',len(failed),0,evidence=failed)
        self.check(name,'no_fatal_error',summary.get('fatal_error'),None)
        self.check(name,'all_expected_summary_boolean',summary.get('all_expected'),bool(rows) and not failed and not summary.get('fatal_error') and
                   summary.get('sources_unchanged') is True and not summary.get('ports_still_open') and summary.get('processes_stopped') is True)
        self.check(name,'result_event_count',len(result_events),len(rows))
        for row,event in zip(rows,result_events):
            self.check(name,'case_file_matches_raw_event:'+row['case'],{key:event.get(key) for key in row},row)
        rpc=self.pair_aip(name,events=events)
        outcomes=Counter(row.get('outcome') for row in rows)
        self.check(name,'summary_outcome_counts',summary.get('actual_outcome_counts'),dict(outcomes))
        for key,outcome in [('recovered_cases','recovered'),('blocked_cases','blocked'),('human_review_cases','needs_human')]:
            self.check(name,'summary_'+key,summary.get(key),outcomes[outcome])
        classifications=Counter()
        names=Counter()
        for row in rows:
            case=row['case']
            names[row['name'].split('-')[0]]+=1
            expected=row['expected']
            before=row['before']
            after=row['after']
            pairs=rpc.get(case,[])
            # A directory with no candidate legitimately makes no AIP call.
            if row.get('aip_tasks',0)>0:
                self.check(name,'case_has_rpc_requests:'+case,bool(pairs))
            self.check(name,'case_aip_start_count:'+case,row.get('aip_tasks'),
                       sum(pair['request']['params']['command'].get('command')=='start' for pair in pairs))
            recomputed={
                'outcome':row.get('outcome')==expected.get('outcome'),
                'target_status':after.get('target',{}).get('status')==expected.get('target_status'),
                'mutations':row.get('mutations')==expected.get('mutations'),
                'known_mutations_zero_when_partially_observed':row.get('mutations') is not None or row.get('known_mutations')==0,
                'data_integrity':row.get('data_hash_before')==row.get('data_hash_after'),
                'fallbacks':row.get('connection_fallbacks',0)>=expected.get('min_connection_fallbacks',0),
            }
            # Some cases additionally verify exact known rows, recorded in actual /orders products.
            if row.get('outcome')=='recovered':
                orders=after.get('target',{}).get('body',{}).get('orders')
                self.check(name,'recovery_has_healthy_real_target_and_expected_rows:'+case,
                           after.get('target',{}).get('status')==200 and orders==[[1,'book'],[2,'keyboard'],[3,'monitor']])
                verifications=[]
                for pair in pairs:
                    cmd=pair['request']['params']['command']
                    if cmd.get('command')!='start':
                        continue
                    for product in ((pair['response'] or {}).get('result') or {}).get('products') or []:
                        for item in product.get('dataItems') or []:
                            payload=item.get('data')
                            if isinstance(payload,dict) and 'passed' in payload and 'samples' in payload:
                                verifications.append(payload)
                self.check(name,'recovery_has_partner_verification_product:'+case,
                           any(p.get('passed') is True and len(p.get('samples',[]))==3 and
                               all(sample.get('status')==200 and sample.get('body',{}).get('orders')==[[1,'book'],[2,'keyboard'],[3,'monitor']]
                                   for sample in p['samples']) for p in verifications))
            available=[after[key]['body'] for key in ['config','database'] if isinstance(after.get(key,{}).get('body'),dict)]
            known=sum(body.get('mutations',0) for body in available)
            self.check(name,'observed_mutation_count:'+case,row.get('known_mutations'),known)
            self.check(name,'full_mutation_observation:'+case,row.get('mutations'),known if len(available)==2 else None)
            self.check(name,'case_data_hashes_present:'+case,bool(row.get('data_hash_before')) and bool(row.get('data_hash_after')))
            self.check(name,'case_pass_recomputed:'+case,row.get('passed'),all(recomputed.values()))
            for check,value in recomputed.items():
                self.check(name,'stored_check_matches_evidence:'+case+':'+check,row.get('checks',{}).get(check),value)
            if not row.get('passed'):
                classifications['product_failure']+=1
            elif row.get('outcome')=='blocked':
                classifications['expected_safe_block']+=1
            elif row.get('outcome')=='needs_human':
                classifications['expected_human_review']+=1
            elif 'explicitly-restarted' in row.get('name',''):
                classifications['operator_restart_validation']+=1
            elif before.get('target',{}).get('status')==200 and row.get('mutations')==0:
                classifications['healthy_or_noop_validation']+=1
            elif row.get('outcome')=='recovered':
                classifications['automatic_recovery_of_injected_fault']+=1
            else:
                classifications['unclassified']+=1
        self.check(name,'classification_count_does_not_double_count',sum(classifications.values()),len(rows))
        ordinary=[r for r in rows if r.get('name','').startswith('paired-')]
        paired=defaultdict(set)
        for row in ordinary:
            paired[row['name']].add(row['mode'])
        self.check(name,'all_ordinary_scenarios_have_fixed_and_discovery_runs',bool(paired) and all(modes=={'fixed','discovery'} for modes in paired.values()))
        self.check(name,'expected_suite_sections_nonempty',
                   all(any(token in r.get('name','') for r in rows) for token in ['paired-','directory','partner-exited','service-process-exited','explicitly-restarted']))
        self.final_sqlite_hash(name,directory,summary.get('data_hash'))
        self.lifecycle(name,events,summary)
        self.details[name].update({'cases':len(rows),'product_failures':len(failed),'reported_outcomes':dict(outcomes),
                                  'disjoint_case_classification':dict(classifications),
                                  'recovery_claims':classifications['automatic_recovery_of_injected_fault'],
                                  'note':'Healthy checks, safe blocks, human review and explicit operator restarts are never counted as autonomous fault recovery.'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',required=True,type=Path)
    parser.add_argument('--consistency',required=True,type=Path)
    parser.add_argument('--resilience',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    inputs={key:getattr(args,key).resolve() for key in ['protocol','consistency','resilience']}
    output=args.output.resolve()
    for directory in inputs.values():
        if output==directory or directory in output.parents:
            parser.error('Audit output must be separate from every suite input directory')
    if (output/'AUDIT.json').exists():
        parser.error('AUDIT.json already exists; use a fresh output directory')
    audit=Audit()
    for name,directory in inputs.items():
        try:
            getattr(audit,name)(directory)
        except Exception as exc:
            audit.unverified(name,'audit_input_read_or_schema',f'{type(exc).__name__}: {exc}')
    for source in ['services.py','run_pilot.py']:
        core={name:details.get('source_sha256',{}).get(source) for name,details in audit.details.items()}
        if len(core)==3 and all(core.values()):
            audit.check('combined','all_three_suites_tested_same_source:'+source,len(set(core.values())),1,evidence=core)
            current=Path(__file__).resolve().parent/source
            if current.exists():
                current_hash=digest(current)
                audit.check('combined','frozen_snapshots_match_current_source:'+source,
                            sorted(set(core.values())),[current_hash],evidence={'current_path':str(current),'current_sha256':current_hash,'suite_sha256':core})
            else:
                audit.unverified('combined','current_source:'+source,'Current source file is unavailable',evidence=str(current))
        else:
            audit.unverified('combined','same_source:'+source,'Source snapshots do not contain comparable SHA-256 hashes',evidence=core)
    failed=[c for c in audit.checks if c['status']=='failed']
    unverified=[c for c in audit.checks if c['status']=='unverified']
    critical_unverified=[c for c in unverified if c.get('critical',True)]
    code=1 if failed else 2 if critical_unverified else 0
    summary={'created_at_utc8':datetime.now(timezone(timedelta(hours=8))).isoformat(),
             'auditor_pid':os.getpid(),'auditor_source_sha256':digest(Path(__file__).resolve()),
             'inputs':{key:str(value) for key,value in inputs.items()},'exit_code':code,
             'verified_checks':sum(c['status']=='verified' for c in audit.checks),'failed_checks':len(failed),
             'unverified_checks':len(unverified),'critical_unverified_checks':len(critical_unverified),
             'audit_passed':code==0,'scope':'Saved artifact consistency, real recorded HTTP/RPC pairing, task state histories, '
             'source snapshot hashes and current owned process/port cleanup. No rerun of business workflows; no claim '
             'about LLM reasoning, Wutong, mTLS or production correctness.'}
    artifact={'summary':summary,'suite_details':audit.details,'checks':audit.checks,
              'failures':failed,'unverified':unverified}
    output.mkdir(parents=True,exist_ok=True)
    (output/'AUDIT.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return code


if __name__=='__main__':
    raise SystemExit(main())
