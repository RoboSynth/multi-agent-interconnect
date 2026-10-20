"""P5 offline control-flow checks. No services, models, or injected resources."""
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
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge.approval import ApprovalAuthority
from eval.methods.runbook import BlindRunbookSelector
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import Hypothesis, HypothesisEngine, rule_hypotheses
from incident.coordinator.incident_planner import IncidentPlanner
from incident.coordinator.planner import PROBES
from incident.partners import VerificationPartner
from business.load import OrderObserver
import httpx
from test_coordinator import FakeHttpClient, FakeIncidentTransport


def model_body(hypotheses=None):
    return {"usage": {"total_tokens": 7}, "choices": [{"message": {"content": json.dumps({
        "hypotheses": [hypothesis.model_dump() for hypothesis in (hypotheses or rule_hypotheses())]})}}]}


def sparse_hypotheses():
    # The valid one-tool-per-candidate shape returned in the real F06 failure.
    return [Hypothesis(cause=cause, predictions={tool: [outcome]}) for cause, tool, outcome in (
        ("process", "ops.containers", "exited"), ("route", "ops.route_status", "v2"),
        ("application", "application.status", "unreachable"),
        ("read_only", "db.read_only_status", "ro"), ("blocker", "db.blocking_sessions", "blocked"))]


