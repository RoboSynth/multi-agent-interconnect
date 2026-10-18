"""Offline F19 ownership/protocol/outcome checks; no worker or HTTP service starts."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.participant_failure_experiment import (assert_owned_ops, build_config, inspect_outcome,
    main, management_control, outcome_passed, public_health, public_order_url, wait_for_heartbeat)
from incident.local_worker import bind_stdio_publisher, parse_bound_command, validate_experiment_crash
from acps_sdk.aip import GroupMgmtCommand, GroupMgmtCommandType, TaskCommand, TaskCommandType
from acps_sdk.aip.aip_group_partner import GroupPartnerMqClient, PartnerGroupState


class ParticipantFailurePreparationTests(unittest.TestCase):
    def test_config_has_only_owned_readonly_ops_and_independent_verifier(self):
        with tempfile.TemporaryDirectory() as folder:
            config, policy, bridge = build_config(Path(folder), "owned-offline", "http://127.0.0.1:28088")
        self.assertFalse(config["automatic_takeover"])
        self.assertEqual([w["role"] for w in config["workers"]], ["ops", "verification"])
        self.assertEqual(config["workers"][0]["crash_point"], "after_observation")
        self.assertEqual(set(policy["tools"]), {"ops.route_status"})
        self.assertEqual(policy["tools"]["ops.route_status"]["risk"], "read")
        self.assertEqual(bridge["env_files"], [])
        self.assertEqual(bridge["servers"]["public-health"]["env_names"], [])
        self.assertEqual(config["participant_health_wait_seconds"], 50)
        self.assertEqual(config["participant_heartbeat_ttl_seconds"], 45)
        self.assertEqual(config["participant_access_ttl_seconds"], 60)
        self.assertNotIn("F19", json.dumps([config, policy, bridge]))

    def test_external_native_and_credential_urls_rejected(self):
        for url in ("https://example.org", "http://127.0.0.1:8088", "http://user:pass@localhost:28088",
                    "http://127.0.0.1:28088/path", "http://127.0.0.1:28088?token=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_order_url(url)

    def test_process_handle_ownership_not_pid_equality(self):
        process = SimpleNamespace(pid=123)
        worker = SimpleNamespace(process=process, spec={"role": "ops", "aic": "local-owned"})
        transport = SimpleNamespace(workers={"owned-ops": worker}, config={"workers": [{"aic": "local-owned"}]})
        self.assertIs(assert_owned_ops(transport, (worker, process)), process)
        with self.assertRaises(ValueError):
            assert_owned_ops(transport, (worker, SimpleNamespace(pid=123)))

    def test_existing_database_hooks_and_only_explicit_ops_read_hook(self):
        args = SimpleNamespace(role="database", experiment_id="F15-offline", crash_tool="db.restore_writes")
        for point in ("after_observation", "before_modification", "after_applied"):
            args.crash_point = point
            validate_experiment_crash(args)
        args = SimpleNamespace(role="ops", experiment_id="F19-offline", crash_tool="ops.route_status", crash_point="after_observation")
        validate_experiment_crash(args)
        for change in ({"experiment_id": None}, {"role": "application"}, {"crash_tool": "ops.restart"},
                       {"crash_point": "after_applied"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_experiment_crash(SimpleNamespace(**{**vars(args), **change}))

    def test_business_health_does_not_prove_participant_recovery(self):
        state = {"status": "needs_attention", "tasks": [], "approvals": [], "model_calls": 0, "tokens": 0,
                 "participant_health": [{"confirmed": True, "participant_state": "unreachable", "task_status": "channel_lost"}],
                 "result": {"participant_failure_confirmed": True, "participant_recovered": False,
                    "incident_resolved": False, "manual_required": True,
                    "order_observation": {"duration_seconds": 30, "completed_workflows": 10,
                                          "unknown": 0, "unresolved_intents": 0, "passed": True}}}
        self.assertTrue(outcome_passed(inspect_outcome(state)))
        state["result"]["participant_recovered"] = True
        self.assertFalse(outcome_passed(inspect_outcome(state)))
        state["result"]["participant_recovered"] = False
        state["participant_health"][0]["task_status"] = "deadline_expired"
        self.assertFalse(outcome_passed(inspect_outcome(state)))


class ParticipantLocalProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.args = SimpleNamespace(aic="local-ops", coordinator_aic="local-leader", group_id="local-group")

    def management(self, **overrides):
        return GroupMgmtCommand(id="management-command", sentAt="2026-10-17T00:00:00Z",
            senderId="local-leader", senderRole="leader", groupId="local-group",
            sessionId="health-probe-1", mentions=["local-ops"], command=GroupMgmtCommandType.GET_STATUS,
            **overrides)

    async def test_real_official_get_status_echoes_bound_probe_session(self):
        command = parse_bound_command(self.management().model_dump_json(), self.args)
        client = GroupPartnerMqClient("local-ops")
        client._group_id, client._state = "local-group", PartnerGroupState.JOINED
        publish = AsyncMock()
        bind_stdio_publisher(client, publish)
        await client._handle_mgmt_command(command)
        response = publish.await_args.args[0]
        self.assertEqual(response.type, "group-mgmt-result")
        self.assertEqual(response.sessionId, "health-probe-1")
        self.assertTrue(response.status.connected)

    async def test_management_wrong_identity_and_non_get_are_rejected(self):
        original = self.management().model_dump(mode="json")
        for changes in ({"senderId": "other"}, {"groupId": "other"}, {"sessionId": None},
                        {"mentions": "all"}, {"command": GroupMgmtCommandType.MUTE.value}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_bound_command(json.dumps({**original, **changes}), self.args)

    async def test_task_command_keeps_same_local_binding(self):
        command = TaskCommand(id="task-command", sentAt="2026-10-17T00:00:00Z",
            senderId="local-leader", senderRole="leader", groupId="local-group",
            sessionId="incident", taskId="task", mentions=["local-ops"], command=TaskCommandType.Get)
        parsed = parse_bound_command(command.model_dump_json(), self.args)
        self.assertIsInstance(parsed, TaskCommand)
        with self.assertRaises(ValueError):
            parse_bound_command(command.model_copy(update={"mentions": ["other"]}).model_dump_json(), self.args)

    async def test_http_adapter_only_reports_public_http_facts(self):
        import httpx
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={"ok": True, "api_version": "v2"})))
        with patch("httpx.AsyncClient", return_value=client) as constructor:
            facts = await public_health("http://127.0.0.1:28088")
        self.assertEqual(facts["public_api_version"], "v2")
        self.assertNotIn("route_version", facts)
        self.assertNotIn("container_state", facts)
        self.assertFalse(constructor.call_args.kwargs["trust_env"])

    async def test_real_mcp_catalog_exposes_only_the_readonly_public_probe(self):
        from mcp.server.fastmcp import FastMCP
        with patch.object(FastMCP, "run", autospec=True) as run:
            with patch("sys.argv", ["participant_failure_experiment.py", "--mcp-observer"]):
                self.assertEqual(main(), 0)
        server = run.call_args.args[0]
        tools = await server.list_tools()
        self.assertEqual([tool.name for tool in tools], ["public_health"])

    async def test_management_control_uses_real_transport_api_and_releases_its_probe(self):
        from incident.coordinator.amp_facts import ManagementStatusEvidence
        worker = object()
        future = asyncio.get_running_loop().create_future()
        future.set_result(2.0)
        transport = SimpleNamespace(_management_pending={"probe": {"future": future}},
            _participant_management=AsyncMock(return_value=(
                ManagementStatusEvidence("local-ops", "reply", 1.0, 2.0), "reply", "probe")))
        record = await management_control(transport, worker)
        self.assertEqual(record["outcome"], "reply")
        transport._participant_management.assert_awaited_once_with(worker, timeout=2)
        self.assertEqual(transport._management_pending, {})

    async def test_restarted_heartbeat_wait_cannot_reuse_old_record(self):
        stamp = datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            rows = [{"aic": "local-ops", "log_type": "heartbeat", "timestamp": value}
                    for value in ("2026-10-17T00:00:00Z", "2026-10-17T00:00:01Z")]
            (Path(folder) / "amp_heartbeat_owned-ops.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            record = await wait_for_heartbeat(folder, "local-ops", after=stamp + .5)
        self.assertEqual(record["timestamp"], "2026-10-17T00:00:01Z")


if __name__ == "__main__":
    unittest.main()
