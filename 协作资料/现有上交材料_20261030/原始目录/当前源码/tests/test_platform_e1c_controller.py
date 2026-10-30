"""Same-process E1-c contracts with synthetic command outputs and local SQLite."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval import platform_resume_experiment as parent
from eval import platform_e1c_controller as revival


class RevivalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        root_patch = patch.object(parent, "ROOT", self.root); root_patch.start(); self.addCleanup(root_patch.stop)
        self.bundle = self.root / "bundle"; self.bundle.mkdir()
        (self.bundle / "worker-source-manifest.json").write_text("{}", encoding="utf-8")
        self.command = ["python", "/experiment/source/eval/platform_database_worker.py", "--serve"]
        import yaml
        (self.bundle / "e1-worker-overlay.yml").write_text(yaml.safe_dump({"services": {
            name: {"command": self.command} for name in parent.DB_SERVICES}}), encoding="utf-8")
        for name in ("target.env", "compose.yml", "route.conf"):
            (self.root / name).write_text("synthetic", encoding="utf-8")
        parent.save(self.root / "target.json", dict(schema_version="incident-evaluator-target/1.0", backend="docker",
            project="synthetic-e1c", wsl_distro=None, compose_files=[str(self.root / "compose.yml")],
            env_file=str(self.root / "target.env"), route_file=str(self.root / "route.conf"),
            ports={"app_v1": 18081, "app_v2": 18082, "order": 18088}))
        self.plan = dict(case="E1-c", crash_point="before_modification", project="synthetic-e1c", experiment_id="e1c-synthetic",
            incident_id="one-incident", operation_id="one-incident:db-restore-writes", target_config="target.json",
            domain_profile="profile", bundle="bundle", image_id="sha256:" + "a" * 64,
            identities={"database": "primary", "database-backup": "backup"})
        self.controller = revival.RevivalController(self.plan, self.root)
        self.records = {}
        for name, role in zip(parent.DB_SERVICES, ("database", "database-backup")):
            self.records[name] = {"Id": "owned-" + name, "Image": self.plan["image_id"],
                "State": {"Running": True, "StartedAt": "original-start", "ExitCode": 0},
                "Config": {"Cmd": self.command, "Labels": {"incident-pilot.experiment": self.plan["experiment_id"],
                    "incident-pilot.e1-role": "primary" if role == "database" else "backup"}},
                "HostConfig": {"ReadonlyRootfs": True, "Init": role == "database", "RestartPolicy": {"Name": "no"}},
                "Mounts": [{"Destination": "/domain", "Source": str(self.root / "profile/domains" / role), "RW": False},
                    {"Destination": "/experiment", "Source": str(self.bundle), "RW": False},
                    {"Destination": "/state", "Type": "volume", "Name": "synthetic-e1c_state", "RW": True}]}
        self.records["nginx"] = {"Id": "unowned-nginx", "Image": "business-image", "State": {"StartedAt": "unchanged"}}
        c = self.controller
        c.original = deepcopy(self.records)
        c.experimental = {s: self.records[s]["Id"] for s in parent.DB_SERVICES}
        c.experimental_started = {s: self.records[s]["State"]["StartedAt"] for s in parent.DB_SERVICES}
        c.switched = c.ownership_confirmed = True
        c.inspect = Mock(side_effect=lambda: deepcopy(self.records))
        self.identity = {"pid": 17, "linux_start_ticks": 456}
        self.payload = dict(kind="act", tool="db.restore_writes", incident_id=self.plan["incident_id"],
            operation_id=self.plan["operation_id"], logical_task_id="original-task", args={}, fence={"coordinator_term": 4, "takeover_version": 0})
        self.payload["approval"] = {"expires_at": 4000000000}
        self.traces = {"primary": [self.start("primary", self.identity)],
                       "backup": [self.start("backup", {"pid": 21, "linux_start_ticks": 500})]}
        self.traces["primary"].append(self.marker("experiment_worker_suspended", ledger_state="received"))
        modify = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"], executor_aic="backup",
            transport="wutong-amqps", operation_id=self.plan["operation_id"], logical_task_id="original-task",
            tool="db.restore_writes", invocation_id="one", server="db", upstream_tool="query")
        self.traces["backup"] += [{**modify, "event": "mcp_modify_invocation"},
                                  {**modify, "event": "mcp_modify_returned", "is_error": False}]
        self.db = self.root / "ledger.sqlite"
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.executescript("CREATE TABLE operations(resource_domain TEXT,operation_id TEXT,state TEXT,coordinator_term INTEGER,takeover_version INTEGER);"
                "CREATE TABLE operation_fences(resource_domain TEXT,coordinator_term INTEGER,takeover_version INTEGER);")
            db.execute("INSERT INTO operations VALUES(?,?,?,?,?)", ("db", self.plan["operation_id"], "applied", 4, 1))
            db.execute("INSERT INTO operation_fences VALUES(?,?,?)", ("db", 4, 1))
        self.resumed = False
        self.argvs = []
        self.controller.command = Mock(side_effect=self.synthetic_command)

    def start(self, role, identity):
        return dict(event="experiment_worker_start", experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
            executor_aic="primary" if role == "primary" else "backup", worker_role=role, armed=role == "primary",
            process_identity=identity, transport="wutong-amqps", bundle_manifest_sha256=parent.digest(self.bundle / "worker-source-manifest.json"))

    def marker(self, event, **extra):
        return dict(event=event, experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"], executor_aic="primary",
            transport="wutong-amqps", operation_id=self.plan["operation_id"], logical_task_id=self.payload["logical_task_id"],
            tool="db.restore_writes", process_identity=self.identity, AIP_product_submitted=False,
            crash_point="before_modification",
            request_sha256=revival.request_sha256(self.payload), fence=self.payload["fence"], **extra)

    def synthetic_command(self, argv):
        self.argvs.append(argv)
        code = argv[argv.index("-c") + 1]
        if code == revival.PROCESS_CODE:
            expected = json.loads(argv[-2])
            if expected["process_identity"] != self.identity:
                raise ValueError("changed synthetic /proc identity")
            resume = argv[-1] == "continue"
            state = "S" if self.resumed else "T"
            if resume:
                if state != "T": raise ValueError("already running")
                self.resumed = True
                self.traces["primary"] += [self.marker("experiment_worker_revived", ledger_state="applied"),
                    self.marker("experiment_stale_request_result", status="rejected", operation_state="rejected_stale_fence",
                        result_operation_id=self.plan["operation_id"])]
            return json.dumps(dict(process_identity=self.identity, state=state, cmdline=self.command, stat="synthetic stat", signal_sent=resume))
        if "def ledger_snapshot" in code:
            return json.dumps(revival.ledger_snapshot(self.db, self.plan["operation_id"], "db"))
        return json.dumps({role: "".join(json.dumps(e) + "\n" for e in events) for role, events in self.traces.items()})

    def assert_no_signal(self):
        self.assertFalse(any(argv[-1] == "continue" for argv in self.argvs))

    def test_same_process_revival_requires_backup_effect_and_keeps_ledger_bytes(self):
        before = self.db.read_bytes()
        result = self.controller.collect(self.payload)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["same_process"])
        self.assertEqual(result["signals_sent"], 1)
        self.assertEqual((result["replay_attempts"], result["rejected_stale_fence"]), (1, 1))
        self.assertEqual(result["counts"]["operations"][0]["executor_aic"], "backup")
        self.assertEqual(self.db.read_bytes(), before)
        self.assertTrue(all("restart" not in argv and "kill" not in argv for argv in self.argvs))
        self.assertEqual(json.loads((self.root / "e1c-revival-metrics.json").read_text())["status"], "completed")

    def test_other_case_refuses_before_target_initialization(self):
        for changes in ({"case": "E1-a"}, {"crash_point": "after_applied"}):
            with self.assertRaises(ValueError): revival.RevivalController(self.plan | changes, self.root)

    def test_backup_may_be_namespace_pid1_but_is_never_signaled(self):
        self.traces["backup"][0]["process_identity"]["pid"] = 1
        self.assertEqual(self.controller.collect(self.payload)["status"], "completed")
        for argv in self.argvs:
            if argv[argv.index("-c") + 1] == revival.PROCESS_CODE:
                self.assertEqual(json.loads(argv[-2])["process_identity"]["pid"], 17)

    def test_container_restart_replacement_init_mount_and_other_service_changes_refuse_signal(self):
        original = deepcopy(self.records)
        mutations = [lambda r: r[parent.DB_SERVICES[0]].update(Id="foreign"),
            lambda r: r[parent.DB_SERVICES[0]]["State"].update(StartedAt="restarted"),
            lambda r: r[parent.DB_SERVICES[0]]["HostConfig"].update(Init=False),
            lambda r: r[parent.DB_SERVICES[0]]["Mounts"][0].update(RW=True),
            lambda r: r[parent.DB_SERVICES[1]]["Mounts"][2].update(Name="foreign_state"),
            lambda r: r["nginx"]["State"].update(StartedAt="restarted")]
        for mutate in mutations:
            self.records = deepcopy(original); mutate(self.records)
            with self.assertRaises(ValueError): self.controller.collect(self.payload)
            self.assert_no_signal()

    def test_wrong_request_marker_start_identity_or_pid1_refuses_signal(self):
        original = deepcopy(self.traces)
        mutations = [lambda t: t["primary"][1].update(request_sha256="0" * 64),
            lambda t: t["primary"][1].update(fence={"coordinator_term": 4, "takeover_version": 1}),
            lambda t: t["primary"][1].update(ledger_state="executing"),
            lambda t: t["primary"][0].update(process_identity={"pid": 1, "linux_start_ticks": 456}),
            lambda t: t["primary"][1].update(process_identity={"pid": 17, "linux_start_ticks": 999}),
            lambda t: t["backup"][0].update(armed=True)]
        for mutate in mutations:
            self.traces = deepcopy(original); mutate(self.traces)
            with self.assertRaises(ValueError): self.controller.collect(self.payload)
            self.assert_no_signal()

    def test_unadvanced_fence_or_unapplied_ledger_refuses_signal(self):
        for state, version in (("received", 1), ("applied", 0)):
            with contextlib.closing(sqlite3.connect(self.db)) as db, db:
                db.execute("UPDATE operations SET state=?,takeover_version=?", (state, version))
                db.execute("UPDATE operation_fences SET takeover_version=?", (version,))
            with self.assertRaises(ValueError): self.controller.collect(self.payload)
            self.assert_no_signal()

    def test_extra_primary_mcp_invocation_is_not_one_backup_effect(self):
        self.traces["primary"].append(self.traces["backup"][1] | {"executor_aic": "primary", "invocation_id": "illegal"})
        with self.assertRaises(ValueError): self.controller.collect(self.payload)
        self.assert_no_signal()

    def test_expired_original_approval_is_not_renewed_or_signaled(self):
        self.payload["approval"]["expires_at"] = 1
        self.traces["primary"][1] = self.marker("experiment_worker_suspended", ledger_state="received")
        with self.assertRaisesRegex(ValueError, "approval"): self.controller.collect(self.payload)
        self.assertEqual(self.payload["approval"]["expires_at"], 1)
        self.assert_no_signal()

    def test_missing_or_wrong_stale_result_preserves_failure_after_one_signal(self):
        original_command = self.synthetic_command
        for mode in ("missing", "wrong_result", "changed_process"):
            self.set_trace_after_reset()
            def command(argv):
                text = original_command(argv)
                if argv[-1] == "continue":
                    if mode == "missing": self.traces["primary"].pop()
                    elif mode == "wrong_result": self.traces["primary"][-1]["operation_state"] = "applied"
                    else: self.traces["primary"][-1]["process_identity"] = {"pid": 18, "linux_start_ticks": 999}
                return text
            self.controller.command.side_effect = command
            with self.assertRaises(ValueError): self.controller.collect(self.payload)
            self.assertEqual(sum(a[-1] == "continue" for a in self.argvs), 1)

    def set_trace_after_reset(self):
        self.resumed = False; self.argvs.clear()
        self.traces["primary"] = [self.start("primary", self.identity), self.marker("experiment_worker_suspended", ledger_state="received")]

    def test_restore_resumes_owned_stopped_primary_then_calls_parent(self):
        order = []
        actual = self.controller.command.side_effect
        def command(argv):
            result = actual(argv)
            if argv[-1] == "continue": order.append("continue")
            return result
        self.controller.command.side_effect = command
        with patch.object(parent.Controller, "restore", side_effect=lambda: order.append("parent")):
            self.controller.restore()
        self.assertEqual(order, ["continue", "parent"])

    def test_restore_never_signals_foreign_identity_and_keeps_both_errors(self):
        self.records[parent.DB_SERVICES[0]]["Id"] = "foreign"
        with patch.object(parent.Controller, "restore", side_effect=RuntimeError("parent failure")) as restore:
            with self.assertRaises(ExceptionGroup) as error: self.controller.restore()
        restore.assert_called_once(); self.assert_no_signal()
        self.assertEqual([type(e) for e in error.exception.exceptions], [ValueError, RuntimeError])
        proof = json.loads((self.root / "e1c-restore.json").read_text())
        self.assertEqual((proof["resume_before_restore"], proof["parent_restore"]), ("failed", "failed"))

    def test_restore_already_running_does_not_resignal(self):
        self.resumed = True
        with patch.object(parent.Controller, "restore") as restore: self.controller.restore()
        restore.assert_called_once(); self.assert_no_signal()


class ProcessProbeTests(unittest.TestCase):
    def run_probe(self, *, ticks=456, command=None, state="T", pid=17, expiry=None):
        expected = {"process_identity": {"pid": pid, "linux_start_ticks": 456}, "command": ["python", "/worker.py", "--serve"]}
        if expiry is not None: expected["approval_expires_at"] = expiry
        actual_command = command or ["python", "/worker.py", "--serve"]
        fields = [state] + ["0"] * 18 + [str(ticks)]
        files = {"stat": str(pid) + " (worker name) " + " ".join(fields), "cmdline": "\0".join(actual_command).encode() + b"\0"}
        class FakePath:
            def __init__(self, value): self.path = PurePosixPath(value)
            def __truediv__(self, value): return FakePath(self.path / value)
            @property
            def name(self): return self.path.name
            def read_text(self): return files[self.name]
            def read_bytes(self): return files[self.name]
        fake_os = SimpleNamespace(pidfd_open=Mock(return_value=123), close=Mock())
        fake_signal = SimpleNamespace(SIGCONT=18, pidfd_send_signal=Mock())
        modules = {"os": fake_os, "signal": fake_signal, "pathlib": SimpleNamespace(Path=FakePath)}
        with patch.dict(sys.modules, modules), patch.object(sys, "argv", ["probe", json.dumps(expected), "continue"]), contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(revival.PROCESS_CODE, {})
            finally:
                self.last_os, self.last_signal = fake_os, fake_signal
        return fake_os, fake_signal

    def test_pidfd_bound_signal_and_finally_close(self):
        fake_os, fake_signal = self.run_probe()
        fake_os.pidfd_open.assert_called_once_with(17)
        fake_signal.pidfd_send_signal.assert_called_once_with(123, 18)
        fake_os.close.assert_called_once_with(123)

    def test_reused_pid_changed_command_running_state_or_pid1_never_signals(self):
        for change in ({"ticks": 999}, {"command": ["python", "/other.py", "--serve"]}, {"state": "S"}, {"pid": 1}):
            with self.assertRaises(ValueError): self.run_probe(**change)
            self.last_signal.pidfd_send_signal.assert_not_called()
            if change.get("pid") != 1: self.last_os.close.assert_called_once_with(123)

    def test_expiry_is_rechecked_inside_pidfd_guard_before_signal(self):
        with self.assertRaises(ValueError): self.run_probe(expiry=1)
        self.last_signal.pidfd_send_signal.assert_not_called()
        self.last_os.close.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
