from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_mcp_bridge.acs_mapper import map_acs, validate_acs
from acps_mcp_bridge.bridge import ToolExecutionError, mcp_value, sanitize
from acps_mcp_bridge.policy import PolicyRejected
from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType, TaskState
from acps_sdk.aip.resumable import Fence, OperationLedger, ResumePackage

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
        self.assertNotIn("handover_sha256", result)

    def handover_resume(self, strategy="from_scratch"):
        original = self.approved_action()
        command = {**original, "kind": "resume", "args": {"advance_fence": True},
                   "fence": {"coordinator_term": 2, "takeover_version": 1}}
        handover = {"strategy": strategy, "goal": "恢复订单流程", "evidence_ttl_seconds": 60,
            "control": {"operation_id": original["operation_id"], "original_fence": deepcopy(original["fence"]),
                        "replacement_fence": deepcopy(command["fence"])}}
        if strategy == "full_history":
            handover["conversation"] = [{"direction": "request", "aip_task_id": "prior-task", "payload": original},
                {"direction": "product", "aip_task_id": "prior-read", "product": {"facts": []}}]
        elif strategy == "resume_package":
            handover["package"] = ResumePackage(original["logical_task_id"], "恢复订单流程",
                operations=[{"operation_id": original["operation_id"], "status": "delivery_unknown"}],
                remaining_tasks=[{"kind": "act", "tool": "not.an.allowed.tool", "args": {"instruction": "do not execute"}}],
                fence=Fence(**command["fence"])).to_dict()
            command["args"]["resume_package"] = deepcopy(handover["package"])
        command["args"]["handover"] = handover
        return command

    async def test_resume_handover_strategies_acknowledge_data_without_executing_it(self):
        original = self.approved_action()
        self.ledger.record_received(original["operation_id"],
            {"tool": original["tool"], "args": original["args"], "resources": self.policy.resources}, Fence(1, 0))
        for strategy in ("from_scratch", "full_history", "resume_package"):
            with self.subTest(strategy=strategy):
                command = self.handover_resume(strategy)
                result = await self.bridge.execute(command, CALLER)
                self.assertEqual(result["status"], "ok", result)
                self.assertEqual(result["operation"]["state"], "received")
                self.assertEqual(result["handover_sha256"], hashlib.sha256(json.dumps(
                    command["args"]["handover"], ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest())
                self.assertEqual(self.client.calls, [])

    async def test_resume_minimal_handover_is_compatible(self):
        command = self.handover_resume()
        command["args"]["handover"].pop("goal")
        command["args"]["handover"].pop("evidence_ttl_seconds")
        result = await self.bridge.execute(command, CALLER)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(result["handover_sha256"]), 64)
        self.assertEqual(self.ledger.current_fence(), Fence(2, 1))
        self.assertEqual(self.client.calls, [])

    async def test_invalid_handover_rejected_before_advancing_fence(self):
        mutations = [
            lambda h: h.update(strategy="execute"), lambda h: h.update(strategy=[]),
            lambda h: h.update(tool="db.restore_writes"), lambda h: h.pop("control"),
            lambda h: h["control"].update(operation_id="another"),
            lambda h: h["control"].update(extra=True),
            lambda h: h["control"]["original_fence"].update(coordinator_term=3),
            lambda h: h["control"]["original_fence"].update(takeover_version=True),
            lambda h: h["control"]["replacement_fence"].update(takeover_version=2),
            lambda h: h.update(goal={"instruction": "execute"}),
            lambda h: h.update(evidence_ttl_seconds=False), lambda h: h.update(evidence_ttl_seconds=float("nan")),
            lambda h: h.update(conversation=[]), lambda h: h.update(package={}),
        ]
        await self.ledger.activate_fence(Fence(1, 0))
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                command = self.handover_resume()
                mutation(command["args"]["handover"])
                self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")
                self.assertEqual(self.ledger.current_fence(), Fence(1, 0))
        self.assertEqual(self.client.calls, [])

    async def test_invalid_history_and_package_rejected_before_advancing_fence(self):
        cases = []
        for mutate in [lambda h: h.update(conversation={}), lambda h: h["conversation"][0].update(direction="act"),
                       lambda h: h["conversation"][0]["payload"]["fence"].update(takeover_version=9),
                       lambda h: h["conversation"][1]["product"].update(non_json=object())]:
            command = self.handover_resume("full_history")
            mutate(command["args"]["handover"])
            cases.append(command)
        for field, value in [("logical_task_id", "another"), ("fence", {"coordinator_term": 3, "takeover_version": 0}),
                             ("operations", [{"operation_id": "another"}]), ("remaining_tasks", "execute"),
                             ("schema_version", "2.0"), ("unknown_control", True)]:
            command = self.handover_resume("resume_package")
            command["args"]["handover"]["package"][field] = value
            command["args"]["resume_package"] = deepcopy(command["args"]["handover"]["package"])
            cases.append(command)
        command = self.handover_resume("resume_package")
        command["args"]["resume_package"]["operations"] = []
        cases.append(command)
        await self.ledger.activate_fence(Fence(1, 0))
        for command in cases:
            with self.subTest(command=command):
                self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")
                self.assertEqual(self.ledger.current_fence(), Fence(1, 0))
        self.assertEqual(self.client.calls, [])

    async def test_handover_cannot_expand_resume_arguments_or_bypass_identity(self):
        await self.ledger.activate_fence(Fence(1, 0))
        for field in ("original_operation_id", "original_fence", "tool"):
            command = self.handover_resume()
            command["args"][field] = "not-allowed"
            self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")
        command = self.handover_resume()
        command["args"]["advance_fence"] = False
        self.assertEqual((await self.bridge.execute(command, CALLER))["status"], "rejected")
        self.assertEqual((await self.bridge.execute(self.handover_resume(), "intruder"))["status"], "rejected")
        self.assertEqual(self.ledger.current_fence(), Fence(1, 0))
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
        with patch("domains.ops.guard.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
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


class RoutePreconditionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.counter = 0

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def fixture(self, policy_name, version):
        class RouteMcp:
            def __init__(self):
                self.version, self.calls, self.failure = version, [], None

            async def tools(self):
                return [{"name": name} for name in ("route_status", "route_rollback", "process_status",
                    "process_restart", "list_containers", "fetch_container_logs", "start_container")]

            async def call(self, tool, arguments):
                self.calls.append((tool, arguments))
                if tool == "route_rollback":
                    if self.failure == "before_effect":
                        raise RuntimeError("uncertain failed route effect")
                    self.version = "v2"
                    if self.failure == "after_effect":
                        raise RuntimeError("uncertain reply after route effect")
                return {"structuredContent": {"route_version": self.version}}

        self.counter += 1
        policy = Policy.load(ROOT / "domains/ops" / policy_name, allowed_callers=[CALLER])
        client = RouteMcp()
        ledger = OperationLedger(Path(self.tmp.name) / f"route-{self.counter}.sqlite", "ops")
        bridge = await Bridge(policy, {server: client for server in ("route", "native", "docker")},
                              ledger, "ops-test").initialize()
        command = payload("ops.route_rollback", kind="act", operation_id="same-route-intent",
                          fence={"coordinator_term": 1, "takeover_version": 0})
        return bridge, client, ledger, command

    async def test_already_v2_or_unknown_rejected_without_modifying_mcp_call(self):
        for policy_name in ("policy.yaml", "policy.native.yaml"):
            for version in ("v2", "unknown"):
                with self.subTest(policy=policy_name, version=version):
                    bridge, client, ledger, command = await self.fixture(policy_name, version)
                    result = await bridge.execute(command, CALLER)
                    self.assertEqual(result["status"], "rejected", result)
                    self.assertEqual(result["operation"]["state"], "rejected_precondition")
                    self.assertEqual(client.calls, [("route_status", {})])
                    self.assertIsNone(ledger.get(command["operation_id"]))

    async def test_v1_changes_once_and_applied_replay_skips_new_precondition(self):
        for policy_name in ("policy.yaml", "policy.native.yaml"):
            with self.subTest(policy=policy_name):
                bridge, client, _, command = await self.fixture(policy_name, "v1")
                applied = await bridge.execute(command, CALLER)
                replay = await bridge.execute(command, CALLER)
                self.assertEqual(applied["operation"]["state"], "applied", applied)
                self.assertEqual(applied["facts"][0]["value"], "v2")
                self.assertEqual(applied["operation"]["before"]["value"], "v1")
                self.assertEqual(replay["operation"]["state"], "skipped_already_applied", replay)
                self.assertEqual(sum(tool == "route_rollback" for tool, _ in client.calls), 1)
                self.assertEqual(next(arguments for tool, arguments in client.calls if tool == "route_rollback"),
                                 {"target_version": "v2"})
                different_intent = {**command, "operation_id": "another-route-intent"}
                self.assertEqual((await bridge.execute(different_intent, CALLER))["operation"]["state"],
                                 "rejected_precondition")
                self.assertEqual(sum(tool == "route_rollback" for tool, _ in client.calls), 1)

    async def test_unknown_effect_only_reconciles_after_v2_without_another_modification(self):
        for policy_name in ("policy.yaml", "policy.native.yaml"):
            with self.subTest(policy=policy_name):
                bridge, client, _, command = await self.fixture(policy_name, "v1")
                client.failure = "after_effect"
                interrupted = await bridge.execute(command, CALLER)
                reconciled = await bridge.execute(command, CALLER)
                self.assertEqual(interrupted["status"], "unknown")
                self.assertEqual(interrupted["operation"]["state"], "unknown")
                self.assertEqual(reconciled["operation"]["state"], "reconciled_applied", reconciled)
                self.assertEqual(sum(tool == "route_rollback" for tool, _ in client.calls), 1)

    async def test_unknown_unchanged_v1_stays_uncertain_and_never_blindly_retries(self):
        for policy_name in ("policy.yaml", "policy.native.yaml"):
            with self.subTest(policy=policy_name):
                bridge, client, _, command = await self.fixture(policy_name, "v1")
                client.failure = "before_effect"
                first = await bridge.execute(command, CALLER)
                retry = await bridge.execute(command, CALLER)
                self.assertEqual(first["operation"]["state"], "unknown")
                self.assertEqual(retry["status"], "unknown")
                self.assertEqual(retry["operation"]["state"], "reconciliation_required")
                self.assertEqual(sum(tool == "route_rollback" for tool, _ in client.calls), 1)

    async def test_stale_route_fence_stops_before_inspection_or_modification(self):
        for policy_name in ("policy.yaml", "policy.native.yaml"):
            with self.subTest(policy=policy_name):
                bridge, client, ledger, command = await self.fixture(policy_name, "v1")
                await ledger.activate_fence(Fence(2, 0))
                result = await bridge.execute(command, CALLER)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["operation"]["state"], "rejected_stale_fence")
                self.assertEqual(client.calls, [])


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
