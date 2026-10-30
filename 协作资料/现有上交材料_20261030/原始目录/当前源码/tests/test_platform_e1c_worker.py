"""E1-c same-process revival: real Bridge/ledger, fake MCP and injected suspension."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
sys.path.insert(0, str(ROOT / "tests"))

import test_platform_e1_worker as fixtures
from acps_mcp_bridge import ApprovalAuthority, Policy
from acps_mcp_bridge import experiment as hooks
from acps_mcp_bridge.experiment import DurableTrace, ExperimentBridge, ExperimentSpec, TracedSystemEmitter, operation_counts
from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType
from acps_sdk.aip.resumable import Fence, OperationLedger
from eval import platform_database_worker as worker
from eval.prepare_platform_e1_worker import documents, prepare
from incident.local_worker import CountedMcpClient

CALLER, PRIMARY, BACKUP = fixtures.CALLER, fixtures.PRIMARY, fixtures.BACKUP
EXPERIMENT, INCIDENT = "e1c-offline-fixture", "e1c-fixture-incident"
IDENTITY = {"pid": 42, "linux_start_ticks": 10023}


class SuspendedWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger_path = self.root / "shared.sqlite"
        self.authority = ApprovalAuthority("offline-e1c-fixture-" * 4)
        self.raw = {role: fixtures.FakeMcp() for role in ("primary", "backup")}
        self.events, self.exits = {}, []

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def bridge(self, *, role="primary", callback=None, identity_callback=None, armed=True):
        aic = PRIMARY if role == "primary" else BACKUP
        document = documents(experiment_id=EXPERIMENT, incident_id=INCIDENT,
            primary_aic=PRIMARY, backup_aic=BACKUP, crash_point="before_modification",
            arm_primary=armed, suspend_primary=True)[role + ".json"]
        spec = ExperimentSpec.from_document(document, experiment_id=EXPERIMENT, executor_aic=aic)
        policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER],
                             approval_verifier=self.authority.verify)
        current = ContextVar("test_e1c_" + role, default=None)
        trace = DurableTrace(self.root / (role + ".jsonl"), spec, aic)
        self.events[role] = fixtures.Events()
        counted = CountedMcpClient(self.raw[role], "postgres", policy,
            SimpleNamespace(system=TracedSystemEmitter(self.events[role], trace)), current,
            transport="wutong-amqps")
        return await ExperimentBridge(policy, {"postgres": counted},
            OperationLedger(self.ledger_path, "orders"), aic, experiment=spec,
            current_payload=current, trace=trace, exit_callback=self.exits.append,
            suspend_callback=callback or (lambda identity: None),
            identity_callback=identity_callback or (lambda: dict(IDENTITY))).initialize()

    def payload(self, *, operation="op-restore", fence=Fence(1, 0)):
        value = dict(schema_version="ifc/1.0", incident_id=INCIDENT,
            logical_task_id="logical-" + operation, kind="act", tool="db.restore_writes",
            args={}, budget={"deadline_ms": 15000}, operation_id=operation, fence=fence.to_dict())
        value["approval"] = self.authority.issue(value, CALLER, approved_by="offline-fixture")
        return value

    def recorded(self, bridge):
        if not bridge.trace.path.exists():
            return []
        return [json.loads(line) for line in bridge.trace.path.read_text(encoding="utf-8").splitlines()]

    async def test_original_authorized_request_revives_and_is_rejected_after_backup_apply(self):
        payload = self.payload()
        original = deepcopy(payload)
        expected_sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        backup = await self.bridge(role="backup")
        suspended = []
        partner = fixtures.Partner(PRIMARY)

        async def suspension(identity):
            suspended.append(identity)
            self.assertEqual(identity, IDENTITY)
            # Open a separate ledger connection: received is durable before callback.
            self.assertEqual(OperationLedger(self.ledger_path, "orders").get("op-restore")["state"], "received")
            pause = self.recorded(primary)[-1]
            self.assertEqual(pause["event"], "experiment_worker_suspended")
            self.assertEqual(pause["ledger_state"], "received")
            self.assertEqual(pause["request_sha256"], expected_sha)
            self.assertEqual(self.raw["primary"].calls, [])
            self.assertNotIn("submit_for_completion", partner.events)
            resume = {**payload, "kind": "resume", "args": {"advance_fence": True},
                      "fence": Fence(1, 1).to_dict()}
            self.assertEqual((await backup.execute(resume, CALLER))["operation"]["state"], "received")
            action = self.payload(fence=Fence(1, 1))
            self.assertEqual((await backup.execute(action, CALLER))["operation"]["state"], "applied")
            self.assertEqual(self.raw["backup"].modifications, 1)

        primary = await self.bridge(callback=suspension)
        handler = primary.bind_partner(partner)
        command = TaskCommand(id="e1c-original-command", sentAt="2026-10-19T00:00:00Z",
            senderId=CALLER, senderRole="leader", groupId=partner.group_id,
            sessionId="formal-session-not-incident", taskId="original-aip-task", mentions=[PRIMARY],
            command=TaskCommandType.Start, dataItems=[StructuredDataItem(data=payload)])
        await handler(command, True)

        self.assertEqual(payload, original)
        self.assertEqual(suspended, [IDENTITY])
        self.assertEqual(self.raw["primary"].calls, [])
        self.assertEqual(self.raw["primary"].modifications, 0)
        self.assertEqual(self.raw["backup"].modifications, 1)
        self.assertEqual(primary.ledger.get("op-restore")["state"], "applied")
        self.assertEqual(primary.current_payload.get(), None)
        self.assertEqual(self.exits, [])
        events = [row for row in self.recorded(primary) if row["event"].startswith("experiment_")]
        self.assertEqual([row["event"] for row in events], ["experiment_worker_suspended",
            "experiment_worker_revived", "experiment_stale_request_result"])
        self.assertEqual([row.get("ledger_state") for row in events[:2]], ["received", "applied"])
        for row in events:
            self.assertEqual(row["process_identity"], IDENTITY)
            self.assertEqual(row["request_sha256"], expected_sha)
            self.assertEqual(row["fence"], Fence(1, 0).to_dict())
            self.assertEqual(row["incident_id"], INCIDENT)
            self.assertEqual(row["logical_task_id"], payload["logical_task_id"])
            self.assertEqual(row["operation_id"], "op-restore")
            self.assertEqual(row["tool"], "db.restore_writes")
            self.assertEqual(row["crash_point"], "before_modification")
            self.assertFalse(row["AIP_product_submitted"])
        self.assertEqual(events[-1]["status"], "rejected")
        self.assertEqual(events[-1]["operation_state"], "rejected_stale_fence")
        self.assertEqual(events[-1]["result_operation_id"], "op-restore")
        counts = operation_counts([backup.trace.path], experiment_id=EXPERIMENT, incident_id=INCIDENT)
        self.assertEqual(counts["operations"], [dict(executor_aic=BACKUP, operation_id="op-restore",
            invocations=1, returned=1, returned_errors=0, without_return=0)])

    async def test_invalid_caller_approval_and_initial_stale_fence_never_suspend(self):
        callbacks = []
        primary = await self.bridge(callback=callbacks.append)
        for failure in ("caller", "approval", "stale"):
            with self.subTest(failure=failure):
                payload = self.payload(operation="op-" + failure)
                if failure == "approval":
                    payload.pop("approval")
                if failure == "stale":
                    primary.ledger.advance_fence(Fence(2, 0))
                result = await primary.execute(payload, "wrong-caller" if failure == "caller" else CALLER)
                self.assertEqual(result["status"], "rejected")
        self.assertEqual(callbacks, [])
        self.assertEqual(primary.ledger.list_operations(), [])
        self.assertEqual(self.raw["primary"].calls, [])
        self.assertEqual(self.recorded(primary), [])

    async def test_revived_identity_or_request_change_stops_before_original_execution(self):
        for failure in ("process", "request"):
            with self.subTest(failure=failure):
                current_identity = dict(IDENTITY)
                payload = self.payload(operation="changed-" + failure)

                def suspension(identity):
                    if failure == "process":
                        current_identity["linux_start_ticks"] += 1
                    else:
                        payload["budget"]["deadline_ms"] += 1

                primary = await self.bridge(callback=suspension, identity_callback=lambda: current_identity)
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    await primary.execute(payload, CALLER)
                self.assertEqual(primary.ledger.get(payload["operation_id"])["state"], "received")
                self.assertEqual(self.raw["primary"].calls, [])
                self.assertEqual(primary.current_payload.get(), None)
        self.assertEqual(self.exits, [])

    async def test_unarmed_suspend_plan_and_backup_keep_normal_execution(self):
        callbacks = []
        primary = await self.bridge(armed=False, callback=callbacks.append)
        backup = await self.bridge(role="backup", callback=callbacks.append)
        self.assertEqual((await primary.execute(self.payload(operation="unarmed"), CALLER))["operation"]["state"], "applied")
        self.assertEqual((await backup.execute(self.payload(operation="backup"), CALLER))["operation"]["state"], "applied")
        self.assertEqual(callbacks, [])
        self.assertEqual(self.exits, [])


class SuspendPreparationTests(unittest.TestCase):
    def options(self):
        return dict(experiment_id=EXPERIMENT, incident_id=INCIDENT, primary_aic=PRIMARY,
                    backup_aic=BACKUP, crash_point="before_modification")

    def test_old_schema_default_exit_and_new_schema_exact_modes(self):
        old = documents(**self.options())
        self.assertEqual(old["primary.json"]["schema_version"], "e1-worker/1")
        self.assertNotIn("interruption_mode", old["primary.json"])
        self.assertEqual(ExperimentSpec.from_document(old["primary.json"], experiment_id=EXPERIMENT,
                                                     executor_aic=PRIMARY).interruption_mode, "exit")
        new = documents(**self.options(), arm_primary=True, suspend_primary=True)
        self.assertEqual(new["primary.json"]["schema_version"], "e1-worker/2")
        self.assertEqual(new["primary.json"]["interruption_mode"], "suspend")
        self.assertEqual(new["backup.json"]["interruption_mode"], "exit")
        self.assertFalse(new["backup.json"]["armed"])
        for changes in ({"interruption_mode": "other"}, {"crash_point": "after_applied"},
                        {"crash_tool": "db.read_only_status"}, {"schema_version": "e1-worker/1"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ExperimentSpec.from_document({**new["primary.json"], **changes},
                    experiment_id=EXPERIMENT, executor_aic=PRIMARY)
        with self.assertRaises(ValueError):
            ExperimentSpec.from_document({**new["backup.json"], "interruption_mode": "suspend"},
                experiment_id=EXPERIMENT, executor_aic=BACKUP)
        with self.assertRaises(ValueError):
            ExperimentSpec.from_document({key: value for key, value in new["primary.json"].items()
                if key != "interruption_mode"}, experiment_id=EXPERIMENT, executor_aic=PRIMARY)

    def test_suspend_bundle_adds_init_only_to_primary_and_pins_exact_new_sources(self):
        import yaml
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            receipt = prepare(output, **self.options(), arm_primary=True, suspend_primary=True)
            self.assertTrue(receipt["primary_armed"])
            self.assertFalse(receipt["backup_armed"])
            manifest = worker.verify_bundle(output / "worker-source-manifest.json", receipt["manifest_sha256"], EXPERIMENT)
            self.assertEqual(set(manifest["source_sha256"]), worker.BUNDLE_SOURCES)
            overlay = yaml.safe_load((output / "e1-worker-overlay.yml").read_text())
            primary, backup = overlay["services"]["database-agent"], overlay["services"]["database-backup-agent"]
            self.assertIs(primary["init"], True)
            self.assertNotIn("init", backup)
            self.assertEqual(primary["restart"], "no")
            self.assertNotIn("restart", backup)
            self.assertEqual(len(primary["volumes"]), 1)
            self.assertTrue(primary["volumes"][0]["read_only"])
            self.assertEqual(primary["volumes"][0]["target"], "/experiment")
            document = json.loads((output / "primary.json").read_text())
            self.assertEqual(document["interruption_mode"], "suspend")
            self.assertEqual(json.loads((output / "backup.json").read_text())["interruption_mode"], "exit")

    def test_other_suspend_points_rejected_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            for point in ("after_observation", "after_applied"):
                output = Path(temporary) / point
                with self.subTest(point=point), self.assertRaises(ValueError):
                    prepare(output, **{**self.options(), "crash_point": point}, suspend_primary=True)
                self.assertFalse(output.exists())

    def test_linux_process_identity_reads_proc_field22_with_parenthesized_name(self):
        suffix = ["S", *[str(number) for number in range(4, 22)], "87654", "23"]
        with patch.object(hooks.sys, "platform", "linux"), patch.object(hooks.os, "getpid", return_value=42), \
             patch.object(hooks.Path, "read_text", return_value="42 (fixture (worker) name) " + " ".join(suffix)):
            self.assertEqual(hooks.process_identity(), {"pid": 42, "linux_start_ticks": 87654})

    def test_real_suspend_requires_exact_noninit_linux_process_and_only_self_sigstop(self):
        with patch.object(hooks.sys, "platform", "linux"), patch.object(hooks.os, "getpid", return_value=42), \
             patch.object(hooks, "process_identity", return_value=dict(IDENTITY)), \
             patch.object(hooks.os, "kill") as kill, patch.object(hooks.signal, "SIGSTOP", 19, create=True):
            hooks.suspend_current_process(dict(IDENTITY))
            kill.assert_called_once_with(42, 19)
            kill.reset_mock()
            for identity in ({"pid": 1, "linux_start_ticks": 10023}, {"pid": 42, "linux_start_ticks": 0},
                             {"pid": 43, "linux_start_ticks": 10023}, {"pid": True, "linux_start_ticks": 10023},
                             {"pid": 42, "linux_start_ticks": None}):
                with self.subTest(identity=identity), self.assertRaises(ValueError):
                    hooks.suspend_current_process(identity)
            kill.assert_not_called()
        with patch.object(hooks.sys, "platform", "win32"), patch.object(hooks.os, "kill") as kill:
            with self.assertRaises(ValueError):
                hooks.suspend_current_process(dict(IDENTITY))
            kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
