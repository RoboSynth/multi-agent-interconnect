"""E1 controller/entrypoint contract using only synthetic files and stubs."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval import platform_resume_experiment as e1
from eval.prepare_platform_e1_worker import prepare as prepare_workers
from eval.targets import DOMAIN_SERVICES


def healthy():
    return dict(passed=True, duration_seconds=30.01, completed_workflows=10,
                failed=0, unknown=0, unresolved_intents=0, state={"pending": []})


class Fixture(unittest.TestCase):
    point = "after_applied"

    def setUp(self):
        (ROOT / "artifacts").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "artifacts")
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(e1, "ROOT", self.root); self.root_patch.start()
        self.addCleanup(self.root_patch.stop); self.addCleanup(self.temp.cleanup)
        self.source = self.root / "runner-source.py"; self.source.write_text("# synthetic freeze\n", encoding="utf-8")
        self.source_patch = patch.object(e1, "source_paths", return_value={self.source}); self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.profile = self.root / "profile"
        for role in (*e1.ROLES, "coordinator"):
            folder = self.profile / "domains" / role; folder.mkdir(parents=True)
            (folder / "binding.json").write_text("{}", encoding="utf-8")
        self.config = dict(leader={"aic": "coordinator", "cert": str(self.root / "cert.pem"), "key": str(self.root / "key.pem")},
            trust_bundle=str(self.root / "ca.pem"), approval_env_file=str(self.root / "approval.env"),
            term_journal_path=str(self.root / "persistent-terms.sqlite"), term_namespace="synthetic/orders",
            skills={role: role + ".skill" for role in ("application", "database", "ops", "verification", "onboarding")},
            trusted_participant_aics={role: [role] for role in ("application", "ops", "verification", "onboarding")},
            initial_participant_aics={"database": "primary"})
        self.config["trusted_participant_aics"]["database"] = ["primary", "backup"]
        for name in ("cert.pem", "key.pem", "ca.pem", "approval.env", "target.env", "compose.yml", "route.conf"):
            (self.root / name).write_text("synthetic fixture", encoding="utf-8")
        e1.save(self.root / "config.json", self.config)
        e1.save(self.root / "target.json", dict(schema_version="incident-evaluator-target/1.0", backend="docker",
            project="synthetic-e1", wsl_distro=None, compose_files=[str(self.root / "compose.yml")],
            env_file=str(self.root / "target.env"), route_file=str(self.root / "route.conf"),
            ports={"app_v1": 18081, "app_v2": 18082, "order": 18088}))
        self.bundle = self.root / "bundle"
        prepare_workers(self.bundle, experiment_id="e1-synthetic", incident_id="incident-synthetic",
            primary_aic="primary", backup_aic="backup", crash_point=self.point, arm_primary=True)
        sources = {self.source}
        for name in ("eval/platform_database_worker.py", "acps_mcp_bridge/experiment.py", "incident/local_worker.py"):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.bundle / "source" / name).read_bytes()); sources.add(path)
        e1.source_paths.return_value = sources
        self.args = SimpleNamespace(config=self.root / "config.json", target_config=self.root / "target.json",
            domain_profile=self.profile, bundle=self.bundle, image_id="sha256:" + "a" * 64,
            output=self.root / "eval/results/platform/e1-once", plan=self.root / "plan.json")
        self.plan = e1.prepare(self.args)

    def auth(self, **changes):
        value = dict(schema_version="platform-e1-authorization/" + self.plan["schema_version"].rsplit("/", 1)[1], authorized=True,
            plan_sha256=e1.digest(self.args.plan), experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
            output=self.plan["output"], case=self.plan["case"], crash_point=self.plan["crash_point"], effects=self.plan["effects"],
            exclusive_coordinator=True, no_other_identity_consumers=True, no_active_or_unknown_operations=True)
        value.update(changes); path = self.root / "authorization.json"; e1.save(path, value)
        return path

    def records(self, *, experiment=False):
        result = {}
        for service, role in DOMAIN_SERVICES.items():
            aic = {"database-agent": "primary", "database-backup-agent": "backup"}.get(service, role)
            labels = {"incident-pilot": "true", "com.docker.compose.project": "synthetic-e1", "com.docker.compose.service": service}
            command = ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"]
            mounts = [{"Destination": "/domain", "RW": False, "Type": "bind", "Source": str(self.profile / "domains" /
                       ("database-backup" if service == "database-backup-agent" else role))},
                      {"Destination": "/state", "Type": "volume", "Name": "synthetic-e1_database-agent-state", "RW": True}]
            if experiment and service in e1.DB_SERVICES:
                import yaml
                spec = yaml.safe_load((self.bundle / "e1-worker-overlay.yml").read_text(encoding="utf-8"))["services"][service]
                command = spec["command"]; labels.update(spec["labels"])
                mounts.append({"Destination": "/experiment", "Source": str(self.bundle), "Type": "bind", "RW": False})
            result[service] = {"Id": ("experimental-" if experiment and service in e1.DB_SERVICES else "original-") + service,
                "Image": self.args.image_id, "Config": {"Labels": labels, "Cmd": command}, "Mounts": mounts,
                "State": {"Running": True, "StartedAt": "synthetic-start", "ExitCode": 0},
                "HostConfig": {"ReadonlyRootfs": True, "RestartPolicy": {"Name": "no" if experiment and service == e1.DB_SERVICES[0] else "unless-stopped"}}}
        for service in ("postgres", "app-v1", "app-v2", "nginx"):
            result[service] = {"Id": "original-" + service, "Image": "business-image", "State": {"Running": True, "StartedAt": "business-start"},
                "Config": {"Labels": {"incident-pilot": "true", "com.docker.compose.project": "synthetic-e1", "com.docker.compose.service": service}}}
        return result


class EntryTests(Fixture):
    def test_existing_identity_lock_path_is_exclusive_across_processes_and_releases(self):
        code = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from eval import platform_resume_experiment as m
m.ROOT=Path(sys.argv[2])
try:
    with m.coordinator_lock('synthetic-lock-only'):
        print(json.dumps({'acquired':True}))
except OSError:
    print(json.dumps({'acquired':False}))
    raise SystemExit(23)
"""
        command = [sys.executable, "-c", code, str(ROOT), str(self.root)]
        with e1.coordinator_lock("synthetic-lock-only"):
            expected = self.root / "artifacts/new7-platform-healthy-plan-20261018/ownership" / (
                __import__("hashlib").sha256(b"synthetic-lock-only").hexdigest() + ".lock")
            self.assertTrue(expected.is_file())
            blocked = subprocess.run(command, capture_output=True, text=True, timeout=15, env=e1.clean_environment())
            self.assertEqual(blocked.returncode, 23, blocked.stderr)
            self.assertEqual(json.loads(blocked.stdout), {"acquired": False})
        acquired = subprocess.run(command, capture_output=True, text=True, timeout=15, env=e1.clean_environment())
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        self.assertEqual(json.loads(acquired.stdout), {"acquired": True})

    def test_default_validates_without_runtime_or_output(self):
        with patch.object(e1, "run_case") as live, patch.object(e1, "coordinator_lock") as lock, patch("subprocess.run") as process:
            self.assertEqual(e1.main(["--plan", str(self.args.plan)]), 0)
        live.assert_not_called(); lock.assert_not_called(); process.assert_not_called()
        self.assertFalse(self.args.output.exists()); self.assertFalse((self.root / "runtime").exists())
        self.assertFalse((self.root / "persistent-terms.sqlite").exists())

    def test_missing_wrong_and_stale_authorization_stop_before_runtime(self):
        for changes in (None, {"authorized": False}, {"authorized": 1}, {"plan_sha256": "0" * 64}, {"incident_id": "other"},
                        {"exclusive_coordinator": False}, {"no_other_identity_consumers": False}, {"extra": True}):
            argv = ["--plan", str(self.args.plan), "--execute", "--approve-high"]
            if changes is not None:
                argv += ["--authorization-file", str(self.auth(**changes))]
            with self.subTest(changes=changes), patch.object(e1, "run_case") as live, patch.object(e1, "coordinator_lock") as lock:
                with self.assertRaises(ValueError):
                    e1.main(argv)
                live.assert_not_called(); lock.assert_not_called()
                self.assertFalse(self.args.output.exists())

    def test_approval_resource_environment_and_changed_source_block(self):
        auth = self.auth()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(e1.authorize(self.plan, self.args.plan, auth, True)["authorized"], True)
            with self.assertRaises(ValueError): e1.authorize(self.plan, self.args.plan, auth, False)
            with patch.dict(os.environ, {"PGPASSWORD": "synthetic"}):
                with self.assertRaises(ValueError): e1.authorize(self.plan, self.args.plan, auth, True)
        self.source.write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError): e1.validate_plan(self.args.plan)

    def test_output_reuse_and_missing_freeze_inputs_refused(self):
        changed = deepcopy(self.plan); changed["file_sha256"].pop("target.env")
        with self.assertRaises(ValueError): e1.validate_plan(document=changed)
        self.args.output.mkdir(parents=True)
        with self.assertRaises(ValueError): e1.validate_plan(self.args.plan)

    def test_bundle_mutations_fail_even_with_updated_outer_hash(self):
        for name, change in (("backup.json", lambda v: v.update(armed=True)),
                             ("primary.json", lambda v: v.update(incident_id="other"))):
            original = (self.bundle / name).read_bytes()
            value = json.loads(original); change(value); e1.save(self.bundle / name, value)
            plan = deepcopy(self.plan); relative = (self.bundle / name).relative_to(self.root).as_posix()
            plan["file_sha256"][relative] = e1.digest(self.bundle / name)
            with self.assertRaises(ValueError): e1.validate_plan(document=plan)
            (self.bundle / name).write_bytes(original)

    def test_bad_prepare_is_checked_before_plan_or_output_creation(self):
        args = deepcopy(self.args); args.plan = self.root / "new-plan.json"; args.image_id = "latest"
        with self.assertRaises(ValueError): e1.prepare(args)
        self.assertFalse(args.plan.exists()); self.assertFalse(args.output.exists())


