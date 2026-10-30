"""Original-journal recovery and controller ordering; no platform or business services."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk"), str(ROOT / "tests")]
from acps_sdk.amp import DurableAccessEmitter
from incident.recover_access import recover, main
from test_platform_resume_experiment import Fixture
import test_platform_resume_experiment as original
from eval import platform_resume_experiment as e1


class DomainRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name)
        self.directory = self.state / "amp-worker"
        self.path = self.directory / "amp_access_worker.jsonl"
        self.config = self.state / "bridge.json"
        self.config.write_text(json.dumps({"executor_aic": "worker", "platform": {
            "name": "worker", "amp_directory": str(self.directory)}, "env_files": ["MUST-NOT-READ"],
            "servers": {"MUST-NOT-START": {}}}), encoding="utf-8")
        self.options = dict(expected_aic="worker", expected_name="worker",
                            expected_directory=str(self.directory), state_root=self.state)

    def seed_crash(self, mode="handler"):
        fixture = ROOT / "vendor/ACPs-community/acps-sdk/tests/amp/fixtures/durable_access_process.py"
        result = subprocess.run([sys.executable, str(fixture), mode, str(self.path)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 71 if mode == "handler" else 73, result.stderr.decode(errors="replace"))

    def test_missing_original_journal_fails_without_creating_a_log_or_journal(self):
        with self.assertRaises(ValueError):
            recover(self.config, **self.options)
        self.assertFalse(self.directory.exists())

    def test_empty_file_or_unowned_database_is_not_initialized_as_a_recovery(self):
        self.directory.mkdir()
        journal = self.path.with_suffix(".outbox.sqlite3")
        journal.touch()
        for empty_database in (False, True):
            if empty_database:
                connection = sqlite3.connect(journal)
                connection.execute("CREATE TABLE unrelated(value TEXT)")
                connection.commit()
                connection.close()
            original = journal.read_bytes()
            with self.subTest(empty_database=empty_database), self.assertRaises(sqlite3.OperationalError):
                recover(self.config, **self.options)
            self.assertEqual(journal.read_bytes(), original)
            self.assertFalse(self.path.exists())

    def test_real_handler_exit_recovers_unknown_without_reexecuting_callback(self):
        self.seed_crash()
        effect = self.path.with_suffix(".effect.txt").read_bytes()
        receipt = recover(self.config, **self.options)
        row = json.loads(self.path.read_text())
        self.assertEqual(receipt["unconfirmed_outcomes"], 1)
        self.assertEqual(receipt["business_or_platform_actions"], 0)
        self.assertEqual(row["body"]["error"]["code"], "OutcomeUnconfirmed")
        self.assertNotIn("response", row["body"])
        self.assertNotIn("durationMs", row["body"])
        self.assertEqual(self.path.with_suffix(".effect.txt").read_bytes(), effect)

    def test_appended_record_recovery_and_second_run_preserve_exact_log_bytes(self):
        self.seed_crash("append")
        original = self.path.read_bytes()
        first = recover(self.config, **self.options)
        second = recover(self.config, **self.options)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(first["unique_access_ids"], 1)
        self.assertEqual(second["access_rows"], 1)
        self.assertEqual(first["unconfirmed_outcomes"], 0)

    def test_identity_directory_and_state_scope_mismatch_leave_original_bytes_unchanged(self):
        self.seed_crash()
        journal = self.path.with_suffix(".outbox.sqlite3")
        original = journal.read_bytes()
        for changes in ({"expected_aic": "other"}, {"expected_name": "other"},
                        {"expected_directory": str(self.state / "other")}, {"state_root": self.state / "other"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                recover(self.config, **(self.options | changes))
            self.assertEqual(journal.read_bytes(), original)
        self.assertFalse(self.path.exists())

    def test_live_owner_rejected_and_cli_does_not_print_private_configuration(self):
        owner = DurableAccessEmitter(self.path, "worker")
        owner.start_sync()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                recover(self.config, **self.options)
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--config", str(self.config), "--expected-aic", "other",
                    "--expected-name", "worker", "--expected-directory", str(self.directory), "--state-root", str(self.state)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue()), {"status": "failed", "error_class": "ValueError"})
            self.assertNotIn("MUST-NOT", output.getvalue())
        finally:
            owner.close_sync()


class RecoveryControllerTests(Fixture):
    def prepare_recovery(self):
        self.args.plan = self.root / "recovery-plan.json"
        self.args.recover_access = True
        self.plan = e1.prepare(self.args)
        return self.plan

    def test_plan_effect_and_authorization_bind_recovery_with_strict_boolean(self):
        self.prepare_recovery()
        self.assertTrue(self.plan["recover_access"])
        self.assertIn("network-disabled", self.plan["effects"][-1])
        for value in (1, "true"):
            with self.subTest(value=value):
                changed = deepcopy(self.plan); changed["recover_access"] = value
                with self.assertRaises(ValueError):
                    e1.validate_plan(document=changed)
        for value in (None, 1):
            auth = self.auth(**({} if value is None else {"recover_access": value}))
            with self.assertRaises(ValueError):
                e1.authorize(self.plan, self.args.plan, auth, True)
        e1.authorize(self.plan, self.args.plan, self.auth(recover_access=True), True)

    def setup_restore(self):
        self.prepare_recovery()
        controller = e1.Controller(self.plan, self.root)
        controller.original = self.records()
        controller.switched = True
        before = self.records(experiment=True)
        controller.experimental = {s: before[s]["Id"] for s in e1.DB_SERVICES}
        stopped = deepcopy(before)
        restored = self.records()
        receipts = []
        for service, role in zip(e1.DB_SERVICES, ("database", "database-backup")):
            stopped[service]["State"]["Running"] = False
            restored[service]["Id"] = "restored-" + service
            path = self.profile / "domains" / role / "bridge.json"
            e1.save(path, {"executor_aic": self.plan["identities"][role],
                "platform": {"name": role, "amp_directory": "/state/amp-" + role}})
            receipts.append(json.dumps({"schema_version": "domain-access-recovery/1", "status": "recovered",
                "aic": self.plan["identities"][role], "name": role, "config_sha256": e1.digest(path),
                "business_or_platform_actions": 0}))
        controller.inspect = Mock(side_effect=[before, stopped, restored])
        controller.command = Mock(side_effect=["", *receipts, ""])
        controller.injector = Mock(return_value={"fresh": "attestation"})
        return controller, before, stopped, restored

    def test_recovery_uses_original_volumes_without_network_before_normal_workers_start(self):
        controller, *_ = self.setup_restore()
        controller.restore()
        commands = [call.args[0] for call in controller.command.call_args_list]
        self.assertIn("stop", commands[0])
        for command in commands[1:3]:
            self.assertIn("incident.recover_access", command)
            self.assertEqual(command[command.index("--network") + 1], "none")
            self.assertIn(self.plan["image_id"], command)
            self.assertNotIn("/experiment", " ".join(command))
        self.assertIn("up", commands[3])
        self.assertEqual([r["status"] for r in controller.access_recovery], ["recovered", "recovered"])

    def test_recovery_failure_is_retained_while_normal_resource_restoration_continues(self):
        controller, *_ = self.setup_restore()
        # Keep one role failure distinct from the succeeding other role and resource restore.
        backup = json.dumps({"schema_version": "domain-access-recovery/1", "status": "recovered", "aic": "backup",
            "name": "database-backup", "config_sha256": e1.digest(self.profile / "domains/database-backup/bridge.json"),
            "business_or_platform_actions": 0})
        controller.command = Mock(side_effect=["", RuntimeError("synthetic failure"), backup, ""])
        controller.restore()
        self.assertEqual(controller.access_recovery[0]["status"], "failed")
        self.assertEqual(controller.access_recovery[1]["status"], "recovered")
        self.assertEqual(controller.injector.call_count, 2)

    def test_worker_still_running_blocks_recovery_and_normal_replacement(self):
        controller, before, stopped, restored = self.setup_restore()
        stopped[e1.DB_SERVICES[0]]["State"]["Running"] = True
        controller.inspect = Mock(side_effect=[before, stopped])
        controller.command = Mock(return_value="")
        with self.assertRaises(ValueError):
            controller.restore()
        self.assertEqual(controller.command.call_count, 1)

    def test_different_project_volume_is_not_used_for_journal_recovery(self):
        controller, _, stopped, _ = self.setup_restore()
        stopped[e1.DB_SERVICES[0]]["Mounts"][1]["Name"] = self.plan["project"] + "_different-state"
        controller.command = Mock(return_value="")
        controller.recover_access(stopped)
        self.assertEqual(controller.access_recovery[0]["status"], "failed")
        # Only the valid backup is attempted; the changed primary volume is never mounted.
        self.assertEqual(controller.command.call_count, 1)
        self.assertNotIn("different-state", " ".join(controller.command.call_args.args[0]))


class RecoveryOutcomeTests(Fixture, unittest.IsolatedAsyncioTestCase):
    dependencies = original.FlowTests.dependencies

    async def run_recovery_case(self, receipts):
        self.plan["recover_access"] = True
        controller, transport, _, _ = self.dependencies()
        controller.access_recovery = receipts
        health = AsyncMock(return_value=original.healthy())
        with patch("subprocess.run", side_effect=AssertionError("real resources forbidden")):
            code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                                     transport_factory=lambda *_: transport, final_health=health)
        controller.restore.assert_called_once()
        health.assert_awaited_once()
        return code, e1.load(self.args.output / "results.json")

    async def test_recovered_journals_and_healthy_business_allow_the_case_to_complete(self):
        code, report = await self.run_recovery_case([{"status": "recovered"}, {"status": "recovered"}])
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "completed")

    async def test_healthy_resource_restoration_does_not_override_a_journal_recovery_failure(self):
        code, report = await self.run_recovery_case([{"status": "failed", "error_class": "ValueError"}, {"status": "recovered"}])
        self.assertEqual(code, 1)
        self.assertEqual(report["resource_and_worker_restore"], "completed")
        self.assertTrue(report["independent_final_H00"]["passed"])
        self.assertEqual(report["access_recovery_error_class"], "AccessRecoveryIncomplete")
        self.assertEqual(report["status"], "failed")


if __name__ == "__main__":
    unittest.main()
