"""Offline platform-worker checks with generated test certificates and broker doubles.

Official Inbox/group consumer identity checks, AIP models, AMP emitters and
signatures run here. No formal platform Agent or real resource is started.
"""
from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import jcs
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType, TaskResult, TaskState
from acps_sdk.aip.aip_group_identity import SenderIdentityMismatchError
from acps_sdk.aip.aip_group_model import ACSObject, AMQPConfig, GroupInfo, InboxGroupInvitation
from acps_sdk.aip.aip_group_partner import PartnerGroupState
from acps_sdk.amp.trace_context import TRACEPARENT_HEADER
from incident.platform_worker import DomainExecutorAdapter, PlatformWorker, load_config, tls_context
from integration import wutong_smoke as native

LEADER = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
PARTNER = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JU5"
OTHER = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"
TRACE = "a" * 32
PARENT = "b" * 16


class Incoming:
    def __init__(self, message, user_id=LEADER):
        self.body = message.model_dump_json(exclude_none=True).encode()
        self.user_id = user_id
        self.headers = {TRACEPARENT_HEADER: f"00-{TRACE}-{PARENT}-01"}
        self.routing_key = ""
        self.redelivered = False

    @asynccontextmanager
    async def process(self):
        yield self


def test_material(directory, *, encrypted=False):
    now = datetime.now(timezone.utc)
    ca_key, key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unittest CA only")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, None))
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, PARTNER)]))
        .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier("acps://"+PARTNER)]), critical=False)
        .sign(ca_key, None))
    (directory/"trust.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (directory/"identity.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    algorithm = serialization.BestAvailableEncryption(b"test-key-pass") if encrypted else serialization.NoEncryption()
    (directory/"identity.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, algorithm))
    (directory/"domain.env").write_text("APP_ADMIN_TOKEN=domain-test-only-token\nTEST_PLATFORM_KEY_PASSWORD=test-key-pass\n", encoding="utf-8")
    return cert


class PlatformWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.env_patch = patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        self.cert = test_material(self.directory)
        self.config_dict = {"name": "application-test", "role": "application", "aic": PARTNER,
            "allowed_leaders": [LEADER], "endpoint": f"amqps://broker.test:5671/acps?inbox={native.build_inbox_queue_name(PARTNER)}",
            "mq_auth_url": "https://acl.test", "cert": "identity.pem", "key": "identity.key", "trust_bundle": "trust.pem",
            "env_file": "domain.env", "ledger_path": "operations.sqlite", "amp_directory": "amp",
            "evidence_path": "events.jsonl", "base_url": "http://127.0.0.1:9"}
        self.path = self.directory/"worker.json"
        self.path.write_text(json.dumps(self.config_dict), encoding="utf-8")
        self.config = load_config(self.path)
        self.executor = Mock()
        async def execute(payload, caller):
            result = {"schema_version": "ifc/1.0", "incident_id": payload["incident_id"],
                "logical_task_id": payload["logical_task_id"], "executor_aic": PARTNER, "status": "ok", "facts": []}
            if payload["kind"] == "describe":
                result["description"] = {"resources": ["orders"], "tools": ["application.status"]}
            return result
        self.executor.execute = AsyncMock(side_effect=execute)
        self.worker = PlatformWorker(self.config, executor=self.executor)
        self.runtime = self.worker.prepare()

    def tearDown(self):
        self.env_patch.stop()
        self.temp.cleanup()

    def invitation(self, leader=LEADER):
        return InboxGroupInvitation(groupId="platform-group", protocol="rabbitmq:4.0", invitationToken="test-only-token",
            expiresAt=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
            group=GroupInfo(groupId="platform-group", leader=ACSObject(aic=leader), partners=[ACSObject(aic=PARTNER)]),
            amqp=AMQPConfig(exchange=native.build_group_exchange_name(leader,"platform-group"), exchangeType="fanout", routingKey=""))

    def command(self, *, kind="observe", task="native-task", session="native-session", sender=LEADER):
        payload = {"schema_version":"ifc/1.0", "incident_id":"business-incident", "logical_task_id":"logical-task",
                   "kind":kind, "tool":"application.status", "args":{}}
        if kind == "act":
            payload.update(operation_id="business-incident:change", fence={"coordinator_term":1,"takeover_version":0})
        return TaskCommand(id="command-"+task, sentAt="2026-10-17T00:00:00Z", senderRole="leader", senderId=sender,
            sessionId=session, groupId="platform-group", taskId=task, command=TaskCommandType.Start, mentions=[PARTNER],
            dataItems=[StructuredDataItem(data=payload)])

    async def partner(self):
        client = self.runtime._partner_client()
        client._group_id = "platform-group"
        client._group_info = self.invitation().group
        client._state = PartnerGroupState.JOINED
        client._exchange_name = native.build_group_exchange_name(LEADER,"platform-group")
        client._queue_name = "unittest-task-queue"
        self.published = []
        async def publish(message, routing_key=""):
            self.published.append(message)
        client._exchange = Mock(publish=AsyncMock(side_effect=publish))
        client._queue = Mock(consume=AsyncMock(return_value="test-consumer"))
        self.runtime._bind_client(client)
        await client._start_consuming()
        callback = client._queue.consume.call_args.args[0]
        return client, callback

    def rows(self, kind):
        path = Path(self.config["amp_directory"])/f"amp_{kind}_application-test.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    async def test_official_group_identity_start_complete_trace_and_cached_product(self):
        client, consume = await self.partner()
        start = self.command()
        await consume(Incoming(start))
        complete = start.model_copy(update={"id":"complete-command","command":TaskCommandType.Complete,"dataItems":[]})
        await consume(Incoming(complete))
        await consume(Incoming(start))
        self.executor.execute.assert_awaited_once()
        results = [TaskResult.model_validate_json(message.body) for message in self.published]
        self.assertEqual([r.status.state for r in results[:4]], [TaskState.Accepted,TaskState.Working,TaskState.AwaitingCompletion,TaskState.Completed])
        self.assertEqual(results[-1].status.state, TaskState.Completed)
        self.assertTrue(all(message.user_id == PARTNER for message in self.published))
        self.assertTrue(all(message.headers[TRACEPARENT_HEADER].split("-")[1] == TRACE for message in self.published))
        access = self.rows("access")
        self.assertEqual(len(access),1)
        self.assertEqual(access[0]["trace_id"],"native-session")
        self.assertEqual(access[0]["correlation_id"],"native-task")
        self.assertEqual(access[0]["body"]["request"]["route"],"application.status")
        self.assertTrue(all(r["trace_id"] == TRACE for r in self.rows("message")))
        self.assertIs(client._message_emitter, self.worker.amp.message)
        self.assertIs(client._group_access.emitter, self.worker.amp.access)
        audit=self.rows("audit")[0]
        integrity=audit.pop("integrity")
        self.cert.public_key().verify(base64.urlsafe_b64decode(integrity["sig"]+"="*(-len(integrity["sig"])%4)),jcs.canonicalize(audit))
        self.assertEqual(audit["trace_id"],"business-incident")

    async def test_official_consumer_rejects_spoofed_amqp_identity_before_executor(self):
        _, consume = await self.partner()
        with self.assertRaises(SenderIdentityMismatchError):
            await consume(Incoming(self.command(),user_id=OTHER))
        self.executor.execute.assert_not_called()
        self.assertEqual(self.published,[])

    async def test_complete_rejects_other_leader_and_session_without_state_change(self):
        client, consume=await self.partner()
        start=self.command()
        await consume(Incoming(start))
        initial=len(self.published)
        for sender,session in ((OTHER,"native-session"),(LEADER,"wrong-session")):
            command=start.model_copy(update={"senderId":sender,"sessionId":session,"command":TaskCommandType.Complete,"dataItems":[]})
            await consume(Incoming(command,user_id=sender))
        self.assertEqual(len(self.published),initial)
        self.assertEqual(client._task_states[start.taskId],TaskState.AwaitingCompletion)

    async def test_invitation_uses_unified_inbox_authenticated_identity(self):
        self.runtime._accept_probe_invitation=AsyncMock()
        invitation=self.invitation()
        await self.runtime._dispatch_inbox(Incoming(invitation))
        self.runtime._accept_probe_invitation.assert_awaited_once()
        await self.runtime._dispatch_inbox(Incoming(invitation,user_id=OTHER))
        self.runtime._accept_probe_invitation.assert_awaited_once()
        self.assertIsNone(self.runtime._invitation_policy(invitation))
        self.assertIsNotNone(self.runtime._invitation_policy(self.invitation(OTHER)))
        wrong=invitation.model_copy(update={"amqp":AMQPConfig(exchange="unrelated",exchangeType="fanout",routingKey="")})
        self.assertIsNotNone(self.runtime._invitation_policy(wrong))

    async def test_business_handler_is_bound_before_join_starts_task_consumer(self):
        client=self.runtime._partner_client()
        client._group_id="platform-group"
        client._group_info=self.invitation().group
        client.submit_for_completion=AsyncMock()
        client.accept_task=AsyncMock()
        client.start_working=AsyncMock()
        async def join(invitation):
            self.assertIsNotNone(client._command_handler)
            result=await client._command_handler(self.command(),True)
            self.assertEqual(result["status"],"ok")
            return True
        client.join_group_from_invitation=AsyncMock(side_effect=join)
        self.runtime._partner_client=Mock(return_value=client)
        await self.runtime._accept_probe_invitation(self.invitation())
        client.submit_for_completion.assert_awaited_once()
        self.executor.execute.assert_awaited_once()

    async def test_invalid_schema_and_business_rejection_are_not_access_success(self):
        _,consume=await self.partner()
        invalid=self.command(task="bad-schema").model_copy(update={"dataItems":[StructuredDataItem(data={"schema_version":"wrong"})]})
        await consume(Incoming(invalid))
        self.executor.execute.assert_not_called()
        async def rejected(payload,caller):
            return {"incident_id":payload["incident_id"],"logical_task_id":payload["logical_task_id"],"executor_aic":PARTNER,"status":"rejected","facts":[]}
        self.executor.execute.side_effect=rejected
        await consume(Incoming(self.command(task="denied")))
        self.assertTrue(all(r["body"]["response"]["statusCode"]==500 for r in self.rows("access")))

    async def test_periodic_start_close_writes_six_official_amp_types(self):
        self.runtime.start_inbound=AsyncMock()
        self.runtime.close=AsyncMock()
        await self.worker.start()
        self.assertEqual(len(self.worker.amp.tasks),2)
        _,consume=await self.partner()
        await consume(Incoming(self.command(kind="describe")))
        await self.worker.amp.heartbeat.emit()
        await self.worker.amp.metrics.emit()
        await self.worker.close()
        for kind in ("heartbeat","metrics","access","message","audit","system"):
            self.assertTrue(self.rows(kind))
        self.assertTrue(all("integrity" in row for row in self.rows("audit")))
        self.assertEqual(self.worker.amp.tasks,[])

    async def test_adapter_forwards_all_ifc_kinds_without_resource_commands_in_transport(self):
        _,consume=await self.partner()
        for index,kind in enumerate(("describe","observe","act","verify")):
            await consume(Incoming(self.command(kind=kind,task=f"kind-{index}")))
        self.assertEqual([call.args[0]["kind"] for call in self.executor.execute.await_args_list],
                         ["describe","observe","act","verify"])

    def test_encrypted_key_stays_on_disk_encrypted_and_signs_with_domain_password(self):
        test_material(self.directory,encrypted=True)
        config={**self.config,"key_password_env":"TEST_PLATFORM_KEY_PASSWORD"}
        worker=PlatformWorker(config,executor=self.executor)
        worker.prepare()
        self.assertTrue(worker.amp.signed_audit)
        self.assertIn("ENCRYPTED PRIVATE KEY",Path(config["key"]).read_text(encoding="utf-8"))

    def test_binding_requires_official_identity_and_config_resolves_only_domain_paths(self):
        client=self.runtime._partner_client()
        client._identity_binding_enabled=False
        with self.assertRaises(ValueError):
            self.runtime.bridge.bind_partner(client)
        self.assertEqual(Path(self.config["env_file"]),self.directory/"domain.env")
        self.assertEqual(Path(self.config["ledger_path"]),self.directory/"operations.sqlite")
        self.assertEqual(os.environ["APP_ADMIN_TOKEN"],"domain-test-only-token")
        with patch("incident.platform_worker.native.validate_certificates",side_effect=AssertionError("offline only")):
            with self.assertRaises(AssertionError):
                tls_context(self.config)


if __name__=="__main__":
    unittest.main()
