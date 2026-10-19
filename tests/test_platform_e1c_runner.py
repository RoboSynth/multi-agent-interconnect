"""E1-c plan/authorization and flow checks; no platform, containers or resources."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval import platform_resume_experiment as e1
from eval.prepare_platform_e1_worker import prepare as prepare_workers
import test_platform_resume_experiment as original_tests


class RevivalFixture(original_tests.Fixture):
    point = "before_modification"

    def setUp(self):
        super().setUp()
        self.bundle = self.root / "revival-bundle"
        prepare_workers(self.bundle, experiment_id="e1-synthetic", incident_id="incident-synthetic",
            primary_aic="primary", backup_aic="backup", crash_point=self.point,
            arm_primary=True, suspend_primary=True)
        self.args.bundle = self.bundle
        self.args.case, self.args.method = "E1-c", None
        self.args.plan = self.root / "revival-plan.json"
        self.args.output = self.root / "eval/results/platform/e1-revival"
        self.plan = e1.prepare(self.args)

    def auth(self, **changes):
        return super().auth(interruption_mode="suspend", replay_attempts=1, **changes)


class EntryTests(RevivalFixture):
    def test_preparation_binds_one_suspended_request_without_runtime(self):
        self.assertEqual(self.plan["schema_version"], "platform-e1-plan/3")
        self.assertEqual(self.plan["interruption_mode"], "suspend")
        self.assertEqual(self.plan["replay_attempts"], 1)
        self.assertIn("SIGSTOP", self.plan["effects"][2])
        with patch.object(e1, "run_case") as run, patch("subprocess.run") as process:
            self.assertEqual(e1.main(["--plan", str(self.args.plan)]), 0)
        run.assert_not_called(); process.assert_not_called()
        self.assertFalse(self.args.output.exists())

    def test_version_case_point_method_and_replay_scope_cannot_drift(self):
        for changes in ({"schema_version": "platform-e1-plan/2"}, {"case": "E1-a"},
                        {"crash_point": "after_applied"}, {"method": "resume_package"},
                        {"interruption_mode": "exit"}, {"replay_attempts": 2}, {"replay_attempts": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                e1.validate_plan(document={**self.plan, **changes})

    def test_exit_worker_cannot_be_relabelled_as_revival(self):
        self.args.bundle = self.root / "bundle"
        self.args.plan = self.root / "wrong-plan.json"
        with self.assertRaisesRegex(ValueError, "interruption mode"):
            e1.prepare(self.args)

    def test_old_and_wrong_authorization_stops_before_lock_and_runtime(self):
        authorized = e1.load(self.auth())
        for changes in ({"schema_version": "platform-e1-authorization/2"}, {"case": "E1-a"},
                        {"interruption_mode": "exit"}, {"replay_attempts": 2}, {"replay_attempts": True},
                        {"effects": e1.effects(self.point)}, {"authorized": False}):
            path = self.root / "wrong-authorization.json"
            e1.save(path, {**authorized, **changes})
            with self.subTest(changes=changes), patch.object(e1, "run_case") as run, patch.object(e1, "coordinator_lock") as lock:
                with self.assertRaises(ValueError):
                    e1.main(["--plan", str(self.args.plan), "--execute", "--approve-high", "--authorization-file", str(path)])
                run.assert_not_called(); lock.assert_not_called()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(e1.authorize(self.plan, self.args.plan, self.auth(), True), authorized)

    def test_overlay_init_and_source_changes_are_bound(self):
        import yaml
        path = self.bundle / "e1-worker-overlay.yml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIs(document["services"][e1.DB_SERVICES[0]]["init"], True)
        document["services"][e1.DB_SERVICES[0]].pop("init")
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        tampered = deepcopy(self.plan)
        tampered["file_sha256"][path.relative_to(self.root).as_posix()] = e1.digest(path)
        with self.assertRaisesRegex(ValueError, "overlay"):
            e1.validate_plan(document=tampered)

    def test_future_compose_allows_only_primary_init_change(self):
        import yaml
        controller = e1.Controller(self.plan, self.root)
        controller.command = Mock()
        normal = {"services": {}}
        overlay = yaml.safe_load((self.bundle / "e1-worker-overlay.yml").read_text(encoding="utf-8"))
        for service in e1.DB_SERVICES:
            normal["services"][service] = dict(image="synthetic", command=["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"],
                labels={"incident-pilot": "true"}, volumes=[], restart="unless-stopped", read_only=True)
        changed = deepcopy(normal)
        for service, spec in overlay["services"].items():
            changed["services"][service].update(deepcopy(spec))
            changed["services"][service]["labels"] = normal["services"][service]["labels"] | spec["labels"]
            changed["services"][service]["volumes"][0]["source"] = str(self.bundle)
        def configure(document):
            controller.command.side_effect = [json.dumps(normal), json.dumps(document), *[self.args.image_id] * 4]
        configure(changed)
        controller.future_configuration()
        for service, key, value in ((e1.DB_SERVICES[0], "init", False), (e1.DB_SERVICES[1], "init", True),
                                    (e1.DB_SERVICES[0], "privileged", True)):
            altered = deepcopy(changed); altered["services"][service][key] = value
            configure(altered)
            with self.subTest(service=service, key=key), self.assertRaises(ValueError):
                controller.future_configuration()


class FlowTests(RevivalFixture, unittest.IsolatedAsyncioTestCase):
    def dependencies(self, **options):
        controller, transport, order, sent = original_tests.FlowTests.dependencies(self, **options)
        transport.runtime.force_remove_partner = AsyncMock(side_effect=lambda *_args, **_kw: order.append("remove-primary"))
        original_call = transport.call.side_effect
        async def call(payload):
            result = await original_call(payload)
            if payload["tool"] == "db.restore_writes":
                await transport.runtime.force_remove_partner("primary", session_id="owned")
            return result
        transport.call.side_effect = call
        return controller, transport, order, sent

    async def test_revival_runs_after_backup_before_business_verification_and_closes(self):
        controller, transport, order, sent = self.dependencies()
        def collect(payload):
            self.assertEqual(transport.selected["database"], "backup")
            self.assertEqual(payload["fence"]["takeover_version"], 0)
            order.append("revive-original-request")
            return dict(replay_attempts=1, rejected_stale_fence=1, same_process=True)
        controller.collect.side_effect = collect
        code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
            transport_factory=lambda *_: transport, final_health=AsyncMock(return_value=original_tests.healthy()))
        self.assertEqual(code, 0)
        report = e1.load(self.args.output / "results.json")
        self.assertEqual(report["schema_version"], "platform-e1-result/3")
        self.assertEqual(report["worker_revival_and_mcp"]["rejected_stale_fence"], 1)
        self.assertNotIn("worker_exit_and_mcp", report)
        self.assertLess(order.index("db.restore_writes"), order.index("revive-original-request"))
        self.assertLess(order.index("revive-original-request"), order.index("remove-primary"))
        self.assertEqual(report["old_primary_removal"]["completed_removals"], 1)
        self.assertLess(order.index("revive-original-request"), order.index("application.pool_rebuild"))
        self.assertLess(order.index("close"), order.index("restore"))
        self.assertIn("Same primary PID", report["journal_resolution"]["basis"])
        self.assertEqual(len([p for p in sent if p["tool"] == "db.restore_writes"]), 1)

    async def test_unproven_revival_is_failure_and_still_restores(self):
        controller, transport, order, _ = self.dependencies()
        controller.collect.side_effect = ValueError("synthetic changed PID")
        code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
            transport_factory=lambda *_: transport, final_health=AsyncMock(return_value=original_tests.healthy()))
        self.assertEqual(code, 1)
        report = e1.load(self.args.output / "results.json")
        self.assertEqual(report["error_class"], "ValueError")
        self.assertNotIn("task_phase_status", report)
        self.assertNotIn("application.pool_rebuild", order)
        self.assertNotIn("remove-primary", order)
        self.assertLess(order.index("close"), order.index("restore"))


if __name__ == "__main__":
    unittest.main()