class OwnershipTests(Fixture):
    def controller(self):
        return e1.Controller(self.plan, self.root)

    def rendered(self):
        import yaml
        spec = yaml.safe_load((self.bundle / "e1-worker-overlay.yml").read_text(encoding="utf-8"))["services"]
        normal = dict(services={}, networks={"default": {"name": "synthetic-e1_default"}})
        for name in e1.DB_SERVICES:
            normal["services"][name] = dict(image="frozen-local-tag", command=["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"],
                restart="unless-stopped", labels={"incident-pilot": "true"},
                environment={"PRIVATE_SYNTHETIC": "never-retain-this-fixture-value"},
                volumes=[{"type": "volume", "source": "synthetic-state", "target": "/state"}])
        extra = deepcopy(normal)
        for name in e1.DB_SERVICES:
            extra["services"][name].update(command=spec[name]["command"], labels=normal["services"][name]["labels"] | spec[name]["labels"])
            extra["services"][name]["volumes"].append(dict(type="bind", source=str(self.bundle), target="/experiment", read_only=True))
        extra["services"][e1.DB_SERVICES[0]]["restart"] = "no"
        return normal, extra

    def test_future_image_mismatch_stops_before_owned_workers_even_if_current_image_matches(self):
        controller = self.controller(); controller.inspect = Mock(return_value=self.records())
        normal, extra = self.rendered()
        controller.command = Mock(side_effect=[json.dumps(normal), json.dumps(extra), "sha256:wrong-future-image"])
        controller.injector = Mock()
        with self.assertRaises(ValueError): controller.begin()
        self.assertFalse(controller.switched); self.assertFalse(controller.ownership_confirmed)
        controller.injector.assert_not_called()
        self.assertFalse(any("stop" in call.args[0] for call in controller.command.call_args_list))

    def test_all_profiles_only_used_for_readonly_render(self):
        controller = self.controller(); normal, extra = self.rendered()
        controller.command = Mock(side_effect=[json.dumps(normal), json.dumps(extra)] + [self.plan["image_id"]] * 4)
        controller.future_configuration()
        calls = [call.args[0] for call in controller.command.call_args_list]
        for argv in calls[:2]:
            self.assertEqual(argv[-5:], ["--profile", "*", "config", "--format", "json"])
        self.assertFalse(any("--profile" in argv or "*" in argv for argv in calls[2:]))
        for compose in (controller.normal, controller.overlay):
            up = compose + ["up", "-d", "--no-deps", "--force-recreate", "--no-build", "--pull", "never", *e1.DB_SERVICES]
            self.assertNotIn("--profile", up); self.assertNotIn("*", up)

    def test_rendered_contract_pins_both_future_images_and_never_retains_private_values(self):
        controller = self.controller(); normal, extra = self.rendered()
        controller.command = Mock(side_effect=[json.dumps(normal), json.dumps(extra)] + [self.plan["image_id"]] * 4)
        controller.future_configuration()
        proof = (self.root / "future-compose-image-bindings.json").read_text(encoding="utf-8")
        self.assertNotIn("never-retain-this-fixture-value", proof)
        self.assertFalse(json.loads(proof)["raw_render_retained"])
        extra["services"][e1.DB_SERVICES[0]]["environment"]["UNPLANNED"] = "bad"
        controller.command = Mock(side_effect=[json.dumps(normal), json.dumps(extra)])
        with self.assertRaises(ValueError): controller.future_configuration()

    def test_wrong_owner_or_duplicate_service_refused(self):
        controller = self.controller()
        for changes in ({"incident-pilot": "false"}, {"com.docker.compose.project": "foreign"}):
            records = list(self.records().values()); records[0]["Config"]["Labels"].update(changes)
            controller.command = Mock(side_effect=["ids", json.dumps(records)])
            with self.assertRaises(ValueError): controller.inspect()
        records = list(self.records().values()); records.append(records[0])
        controller.command = Mock(side_effect=["ids", json.dumps(records)])
        with self.assertRaises(ValueError): controller.inspect()

    def test_unfinished_or_reused_database_operation_blocks_before_worker_stop(self):
        for operation in ({"operation_id": "prior", "state": "unknown"},
                          {"operation_id": self.plan["operation_id"], "state": "applied"}):
            controller = self.controller(); controller.inspect = Mock(return_value=self.records())
            controller.injector = Mock(return_value={name: {"image_id": self.plan["image_id"]} for name in DOMAIN_SERVICES})
            controller.future_configuration = Mock()
            controller.ledger_probe = Mock(return_value={"exists": True, "operations": [operation]})
            controller.command = Mock()
            with self.assertRaises(ValueError): controller.begin()
            controller.command.assert_not_called()
            self.assertFalse(controller.switched)

    def test_exact_primary_exit_and_trace_correlate_to_one_modifying_invocation(self):
        controller = self.controller(); original = self.records(); records = self.records(experiment=True)
        controller.original = original
        controller.experimental = {name: records[name]["Id"] for name in e1.DB_SERVICES}
        controller.experimental_started = {name: records[name]["State"]["StartedAt"] for name in e1.DB_SERVICES}
        records[e1.DB_SERVICES[0]]["State"].update(Running=False, ExitCode=83)
        controller.inspect = Mock(return_value=records)
        common = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"], executor_aic="primary",
            operation_id=self.plan["operation_id"], logical_task_id="actual-db-task", transport="wutong-amqps",
            invocation_id="one", server="postgres", upstream_tool="query", tool="db.restore_writes")
        events = [{**common, "event": "mcp_modify_invocation"}, {**common, "event": "mcp_modify_returned", "is_error": False},
                  {**common, "event": "experiment_worker_crash", "crash_point": "after_applied", "exit_code": 83,
                   "ledger_state": "applied", "AIP_product_submitted": False}]
        def startup(role, aic):
            return dict(event="experiment_worker_start", experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
                executor_aic=aic, transport="wutong-amqps", worker_role=role, armed=role == "primary",
                bundle_manifest_sha256=e1.digest(self.bundle / "worker-source-manifest.json"))
        events.insert(0, startup("primary", "primary"))
        trace = "".join(json.dumps(row) + "\n" for row in events)
        backup_trace = json.dumps(startup("backup", "backup")) + "\n"
        controller.command = Mock(side_effect=[trace, backup_trace])
        result = controller.collect({"logical_task_id": "actual-db-task"})
        self.assertEqual(result["actual_exit_code"], 83)
        self.assertEqual(result["counts"]["operations"][0]["invocations"], 1)
        controller.command = Mock(side_effect=[trace, backup_trace])
        with self.assertRaises(ValueError): controller.collect({"logical_task_id": "wrong-task"})
        records[e1.DB_SERVICES[0]]["State"]["StartedAt"] = "unexpected-restart"
        controller.command.reset_mock()
        with self.assertRaises(ValueError): controller.collect({"logical_task_id": "actual-db-task"})
        controller.command.assert_not_called()

    def test_worker_image_mount_command_restart_and_shared_state_contract(self):
        controller = self.controller(); valid = self.records(experiment=True)
        controller.owned_database(valid, experiment=True)
        mutations = [lambda v: v[e1.DB_SERVICES[0]].update(Image="sha256:foreign"),
            lambda v: v[e1.DB_SERVICES[0]]["Mounts"][0].update(RW=True),
            lambda v: v[e1.DB_SERVICES[0]]["Config"].update(Cmd=["foreign"]),
            lambda v: v[e1.DB_SERVICES[0]]["HostConfig"]["RestartPolicy"].update(Name="always"),
            lambda v: v[e1.DB_SERVICES[1]]["Mounts"][1].update(Name="other-project-state")]
        for mutate in mutations:
            value = deepcopy(valid); mutate(value)
            with self.assertRaises(ValueError): controller.owned_database(value, experiment=True)

    def test_restore_refuses_unknown_replacement_before_any_stop(self):
        controller = self.controller(); controller.original = self.records(); controller.switched = True
        controller.experimental = {s: "expected-" + s for s in e1.DB_SERVICES}
        changed = self.records(experiment=True)
        controller.inspect = Mock(return_value=changed); controller.command = Mock()
        with self.assertRaises(ValueError): controller.restore()
        controller.command.assert_not_called()

    def test_partial_owned_overlay_failure_can_restore_only_two_database_services(self):
        controller = self.controller(); controller.original = self.records(); controller.switched = True
        partial = self.records(); partial[e1.DB_SERVICES[0]] = self.records(experiment=True)[e1.DB_SERVICES[0]]
        restored = self.records()
        for service in e1.DB_SERVICES: restored[service]["Id"] = "restored-" + service
        controller.inspect = Mock(side_effect=[partial, restored]); controller.command = Mock(return_value="")
        controller.injector = Mock(return_value={"fresh": "attestation"})
        controller.restore()
        commands = [call.args[0] for call in controller.command.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][-2:], [partial[s]["Id"] for s in e1.DB_SERVICES])
        self.assertEqual(commands[1][-2:], list(e1.DB_SERVICES))
        self.assertIn("--no-build", commands[1]); self.assertEqual(commands[1][commands[1].index("--pull") + 1], "never")
        self.assertEqual([call.args for call in controller.injector.call_args_list], [("check",), ("restore", {"fresh": "attestation"})])

    def test_other_service_restart_or_bad_partial_overlay_never_stopped(self):
        controller = self.controller(); controller.original = self.records(); controller.switched = True
        partial = self.records(experiment=True); partial["ops-agent"]["State"]["StartedAt"] = "changed"
        controller.inspect = Mock(return_value=partial); controller.command = Mock()
        with self.assertRaises(ValueError): controller.restore()
        controller.command.assert_not_called()
        partial["ops-agent"]["State"]["StartedAt"] = "synthetic-start"
        partial[e1.DB_SERVICES[0]]["Config"]["Labels"]["incident-pilot.experiment"] = "foreign"
        with self.assertRaises(ValueError): controller.restore()
        controller.command.assert_not_called()

    def test_wsl_overlay_environment_is_argv_not_shell_or_inherited_secret(self):
        controller = self.controller()
        with patch.object(controller, "target", SimpleNamespace(wsl_distro=None)), patch.dict(os.environ, {"APP_ADMIN_TOKEN": "synthetic"}), patch("subprocess.run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")
            self.assertEqual(controller.command(["exact", "argument with spaces"]), "ok")
            self.assertEqual(run.call_args.args[0], ["exact", "argument with spaces"])
            self.assertNotIn("APP_ADMIN_TOKEN", run.call_args.kwargs["env"])

    def test_success_utf8_stdout_and_utf16_stderr_preserves_binary_hashes(self):
        controller = self.controller()
        stdout = "ok 中文".encode("utf-8")
        stderr = "synthetic WSL diagnostic 中文".encode("utf-16le")
        code = "import sys;sys.stdout.buffer.write(bytes.fromhex(%r));sys.stderr.buffer.write(bytes.fromhex(%r))" % (stdout.hex(), stderr.hex())
        with patch.object(controller, "target", SimpleNamespace(wsl_distro=None)):
            self.assertEqual(controller.command([sys.executable, "-c", code]), "ok 中文")
        records = [json.loads(line) for line in (self.root / "subprocess-exits.jsonl").read_text().splitlines()]
        self.assertEqual(records[-1]["actual_exit_code"], 0)
        self.assertEqual(records[-1]["stdout_sha256"], hashlib.sha256(stdout).hexdigest())
        self.assertEqual(records[-1]["stderr_sha256"], hashlib.sha256(stderr).hexdigest())
        self.assertNotIn("synthetic WSL diagnostic", json.dumps(records))

    def test_failed_utf16_streams_keep_actual_exit_and_hide_diagnostics(self):
        controller = self.controller()
        stdout = "synthetic private stdout 中文".encode("utf-16le")
        stderr = "synthetic private stderr 中文".encode("utf-16le")
        code = "import sys;sys.stdout.buffer.write(bytes.fromhex(%r));sys.stderr.buffer.write(bytes.fromhex(%r));sys.exit(37)" % (stdout.hex(), stderr.hex())
        with patch.object(controller, "target", SimpleNamespace(wsl_distro=None)):
            with self.assertRaisesRegex(RuntimeError, "exit 37") as caught:
                controller.command([sys.executable, "-c", code])
        self.assertNotIn("private", str(caught.exception))
        records = [json.loads(line) for line in (self.root / "subprocess-exits.jsonl").read_text().splitlines()]
        self.assertEqual(records[-1]["actual_exit_code"], 37)
        self.assertEqual(records[-1]["stdout_sha256"], hashlib.sha256(stdout).hexdigest())
        self.assertEqual(records[-1]["stderr_sha256"], hashlib.sha256(stderr).hexdigest())
        self.assertNotIn("synthetic private", json.dumps(records))


