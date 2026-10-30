"""Native-process takeover tests; every resource is a temporary fixture file."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_sdk.aip.resumable import Fence
from incident.local_transport import LocalAipStdioTransport


def modification_events(directory: Path):
    events = []
    for path in directory.glob("amp_system_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("body", {}).get("event") == "mcp_modify_invocation":
                events.append(record)
    return events


class LocalTakeoverTests(unittest.IsolatedAsyncioTestCase):
    def configuration(self, directory, point):
        directory = Path(directory)
        resource = directory / "resource.json"
        resource.write_text(json.dumps({"read_only": True, "modifying_calls": 0}), encoding="utf-8")
        approval = directory / "approval.env"
        approval.write_text("INCIDENT_APPROVAL_SECRET=fixture-approval-only-key-at-least-32-bytes\n", encoding="utf-8")
        policy = directory / "policy.yaml"
        policy.write_text("""domain: db
resources: {database: temporary-unittest-resource}
tools:
  db.read_only_status:
    server: fixture
    mcp_tool: execute_sql
    risk: read
    description: Read only the isolated fixture state
    input_schema: {type: object, additionalProperties: false, properties: {}}
    sql_template: SELECT read_only
  db.restore_writes:
    server: fixture
    mcp_tool: execute_sql
    risk: high
    description: Modify only the isolated fixture state
    input_schema: {type: object, additionalProperties: false, properties: {}}
    sql_template: SELECT restore_writes
    reconcile: {tool_alias: db.read_only_status, expected_after: false}
""", encoding="utf-8")
        workers = []
        for name in ("primary", "backup"):
            config = {"executor_aic": "test-database-"+name, "allowed_callers": ["test-coordinator"],
                "policy": str(policy), "ledger_path": str(directory / "domain-operations.sqlite"),
                "ledger_domain": "database", "approval_secret_env": "INCIDENT_APPROVAL_SECRET",
                "env_files": [str(approval)], "servers": {"fixture": {"command": sys.executable,
                    "args": [str(ROOT / "tests/fixtures/resume_fake_mcp.py"), str(resource)]}}}
            path = directory / (name + ".json")
            path.write_text(json.dumps(config), encoding="utf-8")
            worker = {"name": name, "role": "database", "aic": "test-database-"+name,
                      "bridge_config": str(path), "standby": name == "backup"}
            if name == "primary":
                worker.update(crash_point=point, crash_tool="db.read_only_status" if point == "after_observation" else "db.restore_writes")
            workers.append(worker)
        return {"coordinator_aic": "test-coordinator", "approval_env_file": str(approval),
                "term_journal_path": str(directory / "terms.sqlite"), "workers": workers,
                "experiment_id": "isolated-file-fixture", "allow_experiment_crash": True,
                "startup_timeout_seconds": 30}

    async def exercise(self, point):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config = self.configuration(directory, point)
            transport = LocalAipStdioTransport(config, directory / "transport")
            try:
                await transport.start()
                observation = {"incident_id": "fixture-incident", "logical_task_id": "logical-observation", "kind": "observe",
                               "tool": "db.read_only_status", "args": {}, "budget": {"deadline_ms": 15000}}
                observed = await transport.call(observation)
                self.assertEqual(observed["status"], "ok")
                action = {"incident_id": "fixture-incident", "logical_task_id": "logical-action", "kind": "act",
                          "tool": "db.restore_writes", "args": {}, "operation_id": "fixture-incident:repair",
                          "fence": {"coordinator_term": transport.term, "takeover_version": 0}, "budget": {"deadline_ms": 15000}}
                action["approval"] = transport.issue_approval(action)
                result = await transport.call(action)
                self.assertEqual(result["status"], "ok", result)
                self.assertEqual(result["logical_task_id"], "logical-action")
                actual = json.loads((directory / "resource.json").read_text(encoding="utf-8"))
                self.assertEqual(actual, {"read_only": False, "modifying_calls": 1})
                invocations = modification_events(transport.amp_directory)
                self.assertEqual(len(invocations), 1)
                self.assertEqual(invocations[0]["body"]["operation_id"], action["operation_id"])
                takeovers = [e for e in transport.events if e["event"] == "takeover_completed"]
                self.assertEqual(len(takeovers), 1)
                self.assertEqual(takeovers[0]["discovery"], "local process directory")
                self.assertEqual(takeovers[0]["replacement_aic"], "test-database-backup")
                replay = await transport.call_on_worker("test-database-backup", action)
                self.assertEqual(replay["status"], "rejected")
                self.assertEqual(replay["operation"]["state"], "rejected_stale_fence")
                self.assertEqual(len(modification_events(transport.amp_directory)), 1)
                self.assertEqual(transport.journal.list_tasks(in_flight_only=True), [])
                if point == "after_applied":
                    self.assertEqual(result["operation"]["state"], "skipped_already_applied")
                    self.assertEqual(invocations[0]["aic"], "test-database-primary")
                else:
                    self.assertEqual(invocations[0]["aic"], "test-database-backup")
            finally:
                await transport.close()

    async def test_after_observation_process_exit_resumes_on_confirmed_backup(self):
        await self.exercise("after_observation")

    async def test_before_modification_process_exit_executes_received_once(self):
        await self.exercise("before_modification")

    async def test_after_applied_process_exit_skips_modification_on_backup(self):
        await self.exercise("after_applied")

    async def test_unknown_resume_never_issues_an_action(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"coordinator_aic": "test", "workers": [], "term_journal_path": str(Path(directory)/"terms.sqlite")}
            transport = LocalAipStdioTransport(config, Path(directory)/"transport")
            failed = SimpleNamespace(spec={"role": "database", "aic": "old"}, resource_scope={"database": "fixture"})
            backup = SimpleNamespace(spec={"role": "database", "aic": "backup", "name": "backup"},
                                     state="ready", tools=["db.restore_writes"])
            transport.workers = {"backup": backup}
            async def call(worker, payload):
                if payload["kind"] == "describe":
                    return {"status": "ok", "description": {"executor_aic": "backup", "tools": ["db.restore_writes"],
                            "resource_scope": {"database": "fixture"}}}
                self.assertEqual(payload["kind"], "resume")
                return {"status": "unknown", "operation": {"state": "reconciliation_required"}, "active_fence": payload["fence"]}
            transport._call_worker = AsyncMock(side_effect=call)
            result = await transport._takeover(failed, {"schema_version":"ifc/1.0","incident_id":"inc","logical_task_id":"task",
                "kind":"act","tool":"db.restore_writes","operation_id":"op","fence":Fence(transport.term).to_dict(),"args":{}}, "test_timeout")
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(transport._call_worker.await_count, 2)

    def test_term_journal_is_shared_while_attempt_journals_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"coordinator_aic": "test", "term_journal_path": str(Path(directory)/"terms.sqlite")}
            first = LocalAipStdioTransport(config, Path(directory)/"first")
            second = LocalAipStdioTransport(config, Path(directory)/"second")
            self.assertEqual(second.term, first.term+1)
            self.assertNotEqual(first.journal.path, second.journal.path)
            self.assertEqual(first.term_journal.path, second.term_journal.path)


if __name__ == "__main__":
    unittest.main()
