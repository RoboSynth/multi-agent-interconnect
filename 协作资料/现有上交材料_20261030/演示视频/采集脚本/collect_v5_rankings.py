"""Re-query hourly cumulative ranking windows and export anonymous video data.

This is retrospective querying, not a recording of hourly observations made live.
Raw responses and identity mappings must be kept in a separate private directory.
"""
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode

TZ = timezone(timedelta(hours=8))
START = '2026-09-24T00:00:00+08:00'
BOARDS = ('caller', 'callee', 'callerNonInternal', 'calleeNonInternal')
FIRST = datetime(2026, 10, 20, 7, tzinfo=TZ)

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = ArgumentParser()
    parser.add_argument('--private-identities', required=True, type=Path)
    parser.add_argument('--private-cache', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--probe-only', action='store_true')
    parser.add_argument('--retry-failed', action='store_true', help='Retry failed windows once, preserving each earlier request receipt and raw response.')
    parser.add_argument('--delay-seconds', type=float, default=0.8)
    args = parser.parse_args()
    identities = json.loads(args.private_identities.read_text(encoding='utf-8-sig'))
    assert set(identities) == {'A01', 'A02', 'A03', 'A04', 'A05', 'A06', 'A07'}
    assert len(set(identities.values())) == 7
    aliases = {value: key for key, value in identities.items()}
    args.private_cache.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    last = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    endpoints = [FIRST + timedelta(hours=i) for i in range(int((last-FIRST).total_seconds() // 3600) + 1)]

    def alias(identity):
        if identity is None:
            return None
        return aliases.get(identity) or 'EXT-' + digest(str(identity).encode())[:12].upper()

    def anon_error(value):
        for identity, name in aliases.items():
            value = value.replace(identity, name)
        value = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', '[redacted-address]', value)
        value = re.sub(r'(?i)[A-Z]:[\\/][^\r\n"]+', '[private-path]', value)
        return value

    def fetch(endpoint):
        token = endpoint.strftime('%Y%m%dT%H00')
        body_path = args.private_cache / (token + '.json')
        headers_path = args.private_cache / (token + '.headers.txt')
        receipt_path = args.private_cache / (token + '.receipt.json')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
        if receipt and receipt.get('raw_body_file'):
            body_path = args.private_cache / receipt['raw_body_file']
        previous_attempts = []
        should_fetch = receipt is None
        if receipt is not None and args.retry_failed:
            try:
                previous_data = json.loads(body_path.read_text(encoding='utf-8'))
                previous_range = previous_data.get('timeRange', {})
                previous_ok = receipt.get('curl_exit_code') == 0 and (receipt.get('http_status') or '').split(' ')[1:2] == ['200'] and previous_range.get('startAt') == START and previous_range.get('endAt') == endpoint.isoformat()
            except (ValueError,OSError,AttributeError):
                previous_ok = False
            if not previous_ok:
                previous_attempts = receipt.get('previous_attempts', []) + [{k:v for k,v in receipt.items() if k != 'previous_attempts'}]
                retry_suffix = '-attempt' + str(len(previous_attempts) + 1)
                body_path = args.private_cache / (token + retry_suffix + '.json')
                headers_path = args.private_cache / (token + retry_suffix + '.headers.txt')
                should_fetch = True
        if should_fetch:
            url = 'https://wt.ioa.pub/api/rankings/top?' + urlencode({'startAt':START, 'endAt':endpoint.isoformat(), 'n':200})
            begun = datetime.now(timezone.utc).isoformat()
            proc = subprocess.run(['curl.exe', '--connect-timeout', '8', '--max-time', '25', '-sS', '-D', str(headers_path),
                '-o', str(body_path), url], capture_output=True, encoding='utf-8', errors='replace')
            header_text = headers_path.read_text(encoding='utf-8', errors='replace') if headers_path.exists() else ''
            statuses = [line for line in header_text.splitlines() if line.startswith('HTTP/')]
            headers = {}
            for line in header_text.splitlines():
                if ':' in line:
                    key,value = line.split(':', 1)
                    if key.lower().strip() not in ('set-cookie','authorization','proxy-authorization'):
                        headers[key.lower().strip()] = value.strip()
            receipt = {'request_url':url, 'requested_start_at':START, 'requested_end_at':endpoint.isoformat(),
                'queried_at_utc':begun, 'received_at_utc':datetime.now(timezone.utc).isoformat(),
                'curl_exit_code':proc.returncode, 'http_status':statuses[-1] if statuses else None,
                'response_headers':headers, 'error':proc.stderr.strip() or None,
                'original_body_sha256':digest(body_path.read_bytes()) if body_path.exists() else None,
                'raw_body_file':body_path.name, 'raw_headers_file':headers_path.name,
                'previous_attempts':previous_attempts}
            save(receipt_path, receipt)
            time.sleep(args.delay_seconds)
        try:
            data = json.loads(body_path.read_text(encoding='utf-8'))
            if not isinstance(data,dict):
                raise ValueError('JSON body is not an object')
        except (ValueError,OSError) as exc:
            data = None
            receipt = {**receipt, 'decode_error':type(exc).__name__}
        return receipt,data

    def project(receipt,data):
        row = {**receipt, 'error':anon_error(receipt['error']) if receipt.get('error') else None,
            'source_mode':'queried_historical_windows', 'boards':{}}
        if row.get('previous_attempts'):
            row['previous_attempts'] = [{**attempt, 'error':anon_error(attempt['error']) if attempt.get('error') else None} for attempt in row['previous_attempts']]
        actual = data.get('timeRange') if isinstance(data,dict) else None
        row['returned_time_range'] = actual
        row['range_matches_request'] = bool(actual and actual.get('startAt')==START and actual.get('endAt')==receipt['requested_end_at'])
        row['meta'] = data.get('meta') if isinstance(data,dict) else None
        row['success'] = bool(receipt.get('curl_exit_code')==0 and (receipt.get('http_status') or '').split(' ')[1:2]==['200'] and row['range_matches_request'])
        row['response_error'] = anon_error(str(data.get('error'))) if isinstance(data,dict) and data.get('error') is not None else None
        for board in BOARDS:
            entries = data.get(board,[]) if isinstance(data,dict) else []
            lookup = {entry.get('aic'):(index+1,entry) for index,entry in enumerate(entries)}
            team = []
            for name,identity in identities.items():
                found = lookup.get(identity)
                team.append({'agent':name, 'presence':'returned' if found else 'not_in_returned_top_n',
                    'rank':found[0] if found else None,
                    'count':found[1].get('count') if found else None,
                    'accessCount':found[1].get('accessCount') if found else None,
                    'messageCount':found[1].get('messageCount') if found else None})
            leader = entries[0] if entries else None
            row['boards'][board] = {'returned_entries':len(entries), 'team':team,
                'leader':{'agent':alias(leader.get('aic')),'rank':1,**{k:leader.get(k) for k in ('count','accessCount','messageCount')}} if leader else None}
        return row

    probes = [project(*fetch(point)) for point in (endpoints[0],endpoints[-1])]
    def signature(row):
        return [(board,row['boards'][board]['leader'],row['boards'][board]['team']) for board in BOARDS]
    validation = {'checked_at_utc':datetime.now(timezone.utc).isoformat(), 'endpoint':'https://wt.ioa.pub/api/rankings/top',
        'probe_endpoints':[point.isoformat() for point in (endpoints[0],endpoints[-1])],
        'both_ranges_match':all(row['range_matches_request'] for row in probes),
        'both_requests_succeeded':all(row['success'] for row in probes),
        'results_differ':signature(probes[0])!=signature(probes[1]),
        'interpretation':'Different historical endAt values return the requested ranges and different cumulative results; this supports querying retrospective hourly windows.'}
    validation['passed'] = all(validation[key] for key in ('both_ranges_match','both_requests_succeeded','results_differ'))
    save(args.output_dir/'ranking-endpoint-check.json',{'validation':validation,'probes':probes})
    print(json.dumps({'probe_passed':validation['passed'],'planned_windows':len(endpoints),'first':endpoints[0].isoformat(),'last':endpoints[-1].isoformat()},ensure_ascii=False),flush=True)
    if args.probe_only or not validation['passed']:
        return 0 if validation['passed'] else 2

    output = {'schema_version':1, 'source_mode':'queried_historical_windows',
        'collected_at_utc':datetime.now(timezone.utc).isoformat(), 'timezone':'Asia/Shanghai', 'startAt':START,
        'first_endAt':endpoints[0].isoformat(), 'last_endAt':endpoints[-1].isoformat(), 'step_hours':1,
        'expected_windows':len(endpoints), 'role_aliases':{'A01':'协调','A02':'应用','A03':'数据库主','A04':'数据库备','A05':'运维','A06':'业务验证','A07':'接入体检'},
        'endpoint_validation':validation,
        'notes':['These are historical windows queried now, not continuously sampled historical observations.',
            'Missing top-200 entries have null values, not zero.',
            'count = accessCount + messageCount is official ranking activity, not successful business tasks.',
            'Each row retains request time, original body hash, HTTP headers and any error.'], 'windows':[]}
    for index,endpoint in enumerate(endpoints):
        row = project(*fetch(endpoint))
        output['windows'].append(row)
        output['successful_windows'] = sum(item['success'] for item in output['windows'])
        output['failed_windows'] = len(output['windows']) - output['successful_windows']
        output['complete'] = len(output['windows']) == len(endpoints)
        save(args.output_dir/'ranking-hourly.json',output)
        if (index+1)%10==0 or index+1==len(endpoints):
            print(json.dumps({'queried':index+1,'total':len(endpoints),'failed':output['failed_windows'],'latest_endAt':endpoint.isoformat()}),flush=True)
    text = (args.output_dir/'ranking-hourly.json').read_text(encoding='utf-8')
    assert not any(identity in text for identity in identities.values())
    assert not re.search(r'1\.2\.156\.3088\.1\.|[A-Z]:[\\/]Users|BEGIN (?:RSA )?PRIVATE KEY',text,re.I)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