class CloseTests(unittest.IsolatedAsyncioTestCase):
    def transport(self):
        runtime = SimpleNamespace(group_sessions={"owned": object()}, _inbound_groups={}, _inbox_consumer_tag="tag",
                                  _connection=SimpleNamespace(is_closed=False))
        session = SimpleNamespace(session_id="owned", leader_mq_client=SimpleNamespace(_state="connected"))
        async def close():
            runtime.group_sessions.clear(); runtime._inbox_consumer_tag = None; runtime._connection = None
            session.leader_mq_client._state = "disconnected"
        return SimpleNamespace(runtime=runtime, session=session, close=AsyncMock(side_effect=close))

    async def test_known_partially_started_group_closes_and_foreign_group_refuses(self):
        transport = self.transport()
        self.assertTrue(all((await e1.close_owned(transport, SimpleNamespace(events=[]))).values()))
        transport = self.transport(); transport.runtime.group_sessions["foreign"] = object()
        with self.assertRaises(RuntimeError): await e1.close_owned(transport, SimpleNamespace(events=[]))
        transport.close.assert_not_called()

    async def test_close_error_and_warning_are_not_success(self):
        transport = self.transport(); transport.close.side_effect = OSError("synthetic")
        with self.assertRaises(OSError): await e1.close_owned(transport, SimpleNamespace(events=[]))
        transport = self.transport()
        with self.assertRaises(RuntimeError): await e1.close_owned(transport, SimpleNamespace(events=["queue_cleanup_failed"]))


