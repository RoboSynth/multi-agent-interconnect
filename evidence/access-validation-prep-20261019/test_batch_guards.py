"""File/mock-only guards; these tests never invoke Docker, WSL, MQ or the model."""
from __future__ import annotations
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(HERE / "plan-preparation")]
import batch_scope as scope
import run_authorized as launcher
import run_f10 as f10


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "fixtures")
        self.directory = Path(self.temp.name)
        self.summary_path = self.directory / "summary.json"
        self.summary = dict(source_commit="a"*40, batch_plans_sha256="b"*64,
            plans=[dict(key=row["key"], plan_sha256=str(row["order"])*64) for row in scope.schedule()])
        scope.save(self.summary_path, self.summary)
        self.path = self.directory / "new-authorization.json"
        self.auth = dict(schema_version="access-validation-batch-authorization/1", project=scope.PROJECT,
            plan_count=4, source_commit=self.summary["source_commit"], prepared_summary_sha256=scope.sha(self.summary_path),
            batch_plans_sha256=self.summary["batch_plans_sha256"], plans=scope.plan_map(self.summary["plans"]), model_calls=0,
            **{key: True for key in scope.BOOL_AUTH}, user_confirmation=dict(question_id="fixture-new-four-case-question",
            exact_answer="fixture only; no real authorization"), received_at_utc="2026-10-19T00:00:00+00:00")

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, auth):
        scope.save(self.path, auth)
        return scope.validate_authorization(self.path, self.summary, self.summary_path)

    def test_exact_new_binding_passes_without_effects(self):
        self.assertEqual(self.validate(self.auth), self.auth)

    def test_missing_or_legacy_batch_rejected(self):
        with self.assertRaises(ValueError):
            scope.validate_authorization(None, self.summary, self.summary_path)
        with self.assertRaises(ValueError):
            self.validate(dict(question_id="old", exact_answer="授权12次", count=12))

    def test_scope_and_type_mutations_rejected(self):
        mutations = [(key, False) for key in scope.BOOL_AUTH]
        mutations += [(key, 1) for key in scope.BOOL_AUTH]
        mutations += [("plan_count", True), ("plan_count", 12), ("source_commit", "c"*40),
                      ("prepared_summary_sha256", "c"*64), ("batch_plans_sha256", "c"*64),
                      ("plans", {}), ("model_calls", False), ("model_calls", 1), ("project", "old-project")]
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate({**self.auth, key: value})
        for confirmation in ({}, {"question_id": "", "exact_answer": "yes"}, {"question_id": "new", "exact_answer": 1}):
            with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                self.validate({**self.auth, "user_confirmation": confirmation})

    def test_entrypoint_never_reaches_execute_without_valid_auth(self):
        with patch.object(scope, "validate_summary", return_value=(self.summary, {}, object())), \
             patch.object(launcher, "execute") as execute:
            with self.assertRaises(ValueError):
                launcher.main(["--execute"])
            execute.assert_not_called()
            self.assertEqual(launcher.main([]), 0)
            execute.assert_not_called()


