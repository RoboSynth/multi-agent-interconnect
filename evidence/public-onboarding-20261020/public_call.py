"""Three read-only interoperability checks from one distinct retired identity."""
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import uuid

ROOT = Path('/opt/incident-pilot')
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor/ACPs-community/acps-sdk')]
from acps_sdk.aip import StructuredDataItem, TextDataItem
from domains.onboarding.text import prepare_text_request
from eval.platform_resume_experiment import CleanupWarnings, close_owned, coordinator_lock
from incident.contracts import TaskProduct
from incident.wutong_transport import WutongTransport
from integration import wutong_smoke as native
from ops.aic_lease import AicLease
from tools.onboarding_client import configuration, payload

OUT = ROOT / 'evidence/public-onboarding-20261020/nonallowlisted-call'
PRIVATE = ROOT / 'runtime/private/public-onboarding-caller-20261020'


def save(value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'result.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


async def text_call(transport, service, text, expected_status):
    task = 'aip-' + uuid.uuid4().hex
    session = transport.session.session_id
    expected, _ = prepare_text_request(text, session_id=session, task_id=task, executor_aic=service)
    await transport.runtime.start_task(session, task_content=text, task_id=task,
        logical_task_id=expected['logical_task_id'], target_partners=[service])
    await native.wait_for_state(transport.session, task, service, native.TaskState.AwaitingCompletion, 40)
    messages = [message for message in transport.session.message_history
        if isinstance(message, native.TaskResult) and message.taskId == task and message.senderId == service
        and message.status.state == native.TaskState.AwaitingCompletion]
    assert messages, 'No actual task product'
    items = [item for product in messages[-1].products or [] for item in product.dataItems or []]
    assert len(items) == 2 and isinstance(items[0], StructuredDataItem) and isinstance(items[1], TextDataItem)
    product = TaskProduct.model_validate(items[0].data)
    assert (product.executor_aic, product.incident_id, product.logical_task_id, product.status) == (
        service, expected['incident_id'], expected['logical_task_id'], expected_status)
    assert items[1].text, 'No readable reply'
    await transport.runtime.complete_task(session, task, target_partner=service,
                                          logical_task_id=expected['logical_task_id'])
    await native.wait_for_state(transport.session, task, service, native.TaskState.Completed, 30)
    return dict(task_id=task, status=product.status, product=product.model_dump(), readable=items[1].text,
                completed=True)


async def main():
    assert not OUT.exists(), 'Keep original attempts; use a fresh acceptance script/output for a new run'
    service_config = json.loads((ROOT / 'runtime/private/cloud-new7-20261019/domains/onboarding/config.json').read_text())
    application_config = json.loads((ROOT / 'runtime/private/cloud-new7-20261019/domains/application/config.json').read_text())
    host = json.loads((ROOT / 'runtime/private/cloud-longrun/control/host.json').read_text())
    assert host['status'] == 'running', 'Do not compete with an experiment'
    service, target = service_config['aic'], application_config['aic']
    config = configuration(PRIVATE / 'config.json', OUT, service)
    caller = config['leader']['aic']
    assert caller not in host['aics'] and caller not in service_config['allowed_leaders']
    assert service_config['public_metadata_service'] is True
    report = dict(status='running', started_at=datetime.now(timezone.utc).isoformat(), caller_aic=caller,
        service_aic=service, target_aic=target, caller_in_service_allowlist=False,
        distinct_from_seven_running_identities=True, actual_other_team_usage=False,
        internal_host_session=host['session_id'], model_calls=0, cases=[])
    save(report)
    warnings = CleanupWarnings()
    logging.getLogger().addHandler(warnings)
    transport = WutongTransport(config, OUT / 'transport')
    with coordinator_lock(caller), AicLease([caller], purpose='public-onboarding-readonly-acceptance',
            directory=PRIVATE / 'leases') as lease:
        try:
            await transport.start()
            report['group_id'] = transport.session.group_id
            result = await transport.call(payload(target))
            assert result['status'] == 'ok'
            report['cases'].append(dict(kind='existing_ifc', result=result, completed=True))
            save(report)
            report['cases'].append(dict(kind='plain_text', **await text_call(
                transport, service, '检查 ' + target + ' 的公开元数据', 'ok')))
            save(report)
            refusal = await text_call(transport, service, '重启 ' + target, 'rejected')
            assert refusal['product']['reason'] == 'read_only_metadata_check_required'
            report['cases'].append(dict(kind='read_only_refusal', **refusal))
            report['status'] = 'passed'
        except Exception as error:
            report.update(status='failed', error_class=type(error).__name__, error=str(error))
        finally:
            try:
                report['close_checks'] = await close_owned(transport, warnings)
            except Exception as error:
                report.update(status='failed', close_error_class=type(error).__name__)
                lease.quarantine('Public acceptance own-group normal close unconfirmed', evidence=str(OUT))
            logging.getLogger().removeHandler(warnings)
            after = json.loads((ROOT / 'runtime/private/cloud-longrun/control/host.json').read_text())
            report['internal_host_after'] = dict(status=after['status'], session_id=after['session_id'])
            report['cleanup_warning_events'] = list(warnings.events)
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            save(report)
    print(json.dumps(dict(status=report['status'], cases=len(report['cases']),
        close_checks=report.get('close_checks'), internal_host_after=report['internal_host_after'])))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
