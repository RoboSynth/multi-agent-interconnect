"""Evidence boundaries for multi-input stability reporting; no service fixtures."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.stability_bundle import summarize_bundle, write_bundle
from eval.stability_report import summarize


START, END = "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"


class StabilityBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.amp = self.root / "amp"
        self.amp.mkdir()
        self.scheduler = self.root / "events.jsonl"
        self.incident = self.root / "incident.json"

    def rows(self, path, rows):
        path.write_text("\n".join(json.dumps(row) if not isinstance(row, str) else row for row in rows)+"\n", encoding="utf-8")

    def task(self, task_id="task-1", elapsed=2000, status="ok"):
        return {"logical_task_id": task_id, "kind": "observe", "status": status,
                "started_at": "2026-01-01T00:00:05Z", "elapsed_ms": elapsed}

    def coordinator(self, tasks, path=None):
        path = path or self.incident
        path.write_text(json.dumps({"id": "incident-1", "tasks": tasks}), encoding="utf-8")
        return path

    def event(self, event, **extra):
        return {"at": "2026-01-01T00:00:10Z", "event": event, "run_id": "run-1", **extra}

    def bundle(self, **kwargs):
        return summarize_bundle(self.amp, window_start=START, window_end=END,
                                expected_aics=["a", "absent"], **kwargs)

    def test_legacy_amp_json_unchanged_and_latencies_stay_distinct(self):
        self.rows(self.amp / "amp_access.jsonl", [{"log_id": "one", "log_type": "access", "aic": "a",
            "timestamp": "2026-01-01T00:00:05Z", "body": {"durationMs": 5,
                "caller": {"aic": "other"}, "callee": {"aic": "a"}}}])
        self.coordinator([self.task()])
        result = self.bundle(coordinator_files=[self.incident])
        self.assertEqual(result["amp"], summarize(self.amp, window_start=START, window_end=END, expected_aics=["a", "absent"]))
        self.assertEqual([row["median_ms"] for row in result["latency_metrics"]], [5, 5, 2000])
        self.assertEqual(result["amp"]["agents"][1]["heartbeat_sampling_window"]["missing_slot_count"], 4)

    def test_scheduler_pairs_native_events_and_preserves_missing_drills(self):
        start = self.event("job_started", kind="inspect", incident_id="incident-1")
        finish = self.event("job_finished", incident_id="incident-1", status="completed", seconds=39.094)
        self.rows(self.scheduler, [start, finish, finish, self.event("drill_disabled")])
        result = self.bundle(scheduler_files=[self.scheduler])["scheduler"]
        self.assertEqual(result["counts"], {"completed": 1})
        self.assertEqual(result["jobs"][0]["elapsed_seconds"], 39.094)
        self.assertEqual(result["diagnostics"]["duplicate_records"], 1)
        self.assertEqual(result["by_kind"][1]["evidence"], "unknown_no_recorded_job")

    def test_scheduler_incomplete_conflicting_and_orphan_terminal_stay_unknown(self):
        self.rows(self.scheduler, [self.event("job_started", kind="drill"),
            self.event("job_finished", status="completed", seconds=1),
            self.event("job_finished", status="failed", seconds=2),
            self.event("job_finished", run_id="orphan", status="completed", seconds=0),
            self.event("job_started", run_id="unfinished", kind="inspect")])
        result = self.bundle(scheduler_files=[self.scheduler])["scheduler"]
        self.assertEqual(result["counts"], {"unknown": 3})
        by_id = {row["run_id"]: row for row in result["jobs"]}
        self.assertTrue(by_id["run-1"]["conflicting_records"])
        self.assertIsNone(by_id["run-1"]["elapsed_seconds"])
        self.assertTrue(by_id["orphan"]["missing_start"])
        self.assertTrue(by_id["unfinished"]["missing_finish"])

    def test_window_and_malformed_scheduler_records_do_not_become_successes(self):
        bad = self.event("job_started", kind="inspect", at="2026-01-01T00:00:05")
        outside = self.event("job_finished", at=END, status="completed", seconds=1)
        self.rows(self.scheduler, ["not json", bad, outside, self.event("job_started", kind="inspect"),
            self.event("job_finished", status="completed", seconds=True)])
        result = self.bundle(scheduler_files=[self.scheduler])["scheduler"]
        self.assertEqual(result["diagnostics"]["invalid_records"], 2)
        self.assertEqual(result["diagnostics"]["outside_window_records"], 1)
        self.assertEqual(result["diagnostics"]["invalid_durations"], 1)
        self.assertIsNone(result["jobs"][0]["elapsed_seconds"])

    def test_scheduler_cross_incident_and_reversed_terminal_do_not_count_completed(self):
        self.rows(self.scheduler, [self.event("job_started", kind="inspect", incident_id="one"),
            self.event("job_finished", status="completed", seconds=1, incident_id="other"),
            self.event("job_started", run_id="reversed", kind="inspect", incident_id="two"),
            self.event("job_finished", run_id="reversed", incident_id="two", status="completed", seconds=1,
                       at="2026-01-01T00:00:01Z")])
        result = self.bundle(scheduler_files=[self.scheduler])["scheduler"]
        self.assertEqual(result["counts"], {"unknown": 2})
        self.assertTrue(all(row["conflicting_records"] for row in result["jobs"]))

    def test_task_missing_pending_invalid_and_failed_measurements(self):
        self.coordinator([self.task("missing", None), self.task("boolean", True),
                          self.task("pending", 12, "pending"), self.task("failed", 3000, "failed"),
                          self.task("unknown-effect", 4000, "unknown")])
        result = self.bundle(coordinator_files=[self.incident])["coordinator"]
        self.assertEqual((result["recorded_count"], result["measured_count"], result["unknown_duration_count"]), (5, 2, 3))
        self.assertEqual(result["median_ms"], 3500)
        self.assertEqual(result["diagnostics"]["invalid_durations"], 1)

    def test_conflicting_snapshots_cannot_double_count_or_pick_faster_measurement(self):
        first = self.coordinator([self.task()])
        duplicate = self.coordinator([self.task()], self.root / "duplicate.json")
        conflict = self.coordinator([self.task(elapsed=10)], self.root / "conflict.json")
        same = self.bundle(coordinator_files=[first, duplicate])["coordinator"]
        self.assertEqual(same["measured_count"], 1)
        self.assertEqual(same["diagnostics"]["duplicate_records"], 1)
        changed = self.bundle(coordinator_files=[first, conflict])["coordinator"]
        self.assertEqual(changed["measured_count"], 0)
        self.assertIsNone(changed["median_ms"])
        self.assertTrue(changed["tasks"][0]["conflicting_records"])

    def test_absent_inputs_and_empty_latency_export_unknown_and_do_not_overwrite(self):
        result = self.bundle()
        self.assertFalse(result["scheduler"]["input_provided"])
        self.assertFalse(result["coordinator"]["input_provided"])
        output = self.root / "report"
        artifacts = write_bundle(result, output)
        self.assertEqual(len(artifacts), 7)
        with (output / "latency.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(all(row["median_ms"] == "unknown" for row in rows))
        self.assertTrue((output / "stability-overview.png").is_file())
        self.assertTrue((output / "stability-overview.svg").is_file())
        with self.assertRaises(FileExistsError):
            write_bundle(result, output)

    def test_timezone_bounds_and_invalid_coordinator_schema_are_rejected(self):
        with self.assertRaises(ValueError):
            summarize_bundle(self.amp, window_start=START, window_end="2026-01-01T00:01:00")
        self.incident.write_text('{"id":"incident-1","tasks":{}}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.bundle(coordinator_files=[self.incident])

    def test_malformed_optional_identifiers_do_not_crash_or_create_completed_jobs(self):
        self.rows(self.scheduler, [self.event("job_started", run_id={}, incident_id={}, kind={}),
            self.event("job_finished", run_id="orphan", status={}, seconds={})])
        task = self.task()
        task["kind"] = {}
        self.coordinator([task])
        result = self.bundle(scheduler_files=[self.scheduler], coordinator_files=[self.incident])
        self.assertEqual(result["scheduler"]["counts"], {"unknown": 1})
        self.assertEqual(result["scheduler"]["diagnostics"]["unattributed_events"], 1)
        self.assertEqual(result["coordinator"]["tasks"][0]["kind"], "unknown")

    def test_changing_inputs_cannot_be_bound_to_a_different_hash_after_analysis(self):
        path = self.amp / "amp_heartbeat.jsonl"
        self.rows(path, [])
        legacy = summarize

        def mutate(*args, **kwargs):
            result = legacy(*args, **kwargs)
            path.write_text("changed after reading\n", encoding="utf-8")
            return result

        with patch("eval.stability_bundle.summarize", side_effect=mutate), self.assertRaisesRegex(ValueError, "changed during analysis"):
            self.bundle()


if __name__ == "__main__":
    unittest.main()
