"""Check the collected hourly series without issuing new network requests."""
from argparse import ArgumentParser
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

parser=ArgumentParser()
parser.add_argument('--output-dir',required=True,type=Path)
parser.add_argument('--private-cache',required=True,type=Path)
args=parser.parse_args()
path=args.output_dir/'ranking-hourly.json'
data=json.loads(path.read_text(encoding='utf-8'))
rows=data['windows']
assert len(rows)==data['expected_windows']
first=datetime.fromisoformat(data['first_endAt'])
all_roles={'A01','A02','A03','A04','A05','A06','A07'}
source_hashes_checked=0
preserved_failures=0
for index,row in enumerate(rows):
    endpoint=first+timedelta(hours=index)
    assert row['requested_end_at']==endpoint.isoformat()
    assert row['requested_start_at']=='2026-09-24T00:00:00+08:00'
    assert row['source_mode']=='queried_historical_windows'
    assert set(row['boards'])=={'caller','callee','callerNonInternal','calleeNonInternal'}
    for board in row['boards'].values():
        assert {item['agent'] for item in board['team']}==all_roles
        assert len(board['team'])==7
        for item in board['team']:
            if item['presence']=='not_in_returned_top_n':
                assert all(item[key] is None for key in ('rank','count','accessCount','messageCount'))
            else:
                assert item['rank']>=1
                assert item['count']==item['accessCount']+item['messageCount']
        if board['leader']:
            leader=board['leader']
            assert leader['count']==leader['accessCount']+leader['messageCount']
    if row.get('original_body_sha256'):
        body=args.private_cache/row.get('raw_body_file',endpoint.strftime('%Y%m%dT%H00')+'.json')
        assert hashlib.sha256(body.read_bytes()).hexdigest()==row['original_body_sha256']
        source_hashes_checked+=1
    preserved_failures+=len(row.get('previous_attempts',[]))
for filename in ('ranking-hourly.json','ranking-endpoint-check.json','longrun-summary.json'):
    text=(args.output_dir/filename).read_text(encoding='utf-8')
    assert not re.search(r'1\.2\.156\.3088\.1\.|[A-Z]:[\\/]Users|BEGIN (?:RSA )?PRIVATE KEY',text,re.I)
summary={'window_count':len(rows),'successful_windows':sum(row['success'] for row in rows),
    'failed_windows':sum(not row['success'] for row in rows),'preserved_prior_failed_attempts':preserved_failures,
    'source_hashes_checked':source_hashes_checked,'consecutive_hour_checks_passed':True,
    'all_seven_roles_and_four_boards_checked':True,'counts_and_null_semantics_checked':True,
    'identity_pattern_checks_passed':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(args.output_dir/'ranking-validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