class FrozenPlanTests(unittest.TestCase):
    def test_summary_rejects_consumed_outputs_plan_mutation_and_point_drift(self):
        with tempfile.TemporaryDirectory(dir=HERE / "fixtures") as directory:
            batch = Path(directory)
            root, private, results, profile = batch / "root", batch / "root/plans", batch / "root/results", batch / "root/profile"
            profile.mkdir(parents=True)
            scope.save(profile / "deployment.json", {})
            source = root / "source.py"
            source.write_text("fixture", encoding="utf-8")
            for name in scope.EXECUTION_FILES:
                (batch / name).parent.mkdir(parents=True, exist_ok=True)
                (batch / name).write_text("fixture helper", encoding="utf-8")
            images = {"agent": {"image_id": "fixture-image"}}
            rows = []
            for row in scope.schedule():
                path = private / row["key"] / "plan.json"
                plan = dict(recover_access=True, image_id="fixture-image")
                if row["case"] == "F10":
                    plan = dict(schema_version="access-validation-f10-plan/1", case="F10", method="M0", repeat=1,
                        model_calls=0, enable_llm=False, transport="wutong-amqps", backend="docker", project=scope.PROJECT,
                        effects=scope.F10_EFFECTS, file_sha256={"source.py": scope.sha(source)}, output="results/"+row["key"])
                scope.save(path, plan)
                rows.append({**row, "plan": path.relative_to(root).as_posix(), "plan_sha256": scope.sha(path),
                             "output": "results/"+row["key"]})
            summary = dict(schema_version="access-validation-batch/1", project=scope.PROJECT, ports=scope.PORTS,
                plan_count=4, execution_authorization_written=False, image_results=images,
                deployment_sha256=scope.sha(profile / "deployment.json"), source_sha256={"source.py": scope.sha(source)},
                source_commit="a"*40, execution_script_sha256={name: scope.sha(batch / name) for name in scope.EXECUTION_FILES},
                plans=rows, batch_plans_sha256=scope.canonical_sha(scope.plan_map(rows)))
            summary_path = batch / "summary.json"
            scope.save(summary_path, summary)
            e1 = SimpleNamespace(source_paths=lambda: [source], validate_plan=scope.load)
            with patch.multiple(scope, ROOT=root, PRIVATE=private, RESULTS=results, PROFILE=profile, BATCH=batch), \
                 patch.object(scope, "images", return_value=images), patch.object(scope, "deployment", return_value=({}, object())), \
                 patch.object(scope, "product", return_value=(e1,)), patch.object(scope, "source_commit"):
                scope.validate_summary(summary_path)
                consumed = results / rows[0]["key"]
                consumed.mkdir(parents=True)
                with self.assertRaises(ValueError):
                    scope.validate_summary(summary_path)
                scope.validate_summary(summary_path, allow_consumed=[rows[0]["key"]])
                consumed.rmdir()
                changed = copy.deepcopy(summary)
                changed["plans"][1]["point"] = "after_applied"
                scope.save(summary_path, changed)
                with self.assertRaises(ValueError):
                    scope.validate_summary(summary_path)
                scope.save(summary_path, summary)
                scope.local(rows[1]["plan"]).write_text("{}", encoding="utf-8")
                with self.assertRaises(ValueError):
                    scope.validate_summary(summary_path)

    def test_f10_rejects_model_or_method_and_mutated_inputs(self):
        with tempfile.TemporaryDirectory(dir=HERE / "fixtures") as directory:
            root = Path(directory)
            frozen = root / "input.py"
            frozen.write_text("initial", encoding="utf-8")
            output = root / "results/f10-m0-r1"
            plan = dict(schema_version="access-validation-f10-plan/1", case="F10", method="M0", repeat=1,
                model_calls=0, enable_llm=False, transport="wutong-amqps", backend="docker", project=scope.PROJECT,
                effects=scope.F10_EFFECTS, file_sha256={"input.py": scope.sha(frozen)}, output="results/f10-m0-r1")
            with patch.object(scope, "ROOT", root), patch.object(scope, "RESULTS", output.parent):
                scope.validate_f10(plan)
                for key, value in (("enable_llm", True), ("enable_llm", 0), ("method", "M2"),
                                   ("model_calls", False), ("repeat", 3), ("effects", []), ("backend", "native")):
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        scope.validate_f10({**plan, key: value})
                frozen.write_text("mutated", encoding="utf-8")
                with self.assertRaises(ValueError):
                    scope.validate_f10(plan)

    def test_source_commit_rejects_wrong_git_blob_and_missing_commit(self):
        with tempfile.TemporaryDirectory(dir=HERE / "fixtures") as directory:
            root = Path(directory)
            (root / "one.py").write_bytes(b"frozen")
            run = Mock(side_effect=[SimpleNamespace(returncode=0),
                SimpleNamespace(returncode=0, stdout=b"100644 blob " + b"a"*40 + b"\tone.py\0")])
            with patch.object(scope, "ROOT", root), patch.object(scope.shutil, "which", return_value="fixture-git"), \
                 patch.object(scope.subprocess, "run", run):
                with self.assertRaises(ValueError):
                    scope.source_commit("a"*40, {"one.py": scope.sha(root / "one.py")})
                with self.assertRaises(ValueError):
                    scope.source_commit(None, {})

    def test_f10_arguments_are_exact_no_model(self):
        runner = SimpleNamespace(build_parser=lambda: __import__("argparse").ArgumentParser())
        parser = Mock()
        parser.parse_args = lambda argv: argv
        runner.build_parser = lambda: parser
        argv = f10.arguments(runner, dict(config="runtime/private/c.json", target_config="runtime/private/t.json", output="eval/results/fixture"))
        self.assertNotIn("--enable-llm", argv)
        self.assertEqual(argv[argv.index("--methods")+1], "M0")
        self.assertEqual(argv[argv.index("--scenarios")+1], "F10")
        self.assertEqual(argv[argv.index("--repeats")+1], "1")