class SchedulingTransport(FakeIncidentTransport):
    tools = FakeIncidentTransport.tools + ["incident.symptom_check"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active = {}
        self.maximum_active = 0
        self.maximum_per_domain = 0
        self.route_observed = asyncio.Event()

    async def call(self, payload):
        domain = payload["tool"].split(".")[0]
        self.active[domain] = self.active.get(domain, 0) + 1
        self.maximum_active = max(self.maximum_active, sum(self.active.values()))
        self.maximum_per_domain = max(self.maximum_per_domain, self.active[domain])
        try:
            await asyncio.sleep(0)
            if payload["tool"] == "incident.symptom_check":
                self.calls.append(deepcopy(payload))
                healthy = (self.container == "running" and self.route == "v2" and not self.read_only
                           and not self.blockers and self.pool_ok and not self.verification_fail)
                category = "healthy" if healthy else "entry_error" if self.container != "running" or self.route != "v2" else "write_error"
                return {"incident_id": payload["incident_id"], "logical_task_id": payload["logical_task_id"],
                    "executor_aic": "fake-resource-aic", "status": "ok", "facts": [
                        {"key": "symptom_check_passed", "value": healthy, "source": "fake"},
                        {"key": "symptom_category", "value": category, "source": "fake"}]}
            result = await super().call(payload)
            if payload["tool"] == "application.status":
                result["facts"].append({"key": "application_read_only", "value": not self.pool_ok, "source": "fake"})
            if payload["tool"] == "ops.route_status":
                self.route_observed.set()
            return result
        finally:
            self.active[domain] -= 1


class IncidentSchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, scenario="healthy", *, model=None, transport=None, runbook=False, unknown=False):
        authority = ApprovalAuthority("p5-unit-test-only-approval-secret" * 2)
        transport = transport or SchedulingTransport(scenario, authority)
        transport.authority = authority
        model = model or HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="fake",
                                          client=FakeHttpClient([model_body()] * 3))
        options = {"planner_factory": IncidentPlanner, "incident_hypotheses": True}
        if runbook:
            options = {"step_selector": BlindRunbookSelector(), "generate_hypotheses": False}
            model.enabled = False
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory, hypothesis=model,
                approval_issuer=lambda payload: authority.issue(payload, "coordinator-test", approved_by="offline"), **options)
            state = engine.new("same symptom", original_request_unknown=unknown)
            pending = asyncio.create_task(engine.run(state))
            try:
                async with asyncio.timeout(5):
                    while not pending.done():
                        for approval in list(engine.approvals):
                            if not engine.approvals[approval][0].done():
                                engine.decide(approval, True)
                        await asyncio.sleep(0)
                    result = await pending
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        return result, transport, model

    async def test_one_generation_overlaps_entry_and_preserves_partner_serialization(self):
        transport = SchedulingTransport("F02")
        client = FakeHttpClient([model_body()])
        original_post = client.post
        async def post(*args, **kwargs):
            await transport.route_observed.wait()
            return await original_post(*args, **kwargs)
        client.post = post
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="fake", client=client)
        state, transport, model = await self.execute(transport=transport, model=model)
        self.assertEqual((state["status"], state["model_calls"], state["hypothesis_generations"]), ("completed", 1, 1))
        self.assertEqual([row["tool"] for row in transport.calls[:2]], ["ops.containers", "ops.route_status"])
        self.assertEqual(transport.maximum_per_domain, 1)
        self.assertLessEqual(transport.maximum_active, 3)
        self.assertEqual(sum(row["kind"] == "verify" for row in transport.calls), 1)
        self.assertFalse(any(row["tool"].startswith("db.") for row in transport.calls))

    async def test_compound_fault_uses_failed_quick_check_without_repeated_generation(self):
        state, transport, _ = await self.execute("F10")
        self.assertEqual(state["status"], "completed", state.get("error"))
        self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"],
                         ["ops.route_rollback", "db.restore_writes", "application.pool_rebuild"])
        self.assertTrue(any(event["event"] == "quick_symptom_check" and not event["passed"] for event in state["events"]))
        self.assertEqual(state["model_calls"], 1)
        self.assertEqual(sum(row["kind"] == "verify" for row in transport.calls), 1)

    async def sparse_execution(self, scenario):
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="fake",
                                 client=FakeHttpClient([model_body(sparse_hypotheses())]))
        state, transport, _ = await self.execute(scenario, model=model)
        self.assertEqual(state["status"], "completed", state.get("error"))
        self.assertEqual(state["model_calls"], 1)
        self.assertEqual(sum(row["kind"] == "verify" for row in transport.calls), 1)
        return state, transport

    async def test_sparse_blocker_predictions_confirm_before_zero_discrimination_stop(self):
        state, transport = await self.sparse_execution("F06")
        self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"], ["db.terminate_blocker"])
        repair = next(row for row in transport.calls if row["kind"] == "act")
        self.assertEqual(repair["args"], {"pid": 7301})
        self.assertTrue(any(row.get("selection") == "hypothesis_confirmation" for row in state["planning_history"]))

    async def test_sparse_read_only_predictions_repair_without_inspecting_blockers(self):
        _, transport = await self.sparse_execution("F07")
        self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"],
                         ["db.restore_writes", "application.pool_rebuild"])
        self.assertNotIn("db.blocking_sessions", [row["tool"] for row in transport.calls])

    async def test_sparse_compound_predictions_continue_after_failed_post_route_check(self):
        state, transport = await self.sparse_execution("F10")
        self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"],
                         ["ops.route_rollback", "db.restore_writes", "application.pool_rebuild"])
        self.assertTrue(any(row["event"] == "quick_symptom_check" and not row["passed"] for row in state["events"]))
        self.assertNotIn("db.blocking_sessions", [row["tool"] for row in transport.calls])

    async def test_regeneration_only_after_all_candidates_contradicted_by_new_evidence(self):
        client = FakeHttpClient([model_body([Hypothesis(cause="stale", predictions={"ops.route_status": ["v1"]})]), model_body()])
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="fake", client=client)
        state, _, _ = await self.execute(model=model)
        self.assertEqual((state["status"], state["model_calls"], state["hypothesis_generations"]), ("completed", 2, 2))
        events = [event for event in state["events"] if event["event"] == "hypothesis_generation"]
        self.assertEqual(events[1]["reason"], "all_candidates_contradicted_by_new_evidence")

    async def test_invalid_generation_has_one_attempt_and_disclosed_rule_fallback(self):
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="fake",
            client=FakeHttpClient([{"usage": {"total_tokens": 9}, "choices": [{"message": {"content": "broken"}}]}]))
        state, _, _ = await self.execute(model=model)
        self.assertEqual((state["status"], state["model_calls"], state["model_source"]), ("completed", 1, "rules"))
        self.assertEqual(state["tokens"], 9)
        self.assertEqual(state["model_error"], "JSONDecodeError")

    async def test_quick_success_never_resolves_missing_original_request(self):
        state, _, _ = await self.execute("F02", unknown=True)
        self.assertEqual(state["status"], "needs_attention")
        self.assertFalse(state["result"]["original_request_resolved"])
        self.assertFalse(state["result"]["business_recovered"])

    async def test_batch_three_domains_max_and_same_partner_sequential(self):
        transport = SchedulingTransport()
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory)
            state = engine.new("offline")
            await engine._observe_batch(state, IncidentPlanner(), [probe.tool for probe in PROBES], [])
        self.assertEqual(transport.maximum_active, 3)
        self.assertEqual(transport.maximum_per_domain, 1)

    async def test_mr_entry_error_restarts_without_container_diagnosis_then_verifies(self):
        state, transport, model = await self.execute("F02", runbook=True)
        self.assertEqual(state["status"], "completed", state.get("error"))
        self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"], ["ops.restart", "ops.route_rollback"])
        self.assertNotIn("ops.containers", [row["tool"] for row in transport.calls])
        self.assertEqual(model.calls, 0)

    async def test_mr_no_blocker_pid_is_skipped_instead_of_invented(self):
        state, transport, _ = await self.execute("F07", runbook=True)
        self.assertEqual(state["status"], "completed", state.get("error"))
        self.assertNotIn("db.terminate_blocker", [row["tool"] for row in transport.calls])
        self.assertTrue(any(row.get("runbook_action_skipped") for row in state["planning_history"]))


