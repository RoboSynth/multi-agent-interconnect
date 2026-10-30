"""Run one queued external-agent task per timer tick and retain its result."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run_once(plan_path: Path, *, status_only: bool = False) -> dict:
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    state_path = Path(plan['state_file'])
    state = json.loads(state_path.read_text()) if state_path.exists() else {'jobs': {}, 'disabled_services': {}}
    jobs = plan['jobs']
    identifiers = [job['id'] for job in jobs]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Job identifiers must be unique')
    now = dt.datetime.now(dt.timezone.utc)
    completed = sum(row.get('status') == 'completed' for row in state['jobs'].values())
    pending = [job for job in jobs if job['id'] not in state['jobs']]
    if status_only:
        return {'completed': completed, 'recorded': len(state['jobs']), 'total': len(jobs),
                'pending': len(pending), 'disabled_services': state['disabled_services'],
                'last_run': state.get('last_run')}

    def finish(reason: str) -> dict:
        state['finished_at_utc'] = now.isoformat()
        state['finish_reason'] = reason
        write_json(state_path, state)
        timer = plan.get('timer_unit')
        if timer:
            subprocess.run(['systemctl', 'disable', '--now', timer], check=True)
        return {'status': 'finished', 'reason': reason, 'completed': completed, 'total': len(jobs)}

    if now >= dt.datetime.fromisoformat(plan['stop_at']):
        return finish('time_window_ended')
    for job in pending:
        if job['aic'] in state['disabled_services']:
            state['jobs'][job['id']] = {'status': 'skipped_service_unavailable', 'at_utc': now.isoformat()}
    pending = [job for job in pending if job['aic'] not in state['disabled_services']]
    if not pending:
        return finish('queue_finished')

    job = pending[0]
    directory = Path(plan['evidence_directory']) / job['id']
    directory.mkdir(parents=True, exist_ok=False)
    state['jobs'][job['id']] = {'status': 'running', 'started_at_utc': now.isoformat(), 'aic': job['aic']}
    write_json(state_path, state)
    write_json(directory / 'request.json', job)
    args = [sys.executable, '-B', plan['caller_script'], job['aic'], job['request']]
    try:
        response = subprocess.run(args, capture_output=True, encoding='utf-8', timeout=125)
        if response.returncode:
            raise RuntimeError(response.stderr[-1500:])
        result = json.loads(response.stdout)
    except Exception as error:
        result = {'status': 'runner_failed', 'error_type': type(error).__name__, 'error': str(error)[:1500]}
    write_json(directory / 'result.json', result)
    texts = [item['text'] for product in result.get('products', []) for item in product.get('dataItems', [])
             if item.get('type') == 'text' and item.get('text')]
    if texts:
        (directory / 'response.txt').write_text('\n\n'.join(texts) + '\n', encoding='utf-8')
    success = result.get('status') == 'completed' and result.get('product_count', 0) > 0
    status = 'completed' if success else result.get('status', 'failed')
    if not success and status == 'completed':
        status = 'completed_without_product'
    if not success:
        state['disabled_services'][job['aic']] = {'at_utc': now.isoformat(), 'job_id': job['id'], 'reason': status}
    row = {'status': status, 'aic': job['aic'], 'name': job['name'],
           'started_at_utc': now.isoformat(), 'finished_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'task_id': result.get('task_id'), 'product_count': result.get('product_count', 0),
           'result_file': str(directory / 'result.json')}
    state['jobs'][job['id']] = row
    state['last_run'] = {'job_id': job['id'], **row}
    write_json(state_path, state)
    if len(state['jobs']) == len(jobs):
        finish('queue_finished')
    return {'job_id': job['id'], **row}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if args.status:
        print(json.dumps(run_once(args.plan, status_only=True), ensure_ascii=False))
        return
    import fcntl
    lock = args.plan.with_suffix('.lock')
    with lock.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'already_running'}))
            return
        print(json.dumps(run_once(args.plan), ensure_ascii=False))


if __name__ == '__main__':
    main()
