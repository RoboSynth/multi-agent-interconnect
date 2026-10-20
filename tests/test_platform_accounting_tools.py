"""Offline task pairing and official boolean aliveMap fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.reconcile_access import platform_pairing
from tools.check_alive import main, request_for, summarize


def access(actor, task="task", **extra):
    return {"aic": actor, "correlation_id": task, "trace_id": "session",
            "body": {"request": {"method": "start"}, "caller": {"aic": "caller"},
                     "callee": {"aic": "callee"}}, **extra}


class PairingTests(unittest.TestCase):
    def report(self, records):
        return platform_pairing(records, task_ids=["task"], expected_participants={"task": ("caller", "callee")})

    def test_exact_pair_counts_once_and_outcome_does_not_prove_task_success(self):
        rows = [access("caller"), access("callee")]
        rows[-1]["body"]["error"] = {"code": "OutcomeUnconfirmed"}
        result = self.report(rows)
        self.assertEqual((result["paired_task_count"], result["pairing_rate"]), (1, 1))
        self.assertTrue(result["passed"])
        self.assertIsNone(result["platform_ingestion_confirmed"])

    def test_single_endpoint_and_duplicate_endpoint_are_not_full_pairs(self):
        for rows, field in [([access("caller")], "missing_endpoint_task_ids"),
                            ([access("caller"), access("callee"), access("callee")], "duplicate_endpoint_task_ids")]:
            with self.subTest(field=field):
                result = self.report(rows)
                self.assertEqual(result["paired_task_count"], 0)
                self.assertEqual(result[field], ["task"])
                self.assertFalse(result["passed"])

    def test_wrong_actor_multimention_and_mismatched_participants_are_invalid(self):
        wrong_callee = access("callee")
        wrong_callee["body"]["callee"]["aic"] = "group:group"
        wrong_caller = access("callee")
        wrong_caller["body"]["caller"]["aic"] = "other"
        for row in (access("outsider"), wrong_callee, wrong_caller, {"correlation_id": []}):
            with self.subTest(row=row):
                result = self.report([access("caller"), row])
                self.assertFalse(result["passed"])
                self.assertEqual(result["invalid_access_records"], 1)

    def test_conflicting_task_reuse_and_unrelated_rows_do_not_inflate_count(self):
        other = deepcopy(access("caller"))
        other["body"]["callee"]["aic"] = "different"
        result = platform_pairing([access("caller"), access("callee"), other])
        self.assertEqual(result["conflicting_task_ids"], ["task"])
        self.assertEqual(result["paired_task_count"], 0)
        scoped = self.report([access("caller"), access("callee"), access("caller", task="other")])
        self.assertEqual(scoped["paired_task_count"], 1)
        self.assertEqual(scoped["unrelated_access_records_excluded"], 1)


class AliveTests(unittest.TestCase):
    def test_official_bool_alive_and_missing_id_remain_distinct(self):
        raw = {"result": {"aliveMap": {"a": {"alive": True, "aliveLastSeenAt": "2026-10-19T01:00:00Z"},
                                       "b": {"alive": False, "aliveLastSeenAt": None}}}}
        report = summarize(raw, ["a", "b", "c"])
        self.assertEqual(report["online_count"], 1)
        self.assertEqual([report["aics"][name]["alive"] for name in "abc"], ["online", "offline", "unknown"])
        self.assertFalse(report["aics"]["c"]["present"])
        self.assertEqual(report["aics"]["a"]["last_seen_at"], "2026-10-19T01:00:00Z")
        self.assertIsNone(report["access_ingestion_confirmed"])

    def test_request_includes_all_liveness_states_and_default_never_queries(self):
        self.assertEqual(request_for(["b", "a", "a"])["limit"], 50)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prepared.json"
            self.assertEqual(main(["--aic", "a", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text())["mode"], "PREPARED_NOT_QUERIED")

    def test_error_or_no_map_does_not_claim_online(self):
        with self.assertRaises(ValueError):
            summarize({"error": {"code": 500}}, ["a"])
        self.assertFalse(summarize({"result": {}}, ["a"])["all_online"])


if __name__ == "__main__":
    unittest.main()