class OwnershipTests(unittest.TestCase):
    def row(self):
        return dict(id="new-id", project=scope.PROJECT, service="database-agent", image_id="sha256:agent",
            created="2026-10-19T00:00:02Z", started_at="2026-10-19T00:00:03Z", running=True, recovery=None)

    def test_project_service_image_started_and_original_ids_all_required(self):
        row = self.row()
        expected = {"database-agent": "sha256:agent", "app-v2": "sha256:app"}
        launcher.prove_owned([row], set(), expected, "2026-10-19T00:00:01Z")
        for change in (dict(service="unknown"), dict(image_id="wrong"), dict(created="2026-10-18T00:00:00Z"),
                       dict(started_at="2026-10-18T00:00:00Z")):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                launcher.prove_owned([{**row, **change}], set(), expected, "2026-10-19T00:00:01Z")
        with self.assertRaises(RuntimeError):
            launcher.prove_owned([row], {row["id"]}, expected, "2026-10-19T00:00:01Z")

    def test_final_stop_rejects_replacement_and_start_regression(self):
        row = self.row()
        launcher.match_registered([row], {row["id"]: row})
        for change in (dict(id="replacement"), dict(image_id="wrong"), dict(service="app-v2"),
                       dict(started_at="2026-10-19T00:00:01Z")):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                launcher.match_registered([{**row, **change}], {row["id"]: row})

    def test_final_stop_rejects_same_id_external_restart(self):
        row = self.row()
        registered = {row["id"]: row}
        self.assertEqual(launcher.match_registered([dict(row)], registered), [row])
        restarted = {**row, "started_at": "2026-10-19T00:01:03Z"}
        with self.assertRaisesRegex(RuntimeError, "identity/start time changed"):
            launcher.match_registered([restarted], registered)
        # Rejection must retain the original ownership registration.
        self.assertEqual(registered[row["id"]]["started_at"], "2026-10-19T00:00:03Z")

    def test_only_proven_child_restored_database_ids_can_replace_registration(self):
        primary = self.row()
        backup = {**primary, "id": "old-backup", "service": "database-backup-agent"}
        nginx = {**primary, "id": "nginx", "service": "nginx", "image_id": "sha256:nginx"}
        registered = {row["id"]: row for row in (primary, backup, nginx)}
        new_primary = {**primary, "id": "restored-primary", "created": "2026-10-19T00:01:02Z", "started_at": "2026-10-19T00:01:03Z"}
        new_backup = {**backup, "id": "restored-backup", "created": "2026-10-19T00:01:02Z", "started_at": "2026-10-19T00:01:03Z"}
        initial = {row["service"]: dict(container_id=row["id"], image_id=row["image_id"]) for row in (primary, backup)}
        restored = {row["service"]: dict(container_id=row["id"], image_id=row["image_id"]) for row in (new_primary, new_backup)}
        images = {row["service"]: row["image_id"] for row in (primary, backup, nginx)}
        rows = [new_primary, new_backup, nginx]
        result = launcher.restored_registration(rows, registered, initial, restored, "2026-10-19T00:01:01Z", images)
        self.assertEqual(set(result), {"restored-primary", "restored-backup", "nginx"})
        for altered in ({}, {**restored, "database-agent": dict(container_id="foreign-id", image_id="sha256:agent")}):
            with self.assertRaises(RuntimeError):
                launcher.restored_registration(rows, registered, initial, altered, "2026-10-19T00:01:01Z", images)
        with self.assertRaises(RuntimeError):
            launcher.restored_registration([new_primary, new_backup, {**nginx, "started_at": "2026-10-19T00:01:03Z"}],
                registered, initial, restored, "2026-10-19T00:01:01Z", images)

    def test_cleanup_requires_exact_six_true_checks(self):
        good = dict.fromkeys(("no_group_sessions", "no_inbound_groups", "inbox_cancelled", "connection_closed",
                              "owned_group_disconnected", "no_cleanup_warnings"), True)
        self.assertTrue(launcher.close_safe(dict(close_checks=good)))
        self.assertFalse(launcher.close_safe(dict(close_checks={**good, "connection_closed": 1})))
        self.assertFalse(launcher.close_safe(dict(close_checks={"arbitrary": True})))