class PlannerAndQuickCheckTests(unittest.IsolatedAsyncioTestCase):
    def test_confirmed_prediction_stops_but_required_revision_is_kept(self):
        planner = IncidentPlanner()
        hypotheses = [Hypothesis(cause="one", predictions={"ops.containers": ["running"]})]
        self.assertEqual(planner.next_probes(hypotheses), ["ops.containers"])
        planner.update("ops.containers", [{"key": "container_state", "value": "running"}])
        self.assertIsNone(planner.next_probe(hypotheses))
        planner.completed.add("db.restore_writes")
        self.assertEqual(planner.next_probe(hypotheses), "application.status")

    def test_sparse_confirmation_uses_only_explicit_available_predictions(self):
        planner = IncidentPlanner()
        hypotheses = [Hypothesis(cause="blocker", predictions={"db.blocking_sessions": ["blocked"]})]
        planner.update("ops.containers", [{"key": "container_state", "value": "running"}])
        self.assertEqual(planner.candidates(hypotheses), hypotheses)  # No container prediction means unknown.
        self.assertEqual(planner.next_probes(hypotheses), ["db.blocking_sessions"])
        self.assertEqual(planner.next_probes(hypotheses, available=["application.status"]), [])
        planner.update("db.blocking_sessions", [{"key": "blocking_sessions", "value": []}])
        self.assertEqual(planner.candidates(hypotheses), [])
        self.assertEqual(planner.next_probes(hypotheses), [])

    def test_all_outcome_prediction_has_no_confirmation_value(self):
        planner = IncidentPlanner()
        hypotheses = [Hypothesis(cause="unknown", predictions={"db.blocking_sessions": ["blocked", "clear"]})]
        self.assertEqual(planner.next_probes(hypotheses), [])

    def test_confirmed_fault_removes_only_healthy_and_unknown_evidence_cannot_disprove(self):
        planner = IncidentPlanner()
        planner.update("ops.containers", [{"key": "container_state", "value": "exited"}])
        planner.update("ops.route_status", [{"key": "route_version", "value": "unknown"}])
        hypotheses = rule_hypotheses() + [Hypothesis(cause="unclassified", predictions={"ops.route_status": ["v2"]})]
        causes = {hypothesis.cause for hypothesis in planner.candidates(hypotheses)}
        self.assertNotIn("healthy_or_other", causes)
        self.assertIn("unclassified", causes)

    async def test_three_request_check_is_not_final_verification(self):
        summary = {"requests": 3, "success": 3, "failed": 0, "unknown": 0, "completed_workflows": 1,
                   "unresolved_intents": 0, "passed": False, "events": [],
                   "state": {"pending": [], "completed": [], "next_index": 1}}
        partner = VerificationPartner("verifier", allowed_callers=["leader"])
        payload = {"incident_id": "inc", "logical_task_id": "task", "kind": "observe", "tool": "incident.symptom_check"}
        with patch("business.load.OrderObserver.observe", new=AsyncMock(return_value=summary)) as observe:
            result = await partner.execute(payload, "leader")
        self.assertEqual(observe.await_args.kwargs, {"duration": 3, "min_complete": 1, "stop_after_completed": 1})
        facts = {fact["key"]: fact["value"] for fact in result["facts"]}
        self.assertTrue(facts["symptom_check_passed"])
        self.assertNotIn("business_recovered", facts)

    async def test_quick_unknown_request_state_is_carried_into_final_verification(self):
        pending = {"pending": [{"request_key": "same-key", "phase": "resolve"}], "completed": [], "next_index": 1}
        quick = {"requests": 3, "success": 0, "failed": 0, "unknown": 3, "completed_workflows": 0,
                 "unresolved_intents": 1, "passed": False, "events": [], "state": pending}
        final = {"passed": False, "completed_workflows": 0, "state": pending}
        partner = VerificationPartner("verifier", allowed_callers=["leader"])
        payload = {"incident_id": "inc", "logical_task_id": "quick", "kind": "observe", "tool": "incident.symptom_check"}
        with patch("business.load.OrderObserver") as observer:
            observer.return_value.observe = AsyncMock(side_effect=[quick, final])
            await partner.execute(payload, "leader")
            await partner.execute({**payload, "logical_task_id": "final", "kind": "verify", "tool": "incident.verification"}, "leader")
        self.assertIs(observer.call_args_list[1].kwargs["state"], pending)
        self.assertEqual(observer.return_value.observe.call_args_list[1].kwargs, {"duration": 30, "min_complete": 10})

    async def test_resumed_symptom_workflow_finishes_same_key_without_creating_another(self):
        state = {"pending": [{"request_key": "same-key", "operation_key": "same-key-cancel", "order_id": "order-one",
                              "phase": "query", "was_unknown": True}], "completed": [], "next_index": 1}
        calls = []
        def handler(request):
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json={"order_api_version": "v2", "order": {"id": "order-one", "status": "CANCELLED"}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch("business.load.asyncio.sleep", new=AsyncMock()):
                summary = await OrderObserver("http://orders.test", state=state, client=client,
                    expected_api_version="v2").observe(duration=3, min_complete=1, stop_after_completed=1)
        self.assertEqual(calls, [("GET", "/orders/order-one"), ("POST", "/orders/order-one/cancel")])
        self.assertEqual((summary["requests"], summary["completed_workflows"], summary["unresolved_intents"]), (2, 1, 0))
        self.assertEqual(summary["state"]["completed"][0]["request_key"], "same-key")


if __name__ == "__main__":
    unittest.main()
