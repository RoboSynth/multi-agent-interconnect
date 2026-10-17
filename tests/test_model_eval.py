"""Model/evaluation behavior with fake HTTP; not evidence of real model quality."""
from __future__ import annotations

import json
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import httpx
from eval.methods import FixedPlanner, FreeModelSelector
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine, ModelBudgetExceeded, OBSERVABLE_TOOLS
from incident.coordinator.planner import EvidencePlanner, blocking_root_pid
from eval.inject import Injector
from eval.observation import ContinuousObserver, VersionedClient
from eval.scheduling_report import confirmation_time
from test_coordinator import FakeHttpClient, FakeIncidentTransport
from acps_mcp_bridge.approval import ApprovalAuthority


def response(content, tokens=7):
    return {"usage": {"total_tokens": tokens}, "choices": [{"message": {"content": json.dumps(content)}}]}


class ModelFairnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_prediction_prose_is_rejected_and_both_attempts_count(self):
        body = response({"hypotheses": [{"cause": "route", "predictions": {
            "ops.route_status": ["Check and roll back the gateway configuration"]}}]}, 13)
        client = FakeHttpClient([body, body])
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same", client=client)
        await model.generate("same symptom", [], list(OBSERVABLE_TOOLS))
        self.assertEqual((model.calls, model.tokens, model.last_source), (2, 26, "rules"))
        self.assertTrue(all(row["status"] == "invalid" for row in model.requests))
        request = client.calls[0][1]["json"]
        self.assertEqual({key: request[key] for key in ("seed", "temperature", "top_p", "max_tokens")},
                         {"seed": 42, "temperature": 0, "top_p": 1, "max_tokens": 768})
        properties = request["response_format"]["json_schema"]["schema"]["$defs"]["Hypothesis"]["properties"]["predictions"]["properties"]
        self.assertEqual(properties["ops.route_status"]["items"]["enum"], ["v1", "v2"])
        context = json.loads(request["messages"][1]["content"])
        self.assertTrue(all("input_schema" in tool and "outcomes" in tool for tool in context["tools"]))

    async def test_m1_failure_is_explicit_without_rule_fallback(self):
        client = FakeHttpClient([response({"tool": "shell.exec"}, 17)])
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same", client=client)
        with tempfile.TemporaryDirectory() as tmp:
            engine = IncidentCoordinator(FakeIncidentTransport(), tmp, hypothesis=model,
                generate_hypotheses=False, probe_selector=FreeModelSelector(model), entry_first=False)
            result = await engine.run(engine.new("same symptom"))
        self.assertEqual((result["status"], result["model_source"]), ("needs_attention", "llm_failed"))
        self.assertEqual((result["model_calls"], result["tokens"], result["model_source_counts"]["rules"]), (1, 17, 0))
        self.assertEqual(result["tasks"], [])

    async def test_final_m1_selection_tokens_are_included(self):
        client = FakeHttpClient([response({"tool": tool}, index + 2) for index, tool in enumerate(OBSERVABLE_TOOLS)])
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same", client=client)
        with tempfile.TemporaryDirectory() as tmp:
            engine = IncidentCoordinator(FakeIncidentTransport(), tmp, hypothesis=model,
                generate_hypotheses=False, probe_selector=FreeModelSelector(model), entry_first=False)
            result = await engine.run(engine.new("same symptom"))
        self.assertEqual((result["status"], result["model_source"], result["model_calls"], result["tokens"]),
                         ("completed", "llm", 5, 20))
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(result["model_source_counts"]["rules"], 0)

    async def test_call_budget_rejects_before_second_dispatch(self):
        client = FakeHttpClient([response({"tool": "ops.containers"})])
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same", client=client, max_calls=1)
        selector = FreeModelSelector(model)
        planner = EvidencePlanner()
        await selector(planner, [], set(OBSERVABLE_TOOLS))
        with self.assertRaises(ModelBudgetExceeded):
            await selector(planner, [], set(OBSERVABLE_TOOLS))
        self.assertEqual((model.calls, len(client.calls)), (1, 1))
        self.assertEqual(model.requests[0]["status"], "validated")

    async def test_transport_failure_counts_attempt(self):
        class FailedClient:
            async def post(self, *args, **kwargs):
                raise httpx.ConnectError("offline")
        model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same", client=FailedClient())
        with self.assertRaises(httpx.ConnectError):
            await FreeModelSelector(model)(EvidencePlanner(), [], set(OBSERVABLE_TOOLS))
        self.assertEqual((model.calls, model.last_source, model.requests[0]["status"]), (1, "llm_failed", "invalid"))

    async def test_m0_remains_model_free(self):
        model = HypothesisEngine(enabled=False)
        with tempfile.TemporaryDirectory() as tmp:
            engine = IncidentCoordinator(FakeIncidentTransport(), tmp, hypothesis=model,
                                         planner_factory=FixedPlanner, eager_actions=False)
            result = await engine.run(engine.new("same symptom"))
        self.assertEqual((result["status"], result["model_calls"], result["tokens"], result["model_source"]),
                         ("completed", 0, 0, "rules"))

    async def test_public_version_contract_detects_stale_route(self):
        class Client:
            async def request(self, *args, **kwargs):
                return httpx.Response(200, json={"order_id": "a"})
        with self.assertRaisesRegex(ValueError, "contract_version"):
            await VersionedClient(Client()).request("GET", "/orders/a")

    def test_recovery_window_resets_after_last_failure_and_requires_drained_intents(self):
        from types import SimpleNamespace
        observer = ContinuousObserver("http://unused", ".", seed=101, run_id="unit", clock=lambda: 200)
        observer.fault_at = 100
        observer.observer = SimpleNamespace(state={"pending": [], "completed": []})
        observer.events = [{"at_monotonic": 101, "outcome": "unknown", "completed_workflows": 0}]
        observer.events += [{"at_monotonic": tick, "outcome": "success", "completed_workflows": int(tick % 3 == 0)}
                            for tick in range(102, 132)]
        summary = observer.summary()
        self.assertEqual((summary["recovery_confirmed"], summary["recovery_observed_seconds"],
                          summary["recovery_confirmed_seconds"], summary["healthy_completed_workflows"]), (True, 2, 32, 10))
        observer.observer.state["pending"] = [{"phase": "query"}]
        self.assertFalse(observer.summary()["recovery_confirmed"])
        observer.observer.state["pending"] = []
        observer.events.append({"at_monotonic": 132, "outcome": "failed", "completed_workflows": 0})
        self.assertFalse(observer.summary()["recovery_confirmed"])

    def test_analysis_uses_earliest_confirmation_not_later_stop(self):
        events = [{"at_monotonic": 101, "outcome": "unknown", "completed_workflows": 0}]
        events += [{"at_monotonic": tick, "outcome": "success", "completed_workflows": int((tick - 101) % 3 == 0)}
                   for tick in range(102, 162)]
        self.assertEqual(confirmation_time(events, 100), 32)
        events.append({"at_monotonic": 162, "outcome": "unknown", "completed_workflows": 0})
        self.assertIsNone(confirmation_time(events, 100))

    def test_blocker_is_graph_root_and_not_waiter_or_intermediate_session(self):
        rows = [{"pid": 300, "blocking_pids": [200]}, {"pid": 200, "blocking_pids": [100]}]
        for value in (rows, list(reversed(rows))):
            self.assertEqual(blocking_root_pid(value), 100)
            planner = EvidencePlanner()
            planner.update("db.blocking_sessions", [{"key": "blocking_sessions", "value": value}])
            self.assertEqual(planner.actions()[0].args, {"pid": 100})
        self.assertIsNone(blocking_root_pid([{"pid": 100, "blocking_pids": [200]}, {"pid": 200, "blocking_pids": [100]}]))
        self.assertIsNone(blocking_root_pid([{"pid": True, "blocking_pids": [100]}]))
        self.assertEqual(blocking_root_pid([{"pid": 7301}]), 7301)

    def test_native_f06_holder_uses_application_role_not_admin_credential(self):
        injector = object.__new__(Injector)
        injector.backend, injector.runtime = "native", {"pgport": 5432}
        injector._environment = lambda key: {"PGPASSWORD": "unit-test-application-password"}[key]
        captured = {}
        injector._native_start = lambda *args, **kwargs: captured.update(kwargs["env"])
        injector.sql = lambda sql: "1"
        injector.lock(True)
        self.assertEqual(captured["PGUSER"], "orders_app")
        self.assertEqual(captured["PGPASSWORD"], "unit-test-application-password")

    async def test_diagnosis_is_evidence_based_and_independent_of_model_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = IncidentCoordinator(FakeIncidentTransport("F02"), tmp)
            result = await engine.run(engine.new("same symptom"))
        self.assertEqual(result["diagnosed_causes"], ["stale_route"])

    async def test_all_methods_honor_required_conflict_reobservation_before_pool_rebuild(self):
        class PoolTransport(FakeIncidentTransport):
            async def call(self, payload):
                result = await super().call(payload)
                if payload["tool"] == "application.status":
                    result["facts"].append({"key": "application_read_only", "value": not self.pool_ok, "source": "test"})
                return result
        class SelectingClient:
            async def post(self, url, **kwargs):
                context = json.loads(kwargs["json"]["messages"][1]["content"])
                tool = context["available_tools"][0]["tool"]
                return httpx.Response(200, json=response({"tool": tool}), request=httpx.Request("POST", url))
        authority = ApprovalAuthority("unit-only-secret-for-model-fairness" * 2)
        for method in ("M0", "M1", "M2"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                model = HypothesisEngine(enabled=method == "M1", base_url="http://model.test/v1",
                    model="same", client=SelectingClient())
                options = {"planner_factory": FixedPlanner, "eager_actions": False} if method == "M0" else {}
                if method == "M1":
                    options.update(probe_selector=FreeModelSelector(model), generate_hypotheses=False, entry_first=False)
                transport = PoolTransport("F07", authority)
                engine = IncidentCoordinator(transport, tmp, hypothesis=model,
                    approval_issuer=lambda payload: authority.issue(payload, "coordinator-test", approved_by="test"), **options)
                state = engine.new("same symptom")
                task = asyncio.create_task(engine.run(state))
                while not task.done():
                    for approval in state["approvals"]:
                        if approval["status"] == "pending":
                            engine.decide(approval["id"], True)
                    await asyncio.sleep(.001)
                result = await task
                self.assertEqual(result["status"], "completed", result["error"])
                self.assertEqual([row["tool"] for row in transport.calls if row["kind"] == "act"],
                                 ["db.restore_writes", "application.pool_rebuild"])


if __name__ == "__main__":
    unittest.main()
