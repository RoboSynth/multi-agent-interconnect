from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_mcp_bridge.acs_mapper import map_acs, validate_acs
from acps_mcp_bridge.bridge import ToolExecutionError, mcp_value, sanitize
from acps_mcp_bridge.policy import PolicyRejected
from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType, TaskState
from acps_sdk.aip.resumable import Fence, OperationLedger

CALLER = "coordinator-AIC"


def payload(tool="db.read_only_status", *, kind="observe", **extras):
    return {"schema_version": "ifc/1.0", "incident_id": "inc-test", "logical_task_id": "lt-test",
            "kind": kind, "tool": tool, "args": {}, **extras}


class FakeMcp:
    def __init__(self):
        self.calls = []
        self.read_only = True

    async def tools(self):
        return [{"name": n, "description": n, "inputSchema": {"type": "object"}}
                for n in ("analyze_db_health", "execute_sql")]

    async def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if "restore_writes" in arguments.get("sql", ""):
            self.read_only = False
        return {"content": [{"type": "text", "text": repr([{"read_only": self.read_only}])}]}


class FakePartner:
    _identity_binding_enabled = True
    partner_aic = "database-AIC"
    group_id = "group-test"

    def __init__(self):
        self.events = []

    def set_command_handler(self, handler):
        self.handler = handler

    def __getattr__(self, method):
        async def call(*args, **kwargs):
            self.events.append((method, args, kwargs))
        return call


class BridgePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.authority = ApprovalAuthority("test-approval-secret-" * 3)
        self.policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER],
                                  approval_verifier=self.authority.verify)
        self.client = FakeMcp()
        self.audit = []
        self.ledger_path = Path(self.tmp.name) / "shared.sqlite"
        self.ledger = OperationLedger(self.ledger_path, "orders")
        self.bridge = await Bridge(self.policy, {"postgres": self.client}, self.ledger,
                                    "database-AIC", audit=lambda event: self.audit.append(event)).initialize()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def approved_action(self):
        command = payload("db.restore_writes", kind="act", operation_id="op-restore",
                          fence={"coordinator_term": 1, "takeover_version": 0})
        command["approval"] = self.authority.issue(command, CALLER, approved_by="workbench")
        return command

    async def test_unknown_caller_rejected_and_audited(self):
        result = await self.bridge.execute(payload(), "unknown-AIC")
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(self.audit), 1)
        self.assertEqual(self.client.calls, [])

    async def test_arbitrary_sql_is_never_forwarded(self):
        for command in [payload("execute_sql"), payload(args={"sql": "DROP DATABASE orders"}),
                        payload("db.terminate_blocker", kind="act", args={"pid": "1); DROP TABLE orders"})]:
            self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")
        self.assertEqual(self.client.calls, [])
        self.assertEqual(len(self.audit), 3)

    async def test_kind_cannot_disguise_write_as_read(self):
        command = self.approved_action()
        command["kind"] = "observe"
        self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")

    async def test_self_declared_approval_rejected(self):
        command = self.approved_action()
        command["approval"] = {"approved_by": "workbench", "approved_at": "now"}
        self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")

    async def test_tampered_approval_rejected(self):
        command = self.approved_action()
        command["operation_id"] = "other-operation"
        self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")

    async def test_write_requires_fence_and_operation(self):
        for field in ("operation_id", "fence"):
            command = self.approved_action()
            command.pop(field)
            self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")

    async def test_primary_and_backup_use_same_ledger(self):
        command = self.approved_action()
        first = await self.bridge.execute(command, CALLER)
        other = Bridge(self.policy, {"postgres": self.client}, OperationLedger(self.ledger_path, "orders"), "backup-AIC")
        second = await other.execute(command, CALLER)
        self.assertEqual(first["operation"]["state"], "applied")
        self.assertEqual(second["operation"]["state"], "skipped_already_applied")
        self.assertEqual(sum("restore_writes" in args.get("sql", "") for _, args in self.client.calls), 1)
        self.assertIs(first["facts"][0]["value"], False)

    async def test_unknown_effect_reconciles_by_real_postcondition(self):
        command = self.approved_action()
        async def interrupted_effect():
            self.client.read_only = False
            raise RuntimeError("reply interrupted after effect")
        await self.ledger.execute(command["operation_id"],
            {"tool": command["tool"], "args": command["args"], "resources": self.policy.resources},
            Fence(**command["fence"]), interrupted_effect)
        result = await self.bridge.execute(command, CALLER)
        self.assertEqual(result["operation"]["state"], "reconciled_applied")
        self.assertIs(result["facts"][0]["value"], False)
        self.assertFalse(any("restore_writes" in args.get("sql", "") for _, args in self.client.calls))

    async def test_resume_advances_fence_without_executing_received(self):
        command = self.approved_action()
        parameters = {"tool": command["tool"], "args": command["args"], "resources": self.policy.resources}
        self.ledger.record_received(command["operation_id"], parameters, Fence(1, 0))
        resumed = {**command, "kind": "resume", "args": {"advance_fence": True, "resume_package": {}},
                   "fence": {"coordinator_term": 2, "takeover_version": 1}}
        result = await self.bridge.execute(resumed, CALLER)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["operation"]["state"], "received")
        self.assertEqual(result["active_fence"], {"coordinator_term": 2, "takeover_version": 1})
        self.assertEqual(self.client.calls, [])

    async def test_resume_rejects_old_fence_and_unauthorized_caller(self):
        await self.ledger.activate_fence(Fence(2, 0))
        command = payload("db.restore_writes", kind="resume", operation_id="op-no-effect",
                          args={"advance_fence": True}, fence={"coordinator_term": 1, "takeover_version": 0})
        result = await self.bridge.execute(command, CALLER)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["operation"]["state"], "rejected_stale_fence")
        command["fence"]["coordinator_term"] = 99
        self.assertEqual((await self.bridge.execute(command, "intruder"))["status"], "rejected")
        self.assertEqual(self.ledger.current_fence(), Fence(2, 0))

    async def test_resume_unknown_only_inspects_and_reconciles(self):
        command = self.approved_action()
        async def interrupted_effect():
            self.client.read_only = False
            raise RuntimeError("interrupted after effect")
        await self.ledger.execute(command["operation_id"],
            {"tool": command["tool"], "args": {}, "resources": self.policy.resources}, Fence(1, 0), interrupted_effect)
        resumed = {**command, "kind": "resume", "args": {"advance_fence": True},
                   "fence": {"coordinator_term": 2, "takeover_version": 1}}
        result = await self.bridge.execute(resumed, CALLER)
        self.assertEqual(result["operation"]["state"], "reconciled_applied")
        self.assertIs(result["facts"][0]["value"], False)
        self.assertFalse(any("restore_writes" in args.get("sql", "") for _, args in self.client.calls))

    async def test_old_fence_is_rejected_with_audit(self):
        await self.ledger.activate_fence(Fence(2, 0))
        result = await self.bridge.execute(self.approved_action(), CALLER)
        self.assertEqual(result["operation"]["state"], "rejected_stale_fence")
        self.assertEqual(self.audit[-1]["status"], "rejected")
        self.assertEqual(self.client.calls, [])

    async def test_read_returns_normalized_fact_and_hypothesis(self):
        result = await self.bridge.execute(payload(), CALLER)
        self.assertIs(result["facts"][0]["value"], True)
        self.assertEqual(result["facts"][0]["key"], "read_only")
        self.assertEqual(result["local_hypotheses"][0]["cause"], "db_read_only")
        self.assertNotIn("sql", json.dumps(result))

    async def test_describe_inventory_and_acs_official_schema(self):
        described = await self.bridge.execute(payload(kind="describe"), CALLER)
        self.assertEqual(len(described["description"]["tools"]), 5)
        base = json.loads((ROOT / "integration/incident/database.submission.acs.json").read_text(encoding="utf-8"))
        mapped = map_acs(base, self.policy, self.bridge.inventory)
        self.assertEqual({s["id"] for s in mapped["skills"]}, {"db.observe", "db.act"})
        validated = validate_acs(mapped)
        self.assertTrue(validated["official_registry_schema_valid"], validated)
        self.assertTrue(validated["sdk_schema_valid"], validated)

    async def test_rate_limit(self):
        self.policy.document["rate_limit"] = {"window_seconds": 60, "max_calls": 1}
        self.assertEqual((await self.bridge.execute(payload(), CALLER))["status"], "ok")
        self.assertEqual((await self.bridge.execute(payload(), CALLER))["status"], "rejected")

    async def test_binding_requires_identity_validation(self):
        partner = FakePartner()
        partner._identity_binding_enabled = False
        with self.assertRaises(ValueError):
            self.bridge.bind_partner(partner)

    async def test_real_aip_models_product_and_start_replay(self):
        partner = FakePartner()
        handler = self.bridge.bind_partner(partner)
        command = TaskCommand(id="msg-test", sentAt="2026-10-17T00:00:00Z", senderRole="leader", senderId=CALLER,
            groupId="group-test", sessionId="session-test", taskId="task-test", command=TaskCommandType.Start,
            dataItems=[StructuredDataItem(data=payload())])
        first = await handler(command, True)
        replay = await handler(command, True)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(replay, first)
        self.assertEqual(len(self.client.calls), 1)
        submission = next(e for e in partner.events if e[0] == "submit_for_completion")
        self.assertIsInstance(submission[1][2][0].dataItems[0], StructuredDataItem)
        self.assertEqual(partner.events[-1][0], "send_task_result")

    async def test_start_returns_business_rejection_to_access_middleware(self):
        partner = FakePartner()
        handler = self.bridge.bind_partner(partner)
        command = TaskCommand(id="msg-denied", sentAt="2026-10-17T00:00:00Z", senderRole="leader", senderId="intruder",
            groupId="group-test", sessionId="session-test", taskId="task-denied", command=TaskCommandType.Start,
            dataItems=[StructuredDataItem(data=payload())])
        result = await handler(command, True)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(partner.events[-1][0], "submit_for_completion")

    async def test_terminate_nonblocking_pid_rejected_before_modification(self):
        command = payload("db.terminate_blocker", kind="act", args={"pid": 12345}, operation_id="op-not-blocker",
                          fence={"coordinator_term": 1, "takeover_version": 0})
        command["approval"] = self.authority.issue(command, CALLER, approved_by="workbench")
        result = await self.bridge.execute(command, CALLER)
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(any("incident_ops.terminate_blocker" in args.get("sql", "") for _, args in self.client.calls))

    async def test_container_guard_denies_without_docker(self):
        from domains.ops.guard import labeled_container
        with self.assertRaises(PolicyRejected):
            await labeled_container("a-container-that-does-not-exist")

    def test_postgres_text_errors_and_python_rows(self):
        self.assertEqual(mcp_value({"content": [{"type": "text", "text": "[{'read_only': True}]"}]}), [{"read_only": True}])
        self.assertEqual(mcp_value({"structuredContent": {"result": [{"type": "text", "text": "[{'read_only': False}]"}]}}), [{"read_only": False}])
        with self.assertRaises(ToolExecutionError):
            mcp_value({"content": [{"type": "text", "text": "Error: permission denied"}]})
        with self.assertRaises(ToolExecutionError):
            mcp_value({"isError": True, "content": []})

    def test_credentials_are_scrubbed(self):
        value = sanitize({"password": "s", "logs": "postgresql://u:p@host/db token=abc", "more": "exact-secret"}, ["exact-secret"])
        self.assertNotIn("u:p", json.dumps(value))
        self.assertNotIn("abc", json.dumps(value))
        self.assertEqual(value["more"], "[REDACTED]")


class RealStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_sdk_tools_list_call_and_durable_replay(self):
        config = ServerConfig(sys.executable, [str(ROOT / "tests/fixtures/bridge_mcp_server.py")])
        with tempfile.TemporaryDirectory() as tmp:
            async with McpStdioClient(config) as client:
                authority = ApprovalAuthority("stdio-test-secret-" * 4)
                policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER],
                                     approval_verifier=authority.verify)
                bridge = await Bridge(policy, {"postgres": client}, OperationLedger(Path(tmp) / "ledger.sqlite"), "db").initialize()
                self.assertIn("execute_sql", [tool["name"] for tool in await client.tools()])
                before = await bridge.execute(payload(), CALLER)
                self.assertIs(before["facts"][0]["value"], True)
                command = payload("db.restore_writes", kind="act", operation_id="op-stdio",
                                  fence={"coordinator_term": 1, "takeover_version": 0})
                command["approval"] = authority.issue(command, CALLER, approved_by="unit-test")
                self.assertEqual((await bridge.execute(command, CALLER))["operation"]["state"], "applied")
                self.assertEqual((await bridge.execute(command, CALLER))["operation"]["state"], "skipped_already_applied")
                health = mcp_value(await client.call("analyze_db_health", {}))
                self.assertEqual(health["writes"], 1)


if __name__ == "__main__":
    unittest.main()