class JournalTests(Fixture):
    def journal(self):
        from acps_sdk.aip.resumable import TaskJournal
        journal = TaskJournal(self.root / "synthetic-journal.sqlite")
        original = dict(schema_version="ifc/1.0", incident_id=self.plan["incident_id"], logical_task_id="db-logical",
            kind="act", tool="db.restore_writes", operation_id=self.plan["operation_id"], args={},
            fence={"coordinator_term": 3, "takeover_version": 0}, budget={"deadline_ms": 15000}, approval={"proof": "synthetic"})
        old = journal.record_attempt("db-logical", session_id="owned", task_id="old-aip", partner_aic="primary", content=json.dumps(original))
        journal.transition(old, "processing")
        resume = {**original, "kind": "resume", "args": {"advance_fence": True}, "fence": {"coordinator_term": 3, "takeover_version": 1}}
        resumed = journal.record_attempt("db-logical", session_id="owned", task_id="new-aip", partner_aic="backup", content=json.dumps(resume))
        journal.transition(resumed, "awaiting_completion")
        complete = journal.record_attempt("db-logical", session_id="owned", task_id="new-aip", partner_aic="backup", command="complete")
        journal.transition(complete, "completed")
        return journal, original

    def test_lost_primary_acknowledgement_classifies_without_rewriting_raw_history(self):
        journal, original = self.journal()
        before = journal.list_tasks()
        result = e1.journal_resolution(journal, self.plan, original, "owned")
        self.assertEqual(result["raw_in_flight_count"], 1)
        self.assertEqual(result["expected_unacknowledged_primary_attempts"], 1)
        self.assertFalse(result["raw_journal_modified"])
        self.assertEqual(journal.list_tasks(), before)
        self.assertEqual(journal.list_tasks(in_flight_only=True)[0]["state"], "processing")

    def test_foreign_pending_or_uncompleted_resume_is_not_classified_as_recovered(self):
        journal, original = self.journal()
        journal.record_attempt("foreign", session_id="owned", task_id="other", partner_aic="primary", content="{}")
        with self.assertRaises(ValueError): e1.journal_resolution(journal, self.plan, original, "owned")
        with self.assertRaises(ValueError): e1.journal_resolution(journal, self.plan, original, "other-session")

    def test_completed_resume_with_old_fence_is_rejected(self):
        journal, original = self.journal()
        rows = deepcopy(journal.list_tasks())
        for row in rows:
            if row.get("content"):
                content = json.loads(row["content"])
                if content.get("kind") == "resume":
                    content["fence"] = original["fence"]
                    row["content"] = json.dumps(content)
        fake = SimpleNamespace(list_tasks=Mock(side_effect=lambda **kwargs:
            journal.list_tasks(in_flight_only=True) if kwargs.get("in_flight_only") else rows))
        with self.assertRaises(ValueError): e1.journal_resolution(fake, self.plan, original, "owned")

    def test_received_action_requires_completed_replay_using_activated_fence(self):
        journal, original = self.journal()
        self.plan["crash_point"] = "before_modification"
        with self.assertRaises(ValueError): e1.journal_resolution(journal, self.plan, original, "owned")
        replay = {**original, "fence": {"coordinator_term": 3, "takeover_version": 1}}
        attempt = journal.record_attempt("db-logical", session_id="owned", task_id="replay-aip", partner_aic="backup",
                                         content=json.dumps(replay))
        journal.transition(attempt, "awaiting_completion")
        completed = journal.record_attempt("db-logical", session_id="owned", task_id="replay-aip", partner_aic="backup", command="complete")
        journal.transition(completed, "completed")
        result = e1.journal_resolution(journal, self.plan, original, "owned")
        self.assertEqual(result["completed_backup_replay_task_id"], "replay-aip")
        rows = deepcopy(journal.list_tasks())
        for row in rows:
            if row["task_id"] == "replay-aip" and row.get("content"):
                row["content"] = json.dumps(original)
        fake = SimpleNamespace(list_tasks=Mock(side_effect=lambda **kwargs:
            journal.list_tasks(in_flight_only=True) if kwargs.get("in_flight_only") else rows))
        with self.assertRaises(ValueError): e1.journal_resolution(fake, self.plan, original, "owned")


