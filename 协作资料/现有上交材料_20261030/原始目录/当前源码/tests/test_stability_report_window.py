"""Fixed-window completeness is distinct from first/last span and uptime."""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from eval.stability_report import summarize
START = "2026-01-01T00:00:00Z"
END = "2026-01-01T00:01:00Z"


def row(identifier, seconds=0, *, aic="expected", kind="heartbeat", body=None):
    return {"log_id": identifier, "aic": aic, "log_type": kind,
        "timestamp": (datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat(),
        "body": body or {}}


class StabilityWindowTests(unittest.TestCase):
    def report(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "amp_fixture.jsonl").write_text(
                "\n".join(json.dumps(item) for item in rows), encoding="utf-8")
            return summarize(folder, **kwargs)

    def test_boundary_missing_slots_remain_visible_despite_internal_100_percent(self):
        result = self.report([row(str(t), t) for t in (30, 45, 60, 75)],
            window_start=START, window_end="2026-01-01T00:02:00Z", expected_aics=["expected"])
        agent = result["agents"][0]
        self.assertEqual(agent["coverage_percent_in_observed_window"], 100)
        self.assertEqual(agent["heartbeat_sampling_window"], {"expected_slot_count": 8,
            "observed_slot_count": 4, "missing_slot_count": 4, "coverage_percent": 50,
            "start_to_first_heartbeat_seconds": 30, "last_heartbeat_to_end_seconds": 45})
        self.assertEqual(result["primary_heartbeat_metric"], "agents[].heartbeat_sampling_window.coverage_percent")

    def test_completely_absent_expected_identities_keep_full_zero_hit_denominator(self):
        result = self.report([], window_start=START, window_end=END,
            expected_aics=["second", "expected", "expected"])
        self.assertEqual([a["aic"] for a in result["agents"]], ["expected", "second"])
        self.assertEqual(result["expected_aics_without_records"], ["expected", "second"])
        self.assertEqual(result["expected_aics_without_heartbeat"], ["expected", "second"])
        for agent in result["agents"]:
            self.assertEqual(agent["heartbeat_sampling_window"]["expected_slot_count"], 4)
            self.assertEqual(agent["heartbeat_sampling_window"]["observed_slot_count"], 0)
            self.assertEqual(agent["heartbeat_sampling_window"]["coverage_percent"], 0)
            self.assertIsNone(agent["coverage_percent_in_observed_window"])
        self.assertEqual(result["expected_aic_sampling_window"]["expected_slot_count"], 8)
        self.assertEqual(result["expected_aic_sampling_window"]["missing_slot_count"], 8)
        self.assertEqual(result["expected_aic_sampling_window"]["coverage_percent"], 0)

    def test_foreign_heartbeats_and_access_do_not_improve_expected_identity_coverage(self):
        rows = [row("expected-zero"), row("access-only", aic="access-only", kind="access")]
        rows += [row("foreign-"+str(t), t, aic="foreign") for t in (0, 15, 30, 45)]
        result = self.report(rows, window_start=START, window_end=END, expected_aics=["expected", "absent"])
        self.assertEqual(result["unexpected_observed_aics"], ["access-only", "foreign"])
        aggregate = result["expected_aic_sampling_window"]
        self.assertEqual((aggregate["expected_slot_count"], aggregate["observed_slot_count"]), (8, 1))
        self.assertEqual(aggregate["coverage_percent"], 12.5)
        self.assertTrue(aggregate["unexpected_agents_excluded"])

    def test_access_only_expected_identity_is_present_but_has_no_heartbeat(self):
        result = self.report([row("access", kind="access", body={"durationMs": 9})],
            window_start=START, window_end=END, expected_aics=["expected"])
        self.assertEqual(result["expected_aics_without_records"], [])
        self.assertEqual(result["expected_aics_without_heartbeat"], ["expected"])
        self.assertEqual(result["agents"][0]["valid_record_count"], 1)
        self.assertEqual(result["expected_aic_sampling_window"]["coverage_percent"], 0)

    def test_half_open_window_filters_heartbeat_access_and_outside_id_before_dedup(self):
        rows = [row("same-id", -1), row("same-id", 0), row("near", 14.999),
            row("next", 15), row("last", 59.999), row("end", 60),
            row("before-access", -1, kind="access", body={"durationMs": 900}),
            row("inside-access", 30, kind="access", body={"durationMs": 4}),
            row("end-access", 60, kind="access", body={"durationMs": 800})]
        result = self.report(rows, window_start=START, window_end=END)
        sampling = result["agents"][0]["heartbeat_sampling_window"]
        self.assertEqual((sampling["expected_slot_count"], sampling["observed_slot_count"]), (4, 3))
        self.assertEqual(result["log_types"], {"heartbeat": 4, "access": 1})
        self.assertEqual(result["unique_records"], 5)
        self.assertEqual(result["outside_window_records_ignored"], 4)
        self.assertEqual(result["duplicate_records_ignored"], 0)
        self.assertEqual(result["median_access_ms"], 4)

    def test_duplicate_ids_timestamps_and_same_slot_bursts_cannot_inflate_slots(self):
        rows = [row("a"), row("a"), row("b"), row("c", 1), row("d", 2)]
        result = self.report(rows, window_start=START, window_end=END)
        self.assertEqual(result["duplicate_records_ignored"], 1)
        agent = result["agents"][0]
        self.assertEqual((agent["heartbeat_count"], agent["unique_heartbeat_count"]), (4, 3))
        self.assertEqual(agent["heartbeat_sampling_window"]["observed_slot_count"], 1)
        self.assertEqual(agent["heartbeat_sampling_window"]["coverage_percent"], 25)

    def test_floor_assignment_exposes_documented_cadence_jitter_difference(self):
        result = self.report([row("early", 14.9), row("late", 30.1)], window_start=START,
            window_end="2026-01-01T00:00:45Z")
        agent = result["agents"][0]
        self.assertEqual(agent["coverage_percent_in_observed_window"], 100)
        self.assertEqual(agent["heartbeat_sampling_window"]["coverage_percent"], 66.667)
        self.assertIn("floor", result["heartbeat_sampling_estimator"])
        self.assertIn("jitter", result["coverage_limit"])
        self.assertIn("not uptime or TTL liveness", result["coverage_limit"])

    def test_final_partial_slot_is_counted_once(self):
        result = self.report([row("a"), row("b", 15)], window_start=START,
            window_end="2026-01-01T00:00:30.001Z", expected_aics=["expected"])
        self.assertEqual(result["acceptance_window"]["expected_slots_per_agent"], 3)
        self.assertEqual(result["expected_aic_sampling_window"]["coverage_percent"], 66.667)

    def test_offset_bounds_are_normalized_to_the_same_utc_window(self):
        result = self.report([row("a")], window_start="2026-01-01T08:00:00+08:00",
            window_end="2026-01-01T08:01:00+08:00")
        self.assertEqual(result["acceptance_window"]["start"], START)
        self.assertEqual(result["acceptance_window"]["end"], END)

    def test_expected_identities_without_window_add_absence_but_no_fixed_metric(self):
        result = self.report([row("a"), row("b", 15)], expected_aics=["expected", "absent"])
        agents = {item["aic"]: item for item in result["agents"]}
        self.assertIsNone(agents["absent"]["coverage_percent_in_observed_window"])
        self.assertEqual(agents["expected"]["coverage_percent_in_observed_window"], 100)
        self.assertNotIn("heartbeat_sampling_window", agents["absent"])
        self.assertNotIn("acceptance_window", result)

    def test_window_and_expected_identity_arguments_are_validated(self):
        invalid = [{"window_start": START}, {"window_end": END},
            {"window_start": START, "window_end": START}, {"window_start": END, "window_end": START},
            {"window_start": "2026-01-01T00:00:00", "window_end": END},
            {"window_start": True, "window_end": END}, {"expected_aics": "expected"},
            {"expected_aics": [""]}, {"expected_aics": [" expected"]}]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.report([], **kwargs)
        result = self.report([], window_start=START, window_end=END, expected_aics=[])
        self.assertEqual(result["expected_aic_sampling_window"]["expected_slot_count"], 0)
        self.assertIsNone(result["expected_aic_sampling_window"]["coverage_percent"])

    def test_candidate_cli_accepts_repeated_expected_aic_and_writes_the_window(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "amp_fixture.jsonl").write_text(json.dumps(row("a")), encoding="utf-8")
            output = directory / "report.json"
            argv = ["stability_report.py", folder, "--output", str(output),
                "--window-start", START, "--window-end", END,
                "--expected-aic", "expected", "--expected-aic", "absent"]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
                runpy.run_path(str(PROJECT / "eval/stability_report.py"), run_name="__main__")
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["expected_aics"], ["absent", "expected"])
            self.assertEqual(report["expected_aic_sampling_window"]["expected_slot_count"], 8)
            self.assertEqual(report["expected_aic_sampling_window"]["coverage_percent"], 12.5)


if __name__ == "__main__":
    unittest.main()
