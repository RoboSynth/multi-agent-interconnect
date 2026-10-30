"""M1 control-flow checks with fake model HTTP and resources; no live calls."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge.approval import ApprovalAuthority
from eval.methods.free_tools import FreeToolSelector
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine
from incident.coordinator.planner import EvidencePlanner
from test_coordinator import FakeHttpClient, FakeIncidentTransport
from test_model_eval import response


class NoRulePlanner(EvidencePlanner):
    def actions(self):
        raise AssertionError("free selection must not run rule actions")

    def next_probe(self, *args, **kwargs):
        raise AssertionError("free selection must not force rule probes")

    def required_probe(self, *args, **kwargs):
        raise AssertionError("free selection must not force confirmation probes")


def choice(tool, **args):
    return {"tool": tool, "args": args}


class FreeToolEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = ApprovalAuthority("free-loop-unit-approval-secret-" * 2)

    def tearDown(self):
        self.temp.cleanup()

    async def execute(self, choices, *, scenario="healthy", transport=None, approve=True,
                      original_request_key=None, original_request_unknown=False, task_budget=40, max_calls=40):
        transport = transport or FakeIncidentTransport(scenario, self.authority)
        model = HypothesisEngine(enabled=True, base_url="http://fake-model.test/v1", model="offline-fixture",
            client=FakeHttpClient([response(item, 11) for item in choices]), max_calls=max_calls)
        def update(state):
            for entry in state["approvals"]:
                if entry["status"] == "pending":
                    engine.decide(entry["id"], approve)
        engine = IncidentCoordinator(transport, self.temp.name, hypothesis=model,
            approval_issuer=lambda payload: self.authority.issue(payload, "coordinator-test", approved_by="unit-test"),
            step_selector=FreeToolSelector(model), planner_factory=NoRulePlanner,
            task_budget=task_budget, on_update=update)
        state = engine.new("订单异常", original_request_key=original_request_key,
                           original_request_unknown=original_request_unknown)
        result = await engine.run(state)
        return result, transport, model

    async def test_action_then_verification_without_automatic_rule_probe(self):
        result, transport, model = await self.execute([
            choice("ops.route_rollback"), choice("incident.verification")], scenario="F02")
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual([row["kind"] for row in transport.calls], ["act", "verify"])
        action = transport.calls[0]
        self.assertTrue(action["operation_id"].startswith(result["id"] + ":free-"))
        self.assertEqual(action["fence"], {"coordinator_term": 1, "takeover_version": 0})
        self.assertEqual((result["model_calls"], result["tokens"], result["model_source"]), (2, 22, "llm"))
        self.assertEqual(result["model_source_counts"], {"llm": 2, "rules": 0})
        self.assertTrue(result["token_usage_complete"])
        self.assertEqual(len([event for event in result["events"] if event["event"] == "tool_selected"]), 2)
        self.assertTrue(result["planning_history"])
        self.assertEqual(model.requests[1]["context"]["history"][0]["product"]["status"], "ok")

    async def test_failed_verification_feedback_allows_observation_repair_and_verify_again(self):
        result, transport, model = await self.execute([
            choice("incident.verification"), choice("ops.route_status"),
            choice("ops.route_rollback"), choice("incident.verification")], scenario="F02")
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual([row["kind"] for row in transport.calls], ["verify", "observe", "act", "verify"])
        self.assertIn("stale_route", result["diagnosed_causes"])
        initial = model.requests[1]["context"]["history"][0]["product"]
        self.assertIs(next(f["value"] for f in initial["facts"] if f["key"] == "business_recovered"), False)
        self.assertTrue(any(event["event"] == "tool_feedback" for event in result["events"]))
        self.assertEqual((result["model_calls"], result["tokens"]), (4, 44))

    async def test_verification_tool_error_clears_previous_result_before_next_selection(self):
        transport = FakeIncidentTransport("F02")
        original = transport.call
        verification_count = 0
        async def fail_second_verification(payload):
            nonlocal verification_count
            product = await original(payload)
            if payload["kind"] == "verify":
                verification_count += 1
                if verification_count == 2:
                    product.update(status="tool_error", facts=[])
            return product
        transport.call = fail_second_verification
        model = HypothesisEngine(enabled=True, base_url="http://fake-model.test/v1", model="offline-fixture",
            client=FakeHttpClient([response(item, 11) for item in [
                choice("incident.verification"), choice("incident.verification"),
                choice("ops.route_rollback"), choice("incident.verification")]]))
        selector = FreeToolSelector(model)
        selections = []
        async def capture(state, planner, available):
            selections.append({"result": deepcopy(state["result"]), "tasks": deepcopy(state["tasks"])})
            return await selector(state, planner, available)
        engine = IncidentCoordinator(transport, self.temp.name, hypothesis=model, step_selector=capture,
                                     planner_factory=NoRulePlanner)
        result = await engine.run(engine.new("订单异常"))
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertIs(selections[1]["result"]["business_recovered"], False)
        self.assertIsNone(selections[2]["result"])
        self.assertEqual(selections[2]["tasks"][-1]["status"], "tool_error")
        feedback = [event for event in result["events"] if event["event"] == "tool_feedback"]
        self.assertIs(feedback[0]["result"]["business_recovered"], False)
        self.assertEqual(feedback[1]["status"], "tool_error")
        self.assertIsNone(feedback[1]["result"])

    async def test_uncertain_action_or_stale_fence_stops_before_another_selection(self):
        cases = [("unknown", None), ("ok", "unknown"), ("ok", "executing"),
                 ("ok", "reconciliation_required"), ("rejected", "stale_fence"),
                 ("rejected", "rejected_stale_fence"), ("tool_error", None)]
        for status, operation_state in cases:
            with self.subTest(status=status, operation_state=operation_state):
                transport = FakeIncidentTransport("F02")
                original = transport.call
                async def uncertain(payload, original=original, status=status, operation_state=operation_state):
                    product = await original(payload)
                    product["status"] = status
                    if operation_state:
                        product["operation"] = {"state": operation_state, "operation_id": payload["operation_id"]}
                    return product
                transport.call = uncertain
                result, transport, _ = await self.execute([
                    choice("ops.route_rollback"), choice("incident.verification")], transport=transport)
                self.assertEqual(result["status"], "needs_attention")
                self.assertIsNotNone(result["error"])
                self.assertEqual((len(transport.calls), result["model_calls"]), (1, 1))
                self.assertIsNone(result["result"])

    async def test_rejected_high_action_is_feedback_and_reselection_keeps_approval_and_identity(self):
        transport = FakeIncidentTransport("F07", self.authority)
        original = transport.call
        guarded = []
        async def reject_first(payload):
            if payload["tool"] == "db.restore_writes":
                self.assertTrue(self.authority.verify(payload, "coordinator-test"))
                guarded.append(deepcopy(payload))
                if len(guarded) == 1:
                    transport.calls.append(deepcopy(payload))
                    self.assertTrue(transport.read_only)
                    return {"incident_id": payload["incident_id"], "logical_task_id": payload["logical_task_id"],
                        "executor_aic": "fake-resource", "status": "rejected", "facts": [],
                        "operation": {"operation_id": payload["operation_id"], "state": "rejected_precondition"}}
            return await original(payload)
        transport.call = reject_first
        result, transport, model = await self.execute([
            choice("db.restore_writes"), choice("db.read_only_status"), choice("db.restore_writes"),
            choice("application.pool_rebuild", expected_revision=3), choice("incident.verification")], transport=transport)
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual(len(result["approvals"]), 2)
        self.assertTrue(all(entry["status"] == "approved" for entry in result["approvals"]))
        self.assertEqual(guarded[0]["operation_id"], guarded[1]["operation_id"])
        self.assertNotEqual(guarded[0]["logical_task_id"], guarded[1]["logical_task_id"])
        self.assertEqual(model.requests[1]["context"]["history"][0]["status"], "rejected")
        self.assertIn("database_read_only", result["diagnosed_causes"])

    async def test_declined_approval_stops_without_dispatch_or_another_model_choice(self):
        result, transport, _ = await self.execute([
            choice("db.restore_writes"), choice("incident.verification")], scenario="F07", approve=False)
        self.assertEqual(result["status"], "needs_attention")
        self.assertEqual(result["approvals"][0]["status"], "declined")
        self.assertEqual(result["tasks"][0]["status"], "not_dispatched")
        self.assertEqual(transport.calls, [])
        self.assertEqual(result["model_calls"], 1)

    async def test_explicit_read_rejection_or_tool_error_can_feed_next_choice(self):
        for status in ("rejected", "tool_error"):
            with self.subTest(status=status):
                transport = FakeIncidentTransport()
                original = transport.call
                async def read_error(payload, original=original, status=status):
                    product = await original(payload)
                    if payload["kind"] == "observe":
                        product.update(status=status, facts=[])
                    return product
                transport.call = read_error
                result, _, model = await self.execute([
                    choice("application.status"), choice("incident.verification")], transport=transport)
                self.assertEqual(result["status"], "completed", result["error"])
                self.assertEqual(model.requests[1]["context"]["history"][0]["status"], status)

    async def test_protocol_correlation_and_transport_errors_are_not_feedback(self):
        for error in ("incident_id", "logical_task_id", "status", "transport"):
            with self.subTest(error=error):
                transport = FakeIncidentTransport()
                original = transport.call
                async def invalid(payload, original=original, error=error):
                    product = await original(payload)
                    if error == "transport":
                        raise ConnectionError("offline fixture lost delivery")
                    product[error] = "invalid"
                    return product
                transport.call = invalid
                result, transport, _ = await self.execute([
                    choice("application.status"), choice("incident.verification")], transport=transport)
                self.assertEqual(result["status"], "needs_attention")
                self.assertIsNotNone(result["error"])
                self.assertEqual((len(transport.calls), result["model_calls"]), (1, 1))

    async def test_task_and_model_budgets_stop_without_fallback_or_verification(self):
        for limits in ({"task_budget": 1}, {"max_calls": 1}):
            with self.subTest(limits=limits):
                result, transport, _ = await self.execute([
                    choice("application.status"), choice("incident.verification")], **limits)
                self.assertEqual(result["status"], "needs_attention")
                self.assertIn("budget", result["error"])
                self.assertEqual((len(transport.calls), result["model_calls"], result["tokens"]), (1, 1, 11))
                self.assertEqual(result["model_source_counts"]["rules"], 0)
                self.assertTrue(result["token_usage_complete"])

    async def test_healthy_service_with_unresolved_original_stops_for_manual_review(self):
        for key, resolved in ((None, True), ("missing-original", False)):
            with self.subTest(key=key):
                transport = FakeIncidentTransport()
                transport.original_resolved = resolved
                result, transport, _ = await self.execute([choice("incident.verification")], transport=transport,
                    original_request_unknown=True, original_request_key=key)
                self.assertEqual(result["status"], "needs_attention", result["error"])
                self.assertTrue(result["result"]["service_recovered"])
                self.assertFalse(result["result"]["business_recovered"])
                self.assertFalse(result["result"]["original_request_resolved"])
                self.assertTrue(result["result"]["manual_required"])
                self.assertEqual(transport.calls[0]["args"], {"original_request_key": key, "original_request_unknown": True})
                self.assertEqual(result["model_calls"], 1)

    async def test_missing_original_does_not_skip_service_repair_after_failed_verification(self):
        result, transport, _ = await self.execute([
            choice("incident.verification"), choice("ops.route_rollback"), choice("incident.verification")],
            scenario="F02", original_request_unknown=True)
        self.assertEqual(result["status"], "needs_attention", result["error"])
        self.assertEqual([row["kind"] for row in transport.calls], ["verify", "act", "verify"])
        self.assertTrue(result["result"]["service_recovered"])
        self.assertEqual(result["result"]["original_request_resolution"], "unknown_missing_key")
        self.assertFalse(result["result"]["business_recovered"])


if __name__ == "__main__":
    unittest.main()