class FlowTests(Fixture, unittest.IsolatedAsyncioTestCase):
    def dependencies(self, *, main_error=False, close_error=False, restore_error=False):
        order, sent = [], []
        domains = {service: {"aic": {"database-agent": "primary", "database-backup-agent": "backup"}.get(service, role)}
                   for service, role in DOMAIN_SERVICES.items()}
        controller = SimpleNamespace(current=domains, target=SimpleNamespace(order_url="http://127.0.0.1:18088"), ownership_confirmed=True)
        controller.begin = Mock(side_effect=lambda: order.append("begin"))
        controller.apply = Mock(side_effect=lambda: order.append("apply"))
        controller.collect = Mock(return_value={"actual_exit_code": 83})
        def restore():
            order.append("restore")
            if restore_error: raise RuntimeError("synthetic restore")
        controller.restore = Mock(side_effect=restore)
        runtime = SimpleNamespace(group_sessions={"owned": object()}, _inbound_groups={}, _pending_invitations={},
                                  _inbox_consumer_tag="tag", _connection=SimpleNamespace(is_closed=False))
        session = SimpleNamespace(session_id="owned", leader_mq_client=SimpleNamespace(_state="connected"))
        selected = {role: self.plan["identities"][role] for role in self.config["skills"]}
        transport = SimpleNamespace(term=7, runtime=runtime, session=session, selected=selected,
            active_fences={},
            descriptions={"ops": {"resource_scope": dict(compose_project="synthetic-e1", compose_service="app-v2",
                                                        container_name="synthetic-e1-app-v2-1")}},
            journal=SimpleNamespace(list_tasks=Mock(return_value=[])), start=AsyncMock())
        async def close():
            order.append("close")
            if close_error: raise OSError("synthetic close")
            runtime.group_sessions.clear(); runtime._connection = None; runtime._inbox_consumer_tag = None
            session.leader_mq_client._state = "disconnected"
        transport.close = AsyncMock(side_effect=close)
        transport.issue_approval = Mock(return_value={"proof": "synthetic-explicit-approval"})
        def journal_rows(*, in_flight_only=False):
            if in_flight_only: return []
            tool = e1.POINTS[self.point]["tool"]
            db = next(p for p in sent if p["tool"] == tool)
            operation = db.get("operation_id") or db["incident_id"] + ":observe:" + db["logical_task_id"]
            content = {**db, "kind": "resume", "operation_id": operation, "args": {"advance_fence": True},
                       "fence": {"coordinator_term": 7, "takeover_version": 1}}
            rows = [dict(command="start", session_id="owned", task_id="backup-aip", partner_aic="backup",
                         logical_task_id=db["logical_task_id"], content=json.dumps(content), state="awaiting_completion"),
                    dict(command="complete", session_id="owned", task_id="backup-aip", partner_aic="backup",
                         logical_task_id=db["logical_task_id"], content=None, state="completed")]
            if self.point != "after_applied":
                rows.extend([dict(command="start", session_id="owned", task_id="replay-aip", partner_aic="backup",
                                  logical_task_id=db["logical_task_id"],
                                  content=json.dumps(db if db["kind"] == "observe" else {**db, "fence": content["fence"]}),
                                  state="awaiting_completion"),
                             dict(command="complete", session_id="owned", task_id="replay-aip", partner_aic="backup",
                                  logical_task_id=db["logical_task_id"], content=None, state="completed")])
            return rows
        transport.journal.list_tasks.side_effect = journal_rows
        async def call(payload):
            sent.append(deepcopy(payload)); order.append(payload["tool"])
            value = dict(status="ok", incident_id=payload["incident_id"], logical_task_id=payload["logical_task_id"],
                         executor_aic="primary", facts=[])
            if payload["tool"] == "incident.verification":
                value["facts"] = [{"key": "business_recovered", "value": True}, {"key": "order_observation", "value": healthy()}]
            elif payload["tool"] == "db.read_only_status":
                value["facts"] = [{"key": "read_only", "value": True}]
                if self.point == "after_observation":
                    from acps_sdk.aip.resumable import Fence
                    transport.selected["database"] = "backup"
                    transport.active_fences["database"] = Fence(7, 1)
                    value["executor_aic"] = "backup"
            elif payload["tool"] == "db.restore_writes":
                if main_error: raise ValueError("synthetic primary phase")
                transport.selected["database"] = "backup"
                state = "skipped_already_applied" if self.point == "after_applied" else "applied"
                value.update(executor_aic="backup", operation={"state": state, "operation_id": payload["operation_id"]})
            elif payload["tool"] == "application.status":
                value["facts"] = [{"key": "application_pool_revision", "value": 7}]
            return value
        transport.call = AsyncMock(side_effect=call)
        return controller, transport, order, sent

    async def test_complete_stub_case_binds_one_incident_approval_recovery_and_finally(self):
        controller, transport, order, sent = self.dependencies()
        health = AsyncMock(return_value=healthy())
        with patch("subprocess.run", side_effect=AssertionError("real subprocess forbidden")):
            code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                                     transport_factory=lambda *_: transport, final_health=health)
        self.assertEqual(code, 0)
        self.assertEqual([p["tool"] for p in sent], ["incident.verification", "db.read_only_status", "db.restore_writes",
                                                   "application.status", "application.pool_rebuild", "incident.verification"])
        self.assertEqual({p["incident_id"] for p in sent}, {self.plan["incident_id"]})
        self.assertEqual(len({p["logical_task_id"] for p in sent}), len(sent))
        actions = [p for p in sent if p["kind"] == "act"]
        self.assertEqual(actions[0]["operation_id"], self.plan["operation_id"])
        if self.point == "after_observation":
            self.assertEqual(actions[0]["fence"], {"coordinator_term": 7, "takeover_version": 1})
        interrupted = controller.collect.call_args.args[0]
        self.assertEqual(interrupted["tool"], e1.POINTS[self.point]["tool"])
        self.assertEqual(actions[1]["args"], {"expected_revision": 7})
        self.assertTrue(all(p["approval"]["proof"] == "synthetic-explicit-approval" for p in actions))
        self.assertLess(order.index("close"), order.index("restore"))
        self.assertEqual(e1.load(self.args.output / "results.json")["status"], "completed")
        health.assert_awaited_once()

    async def test_primary_error_survives_close_and_restore_errors(self):
        controller, transport, order, _ = self.dependencies(main_error=True, close_error=True, restore_error=True)
        health = AsyncMock(return_value=healthy())
        code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                                 transport_factory=lambda *_: transport, final_health=health)
        self.assertEqual(code, 1)
        report = e1.load(self.args.output / "results.json")
        self.assertEqual(report["error_class"], "ValueError")
        self.assertEqual(report["close_error_class"], "OSError")
        self.assertEqual(report["restore_or_H00_error_class"], "RuntimeError")
        self.assertEqual(order[-2:], ["close", "restore"])
        health.assert_not_awaited()

    async def test_wrong_operation_from_backup_is_not_recovery(self):
        controller, transport, _, _ = self.dependencies()
        original_call = transport.call.side_effect
        async def wrong_operation(payload):
            product = await original_call(payload)
            if payload["tool"] == "db.restore_writes":
                product["operation"]["operation_id"] = "foreign-operation"
            return product
        transport.call.side_effect = wrong_operation
        code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                                 transport_factory=lambda *_: transport, final_health=AsyncMock(return_value=healthy()))
        self.assertEqual(code, 1)
        controller.collect.assert_not_called()
        controller.restore.assert_called_once()

    async def test_unconfirmed_preflight_failure_never_starts_transport_restore_or_H00(self):
        controller, _, _, _ = self.dependencies()
        controller.ownership_confirmed = False
        controller.begin.side_effect = ValueError("unknown resource scope")
        transport = Mock(); health = AsyncMock(return_value=healthy())
        code = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                                 transport_factory=transport, final_health=health)
        self.assertEqual(code, 1)
        controller.restore.assert_not_called(); health.assert_not_awaited(); transport.assert_not_called()
        report = e1.load(self.args.output / "results.json")
        self.assertEqual(report["independent_final_H00_status"], "not_attempted_scope_unconfirmed")


