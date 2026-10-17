"""Statistical edge cases that can otherwise overstate stability evidence."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.stability_report import summarize


def row(identifier, seconds=0, *, kind="heartbeat", body=None):
    return {"log_id": identifier, "aic": "test-agent", "log_type": kind,
            "timestamp": (datetime(2026, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat(),
            "body": body or {}}


class StabilityReportTests(unittest.TestCase):
    def summarize(self, rows, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "amp_test.jsonl").write_text("\n".join(json.dumps(item) for item in rows), encoding="utf-8")
            return summarize(folder, **kwargs)

    def test_jitter_does_not_hide_a_missing_heartbeat(self):
        agent = self.summarize([row("a", 0), row("b", 15.1), row("c", 45)])["agents"][0]
        self.assertEqual(agent["estimated_missing_heartbeats"], 1)
        self.assertEqual(agent["coverage_percent_in_observed_window"], 75)

    def test_repeated_timestamp_cannot_inflate_coverage(self):
        agent = self.summarize([row("a"), row("b", 30), row("c", 30)])["agents"][0]
        self.assertEqual(agent["heartbeat_count"], 3)
        self.assertEqual(agent["unique_heartbeat_count"], 2)
        self.assertEqual(agent["duplicate_timestamp_count"], 1)
        self.assertEqual(agent["coverage_percent_in_observed_window"], 66.667)

    def test_single_instant_has_no_measurable_coverage(self):
        agent = self.summarize([row("a"), row("b")])["agents"][0]
        self.assertEqual(agent["observed_seconds"], 0)
        self.assertIsNone(agent["coverage_percent_in_observed_window"])

    def test_invalid_row_does_not_poison_later_valid_log_id(self):
        invalid = row("a")
        invalid["timestamp"] = "invalid"
        result = self.summarize([invalid, row("a"), row("b", 15), row("b", 15)])
        self.assertEqual(result["invalid_records"], 1)
        self.assertEqual(result["unique_records"], 2)
        self.assertEqual(result["log_types"], {"heartbeat": 2})
        self.assertEqual(result["duplicate_records_ignored"], 1)

    def test_invalid_envelope_and_naive_time_are_counted(self):
        naive = row("a")
        naive["timestamp"] = "2026-01-01T00:00:00"
        result = self.summarize([[], {"log_id": []}, naive, row("b", kind="access", body=[1])])
        self.assertEqual(result["invalid_records"], 4)
        self.assertEqual(result["unique_records"], 0)

    def test_nonfinite_negative_boolean_durations_do_not_enter_metrics(self):
        rows = [row(str(index), kind="access", body={"durationMs": value})
                for index, value in enumerate((float("nan"), float("inf"), -1, True, 0, 10))]
        result = self.summarize(rows)
        self.assertEqual(result["invalid_access_durations"], 4)
        self.assertEqual(result["median_access_ms"], 5)
        self.assertEqual(result["p95_access_ms"], 10)
        json.dumps(result, allow_nan=False)

    def test_nearest_rank_p95_and_partner_processing_are_distinct(self):
        rows = [row(str(index), kind="access", body={"durationMs": index,
                "caller": {"aic": "other"}, "callee": {"aic": "test-agent"}}) for index in range(1, 21)]
        rows.append(row("sender", kind="access", body={"durationMs": 500,
                    "caller": {"aic": "test-agent"}, "callee": {"aic": "other"}}))
        result = self.summarize(rows)
        self.assertEqual(result["p95_partner_processing_ms"], 19)
        self.assertEqual(result["p95_access_ms"], 20)

    def test_interval_is_explicit_and_validated(self):
        agent = self.summarize([row("a"), row("b", 20)], heartbeat_interval_seconds=10)["agents"][0]
        self.assertEqual(agent["estimated_missing_heartbeats"], 1)
        for interval in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.summarize([], heartbeat_interval_seconds=interval)


if __name__ == "__main__":
    unittest.main()
