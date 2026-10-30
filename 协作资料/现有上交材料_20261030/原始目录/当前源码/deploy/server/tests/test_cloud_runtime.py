"""Stage-5 fake orchestration only: no Docker, cloud, SDK or real processes."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cloud_runtime_helper", HERE / "cloud_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
SERVICES = [role + "-agent" for role in ("application", "verification", "database", "database-backup", "ops", "onboarding")]


class StageFiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.settings = dict(coordinator_config="private/coordinator/config.json", lease_directory="private/leases",
            control_directory="private/control", output_directory="artifacts/cloud-longrun-workbench")
        self.target = SimpleNamespace(compose=["docker", "compose"], docker=["docker"])
        self.events = []
        self.session = None

    def tearDown(self):
        self.temporary.cleanup()

    async def exercise(self, *, health_failed=False, missing_receipt=False, business_ready=False):
        parent = self
        class Consumers:
            def __init__(self, target, *, session):
                parent.session = session
                self.owned = {service: "fake-" + service for service in SERVICES}
            async def start(self):
                parent.events.append("domains_start")
            async def stop(self):
                parent.events.append("domains_stop")
                self.owned.clear()
        async def run(argv, *, root, step, timeout=600):
            self.events.append(step)
            if step == "six_domain_health":
                if health_failed:
                    raise runtime.CommandFailed(step, 1)
                output = Path(argv[argv.index("--output") + 1])
                output.mkdir()
                runtime.save(output / "results.json", dict(status="completed", close_status="completed",
                    completed_products=[{}] * 12))
            if "logs" in argv:
                if missing_receipt:
                    return "SDK arbitrary log without a cleanup receipt"
                role = argv[-1].removeprefix("fake-").removesuffix("-agent")
                return "discard-this-private-log\n" + json.dumps(dict(status="managed_consumer_closed", role=role,
                    session=self.session, sdk_cleanup_completed=True))
            return ""
        def launch(root, host, control):
            self.events.append("host_launch")
            return SimpleNamespace(pid=4242, poll=lambda: None)
        async def ready(settings, *, root):
            self.events.append("host_ready")
            return dict(pid=4242, session_id="new-managed-session", status="running")
        return await runtime.stage5(self.root, self.root / "host.json", self.root / "deployment.json", self.evidence,
            self.settings, self.target, consumers_factory=Consumers, run=run, launch=launch, wait_ready=ready,
            business_ready=business_ready)

    async def test_health_and_six_verified_closes_precede_single_host_start(self):
        result = await self.exercise()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.events[:4], ["business_up", "domains_start", "six_domain_health", "domains_stop"])
        self.assertEqual(self.events.count("temporary_domain_close_receipts"), 6)
        self.assertEqual(self.events[-2:], ["host_launch", "host_ready"])
        self.assertEqual(len(result["temporary_domain_close_receipts"]), 6)
        self.assertEqual(result["identities_running"], 7)
        self.assertNotIn("discard-this-private-log", json.dumps(result))

    async def test_health_failure_stops_before_domain_stop_or_host_start(self):
        result = await self.exercise(health_failed=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "six_domain_health")
        self.assertNotIn("domains_stop", self.events)
        self.assertNotIn("host_launch", self.events)

    async def test_already_verified_business_is_reused_without_compose_up(self):
        result = await self.exercise(business_ready=True)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("business_up", self.events)
        self.assertEqual(self.events[0], "domains_start")
        self.assertTrue(result["business"]["reused"])

    async def test_missing_cleanup_receipt_prevents_new_consumer(self):
        result = await self.exercise(missing_receipt=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "temporary_domain_close_receipts")
        self.assertNotIn("host_launch", self.events)

    def test_receipt_must_match_exact_session_and_role(self):
        text = json.dumps(dict(status="managed_consumer_closed", role="database-backup",
                               session="wrong", sdk_cleanup_completed=True))
        with self.assertRaises(RuntimeError):
            runtime.close_receipt(text, "database-backup-agent", "selected-session")

    def test_default_cli_does_not_read_config_or_execute(self):
        with patch.object(runtime, "prepare", create=True, side_effect=AssertionError("must not prepare")), \
             patch.object(runtime, "initialize_host", side_effect=AssertionError("must not initialize")):
            self.assertEqual(runtime.main(["stage5", "--project-root", str(self.root)]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