class AfterObservationFlowTests(FlowTests):
    point = "after_observation"


class BeforeModificationFlowTests(FlowTests):
    point = "before_modification"


class HandoverFlowTests(Fixture, unittest.IsolatedAsyncioTestCase):
    dependencies = FlowTests.dependencies

    async def test_all_methods_use_verified_handover_facts_or_observe_revision_again(self):
        for method in e1.METHODS:
            self.plan.update(case="E1-b", method=method, output="eval/results/platform/" + method)
            controller, transport, _, sent = self.dependencies()
            fresh = {} if method == "from_scratch" else {"application_pool_revision": {"value": 12}}
            with patch("eval.platform_handover.bind_handover", return_value=object()) as bind, \
                    patch("eval.platform_handover.verify_handover", return_value={"fresh_facts": fresh,
                        "metrics": {"native_transmitted_ifc_text_bytes": 567, "model_calls": 0}}) as verify:
                result = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                    transport_factory=lambda *_: transport, final_health=AsyncMock(return_value=healthy()))
            with self.subTest(method=method):
                self.assertEqual(result, 0)
                bind.assert_called_once_with(transport, method, e1.local(self.plan["output"]))
                verify.assert_called_once()
                calls = [p["tool"] for p in sent]
                self.assertEqual(calls[1], "application.status")
                self.assertEqual(calls.count("application.status"), 2 if method == "from_scratch" else 1)
                pool = next(p for p in sent if p["tool"] == "application.pool_rebuild")
                self.assertEqual(pool["args"]["expected_revision"], 7 if method == "from_scratch" else 12)
                report = e1.load(e1.local(self.plan["output"]) / "results.json")
                self.assertEqual(report["additional_post_handover_observations"], 1 if method == "from_scratch" else 0)
                self.assertEqual(report["handover"]["native_transmitted_ifc_text_bytes"], 567)

    async def test_bad_handover_acknowledgement_preserves_failure_and_restores(self):
        self.plan.update(case="E1-b", method="resume_package")
        controller, transport, _, sent = self.dependencies()
        with patch("eval.platform_handover.bind_handover", return_value=object()), \
                patch("eval.platform_handover.verify_handover", side_effect=ValueError("wrong transmitted handover")):
            result = await e1.run_case(self.plan, controller_factory=lambda *_: controller,
                transport_factory=lambda *_: transport, final_health=AsyncMock(return_value=healthy()))
        self.assertEqual(result, 1)
        self.assertNotIn("application.pool_rebuild", [p["tool"] for p in sent])
        controller.restore.assert_called_once()
        report = e1.load(self.args.output / "results.json")
        self.assertEqual(report["error_class"], "ValueError")
        self.assertEqual(report["resource_and_worker_restore"], "completed")


