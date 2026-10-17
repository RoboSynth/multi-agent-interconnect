from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from incident.coordinator.planner import EvidencePlanner
from incident.coordinator.hypothesis import rule_hypotheses


class PlannerConflictTests(unittest.TestCase):
    def test_conflicting_domains_require_an_extra_probe_before_pool_repair(self):
        planner = EvidencePlanner()
        planner.update("application.status", [{"key": "application_read_only", "value": True},
            {"key": "application_pool_revision", "value": 7}])
        planner.update("db.read_only_status", [{"key": "read_only", "value": False}])
        self.assertEqual(planner.actions(), [])
        self.assertEqual(planner.next_probe(rule_hypotheses()), "db.read_only_status")
        planner.update("db.read_only_status", [{"key": "read_only", "value": False}])
        actions = planner.actions()
        self.assertEqual([(n.tool,n.args) for n in actions], [("application.pool_rebuild", {"expected_revision": 7})])
        planner.action_completed(actions[0])
        self.assertNotIn("application_read_only", planner.facts)

    def test_changed_supplementary_evidence_closes_the_conflict(self):
        planner = EvidencePlanner()
        planner.update("application.status", [{"key": "application_read_only", "value": True}])
        planner.update("db.read_only_status", [{"key": "read_only", "value": False}])
        planner.next_probe(rule_hypotheses())
        planner.update("db.read_only_status", [{"key": "read_only", "value": True}])
        self.assertEqual([n.tool for n in planner.actions()], ["db.restore_writes"])
