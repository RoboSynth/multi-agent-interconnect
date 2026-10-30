"""Export only the newly collected video batch; redact identity/secret metadata.

Private source records stay unchanged. Timestamp provenance is retained.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()] if path.exists() else []


class Exporter:
    def __init__(self, raw, output, plan_relative):
        self.raw, self.output = Path(raw), Path(output)
        self.plan_directory = self.raw / plan_relative
        self.plan = read(self.plan_directory / 'batch-plan.json')
        self.capture = self.plan_directory / 'capture'
        self.results = self.raw / self.plan['results']
        codes = {'coordinator': 'A01', 'application': 'A02', 'database': 'A03', 'database-backup': 'A04',
            'ops': 'A05', 'verification': 'A06', 'onboarding': 'A07'}
        self.aliases = {value: codes[role] for role, value in self.plan['identities'].items()}
        self.aliases[self.plan['project']] = 'capture-lab'
        self.captured = lines(self.capture / 'capture-events.jsonl')
        self.provider_identities = set()
        def providers(value, parent=''):
            if isinstance(value, dict):
                for key, item in value.items():
                    if parent == 'provider' and isinstance(item, str) and len(item) >= 2:
                        self.provider_identities.add(item)
                    providers(item, key)
            elif isinstance(value, list):
                for item in value:
                    providers(item, parent)
        providers(self.captured)
        self.clock = read(self.capture / 'clock-anchor.json')
        self.batch = read(self.results / 'batch/summary.json')

    def clean(self, value, parent=''):
        if isinstance(value, dict):
            return {self.clean(str(key)): ('[removed]' if re.search(r'(?i)(secret|password|signature|private_key|certificate_pem)|^(?:authorization|access_token|refresh_token|api_key|token|proof)$', str(key)) else self.clean(item, str(key))) for key, item in value.items()}
        if isinstance(value, list):
            return [self.clean(item, parent) for item in value]
        if not isinstance(value, str):
            return value
        if parent.lower() in {'email', 'phone', 'username', 'account', 'author_name', 'provider_name'}:
            return '[identity removed]'
        for identity, alias in sorted(self.aliases.items(), key=lambda item: len(item[0]), reverse=True):
            value = value.replace(identity, alias)
        for identity in sorted(self.provider_identities, key=len, reverse=True):
            value = value.replace(identity, '[provider identity]')
        value = re.sub(r'1\.2\.156\.3088\.1\.[A-Za-z0-9.]+', lambda m: 'EXT-' + hashlib.sha256(m[0].encode()).hexdigest()[:10], value)
        value = re.sub(r'(?i)(?:https?|amqps?)://[^\s\"<>]+', '[endpoint]', value)
        value = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', '[address]', value)
        value = re.sub(r'(?i)[A-Z]:[\\/][^\r\n\"<>]+|/(?:opt|home|Users|domain|runtime|tmp)/[^\s\"<>]+', '[path]', value)
        return value

    def anonymous(self, value):
        # Provider objects contain personal strings, never business measurements.
        if isinstance(value, dict):
            return {k: ({'identity': '项目团队（已匿名）'} if k.lower() == 'provider' else self.anonymous(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.anonymous(v) for v in value]
        return value

    def save(self, directory, name, value, jsonl=False):
        directory.mkdir(parents=True, exist_ok=True)
        value = self.anonymous(self.clean(value))
        text = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in value) if jsonl else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        (directory / name).write_text(text, encoding='utf-8')

    def capture_events(self, key):
        output, active = [], None
        for row in self.captured:
            if row['event'] == 'capture_case_ready':
                active = row.get('case')
            if active == key:
                output.append(row)
        return output

    def base_run(self, key, directory, incident_id, result):
        rows = self.capture_events(key)
        browser = read(directory / 'browser-run.json') if (directory / 'browser-run.json').exists() else {}
        receipt = next(row for row in self.batch['cases'] if row['key'] == key)
        return {'schema': 'fresh-cloud-video-run/1', 'batch_id': self.plan['batch_id'], 'case_key': key,
            'incident_id': incident_id, 'started_at_utc': receipt['started_at'], 'finished_at_utc': receipt['finished_at'],
            'status': result.get('status'), 'source_commit': self.plan['source_commit'],
            'source_state': 'cloud current working tree; commit alone is not the full source. Bound source SHA256 is retained.',
            'source_sha256': self.plan['source_sha256'], 'model_calls': 0,
            'video': 'video.webm', 'video_timing': browser.get('recording'),
            'server_case_start_utc': browser.get('case_start_utc'),
            'video_t0_to_server_case_start_seconds': browser.get('video_t0_to_server_case_start_seconds'),
            'clock_samples': browser.get('clock_samples'), 'synchronization_note': browser.get('synchronization_note'),
            'view': 'Existing workbench frontend connected to this run through isolated capture adapter on loopback; not the original longrun server.',
            'identity_projection': 'AICs mapped to A01-A07; provider identity, credentials, endpoints and machine paths removed. Numeric business results retained.',
            'cleanup': {'close_checks': result.get('close_checks'), 'resource_restore': result.get('resource_and_worker_restore'),
                'independent_final_H00': result.get('independent_final_H00'), 'batch_consumers': receipt['result'].get('batch_consumer_cleanup'),
                'safe_to_continue': receipt.get('safe_to_continue')},
            'lease_return': self.batch.get('lease'),
            'inspection_restoration_observed': read(self.capture / 'inspection-restoration-observed.json'),
            'capture_clock_anchor': self.clock,
            'capture_events': len(rows)}

    def export_f10(self):
        key = 'f10-m0-r1'
        source, directory = self.results / key, self.output / 'V3-f10'
        states = list((source / 'incidents').glob('*.json'))
        if len(states) != 1:
            raise ValueError('Expected one actual F10 incident')
        state, result = read(states[0]), read(source / 'wrapper-result.json')
        captured = self.capture_events(key)
        transport = [{'captured_at_utc': row['captured_at_utc'], 'time_basis': 'same-host capture arrival; original transport record does not add wall time',
            'source': 'transport/events.jsonl', **row['source_event']} for row in captured if row['event'] == 'transport_observed']
        incident = [{'source': 'IncidentCoordinator persisted events', 'time_basis': 'native UTC event timestamp', **row} for row in state['events']]
        merged = sorted(transport + incident, key=lambda row: row.get('at') or row.get('captured_at_utc') or '')
        self.save(directory, 'events.jsonl', merged, True)
        self.save(directory, 'incident-state.json', state)
        self.save(directory, 'approvals.json', {'records': [{k: row.get(k) for k in ['id', 'tool', 'reason', 'status', 'requested_at', 'decided_at']} for row in state['approvals']],
            'actual_decisions': [row for row in captured if row['event'] == 'capture_operator_decision'],
            'mode': 'actual existing coordinator decision channel; visible hold then scripted authorized click, not spontaneous human input'})
        samples = []
        for row in lines(source / 'workloads/F10-M0-1/requests.jsonl'):
            epoch = self.clock['epoch_seconds'] + row['at_monotonic'] - self.clock['monotonic_seconds']
            samples.append({**row, 'estimated_at_utc': datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                'time_basis': 'same-cloud-host monotonic timestamp mapped with this-run UTC anchor', 'success': row.get('outcome') == 'success'})
        self.save(directory, 'order-samples.json', {'nominal_requests_per_second': 1, 'source': 'same-run continuous observer requests.jsonl',
            'no_resampling_or_interpolation': True, 'samples': samples,
            'counting_scope': 'samples retains the entire stream including healthy baseline. summary.requests counts only records at or after fault_at; these totals intentionally differ.',
            'summary': read(source / 'workloads/F10-M0-1/summary.json')})
        self.save(directory, 'evaluation-result.json', read(source / 'results.json'))
        run = self.base_run(key, directory, state['id'], result)
        run.update(method='M0', workload_seed=101, repeats=1, transport='wutong-amqps', backend='docker',
            comparison_to_20261020='Same F10/M0/seed101/repeat1 selection. This capture replaces evaluator 0.1-second pre-authorization with the actual approval channel held >=2 seconds. Therefore approval timing is a declared demonstration variation.',
            incident_started_at_utc=state.get('started_at'), incident_finished_at_utc=state.get('finished_at'),
            raw_transport_event_count=len(lines(source / 'transport/events.jsonl')), exported_transport_event_count=len(transport),
            incident_event_count=len(incident))
        self.save(directory, 'run.json', run)

    def export_e1(self):
        key = 'e1a-after_applied-r1'
        source, directory = self.results / key, self.output / 'V4-takeover'
        result = read(source / 'results.json')
        captured = self.capture_events(key)
        events = [{'captured_at_utc': row['captured_at_utc'], 'time_basis': 'capture arrival; original transport record lacks native wall timestamp',
            'source': 'coordinator/events.jsonl', **row['source_event']} for row in captured if row['event'] == 'transport_observed']
        system_times = {json.dumps(row['body'], sort_keys=True): (row['timestamp'], number)
            for number, row in enumerate(lines(source / 'coordinator/amp/amp_system_coordinator.jsonl'), 1)}
        for row in events:
            body = {k: v for k, v in row.items() if k not in {'captured_at_utc', 'time_basis', 'source'}}
            matched = system_times.get(json.dumps(body, sort_keys=True))
            if matched:
                row.update(native_at_utc=matched[0], timestamp_source='coordinator/amp/amp_system_coordinator.jsonl', timestamp_source_line=matched[1],
                    time_basis='native AMP system timestamp for the exact same event body')
        timeline = [{'at_utc': row.get('native_at_utc', row['captured_at_utc']), 'time_basis': row['time_basis'], 'event': row['event'], 'record': row}
            for row in events if row['event'].startswith(('takeover', 'official_discovery', 'participant_', 'adp_participant'))]
        states = lines(self.capture / 'worker-state-observations.jsonl')
        for row in states:
            if row.get('service') == 'database-agent' and row['state'].get('ExitCode') == 83:
                timeline.append({'at_utc': row['state']['FinishedAt'], 'event': 'primary_process_exit',
                    'time_basis': 'Docker engine State.FinishedAt; observed later by read-only inspect',
                    'observed_at_utc': row['observed_at_utc'], 'exit_code': 83, 'executor': 'A03'})
        snapshot = read(self.capture / (key + '-snapshot.json'))['incident']
        def objects(value):
            if isinstance(value, dict):
                if 'logical_task_id' in value and ('kind' in value or 'status' in value):
                    yield value
                for item in value.values():
                    yield from objects(item)
            elif isinstance(value, list):
                for item in value:
                    yield from objects(item)
            elif isinstance(value, str):
                try:
                    nested = json.loads(value)
                except ValueError:
                    return
                if isinstance(nested, (dict, list)):
                    yield from objects(nested)
        takeover_start = next(row for row in events if row['event'] == 'takeover_started')
        timeline.append({'at_utc': takeover_start.get('native_at_utc', takeover_start['captured_at_utc']), 'event': 'coordinator_timeout_triggered_takeover',
            'time_basis': takeover_start['time_basis'] + '; actual TimeoutError-triggered takeover, not physical process exit',
            'reason': takeover_start.get('reason'), 'logical_task_id': takeover_start.get('logical_task_id')})
        excerpts, final_verification = [], None
        message_times = {}
        for number, row in enumerate(lines(source / 'coordinator/amp/amp_message_coordinator.jsonl'), 1):
            message_times.setdefault((row['body'].get('messageId'), row['body'].get('eventType')), (row['timestamp'], number))
        for line_number, row in enumerate(lines(source / 'coordinator/messages.jsonl'), 1):
            message = row['message']
            amp_time = message_times.get((message['id'], row['direction']))
            at_utc = amp_time[0] if amp_time else message['sentAt']
            time_basis = 'native AMP message timestamp for matching messageId and direction' if amp_time else 'native AIP envelope sentAt (sender timestamp)'
            for payload in objects(message):
                operation = payload.get('operation') or {}
                if row['direction'] == 'send' and payload.get('kind') == 'describe' and row['worker_aic'] == self.plan['identities']['database-backup']:
                    timeline.append({'at_utc': at_utc, 'event': 'backup_join_completed_before_describe_send',
                        'timestamp_is_upper_bound': True, 'event_time_interval_utc': [takeover_start.get('native_at_utc', takeover_start['captured_at_utc']), at_utc],
                        'time_basis': 'No separate group-join timestamp retained. _describe awaits invite_partner before sending this actual describe command.',
                        'source_message_line': line_number, 'executor': 'A04'})
                if row['direction'] == 'send' and payload.get('kind') == 'resume':
                    timeline.append({'at_utc': at_utc, 'event': 'handover_package_sent',
                        'time_basis': time_basis, 'source_message_line': line_number, 'envelope_sent_at_utc': message['sentAt'],
                        'logical_task_id': payload['logical_task_id'], 'operation_id': payload.get('operation_id'), 'fence': payload.get('fence')})
                    excerpts.append({'source': 'coordinator/messages.jsonl', 'line': line_number, 'sent_at': message['sentAt'], 'direction': row['direction'], 'payload': payload})
                if operation.get('state') == 'skipped_already_applied' and row['direction'] == 'receive':
                    timeline.append({'at_utc': at_utc, 'event': 'backup_returned_skipped_already_applied',
                        'time_basis': time_basis, 'source_message_line': line_number, 'envelope_sent_at_utc': message['sentAt'],
                        'logical_task_id': payload['logical_task_id'], 'operation_id': operation.get('operation_id'), 'operation': operation})
                    excerpts.append({'source': 'coordinator/messages.jsonl', 'line': line_number, 'sent_at': message['sentAt'], 'direction': row['direction'], 'payload': payload})
                facts = {fact['key']: fact['value'] for fact in payload.get('facts', [])}
                if row['direction'] == 'receive' and 'order_observation' in facts:
                    final_verification = {'at_utc': message['sentAt'], 'event': 'business_verification_completed',
                        'time_basis': 'native AIP TaskResult.sentAt from verification domain; final verifier in this case',
                        'source_message_line': line_number, 'logical_task_id': payload['logical_task_id'], 'facts': facts}
        if final_verification:
            audits = [(number, row) for number, row in enumerate(lines(source / 'coordinator/amp/amp_audit_coordinator.jsonl'), 1)
                if row['body'].get('action', {}).get('name') == 'incident.verification' and row['body'].get('result', {}).get('status') == 'success']
            if audits:
                number, audit = audits[-1]
                final_verification.update(at_utc=audit['timestamp'], time_basis='native coordinator AMP audit timestamp for the final successful incident.verification',
                    timestamp_source='coordinator/amp/amp_audit_coordinator.jsonl', timestamp_source_line=number)
            timeline.append(final_verification)
        timeline.sort(key=lambda row: row['at_utc'])
        self.save(directory, 'takeover-timeline.json', {'case': 'E1-a', 'crash_point': 'after_applied',
            'incident_id': result['incident_id'], 'timeline': timeline,
            'worker_trace_time_limit': 'Durable primary/backup trace records have no native timestamps; retained separately without inventing event times.',
            'old_primary_revival_and_stale_fence': {'included': False, 'reason': 'This E1-a after_applied case exits the primary; no resurrection is part of the case.'},
            'worker_exit_and_mcp': result.get('worker_exit_and_mcp'), 'business_verification': result.get('business_verification'),
            'evidence_limit': 'Exactly one MCP invocation is a tool-call count, not a direct physical-write count.'})
        self.save(directory, 'events.jsonl', events, True)
        self.save(directory, 'handover-message-excerpts.json', excerpts)
        self.save(directory, 'primary-trace.jsonl', lines(source / 'primary-trace.jsonl'), True)
        self.save(directory, 'backup-trace.jsonl', lines(source / 'backup-trace.jsonl'), True)
        self.save(directory, 'result.json', result)
        self.save(directory, 'run.json', self.base_run(key, directory, result['incident_id'], result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--plan-relative', required=True)
    args = parser.parse_args()
    exporter = Exporter(args.raw, args.output, args.plan_relative)
    exporter.export_f10()
    exporter.export_e1()
    print(json.dumps({'status': 'exported', 'batch_id': exporter.plan['batch_id'], 'cases': 2}))


if __name__ == '__main__':
    main()
