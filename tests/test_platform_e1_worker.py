"""E1 worker hooks with fake MCP/AIP and temporary operation ledgers only."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Policy
from acps_mcp_bridge.experiment import DurableTrace, ExperimentBridge, ExperimentExit, ExperimentSpec, TracedSystemEmitter, operation_counts
from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType
from acps_sdk.aip.resumable import Fence, OperationLedger
from eval import platform_database_worker as worker
from eval.prepare_platform_e1_worker import documents, prepare
from incident.local_worker import CountedMcpClient

CALLER, PRIMARY, BACKUP = "fixture-coordinator", "fixture-primary", "fixture-backup"
EXPERIMENT, INCIDENT = "e1-offline-fixture", "e1-fixture-incident"


class Events:
    def __init__(self):
        self.values = []

    async def emit(self, value):
        self.values.append(value)


class FakeMcp:
    def __init__(self):
        self.read_only, self.modifications, self.raise_write = True, 0, False
        self.calls = []

    async def tools(self):
        return [{"name": name} for name in ("execute_sql", "analyze_db_health")]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        if "restore_writes" in arguments.get("sql", ""):
            if self.raise_write:
                raise RuntimeError("fixture upstream failure")
            self.modifications += 1
            self.read_only = False
        return {"structuredContent": [{"read_only": self.read_only}], "isError": False}


class Partner:
    _identity_binding_enabled = True
    group_id = "fixture-platform-group"

    def __init__(self, aic):
        self.partner_aic, self.events = aic, []

    def set_command_handler(self, handler):
        self.handler = handler

    def __getattr__(self, name):
        async def action(*args, **kwargs):
            self.events.append(name)
        return action


class WorkerHooksTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger_path = self.root / "shared.sqlite"
        self.authority = ApprovalAuthority("offline-fixture-" * 4)
        self.raw, self.exits = FakeMcp(), []
        self.bridges = []

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def bridge(self, point="after_applied", *, role="primary", armed=True):
        aic = PRIMARY if role == "primary" else BACKUP
        document = documents(experiment_id=EXPERIMENT, incident_id=INCIDENT, primary_aic=PRIMARY,
            backup_aic=BACKUP, crash_point=point, arm_primary=armed)[role + ".json"]
        spec = ExperimentSpec.from_document(document, experiment_id=EXPERIMENT, executor_aic=aic)
        policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER],
                             approval_verifier=self.authority.verify)
        current = ContextVar("test_e1_payload", default=None)
        trace = DurableTrace(self.root / (role + str(len(self.bridges)) + ".jsonl"), spec, aic)
        events = Events()
        counted = CountedMcpClient(self.raw, "postgres", policy,
            SimpleNamespace(system=TracedSystemEmitter(events, trace)), current, transport="wutong-amqps")
        bridge = await ExperimentBridge(policy, {"postgres": counted}, OperationLedger(self.ledger_path, "orders"), aic,
            experiment=spec, current_payload=current, trace=trace, exit_callback=self.exits.append).initialize()
        self.bridges.append(bridge)
        return bridge

    def payload(self, *, observe=False, operation="op-restore", fence=Fence(1, 0), incident=INCIDENT):
        value = dict(schema_version="ifc/1.0", incident_id=incident, logical_task_id="logical-" + operation,
            kind="observe" if observe else "act", tool="db.read_only_status" if observe else "db.restore_writes",
            args={}, budget={"deadline_ms": 15000})
        if not observe:
            value.update(operation_id=operation, fence=fence.to_dict())
            value["approval"] = self.authority.issue(value, CALLER, approved_by="offline-fixture")
        return value

    async def command(self, bridge, payload):
        partner = Partner(bridge.executor_aic)
        handler = bridge.bind_partner(partner)
        command = TaskCommand(id="fixture-command", sentAt="2026-10-18T00:00:00Z",
            senderId=CALLER, senderRole="leader", groupId=partner.group_id,
            sessionId="formal-session-is-not-the-incident", taskId="aip-task", mentions=[bridge.executor_aic],
            command=TaskCommandType.Start, dataItems=[StructuredDataItem(data=payload)])
        return partner, handler, command

    def recorded(self, bridge):
        return [json.loads(line) for line in bridge.trace.path.read_text(encoding="utf-8").splitlines()]

    async def test_after_observation_is_after_read_and_before_AIP_product(self):
        bridge = await self.bridge("after_observation")
        partner, handler, command = await self.command(bridge, self.payload(observe=True))
        with self.assertRaises(ExperimentExit) as caught:
            await handler(command, True)
        self.assertEqual(caught.exception.code, 81)
        self.assertEqual(len(self.raw.calls), 1)
        self.assertEqual(self.raw.modifications, 0)
        self.assertEqual(bridge.ledger.list_operations(), [])
        self.assertNotIn("submit_for_completion", partner.events)
        self.assertEqual(self.recorded(bridge)[-1]["ledger_state"], None)
        self.assertEqual(bridge.current_payload.get(), None)

    async def test_before_modification_has_approval_and_durable_received_no_upstream_write(self):
        bridge = await self.bridge("before_modification")
        partner, handler, command = await self.command(bridge, self.payload())
        with self.assertRaises(ExperimentExit) as caught:
            await handler(command, True)
        self.assertEqual(caught.exception.code, 82)
        fresh = OperationLedger(self.ledger_path, "orders").get("op-restore")
        self.assertEqual(fresh["state"], "received")
        self.assertEqual(fresh["parameters"]["tool"], "db.restore_writes")
        self.assertEqual(self.raw.calls, [])
        self.assertNotIn("submit_for_completion", partner.events)
        self.assertEqual(self.recorded(bridge)[-1]["ledger_state"], "received")

    async def test_after_applied_is_durable_before_submit_backup_skips_and_old_fence_rejected(self):
        primary = await self.bridge()
        payload = self.payload()
        partner, handler, command = await self.command(primary, payload)
        with self.assertRaises(ExperimentExit) as caught:
            await handler(command, True)
        self.assertEqual(caught.exception.code, 83)
        self.assertEqual(OperationLedger(self.ledger_path, "orders").get("op-restore")["state"], "applied")
        self.assertEqual(self.raw.modifications, 1)
        self.assertNotIn("submit_for_completion", partner.events)
        backup = await self.bridge(role="backup")
        resume = {**payload, "kind": "resume", "args": {"advance_fence": True}, "fence": Fence(1, 1).to_dict()}
        result = await backup.execute(resume, CALLER)
        self.assertEqual(result["operation"]["state"], "skipped_already_applied")
        replay = await primary.execute(payload, CALLER)
        self.assertEqual(replay["operation"]["state"], "rejected_stale_fence")
        self.assertEqual(self.raw.modifications, 1)
        self.assertEqual(self.exits, [83])
        counts = operation_counts([primary.trace.path], experiment_id=EXPERIMENT, incident_id=INCIDENT)
        self.assertEqual(counts["operations"], [dict(executor_aic=PRIMARY, operation_id="op-restore",
            invocations=1, returned=1, returned_errors=0, without_return=0)])

    async def test_exact_incident_tool_unarmed_backup_and_caller_do_not_exit(self):
        for kind in ("other_incident", "other_tool", "unarmed", "backup", "wrong_caller"):
            with self.subTest(kind=kind):
                bridge = await self.bridge("after_observation", role="backup" if kind == "backup" else "primary",
                                           armed=kind != "unarmed")
                payload = self.payload(observe=True, incident="other" if kind == "other_incident" else INCIDENT)
                if kind == "other_tool":
                    payload["tool"] = "db.health"
                result = await bridge.execute(payload, "other-caller" if kind == "wrong_caller" else CALLER)
                self.assertEqual(result["status"], "rejected" if kind == "wrong_caller" else "ok")
        self.assertEqual(self.exits, [])

    async def test_missing_or_tampered_approval_and_invalid_envelope_never_record_or_exit(self):
        bridge = await self.bridge("before_modification")
        for change in ("missing", "tampered", "schema"):
            payload = self.payload(operation="op-" + change)
            if change == "missing":
                payload.pop("approval")
            elif change == "tampered":
                payload["args"]["arbitrary_sql"] = "fixture-only"
            else:
                payload["schema_version"] = "wrong"
            self.assertEqual((await bridge.execute(payload, CALLER))["status"], "rejected")
        self.assertEqual(self.exits, [])
        self.assertEqual(bridge.ledger.list_operations(), [])
        self.assertEqual(self.raw.calls, [])

    async def test_stale_before_hook_and_already_applied_replay_do_not_crash_or_modify(self):
        bridge = await self.bridge("before_modification")
        bridge.ledger.advance_fence(Fence(3, 0))
        stale = await bridge.execute(self.payload(), CALLER)
        self.assertEqual(stale["operation"]["state"], "rejected_stale_fence")
        unarmed = await self.bridge(armed=False)
        action = self.payload(operation="already", fence=Fence(3, 0))
        self.assertEqual((await unarmed.execute(action, CALLER))["operation"]["state"], "applied")
        self.assertEqual((await bridge.execute(action, CALLER))["operation"]["state"], "skipped_already_applied")
        self.assertEqual(self.exits, [])
        self.assertEqual(self.raw.modifications, 1)

    async def test_main_backup_operation_counts_exclude_inspection_and_keep_unknown_return(self):
        primary = await self.bridge(armed=False)
        backup = await self.bridge(role="backup")
        self.assertEqual((await primary.execute(self.payload(operation="first"), CALLER))["status"], "ok")
        self.assertEqual((await backup.execute(self.payload(operation="second"), CALLER))["status"], "ok")
        self.raw.raise_write = True
        failed = await primary.execute(self.payload(operation="uncertain"), CALLER)
        self.assertEqual(failed["status"], "unknown")
        counts = operation_counts([primary.trace.path, backup.trace.path], experiment_id=EXPERIMENT, incident_id=INCIDENT)
        rows = {row["operation_id"]: row for row in counts["operations"]}
        self.assertEqual(set(rows), {"first", "second", "uncertain"})
        self.assertEqual(rows["first"]["executor_aic"], PRIMARY)
        self.assertEqual(rows["second"]["executor_aic"], BACKUP)
        self.assertEqual((rows["uncertain"]["invocations"], rows["uncertain"]["returned"], rows["uncertain"]["without_return"]), (1, 0, 1))
        self.assertEqual(sum(row["invocations"] for row in rows.values()), 3)
        with self.assertRaises(ValueError):
            operation_counts([primary.trace.path], experiment_id="other", incident_id=INCIDENT)
        with self.assertRaises(ValueError):
            operation_counts([primary.trace.path, primary.trace.path], experiment_id=EXPERIMENT, incident_id=INCIDENT)

    async def test_counted_client_retains_default_local_transport(self):
        policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER])
        current = ContextVar("legacy_count", default=self.payload())
        events = Events()
        client = CountedMcpClient(self.raw, "postgres", policy, SimpleNamespace(system=events), current)
        await client.call("execute_sql", {"sql": policy.tools["db.restore_writes"]["sql_template"]})
        self.assertEqual([event["transport"] for event in events.values], ["local-aip-stdio", "local-aip-stdio"])


class WorkerPreparationTests(unittest.TestCase):
    def options(self):
        return dict(experiment_id=EXPERIMENT, incident_id=INCIDENT, primary_aic=PRIMARY,
                    backup_aic=BACKUP, crash_point="after_applied")

    def test_backup_and_experiment_identity_guards(self):
        configs = documents(**self.options())
        document = configs["backup.json"]
        for changes in ({"armed": True}, {"crash_point": "after_applied"}, {"primary_aic": BACKUP}, {"experiment_id": "other"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ExperimentSpec.from_document({**document, **changes}, experiment_id=EXPERIMENT, executor_aic=BACKUP)
        with self.assertRaises(ValueError):
            ExperimentSpec.from_document(configs["primary.json"], experiment_id=EXPERIMENT, executor_aic=BACKUP)

    def test_overlay_pins_sources_and_roles_one_RO_mount_only_main_restart_disabled(self):
        import yaml
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            receipt = prepare(output, **self.options())
            self.assertFalse(receipt["primary_armed"])
            self.assertFalse(receipt["backup_armed"])
            manifest = worker.verify_bundle(output / "worker-source-manifest.json", receipt["manifest_sha256"], EXPERIMENT)
            self.assertEqual(set(manifest["source_sha256"]), worker.BUNDLE_SOURCES)
            overlay = yaml.safe_load((output / "e1-worker-overlay.yml").read_text())
            self.assertEqual(set(overlay["services"]), {"database-agent", "database-backup-agent"})
            self.assertEqual(overlay["services"]["database-agent"]["restart"], "no")
            self.assertNotIn("restart", overlay["services"]["database-backup-agent"])
            for service in overlay["services"].values():
                self.assertEqual(len(service["volumes"]), 1)
                self.assertTrue(service["volumes"][0]["read_only"])
                self.assertEqual(service["volumes"][0]["target"], "/experiment")
                self.assertIn(receipt["manifest_sha256"], service["command"])
            old = (output / "worker-source-manifest.json").read_bytes()
            with self.assertRaises(ValueError):
                prepare(output, **self.options())
            self.assertEqual((output / "worker-source-manifest.json").read_bytes(), old)
            (output / "primary.json").write_text("{}")
            with self.assertRaises(ValueError):
                worker.verify_bundle(output / "worker-source-manifest.json", receipt["manifest_sha256"], EXPERIMENT)

    def test_default_worker_checks_never_read_env_open_ledger_or_start_clients(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            experiment = root / "primary.json"
            config.write_text(json.dumps(dict(executor_aic=PRIMARY, allowed_callers=[CALLER], servers={"postgres": {}},
                platform={"endpoint": "amqps://fixture.invalid"}, env_files=[str(root / "never-read.env")],
                ledger_path=str(root / "never-open.sqlite"))))
            experiment.write_text(json.dumps(documents(**self.options())["primary.json"]))
            trace = root / "no-trace" / "trace.jsonl"
            argv = ["--config", str(config), "--experiment", str(experiment), "--experiment-id", EXPERIMENT, "--trace", str(trace)]
            with patch.object(worker, "environment_file", side_effect=AssertionError("no environment read")), \
                 patch.object(worker, "OperationLedger", side_effect=AssertionError("no ledger")), \
                 patch.object(worker, "McpStdioClient", side_effect=AssertionError("no process")), \
                 patch.object(worker, "serve", new_callable=AsyncMock) as serving, patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(worker.main(argv), 0)
                serving.assert_not_called()
                with self.assertRaises(ValueError):
                    worker.main([*argv, "--serve"])
                serving.assert_not_called()
            self.assertFalse(trace.parent.exists())
            self.assertFalse((root / "never-open.sqlite").exists())

    def test_invalid_plan_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "never"
            with self.assertRaises(ValueError):
                prepare(output, **{**self.options(), "experiment_id": "../escape"})
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
