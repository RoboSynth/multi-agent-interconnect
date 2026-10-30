"""Exact-target task/management/AMP evidence, without platform or resource calls."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aip.aip_group_model import GroupMgmtResult, GroupMemberStatus
from acps_sdk.aip.aip_base_model import Product, StructuredDataItem, TaskResult, TaskState, TaskStatus
from incident.local_transport import LocalAipStdioTransport, LocalWorker
from incident.wutong_transport import WutongTransport


class ParticipantHealthTransportTests(unittest.IsolatedAsyncioTestCase):
    def payload(self):
        return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
                "kind": "observe", "tool": "ops.route_status", "args": {}, "budget": {"deadline_ms": 10}}

    def heartbeat(self, directory, *, aic="owned-ops", age=46):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        path = directory / "amp_heartbeat_owned-ops.jsonl"
        row = {"schema_version": "1.0", "aic": aic, "log_id": "heartbeat-one", "log_type": "heartbeat",
               "timestamp": datetime.fromtimestamp(time.time()-age, timezone.utc).isoformat(), "body": {"uptimeSeconds": 1}}
        path.write_text(json.dumps(row)+"\n", encoding="utf-8")
        return path

    def management_result(self, *, session="session", group="group", aic="owned-ops"):
        return GroupMgmtResult(id="status-one", sentAt=datetime.now(timezone.utc).isoformat(),
            senderId=aic, senderRole="partner", sessionId=session, groupId=group,
            status=GroupMemberStatus(connected=True, muted=False), dataItems=[])

    def local(self, directory, **options):
        directory = Path(directory)
        config = {"coordinator_aic": "owned-leader", "group_id": "group", "automatic_takeover": False,
            "term_journal_path": str(directory / "terms.sqlite"), "amp_directory": str(directory / "amp"),
            "participant_health_timeout_seconds": .005, **options}
        transport = LocalAipStdioTransport(config, directory / "transport")
        worker = LocalWorker({"name": "owned-ops", "role": "ops", "aic": "owned-ops"},
            SimpleNamespace(returncode=None, stdout=asyncio.StreamReader()),
            asyncio.get_running_loop().create_future(), None, tools=["ops.route_status"], state="ready")
        worker.ready.set_result({})
        transport.workers["owned-ops"] = worker
        transport.active_workers["ops"] = "owned-ops"
        transport.started = True
        transport.leader.start_task = AsyncMock(side_effect=ConnectionError("task channel lost"))
        transport.leader.get_partner_status = AsyncMock(side_effect=ConnectionError("management channel lost"))
        return transport, worker

    def wutong(self, directory, **options):
        directory = Path(directory)
        config = {"leader": {"aic": "owned-leader", "cert": "unused", "key": "unused"},
            "term_journal_path": str(directory / "terms.sqlite"), "automatic_takeover": False,
            "participant_health_timeout_seconds": .005, **options}
        with patch("incident.wutong_transport.AmpRuntime"):
            transport = WutongTransport(config, directory / "transport")
        transport.selected = {"ops": "owned-ops"}
        transport.session = SimpleNamespace(session_id="session", group_id="group", message_history=[])
        transport.runtime = SimpleNamespace(start_task=AsyncMock(side_effect=ConnectionError("task channel lost")),
            check_partner_status=AsyncMock(side_effect=ConnectionError("management channel lost")))
        return transport

    async def failed_call(self, transport):
        try:
            await transport.call(self.payload())
        except (TimeoutError, ConnectionError) as error:
            return error
        self.fail("fixture must produce a real transport failure")

    async def test_local_joint_evidence_and_exact_AIC(self):
        for aic, expected in (("owned-ops", True), ("other-agent", False)):
            with self.subTest(aic=aic), tempfile.TemporaryDirectory() as directory:
                transport, _ = self.local(directory)
                self.heartbeat(transport.amp_directory, aic=aic)
                error = await self.failed_call(transport)
                result = await transport.participant_health(self.payload(), error=error)
                self.assertEqual(result["confirmed"], expected)
                self.assertEqual(result["aic"], "owned-ops")
                self.assertEqual(result["evidence"]["management_outcome"], "no_reply")
                self.assertEqual(result["task_status"], "channel_lost")
                self.assertTrue(result["manual_required"])
                self.assertEqual(result["business_state"], "unknown")

    async def test_local_real_management_result_is_a_reply_not_publish_success(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, worker = self.local(directory, participant_health_timeout_seconds=1)
            self.heartbeat(transport.amp_directory)
            error = await self.failed_call(transport)
            async def reply(aic, *, session_id):
                message = self.management_result(session=session_id)
                worker.process.stdout.feed_data((message.model_dump_json()+"\n").encode())
                worker.process.stdout.feed_eof()
                await transport._read_worker("owned-ops", worker)
                return SimpleNamespace()
            transport.leader.get_partner_status = AsyncMock(side_effect=reply)
            result = await transport.participant_health(self.payload(), error=error)
            self.assertFalse(result["confirmed"])
            self.assertEqual(result["evidence"]["management_outcome"], "reply")
            self.assertEqual(result["participant_state"], "reachable")
            self.assertFalse(transport._management_pending)

    async def test_local_publish_only_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, _ = self.local(directory)
            self.heartbeat(transport.amp_directory)
            error = await self.failed_call(transport)
            transport.leader.get_partner_status = AsyncMock(return_value=SimpleNamespace())
            result = await transport.participant_health(self.payload(), error=error)
            self.assertTrue(result["confirmed"])
            self.assertEqual(result["evidence"]["management_outcome"], "timeout")
            self.assertFalse(transport._management_pending)

    async def test_local_deadline_is_recorded_from_actual_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, _ = self.local(directory)
            self.heartbeat(transport.amp_directory)
            transport.leader.start_task = AsyncMock(return_value=None)
            error = await self.failed_call(transport)
            self.assertIsInstance(error, TimeoutError)
            saved = transport._participant_failures[("incident", "logical")]
            self.assertGreaterEqual(saved["task"].observed_at, saved["task"].deadline)
            result = await transport.participant_health(self.payload(), error=error)
            self.assertEqual(result["task_status"], "deadline_expired")
            self.assertTrue(result["confirmed"])

    async def test_local_unadvertised_tool_does_not_become_participant_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, worker = self.local(directory)
            worker.tools = []
            with self.assertRaises(RuntimeError):
                await transport.call(self.payload())
            self.assertFalse(transport._participant_failures)

    async def test_explicit_wait_uses_real_heartbeat_expiry_and_late_reply(self):
        for late_reply in (False, True):
            with self.subTest(late_reply=late_reply), tempfile.TemporaryDirectory() as directory:
                transport, _ = self.local(directory, participant_health_wait_seconds=1)
                error = await self.failed_call(transport)
                self.heartbeat(transport.amp_directory, age=44.5)
                if late_reply:
                    async def delayed(aic, *, session_id):
                        future = transport._management_pending[session_id]["future"]
                        asyncio.get_running_loop().call_later(.02, lambda: future.set_result(time.time()))
                        return SimpleNamespace()
                    transport.leader.get_partner_status = AsyncMock(side_effect=delayed)
                result = await transport.participant_health(self.payload(), error=error)
                self.assertEqual(result["confirmed"], not late_reply)
                self.assertEqual(result["evidence"]["management_outcome"], "reply" if late_reply else "no_reply")

    async def test_missing_heartbeat_never_sleeps_or_confirms(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, _ = self.local(directory, participant_health_wait_seconds=50)
            error = await self.failed_call(transport)
            with patch("incident.local_transport.asyncio.sleep", AsyncMock(side_effect=AssertionError("no heartbeat to await"))):
                result = await transport.participant_health(self.payload(), error=error)
            self.assertFalse(result["confirmed"])
            self.assertEqual(result["evidence"]["heartbeat_state"], "unknown")

    async def test_wutong_requires_explicit_target_logs_and_fresh_exact_reply(self):
        for configured, fresh_reply in ((False, False), (True, False), (True, True)):
            with self.subTest(configured=configured, fresh_reply=fresh_reply), tempfile.TemporaryDirectory() as directory:
                heartbeat = self.heartbeat(Path(directory)/"amp")
                transport = self.wutong(directory, participant_amp_paths={"owned-ops": [str(heartbeat)]} if configured else {})
                transport.session.message_history.append(self.management_result())  # Old membership cache is not a reply.
                error = await self.failed_call(transport)
                async def publish(aic, *, session_id):
                    if fresh_reply:
                        transport.session.message_history.append(self.management_result(session=session_id))
                    return SimpleNamespace()
                transport.runtime.check_partner_status = AsyncMock(side_effect=publish)
                result = await transport.participant_health(self.payload(), error=error)
                self.assertEqual(result["confirmed"], configured and not fresh_reply)
                self.assertEqual(result["evidence"]["management_outcome"], "reply" if fresh_reply else "timeout")
                if not configured:self.assertEqual(result["evidence"]["heartbeat_state"], "unknown")

    async def test_wutong_does_not_consume_other_target_or_group_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = self.heartbeat(Path(directory)/"amp")
            transport = self.wutong(directory, participant_amp_paths={"owned-ops": [str(heartbeat)]})
            error = await self.failed_call(transport)
            async def wrong(aic, *, session_id):
                transport.session.message_history.extend([self.management_result(group="other"), self.management_result(aic="other")])
            transport.runtime.check_partner_status = AsyncMock(side_effect=wrong)
            result = await transport.participant_health(self.payload(), error=error)
            self.assertTrue(result["confirmed"])
            self.assertEqual(result["evidence"]["management_outcome"], "timeout")

    async def test_invalid_path_or_config_returns_unknown_without_leaking(self):
        for options in ({"participant_amp_paths": {"owned-ops": ["private/application.env"]}},
                        {"participant_health_wait_seconds": 61}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                transport = self.wutong(directory, **options)
                error = await self.failed_call(transport)
                with patch("incident.wutong_transport.AmpFactStore.load_jsonl") as load:
                    result = await transport.participant_health(self.payload(), error=error)
                    load.assert_not_called()
                self.assertFalse(result["confirmed"])
                self.assertTrue(result["manual_required"])
                self.assertNotIn("application.env", json.dumps(result))

    async def test_error_or_logical_identity_cannot_be_substituted(self):
        for mode in ("local", "wutong"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                transport = self.local(directory)[0] if mode == "local" else self.wutong(directory)
                error = await self.failed_call(transport)
                for payload, replacement in ((self.payload(), ConnectionError()),
                    ({**self.payload(), "logical_task_id": "other"}, error)):
                    result = await transport.participant_health(payload, error=replacement)
                    self.assertFalse(result["confirmed"])
                    self.assertEqual(result["task_status"], "unknown")

    async def test_takeover_failure_preserves_original_channel_error(self):
        for mode in ("local", "wutong"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                transport = self.local(directory, automatic_takeover=True)[0] if mode == "local" else self.wutong(directory, automatic_takeover=True)
                transport._takeover = AsyncMock(side_effect=RuntimeError("replacement unavailable"))
                error = await self.failed_call(transport)
                self.assertIsInstance(error, ConnectionError)
                self.assertIsInstance(error.__cause__, RuntimeError)
                self.assertIs(transport._participant_failures[("incident", "logical")]["error"], error)
                result = await transport.participant_health(self.payload(), error=error.__cause__)
                self.assertFalse(result["confirmed"])

    async def test_completed_then_local_write_failure_is_not_participant_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.wutong(directory, automatic_takeover=True)
            product = {"schema_version": "ifc/1.0", "incident_id": "incident",
                "logical_task_id": "logical", "executor_aic": "owned-ops", "status": "ok"}
            timestamp = datetime.now(timezone.utc).isoformat()
            async def start(session, *, task_id, **kwargs):
                transport.session.message_history.append(TaskResult(id="result-one", sentAt=timestamp,
                    senderId="owned-ops", senderRole="partner", sessionId=session, groupId="group",
                    taskId=task_id, status=TaskStatus(state=TaskState.AwaitingCompletion, stateChangedAt=timestamp),
                    products=[Product(id="product", dataItems=[StructuredDataItem(data=product)])]))
            transport.runtime.start_task = AsyncMock(side_effect=start)
            transport.runtime.complete_task = AsyncMock()
            transport._takeover = AsyncMock()
            with patch("incident.wutong_transport.native.wait_for_state", AsyncMock()) as wait, \
                    patch.object(Path, "write_text", side_effect=OSError("local disk unavailable")):
                with self.assertRaisesRegex(RuntimeError, "local AIP evidence persistence failed"):
                    await transport.call(self.payload())
            self.assertEqual(wait.await_count, 2)
            self.assertEqual(wait.await_args_list[-1].args[3], TaskState.Completed)
            transport.runtime.complete_task.assert_awaited_once()
            transport._takeover.assert_not_awaited()
            self.assertFalse(transport._participant_failures)


if __name__ == "__main__":unittest.main()
