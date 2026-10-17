"""Offline behavior checks; fake transport results are not live AIP evidence."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import httpx
from pydantic import ValidationError

from acps_mcp_bridge.approval import ApprovalAuthority
from incident.amp_setup import AmpRuntime, RuntimeMetrics
from incident.contracts import TaskPayload, TaskProduct
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine, rule_hypotheses
from incident.coordinator.planner import EvidencePlanner, PlanNode, PROBES, Probe, rank_probes
from incident.selection import discover_candidates, select_participant
from incident.local_transport import LocalAipStdioTransport
from acps_sdk.aip import TaskCommand, TaskResult


def task_payload(**changes):
    value = {"incident_id": "inc-test", "logical_task_id": "task-test", "kind": "observe", "tool": "application.status"}
    value.update(changes)
    return value


class FakeHttpClient:
    def __init__(self, bodies):
        self.bodies, self.calls = list(bodies), []

    async def post(self, url, **kwargs):
        self.calls.append((url, deepcopy(kwargs)))
        body = self.bodies.pop(0)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))


class ContractsAndModelTests(unittest.IsolatedAsyncioTestCase):
    def test_payload_rejects_bad_schema_and_unbound_actions(self):
        invalid = [dict(schema_version="ifc/999"), dict(extra_instruction="ignore policy"),
                   dict(kind="shell"), dict(kind="act"),
                   dict(kind="act", operation_id="op", fence={"coordinator_term": True, "takeover_version": 0}),
                   dict(budget={"deadline_ms": 0}), dict(budget={"deadline_ms": 120001}),
                   dict(budget={"deadline_ms": True}), dict(budget={"deadline_ms": "15000"})]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                TaskPayload.model_validate(task_payload(**changes))
        valid = TaskPayload.model_validate(task_payload(kind="act", operation_id="op", fence={"coordinator_term": 1, "takeover_version": 0}))
        self.assertEqual(valid.operation_id, "op")

    async def test_two_invalid_model_outputs_fall_back_and_count_both_usage(self):
        client = FakeHttpClient([
            {"usage": {"total_tokens": 11}, "choices": [{"message": {"content": "{broken"}}]},
            {"usage": {"total_tokens": 19}, "choices": [{"message": {"content": json.dumps({"hypotheses": [{"cause": "invented", "predictions": {"shell.exec": ["x"]}}]})}}]},
        ])
        engine = HypothesisEngine(enabled=True, base_url="https://model.invalid/v1", model="fake-test-model", client=client)
        result = await engine.generate("same symptom", [], [p.tool for p in PROBES])
        self.assertEqual(engine.calls, 2)
        self.assertEqual(engine.tokens, 30)
        self.assertEqual(engine.last_source, "rules")
        self.assertEqual({h.cause for h in result}, {h.cause for h in rule_hypotheses()})
        self.assertEqual(len(client.calls), 2)
        self.assertIn("untrusted", client.calls[0][1]["json"]["messages"][0]["content"])

    async def test_valid_model_json_uses_only_allowed_prediction_tools(self):
        content = {"hypotheses": [{"cause": "route", "because": ["route evidence"], "predictions": {"ops.route_status": ["v1"]}}]}
        client = FakeHttpClient([{"usage": {"total_tokens": 13}, "choices": [{"message": {"content": json.dumps(content)}}]}])
        engine = HypothesisEngine(enabled=True, base_url="https://model.invalid/v1", model="fake", client=client)
        result = await engine.generate("502", [], ["ops.route_status"])
        self.assertEqual((engine.calls, engine.tokens, engine.last_source), (1, 13, "llm"))
        self.assertEqual(result[0].cause, "route")

    async def test_model_disabled_never_constructs_http_client(self):
        with patch("incident.coordinator.hypothesis.httpx.AsyncClient", side_effect=AssertionError("unexpected real model access")):
            engine = HypothesisEngine(enabled=False, base_url="https://model.invalid", model="fake")
            await engine.generate("502", [], [])
        self.assertEqual((engine.calls, engine.tokens, engine.last_source), (0, 0, "rules"))


class FakeIncidentTransport:
    """Small resource model used solely to verify coordinator decisions."""
    mode = "fake_test_transport"
    tools = [p.tool for p in PROBES] + ["ops.restart", "ops.route_rollback", "db.restore_writes",
            "db.terminate_blocker", "application.pool_rebuild", "incident.verification"]

    def __init__(self, scenario="healthy", authority=None):
        self.calls = []
        self.authority = authority
        self.container = "exited" if scenario == "F01" else "running"
        self.route = "v1" if scenario in ("F02", "F10") else "v2"
        self.read_only = scenario in ("F07", "F10")
        self.blockers = [{"pid": 7301}] if scenario == "F06" else []
        self.pool_ok = not self.read_only
        self.pool_revision = 3
        self.verification_fail = False
        self.original_resolved = True

    async def call(self, payload):
        payload = deepcopy(payload)
        self.calls.append(payload)
        tool, facts = payload["tool"], []
        def fact(key, value):
            facts.append({"key": key, "value": value, "source": "fake-resource-model"})
        if tool == "ops.containers":
            fact("container_state", self.container)
        elif tool == "ops.route_status":
            fact("route_version", self.route)
        elif tool == "db.read_only_status":
            fact("read_only", self.read_only)
        elif tool == "db.blocking_sessions":
            fact("blocking_sessions", self.blockers)
        elif tool == "application.status":
            fact("application_reachable", self.container == "running")
            fact("application_pool_revision", self.pool_revision)
        elif tool == "ops.restart":
            self.container = "running"
        elif tool == "ops.route_rollback":
            if payload["args"] != {}:
                raise ValueError("route rollback target is fixed by the resource-domain policy")
            self.route = "v2"
        elif tool in ("db.restore_writes", "db.terminate_blocker"):
            if not self.authority or not self.authority.verify(payload, "coordinator-test"):
                raise PermissionError("missing exact-action approval")
            if tool == "db.restore_writes":
                self.read_only = False
            else:
                assert payload["args"] == {"pid": 7301}
                self.blockers = []
        elif tool == "application.pool_rebuild":
            assert payload["args"] == {"expected_revision": self.pool_revision}
            self.pool_revision += 1
            self.pool_ok = True
        elif tool == "incident.verification":
            recovered = (self.container == "running" and self.route == "v2" and not self.read_only
                         and not self.blockers and self.pool_ok and not self.verification_fail)
            fact("business_recovered", recovered)
            fact("original_request_resolved", self.original_resolved)
            fact("original_request_key", payload["args"].get("original_request_key"))
        else:
            raise AssertionError("unexpected tool " + tool)
        return {"incident_id": payload["incident_id"], "logical_task_id": payload["logical_task_id"],
                "executor_aic": "fake-resource-aic", "status": "ok", "facts": facts}


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = ApprovalAuthority("unit-test-only-not-production-secret" * 2)

    def tearDown(self):
        self.temp.cleanup()

    async def test_original_unknown_is_preserved_through_recovery_and_verification(self):
        cases = [(False, None, True, "completed"), (True, None, True, "needs_attention"),
                 (False, "request-one", True, "completed"), (False, "request-one", False, "needs_attention")]
        for unknown, key, resolved, expected_status in cases:
            with self.subTest(unknown=unknown, key=key, resolved=resolved):
                transport = FakeIncidentTransport("F02" if unknown and not key else "healthy")
                transport.original_resolved = resolved
                engine = IncidentCoordinator(transport, self.temp.name)
                state = engine.new("订单异常", original_request_key=key, original_request_unknown=unknown)
                result = await engine.run(state)
                self.assertIs(state["original_request_unknown"], unknown or key is not None)
                self.assertEqual(result["status"], expected_status, result.get("error"))
                verified = next(call for call in transport.calls if call["kind"] == "verify")
                self.assertEqual(verified["args"], {"original_request_key": key,
                    "original_request_unknown": unknown or key is not None})
                if expected_status == "needs_attention":
                    self.assertFalse(result["result"]["business_recovered"])
                    self.assertFalse(result["result"]["original_request_resolved"])
                    self.assertTrue(result["result"]["manual_required"])
                if unknown and not key:
                    self.assertEqual([call["tool"] for call in transport.calls if call["kind"] == "act"],
                                     ["ops.route_rollback"])
                    self.assertTrue(any(call["kind"] == "observe" for call in transport.calls))
                    self.assertEqual(result["result"]["original_request_resolution"], "unknown_missing_key")

    def test_engine_rejects_non_boolean_unknown_flag(self):
        engine = IncidentCoordinator(FakeIncidentTransport(), self.temp.name)
        with self.assertRaises(ValueError):
            engine.new("订单异常", original_request_unknown="false")

    async def execute(self, scenario, *, approve=True, transport=None):
        transport = transport or FakeIncidentTransport(scenario, self.authority)
        engine = IncidentCoordinator(transport, self.temp.name,
            approval_issuer=lambda payload: self.authority.issue(payload, "coordinator-test", approved_by="unit-test-operator"))
        state = engine.new("502 or write unavailable", original_request_key="request-one")
        running = asyncio.create_task(engine.run(state))
        async def decisions():
            while not running.done():
                for approval_id in list(engine.approvals):
                    future = engine.approvals[approval_id][0]
                    if not future.done():
                        engine.decide(approval_id, approve)
                await asyncio.sleep(0.001)
        driver = asyncio.create_task(decisions())
        try:
            result = await asyncio.wait_for(running, 5)
        finally:
            driver.cancel()
            try:
                await driver
            except asyncio.CancelledError:
                pass
        return result, transport

    async def test_same_symptom_f01_f02_branch_by_observation_and_different_actions(self):
        f01, first = await self.execute("F01")
        f02, second = await self.execute("F02")
        self.assertEqual((f01["status"], f02["status"]), ("completed", "completed"))
        self.assertEqual([t["tool"] for t in first.calls if t["kind"] == "act"], ["ops.restart"])
        self.assertEqual([t["tool"] for t in second.calls if t["kind"] == "act"], ["ops.route_rollback"])
        probes_a = [t["tool"] for t in first.calls if t["kind"] == "observe"]
        probes_b = [t["tool"] for t in second.calls if t["kind"] == "observe"]
        self.assertNotEqual(probes_a, probes_b)
        self.assertTrue(any(e["event"] == "probe_selected" for e in f01["events"]))

    async def test_f10_keeps_diagnosing_after_first_repair_and_rebuilds_pool(self):
        result, transport = await self.execute("F10")
        self.assertEqual(result["status"], "completed", result.get("error"))
        actions = [p for p in transport.calls if p["kind"] == "act"]
        self.assertEqual([p["tool"] for p in actions], ["ops.route_rollback", "db.restore_writes", "application.pool_rebuild"])
        restore = next(p for p in actions if p["tool"] == "db.restore_writes")
        self.assertTrue(self.authority.verify(restore, "coordinator-test"))
        pool = next(p for p in actions if p["tool"] == "application.pool_rebuild")
        self.assertEqual(pool["args"], {"expected_revision": 3})
        self.assertLess(transport.calls.index(restore), transport.calls.index(pool))
        self.assertEqual(result["result"]["original_request_key"], "request-one")
        self.assertGreater(sum(p["kind"] == "observe" for p in transport.calls[transport.calls.index(actions[0])+1:]), 0)
        self.assertEqual(result["tokens"], 0)

    async def test_healthy_incident_has_zero_modifications(self):
        result, transport = await self.execute("healthy")
        self.assertEqual(result["status"], "completed")
        self.assertEqual([p for p in transport.calls if p["kind"] == "act"], [])

    async def test_failed_business_verification_does_not_claim_recovery(self):
        transport = FakeIncidentTransport()
        transport.verification_fail = True
        result, _ = await self.execute("healthy", transport=transport)
        self.assertEqual(result["status"], "needs_attention")
        self.assertIs(result["result"]["business_recovered"], False)

    async def test_operator_decline_never_calls_high_risk_tool(self):
        result, transport = await self.execute("F07", approve=False)
        self.assertEqual(result["status"], "needs_attention")
        self.assertNotIn("db.restore_writes", [p["tool"] for p in transport.calls])
        self.assertEqual(result["approvals"][0]["status"], "declined")
        self.assertEqual(next(t for t in result["tasks"] if t["tool"] == "db.restore_writes")["status"], "not_dispatched")

    def test_string_approval_decision_cannot_be_treated_as_true(self):
        engine = IncidentCoordinator(FakeIncidentTransport(), self.temp.name)
        for value in ("false", "true", 1, 0, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                engine.decide("unknown-approval", value)

    async def test_product_wrong_incident_or_task_is_rejected(self):
        for field in ("incident_id", "logical_task_id"):
            transport = FakeIncidentTransport()
            original = transport.call
            async def wrong(payload, field=field, original=original):
                result = await original(payload)
                result[field] = "different"
                return result
            transport.call = wrong
            result, _ = await self.execute("healthy", transport=transport)
            self.assertEqual(result["status"], "needs_attention")
            self.assertIn("mismatched", result["error"])

    def test_approval_proof_cannot_be_moved_to_other_action_args_or_caller(self):
        payload = task_payload(kind="act", operation_id="op", fence={"coordinator_term": 1, "takeover_version": 0})
        payload["approval"] = self.authority.issue(payload, "coordinator-test", approved_by="test")
        self.assertTrue(self.authority.verify(payload, "coordinator-test"))
        for field, value in (("incident_id", "other"), ("operation_id", "other"), ("tool", "db.restore_writes"), ("args", {"pid": 1})):
            changed = deepcopy(payload)
            changed[field] = value
            self.assertFalse(self.authority.verify(changed, "coordinator-test"))
        self.assertFalse(self.authority.verify(payload, "other-caller"))


class PlannerSelectionAmpTests(unittest.IsolatedAsyncioTestCase):
    def test_pool_rebuild_requires_integer_observed_revision_and_dependency(self):
        planner = EvidencePlanner()
        planner.completed.add("db.restore_writes")
        for invalid in (None, True, "3"):
            planner.facts["application_pool_revision"] = {"value": invalid}
            self.assertFalse(any(n.tool == "application.pool_rebuild" for n in planner.actions()))
            self.assertEqual(planner.next_probe(rule_hypotheses()), "application.status")
        planner.facts["application_pool_revision"] = {"value": 3}
        node = next(n for n in planner.actions() if n.tool == "application.pool_rebuild")
        self.assertEqual(node.args, {"expected_revision": 3})
        self.assertEqual(node.depends_on, ["restore-writes"])

    def test_probe_cost_validation_and_deterministic_ties(self):
        with self.assertRaises(ValueError):
            rank_probes(rule_hypotheses(), [Probe("tool", "fact", cost=0)])
        probes = [Probe("z", "z"), Probe("a", "a")]
        self.assertEqual([r["tool"] for r in rank_probes([], probes)], ["a", "z"])

    async def test_two_candidates_choose_exact_resource_and_confirm_identity(self):
        candidates = [{"aic": "a-other-resource"}, {"aic": "b-correct-resource"}]
        calls = []
        async def describe(acs):
            calls.append(acs["aic"])
            return {"executor_aic": acs["aic"], "resources": ["other" if acs["aic"].startswith("a-") else "orders"],
                    "tools": [{"name": "db.read_only_status"}]}
        selected, _ = await select_participant(candidates, resource="orders", tool="db.read_only_status", describe=describe)
        self.assertEqual(selected["aic"], "b-correct-resource")
        self.assertEqual(len(calls), 2)

    async def test_description_identity_scope_and_tool_shape_fail_closed(self):
        invalid = [{"resources": ["orders"], "tools": ["db.read_only_status"]},
                   {"executor_aic": "spoofed", "resources": ["orders"], "tools": ["db.read_only_status"]},
                   {"executor_aic": "agent", "resources": "orders-prod", "tools": ["db.read_only_status"]},
                   {"executor_aic": "agent", "resources": ["orders"], "tools": [{"name": ["db.read_only_status"]}]}]
        for description in invalid:
            with self.subTest(description=description), self.assertRaises(RuntimeError):
                await select_participant([{"aic": "agent"}], resource="orders", tool="db.read_only_status",
                                         describe=AsyncMock(return_value=description))

    def test_runtime_metrics_are_measured_and_no_samples_means_no_window(self):
        sampler = RuntimeMetrics()
        self.assertEqual(sampler.sample().window_metrics, [])
        sampler.record(100, True)
        sampler.record(300, False)
        sample = sampler.sample()
        self.assertEqual(sample.window_metrics[0].request_total, 2)
        self.assertEqual(sample.window_metrics[0].success_rate, 50)
        self.assertEqual(sample.window_metrics[0].avg_latency_ms, 200)

    async def test_amp_runtime_start_and_stop_use_official_emitters(self):
        with tempfile.TemporaryDirectory() as directory:
            amp = AmpRuntime(directory, "coordinator-test", "test-aic")
            await amp.start()
            self.assertEqual(len(amp.tasks), 2)
            await amp.start()
            self.assertEqual(len(amp.tasks), 2)
            await amp.heartbeat.emit()
            await amp.metrics.emit()
            amp.audit_event({"incident_id": "inc", "tool": "observe", "status": "ok"})
            await amp.close()
            self.assertEqual(amp.tasks, [])
            for kind in ("heartbeat", "metrics", "audit", "system"):
                rows = [json.loads(line) for line in (Path(directory) / f"amp_{kind}_coordinator-test.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertTrue(rows)
                self.assertEqual(rows[0]["aic"], "test-aic")

    async def test_native_aip_stdio_roundtrip_uses_independent_workers_and_full_states(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"coordinator_aic": "test-coordinator", "workers": [
                {"name": "test-app", "role": "application", "aic": "test-application", "base_url": "http://127.0.0.1:9"},
                {"name": "test-verify", "role": "verification", "aic": "test-verification", "base_url": "http://127.0.0.1:9"}],
                "startup_timeout_seconds": 20, "term_journal_path": str(Path(directory) / "terms.sqlite")}
            transport = LocalAipStdioTransport(config, Path(directory) / "transport")
            try:
                await transport.start()
                self.assertEqual(transport.mode, "local-aip-stdio")
                self.assertEqual(len({p["pid"] for p in transport.participants}), 2)
                result = await transport.call(task_payload(kind="describe", tool="application.status"))
                self.assertEqual(result["executor_aic"], "test-application")
                self.assertEqual(result["description"]["executor_aic"], "test-application")
                rows = transport.journal.list_tasks()
                events = transport.journal.events(rows[0]["attempt_id"])
                self.assertEqual([e["state"] for e in events],
                                 ["dispatching", "accepted", "working", "awaiting-completion", "completed"])
                self.assertEqual(transport.journal.list_tasks(in_flight_only=True), [])
                self.assertTrue(all(p["identity_binding"] == "local-process-channel" for p in transport.participants))
                messages = [json.loads(line) for line in transport.messages_path.read_text(encoding="utf-8").splitlines()]
                sent = [TaskCommand.model_validate(row["message"]) for row in messages if row["direction"] == "send"]
                received = [TaskResult.model_validate(row["message"]) for row in messages if row["direction"] == "receive"]
                self.assertEqual([message.command.value for message in sent], ["start", "complete"])
                self.assertEqual([message.status.state.value for message in received], ["accepted", "working", "awaiting-completion", "completed"])
                self.assertEqual(json.loads(sent[0].dataItems[0].text)["kind"], "describe")
                self.assertTrue(all(row["worker_aic"] == "test-application" for row in messages))
                # A policy rejection is a real task outcome; it must not be
                # masked as successful access merely because native AIP finished.
                rejected = await transport.call(task_payload(kind="observe", tool="application.pool_rebuild",
                                                              logical_task_id="rejected-task"))
                self.assertEqual(rejected["status"], "rejected")
                partner_access = [json.loads(line) for line in (transport.amp_directory / "amp_access_test-app.jsonl").read_text(encoding="utf-8").splitlines()]
                leader_access = [json.loads(line) for line in (transport.amp_directory / "amp_access_coordinator.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(partner_access), 2)
                self.assertEqual(len(leader_access), 2)
                self.assertEqual(partner_access[-1]["body"]["response"]["statusCode"], 500)
                self.assertEqual(partner_access[-1]["body"]["error"]["code"], "rejected")
            finally:
                await transport.close()

    def test_coordinator_approval_file_rejects_resource_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incorrect.env"
            path.write_text("PGPASSWORD=test-value\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-approval"):
                LocalAipStdioTransport({"coordinator_aic": "test", "approval_env_file": str(path),
                                       "term_journal_path": str(Path(directory) / "terms.sqlite")},
                                       Path(directory) / "transport")


if __name__ == "__main__":
    unittest.main()