class InterruptionEvidenceTests(Fixture):
    def test_each_point_requires_exact_exit_marker_and_only_its_expected_writer(self):
        for point, expected_writer in (("after_observation", "backup"), ("before_modification", "backup"),
                                       ("after_applied", "primary")):
            self.plan["crash_point"] = point
            contract = e1.POINTS[point]
            controller = e1.Controller(self.plan, self.root)
            records = self.records(experiment=True)
            controller.original = self.records()
            controller.experimental = {name: records[name]["Id"] for name in e1.DB_SERVICES}
            controller.experimental_started = {name: records[name]["State"]["StartedAt"] for name in e1.DB_SERVICES}
            records[e1.DB_SERVICES[0]]["State"].update(Running=False, ExitCode=contract["exit_code"])
            controller.inspect = Mock(return_value=records)
            def traces(writer, *, ledger_state=contract["ledger_state"], duplicate=False):
                common = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
                              transport="wutong-amqps", logical_task_id="interrupted-task")
                events = {}
                for role, aic in (("primary", "primary"), ("backup", "backup")):
                    events[aic] = [{**common, "event": "experiment_worker_start", "worker_role": role,
                        "executor_aic": aic, "armed": role == "primary",
                        "bundle_manifest_sha256": e1.digest(self.bundle / "worker-source-manifest.json")}]
                crash = {**common, "event": "experiment_worker_crash", "executor_aic": "primary",
                    "operation_id": None if point == "after_observation" else self.plan["operation_id"],
                    "tool": contract["tool"], "crash_point": point, "exit_code": contract["exit_code"],
                    "ledger_state": ledger_state, "AIP_product_submitted": False}
                events["primary"].append(crash)
                for index in range(2 if duplicate else 1):
                    invocation = {**common, "executor_aic": writer, "operation_id": self.plan["operation_id"],
                                  "invocation_id": "write-" + str(index), "tool": "db.restore_writes",
                                  "server": "postgres", "upstream_tool": "query"}
                    events[writer].extend([{**invocation, "event": "mcp_modify_invocation"},
                                          {**invocation, "event": "mcp_modify_returned", "is_error": False}])
                return ["".join(json.dumps(row) + "\n" for row in events[aic]) for aic in ("primary", "backup")]
            controller.command = Mock(side_effect=traces(expected_writer))
            with self.subTest(point=point, evidence="valid"):
                result = controller.collect({"logical_task_id": "interrupted-task"})
                self.assertEqual(result["actual_exit_code"], contract["exit_code"])
            for bad in (traces("primary" if expected_writer == "backup" else "backup"),
                        traces(expected_writer, duplicate=True), traces(expected_writer, ledger_state="unknown")):
                controller.command = Mock(side_effect=bad)
                with self.subTest(point=point, evidence="invalid"), self.assertRaises(ValueError):
                    controller.collect({"logical_task_id": "interrupted-task"})

    def test_plan_version_and_information_method_are_bound_before_runtime(self):
        legacy = {**self.plan, "schema_version": "platform-e1-plan/1"}
        self.assertEqual(e1.validate_plan(document=legacy), legacy)
        for changes in ({"crash_point": "before_modification"}, {"case": "E1-b", "method": "full_history"}):
            with self.subTest(version="legacy", changes=changes), self.assertRaises(ValueError):
                e1.validate_plan(document={**legacy, **changes})
        for method in e1.METHODS:
            plan = {**self.plan, "case": "E1-b", "method": method,
                    "effects": e1.effects("after_applied", "E1-b", method)}
            self.assertEqual(e1.validate_plan(document=plan), plan)
        with self.assertRaises(ValueError):
            e1.validate_plan(document={**self.plan, "case": "E1-b", "method": "unspecified"})
        for changes in ({"crash_point": "before_modification"}, {"case": "E1-b"}, {"method": "full_history"}):
            with self.subTest(authorization=changes), self.assertRaises(ValueError):
                e1.authorize(self.plan, self.args.plan, self.auth(**changes), True)


if __name__ == "__main__":
    unittest.main()
