"""Phase-7 fake handoff contracts; no systemctl, SDK, cloud or real process."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cloud_runtime_migration", HERE / "cloud_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.events = []

    def tearDown(self):
        self.temporary.cleanup()

    async def exercise(self, *, stop_failed=False, missing_cleanup=False, pid=222, state_pid=222):
        async def run(argv, *, root, step, timeout=600):
            self.events.append(step)
            if step == "old_host_stop":
                if stop_failed:
                    raise runtime.CommandFailed(step, 1)
                target = Path(argv[argv.index("--report") + 1])
                runtime.save(target, dict(status="stopped", pid=111, host_session="old-session",
                    exact_process_exited=True, consumers_closed=not missing_cleanup, lease_released=True))
            return str(pid) if step == "systemd_pid" else ""
        async def ready(settings, *, root):
            self.events.append("workbench_ready")
            return dict(pid=state_pid, session_id="new-session", status="running")
        return await runtime.migrate(self.root, self.root / "host.json", self.evidence, {}, run=run, wait_ready=ready)

    async def test_exact_old_stop_precedes_new_workbench_scheduler_collector(self):
        result = await self.exercise()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.events, ["old_host_stop", "systemd_reload", "systemd_workbench_start",
            "workbench_ready", "systemd_pid", "incident-scheduler.service", "incident-collector.service"])

    async def test_old_stop_failure_prevents_systemd_handoff(self):
        result = await self.exercise(stop_failed=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.events, ["old_host_stop"])

    async def test_missing_old_cleanup_prevents_systemd_handoff(self):
        result = await self.exercise(missing_cleanup=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.events, ["old_host_stop"])

    async def test_wrong_systemd_pid_prevents_scheduler_and_collector(self):
        result = await self.exercise(state_pid=333)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("incident-scheduler.service", self.events)
        self.assertNotIn("incident-collector.service", self.events)

    async def test_legitimate_reused_pid_with_new_session_is_accepted(self):
        result = await self.exercise(pid=111, state_pid=111)
        self.assertEqual(result["status"], "completed")

    def test_unit_has_business_only_prestart_and_existing_graceful_stop(self):
        unit = (HERE / "incident-workbench.service").read_text()
        self.assertIn("cloud_runtime.py business", unit)
        self.assertIn("stop_managed_host.py", unit)
        self.assertNotIn("--launch", unit)
        self.assertIn("Restart=always", unit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
