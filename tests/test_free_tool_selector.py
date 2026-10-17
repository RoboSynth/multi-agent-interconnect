"""M1 full tool selection validates model choices; fake HTTP is not model-quality evidence."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from eval.methods.free_tools import FreeToolSelector
from incident.coordinator.hypothesis import HypothesisEngine, ModelBudgetExceeded, OBSERVABLE_TOOLS
from incident.coordinator.planner import EvidencePlanner
from test_coordinator import FakeHttpClient
from test_model_eval import response


TOOLS = set(OBSERVABLE_TOOLS) | {"ops.restart", "ops.route_rollback", "db.restore_writes",
    "db.terminate_blocker", "application.pool_rebuild", "incident.verification"}


class FreeToolSelectorTests(unittest.IsolatedAsyncioTestCase):
    def model(self, choices, **kwargs):
        return HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="same",
            client=FakeHttpClient([response(value, 11) for value in choices]), **kwargs)

    async def test_model_selects_observation_action_and_verification_without_repair_ranking(self):
        choices = [{"tool": "ops.containers", "args": {}}, {"tool": "ops.restart", "args": {}},
                   {"tool": "incident.verification", "args": {}}]
        model = self.model(choices)
        selector, planner = FreeToolSelector(model), EvidencePlanner()
        state = {"symptom": "same symptom", "tasks": []}
        steps = [await selector(state, planner, TOOLS) for _ in choices]
        self.assertEqual([step.kind for step in steps], ["observe", "act", "verify"])
        self.assertEqual((model.calls, model.tokens, model.source_counts["llm"]), (3, 33, 3))
        available = model.requests[0]["context"]["available_tools"]
        self.assertEqual({row["kind"] for row in available}, {"observe", "act", "verify"})
        self.assertNotIn("ranking", model.requests[0]["context"])
        self.assertEqual(steps[1].action_node().risk, "high")

    async def test_same_action_reuses_operation_identity_and_changed_args_are_distinct(self):
        choices = [{"tool": "application.pool_rebuild", "args": {"expected_revision": value}}
                   for value in (3, 3, 4)]
        selector = FreeToolSelector(self.model(choices))
        state, planner = {"symptom": "same", "tasks": []}, EvidencePlanner()
        nodes = [(await selector(state, planner, TOOLS)).action_node() for _ in choices]
        self.assertEqual(nodes[0].id, nodes[1].id)
        self.assertNotEqual(nodes[0].id, nodes[2].id)

    async def test_invalid_args_and_unavailable_tools_fail_without_fallback(self):
        for choice in ({"tool": "shell.exec", "args": {}},
                       {"tool": "db.terminate_blocker", "args": {"pid": True}},
                       {"tool": "ops.restart", "args": {"container": "unmanaged"}}):
            with self.subTest(choice=choice):
                model = self.model([choice])
                with self.assertRaises(Exception):
                    await FreeToolSelector(model)({"symptom": "same", "tasks": []}, EvidencePlanner(), TOOLS)
                self.assertEqual((model.calls, model.tokens, model.last_source), (1, 11, "llm_failed"))
                self.assertEqual(model.source_counts["rules"], 0)

    async def test_recorded_context_does_not_change_with_later_task_updates(self):
        model = self.model([{"tool": "application.status", "args": {}}])
        task = {"tool": "ops.containers", "kind": "observe", "args": {}, "status": "pending"}
        state = {"symptom": "same", "tasks": [task]}
        await FreeToolSelector(model)(state, EvidencePlanner(), TOOLS)
        task["status"] = "ok"
        self.assertEqual(model.requests[0]["context"]["history"][0]["status"], "pending")

    async def test_shared_budget_stops_before_another_model_request(self):
        model = self.model([{"tool": "ops.containers", "args": {}}], max_calls=1)
        selector, state, planner = FreeToolSelector(model), {"symptom": "same", "tasks": []}, EvidencePlanner()
        await selector(state, planner, TOOLS)
        with self.assertRaises(ModelBudgetExceeded):
            await selector(state, planner, TOOLS)
        self.assertEqual(model.calls, 1)


if __name__ == "__main__":
    unittest.main()
