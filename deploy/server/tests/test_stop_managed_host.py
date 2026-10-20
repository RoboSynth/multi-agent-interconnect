"""Temporary fake-host tests: no SSH, Docker, live identities or real signals."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("INCIDENT_REPO", str(HERE.parents[1])))
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location("cloud_stop_helper", HERE / "stop_managed_host.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
from ops.aic_lease import load, save


class FakeProcess:
    def __init__(self, pid, root, config):
        self.pid = pid
        self.start_ticks = "123"
        self.argv = [str(root / ".venv/bin/python"), "-B", str(root / "ops/startup.py"),
                     "--config", str(config), "--stage", "workbench"]
        self.signals = 0
        self.closed = False

    def snapshot(self):
        return dict(pid=self.pid, start_ticks=self.start_ticks, argv=list(self.argv))

    def terminate(self):
        self.signals += 1

    def wait_exited(self, timeout):
        return True

    def close(self):
        self.closed = True


class StopManagedHostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.control = self.root / "control"
        self.config = self.root / "host-config.json"
        save(self.config, dict(deployment_manifest="deployment.json", control_directory="control"))
        save(self.root / "deployment.json", dict(mode="seven", coordinator_config="coordinator.json"))
        trusted = dict(application=["fake-app"], verification=["fake-verify"], database=["fake-db", "fake-backup"],
                       ops=["fake-ops"], onboarding=["fake-onboarding"])
        save(self.root / "coordinator.json", dict(mode="wutong-amqps", leader=dict(aic="fake-coordinator"),
                                                  trusted_participant_aics=trusted))
        self.aics = sorted(["fake-coordinator", *(aic for rows in trusted.values() for aic in rows)])
        self.state = dict(status="running", session_id="fake-session", pid=123456, aics=self.aics)
        save(self.control / "host.json", self.state)
        self.process = FakeProcess(123456, self.root, self.config)
        self.elapsed = 0

    def tearDown(self):
        self.temporary.cleanup()

    def pause(self, **changes):
        request = load(self.control / "handoff-request.json")
        self.state.update(status="paused", request_id=request["request_id"], consumers_closed=True, lease_released=True)
        self.state.update(changes)
        save(self.control / "host.json", self.state)

    def run_stop(self, advance=None):
        def tick(seconds):
            self.elapsed += seconds
            if advance:
                advance()
        return helper.request_and_stop(self.root, self.config, timeout=1, exit_timeout=1,
                                       process_factory=lambda pid: self.process,
                                       clock=lambda: self.elapsed, wait=tick, token="fake-stop-token")

    def assert_no_signal(self):
        self.assertEqual(self.process.signals, 0)
        self.assertTrue(self.process.closed)

    def test_confirmed_pause_stops_only_bound_process(self):
        result = self.run_stop(self.pause)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["pid"], 123456)
        self.assertTrue(result["exact_process_exited"])
        self.assertEqual(self.process.signals, 1)
        self.assertTrue(self.process.closed)
        self.assertFalse((self.control / "handoff-result.json").exists())

    def test_changed_session_is_not_signalled(self):
        with self.assertRaisesRegex(RuntimeError, "binding changed"):
            self.run_stop(lambda: self.pause(session_id="replacement"))
        self.assert_no_signal()

    def test_changed_pid_is_not_signalled(self):
        with self.assertRaisesRegex(RuntimeError, "binding changed"):
            self.run_stop(lambda: self.pause(pid=123457))
        self.assert_no_signal()

    def test_missing_cleanup_receipt_is_not_signalled(self):
        with self.assertRaisesRegex(RuntimeError, "confirmed cleanup"):
            self.run_stop(lambda: self.pause(consumers_closed=False))
        self.assert_no_signal()

    def test_unreleased_lease_is_not_signalled(self):
        with self.assertRaisesRegex(RuntimeError, "confirmed cleanup"):
            self.run_stop(lambda: self.pause(lease_released=False))
        self.assert_no_signal()

    def test_timeout_keeps_request_and_never_signals(self):
        with self.assertRaises(TimeoutError):
            self.run_stop()
        self.assert_no_signal()
        self.assertEqual(load(self.control / "handoff-request.json")["request_id"], "fake-stop-token")

    def test_reused_pid_start_time_is_not_signalled(self):
        def replace():
            self.pause()
            self.process.start_ticks = "456"
        with self.assertRaisesRegex(RuntimeError, "process identity changed"):
            self.run_stop(replace)
        self.assert_no_signal()

    def test_wrong_command_is_rejected_before_request(self):
        self.process.argv[-1] = "scheduler"
        with self.assertRaisesRegex(RuntimeError, "not a workbench"):
            self.run_stop(self.pause)
        self.assert_no_signal()
        self.assertFalse((self.control / "handoff-request.json").exists())

    def test_changed_aic_set_is_not_signalled(self):
        with self.assertRaisesRegex(RuntimeError, "binding changed"):
            self.run_stop(lambda: self.pause(aics=["another-team"] * 7))
        self.assert_no_signal()

    def test_answered_request_cannot_be_signalled(self):
        def answered():
            self.pause()
            save(self.control / "handoff-result.json", dict(request_id="fake-stop-token", action="resume"))
        with self.assertRaisesRegex(RuntimeError, "Another controller"):
            self.run_stop(answered)
        self.assert_no_signal()


if __name__ == "__main__":
    unittest.main(verbosity=2)
