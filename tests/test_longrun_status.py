import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.longrun_status import status


class LongrunStatusTests(unittest.TestCase):
    def test_joint_heartbeat_gap_and_planned_pause_are_separate_from_uptime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = []
            for aic, seconds in (("a", [0, 15, 45]), ("b", [0, 15, 30, 45])):
                for second in seconds:
                    rows.append(dict(log_id=f"{aic}-{second}", log_type="heartbeat", aic=aic,
                        timestamp=f"2026-10-19T00:00:{second:02d}Z", body={}))
            (root/"amp_heartbeat_test.jsonl").write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
            events = [dict(at="2026-10-18T23:59:50Z", event="planned_pause_started", request_id="r", host_session="h", reason="experiment"),
                      dict(at="2026-10-19T00:00:10Z", event="planned_pause_finished", request_id="r", host_session="h"),
                      dict(at="2026-10-19T00:00:30Z", event="planned_pause_started", request_id="q", host_session="h", reason="experiment"),
                      dict(at="2026-10-19T00:00:45Z", event="planned_pause_quarantined", request_id="q", host_session="h", reason="ACL unknown")]
            (root/"events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
            report = status(root, root, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z",
                            expected_aics=["a", "b"])
            self.assertEqual(report["heartbeat_continuity"]["longest_joint_heartbeat_coverage_seconds"], 30)
            self.assertEqual(report["heartbeat_continuity"]["missing_joint_slot_count"], 1)
            self.assertEqual(report["heartbeat_continuity"]["interruptions"][0]["seconds"], 15)
            self.assertEqual(report["planned_interruptions"][0]["seconds"], 10)
            self.assertEqual(report["planned_interruptions"][0]["reason"], "experiment")
            self.assertEqual(report["planned_interruptions"][1]["reason"], "ACL unknown")
            self.assertFalse(report["planned_interruptions"][1]["closed"])
            self.assertIsNone(report["actual_process_uptime_seconds"])

    def test_read_only_window_and_external_handler_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schedule, amp = root / "schedule", root / "amp"
            schedule.mkdir()
            amp.mkdir()
            events = [dict(event="job_started", at="2026-10-19T00:00:00Z", run_id="r", kind="inspect", incident_id="i"),
                      dict(event="job_finished", at="2026-10-19T00:00:05Z", run_id="r", incident_id="i", status="completed", seconds=5)]
            (schedule / "events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
            def envelope(identifier, kind, aic="team", **body):
                return dict(log_id=identifier, log_type=kind, aic=aic, timestamp="2026-10-19T00:00:00Z", body=body)
            (amp / "amp_heartbeat_team.jsonl").write_text(json.dumps(envelope("h", "heartbeat")), encoding="utf-8")
            call = envelope("a", "access", caller={"aic": "external"}, callee={"aic": "team"},
                            request={"method": "start", "route": "aip.onboarding.check"}, durationMs=5)
            call.update(correlation_id="task", trace_id="session")
            outgoing = {**call, "log_id": "b", "aic": "external"}
            complete = {**call, "log_id": "c", "body": {**call["body"], "request": {"method": "complete", "route": "aip.onboarding.check"}}}
            (amp / "amp_access_team.jsonl").write_text("\n".join(map(json.dumps, [call, call, outgoing, complete])), encoding="utf-8")
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            report = status(schedule, amp, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z",
                            expected_aics=["team", "absent"], team_aics=["team"])
            self.assertEqual(report["external_onboarding_tasks"], 1)
            self.assertEqual(report["jobs"][0]["completed"], 1)
            self.assertIsNone(report["jobs"][1]["success_percent"])
            self.assertIsNone(report["actual_process_uptime_seconds"])
            self.assertEqual(report["heartbeat_agents"][0]["heartbeat_sampling_window"]["coverage_percent"], 0)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_missing_inputs_are_rejected_without_creating_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            with self.assertRaises(ValueError):
                status(missing, missing, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z", expected_aics=["team"])
            self.assertFalse(missing.exists())

    def test_failure_and_unconfigured_external_count_remain_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "events.jsonl").write_text(json.dumps(dict(event="job_failed", kind="inspect", error_class="ConnectError",
                at="2026-10-19T00:00:01Z")), encoding="utf-8")
            report = status(root, root, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z", expected_aics=["team"])
            self.assertEqual(report["latest_failure"]["error_class"], "ConnectError")
            self.assertIsNone(report["external_onboarding_tasks"])
            self.assertEqual(report["jobs"][0]["failed"], 1)

    def test_failed_restoration_never_counts_as_completed_drill(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = [dict(event="job_started", at="2026-10-19T00:00:00Z", run_id="r", kind="drill", incident_id="i"),
                      dict(event="job_failed", at="2026-10-19T00:00:05Z", run_id="r", kind="drill", phase="restore", error_class="RuntimeError")]
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
            report = status(root, root, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z", expected_aics=["team"], team_aics=["team"])
            self.assertEqual(report["jobs"][1]["failed"], 1)
            self.assertEqual(report["jobs"][1]["success_percent"], 0)
            self.assertIsNone(report["external_onboarding_tasks"])

    def test_later_finished_restoration_resolves_same_failed_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = [dict(event="job_started", at="2026-10-19T00:00:00Z", run_id="r", kind="drill", incident_id="i"),
                      dict(event="job_failed", at="2026-10-19T00:00:05Z", run_id="r", kind="drill", phase="restore", error_class="RuntimeError"),
                      dict(event="job_finished", at="2026-10-19T00:00:20Z", run_id="r", kind="drill", incident_id="i", status="completed", seconds=15)]
            (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
            report = status(root, root, window_start="2026-10-19T00:00:00Z", window_end="2026-10-19T00:01:00Z", expected_aics=["team"])
            self.assertEqual(report["jobs"][1]["completed"], 1)
            self.assertEqual(report["jobs"][1]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