class F10CloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_failure_still_observes_H00_and_retains_evaluation_failure(self):
        with tempfile.TemporaryDirectory(dir=HERE / "fixtures") as directory:
            root = Path(directory)
            output = root / "output"
            raw_close = AsyncMock()
            transport = SimpleNamespace(close=raw_close, session=None, runtime=None)
            parser = Mock()
            parser.parse_args.return_value = SimpleNamespace()
            runner = SimpleNamespace(build_parser=lambda: parser, create_transport=lambda *args: transport,
                                     DOMAIN_SOURCE_FILES=())
            async def run(args):
                output.mkdir()
                made = runner.create_transport()
                try:
                    raise ValueError("fixture evaluation failed")
                finally:
                    await made.close()
            runner.run = run
            runner.inject = AsyncMock(side_effect=[dict(target_proof=dict(compose_sha256={}, domains={})),
                                                   RuntimeError("fixture restore failed")])
            observer = SimpleNamespace(observe=AsyncMock(return_value=dict(passed=True, duration_seconds=30,
                completed_workflows=10, failed=0, unknown=0, unresolved_intents=0, state=dict(pending=[]))))
            plan = dict(config="c.json", target_config="t.json", output="output", file_sha256={})
            with patch.object(scope, "ROOT", root), patch.object(scope, "deployment", return_value=({}, SimpleNamespace(order_url="fixture"))):
                code = await f10.execute(plan, runner=runner, observer_factory=lambda *args, **kwargs: observer)
            self.assertEqual(code, 1)
            report = scope.load(output / "wrapper-result.json")
            self.assertEqual(report["evaluation_error_class"], "ValueError")
            self.assertEqual(report["restore_error_class"], "RuntimeError")
            self.assertTrue(report["independent_final_H00"]["passed"])
            raw_close.assert_awaited_once()
            observer.observe.assert_awaited_once_with(duration=30, min_complete=10)

    async def test_original_close_called_once_without_recursion(self):
        raw = AsyncMock()
        transport = SimpleNamespace(close=raw, session=None, runtime=None)
        e1, *_ = scope.product()
        report = {}
        f10.instrument_close(transport, e1, SimpleNamespace(events=[]), report)
        await transport.close()
        raw.assert_awaited_once()
        self.assertTrue(report["close_requested"])
        self.assertEqual(len(report["close_checks"]), 6)
        with self.assertRaises(RuntimeError):
            await transport.close()
        raw.assert_awaited_once()

    async def test_close_failure_retained_not_retried(self):
        raw = AsyncMock(side_effect=RuntimeError("fixture failed close"))
        transport = SimpleNamespace(close=raw, session=None, runtime=None)
        e1, *_ = scope.product()
        report = {}
        f10.instrument_close(transport, e1, SimpleNamespace(events=[]), report)
        with self.assertRaises(RuntimeError):
            await transport.close()
        self.assertEqual(report["close_error_class"], "RuntimeError")
        self.assertIn("fixture failed close", report["close_traceback"])
        raw.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
