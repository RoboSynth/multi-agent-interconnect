import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "capture_stability.py"
spec = importlib.util.spec_from_file_location("capture_stability", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureTests(unittest.TestCase):
    def test_future_window_rejected_before_touching_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "output"
            with self.assertRaisesRegex(ValueError, "not finished"):
                module.capture(Path(temp), target, "2999-01-01T00:00:00Z", "2999-01-02T00:00:00Z")
            self.assertFalse(target.exists())

    def test_timezones_and_order_required(self):
        for start, end in (("2026-01-01", "2026-01-02T00:00:00Z"),
                           ("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")):
            with self.subTest(start=start), self.assertRaises(ValueError):
                module.validate_window(start, end)

    def test_projection_excludes_task_inputs_and_credentials(self):
        projected = module.project_incident({"id": "incident", "password": "secret",
            "tasks": [{"logical_task_id": "task", "kind": "observe", "args": {"password": "secret"}}]})
        self.assertNotIn("secret", json.dumps(projected))
        self.assertEqual(projected["tasks"][0]["logical_task_id"], "task")

    def test_snapshot_keeps_missing_agents_and_pause_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def write(relative, value):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")
            write("artifacts/cloud-collector-20261019/collection-plan.json", {"sources": [
                {"role": "coordinator", "host_project_relative_directory": "amp"}]})
            write("runtime/private/cloud-longrun/control/host.json", {"aics": list("abcdefg")})
            write("amp/amp_heartbeat_test.jsonl", {"timestamp": "2026-01-01T00:00:15Z",
                "aic": "a", "log_type": "heartbeat", "log_id": "h", "body": {}})
            write("runtime/private/cloud-new7-schedule/events.jsonl", {
                "at": "2026-01-01T00:00:30Z", "event": "planned_pause_started"})
            output = root / "out"
            result = module.capture(root, output, "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z")
            self.assertFalse(result["full_24h_window"])
            self.assertEqual(result["scheduler_other_events"], 1)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(len(summary["amp"]["agents"]), 7)
            self.assertTrue((output / "COMPLETE.json").exists())
            with self.assertRaises(FileExistsError):
                module.capture(root, output, "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z")


if __name__ == "__main__":
    unittest.main()
