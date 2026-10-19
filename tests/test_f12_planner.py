"""Recover an unregistered route from ordinary observations, without fault labels."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from incident.coordinator.planner import EvidencePlanner

ROUTE_SHA = "a" * 64

def observe(planner, tool, key, value):
    planner.update(tool, [{"key": key, "value": value}])


class UnregisteredRoutePlannerTests(unittest.TestCase):
    def test_unregistered_route_needs_confirmed_application_reachability(self):
        for reachable in (None, False, "true", 1):
            with self.subTest(reachable=reachable):
                planner = EvidencePlanner()
                observe(planner, "ops.route_status", "route_version", "unknown")
                observe(planner, "ops.route_status", "route_sha256", ROUTE_SHA)
                if reachable is not None:
                    observe(planner, "application.status", "application_reachable", reachable)
                self.assertFalse(any(node.tool == "ops.route_rollback" for node in planner.actions()))

    def test_ordinary_unknown_route_and_healthy_application_select_existing_write(self):
        planner = EvidencePlanner()
        observe(planner, "ops.route_status", "route_version", "unknown")
        observe(planner, "ops.route_status", "route_sha256", ROUTE_SHA)
        observe(planner, "application.status", "application_reachable", True)
        actions = planner.actions()
        self.assertEqual([(node.tool, node.kind, node.risk, node.args) for node in actions],
                         [("ops.route_rollback", "act", "write",
                           {"expected_route_version": "unknown", "expected_route_sha256": ROUTE_SHA})])
        self.assertNotIn("F12", actions[0].reason)
        self.assertNotIn("reply", actions[0].reason)
        planner.action_completed(actions[0])
        self.assertNotIn("ops.route_status", planner.observed)
        self.assertNotIn("route_version", planner.facts)
        self.assertNotIn("route_sha256", planner.facts)
        self.assertFalse(planner.actions())

    def test_registered_v2_and_missing_route_do_not_select_a_repair(self):
        for route in (None, "v2"):
            with self.subTest(route=route):
                planner = EvidencePlanner()
                observe(planner, "application.status", "application_reachable", True)
                if route is not None:
                    observe(planner, "ops.route_status", "route_version", route)
                self.assertFalse(planner.actions())

    def test_unknown_route_without_a_valid_snapshot_hash_is_not_repaired(self):
        for digest in (None, "", "not-a-digest", "A" * 64, 1):
            with self.subTest(digest=digest):
                planner = EvidencePlanner()
                observe(planner, "ops.route_status", "route_version", "unknown")
                observe(planner, "application.status", "application_reachable", True)
                observe(planner, "ops.route_status", "route_sha256", digest)
                self.assertFalse(planner.actions())

    def test_existing_v1_repair_keeps_its_previous_contract(self):
        planner = EvidencePlanner()
        observe(planner, "ops.route_status", "route_version", "v1")
        actions = planner.actions()
        self.assertEqual([node.tool for node in actions], ["ops.route_rollback"])
        self.assertEqual(actions[0].reason, "入口仍指向旧版本")


if __name__ == "__main__":
    unittest.main()
