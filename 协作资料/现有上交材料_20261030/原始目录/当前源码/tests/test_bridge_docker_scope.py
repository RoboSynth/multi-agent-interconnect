from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Bridge, Policy
from acps_mcp_bridge.policy import PolicyRejected
from acps_sdk.aip.resumable import OperationLedger
from domains.ops.guard import labeled_container

CALLER = "scope-test-coordinator"
SCOPE = {"compose_project": "incident-pilot-new7", "compose_service": "app-v2",
         "container_name": "incident-pilot-new7-app-v2-1"}
TARGET_ID = "a" * 64


def container(scope=SCOPE, *, state="exited", identity=TARGET_ID):
    return {"id": identity, "name": scope["container_name"], "status": state,
            "labels": {"incident-pilot": "true", "com.docker.compose.project": scope["compose_project"],
                       "com.docker.compose.service": scope["compose_service"],
                       "private-domain-file": "do-not-return"}}


def document(scope=SCOPE):
    value = deepcopy(Policy.load(ROOT / "domains/ops/policy.yaml").document)
    value["allowed_callers"] = [CALLER]
    value["resources"].update(scope)
    value["tools"]["ops.containers"]["fixed_arguments"] = {
        "all": True, "filters": {"label": ["incident-pilot",
            "com.docker.compose.project=" + scope["compose_project"],
            "com.docker.compose.service=" + scope["compose_service"]]}}
    value["tools"]["ops.restart"]["fixed_arguments"]["container_id"] = scope["container_name"]
    return value


def task(tool="ops.containers", *, act=False, **changes):
    value = {"schema_version": "ifc/1.0", "incident_id": "scope-incident", "logical_task_id": "scope-task",
             "kind": "act" if act else "observe", "tool": tool, "args": {}}
    if act:
        value.update(operation_id="same-operation", fence={"coordinator_term": 1, "takeover_version": 0})
    return {**value, **changes}


class DockerStub:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    async def tools(self):
        return [{"name": name} for name in ("list_containers", "fetch_container_logs", "start_container",
                                             "stop_container", "route_status", "route_rollback", "process_status")]

    async def call(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == "list_containers":
            # Deliberately ignore filters: the bridge must still discard other projects/services.
            return {"structuredContent": {"result": deepcopy(self.rows)}}
        if name in {"stop_container", "start_container"}:
            for row in self.rows:
                if row["id"] == arguments["container_id"]:
                    row["status"] = "running" if name == "start_container" else "exited"
            return {"structuredContent": {"status": "exited"}}  # upstream cached pre-start state
        if name == "process_status":
            return {"structuredContent": {"backend": "native", "container_state": "exited"}}
        return {"structuredContent": {"route_version": "v2"}}


class ContainerGuardTests(unittest.IsolatedAsyncioTestCase):
    async def inspect(self, row, **scope):
        record = {"Id": row["id"], "Name": "/" + row["name"], "Config": {"Labels": row["labels"]}}
        process = AsyncMock(returncode=0)
        process.communicate.return_value = (json.dumps([record]).encode(), b"")
        with patch("domains.ops.guard.asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as spawn:
            result = await labeled_container(row["name"], command=["mock-docker"], **scope)
        self.assertEqual(spawn.await_args.args, ("mock-docker", "inspect", "--type", "container", row["name"]))
        return result

    async def test_exact_scope_resolves_to_immutable_id(self):
        self.assertEqual(await self.inspect(container(), **SCOPE), TARGET_ID)

    async def test_other_project_service_replica_or_missing_label_is_rejected(self):
        rows = []
        for key, value in (("compose_project", "incident-pilot-team-cold"), ("compose_service", "app-v1"),
                           ("container_name", "incident-pilot-new7-app-v2-2")):
            wrong = {**SCOPE, key: value}
            rows.append(container(wrong))
        unlabeled = container()
        unlabeled["labels"].pop("incident-pilot")
        rows.append(unlabeled)
        for row in rows:
            with self.subTest(row=row["name"], labels=row["labels"]):
                with self.assertRaises(PolicyRejected):
                    await self.inspect(row, **SCOPE)

    async def test_partial_scope_fails_before_inspect_and_no_scope_keeps_legacy_label_check(self):
        with patch("domains.ops.guard.asyncio.create_subprocess_exec", AsyncMock()) as spawn:
            with self.assertRaises(PolicyRejected):
                await labeled_container("target", command=["mock-docker"], compose_project="only-one-field")
            spawn.assert_not_called()
        self.assertEqual(await self.inspect(container({**SCOPE, "compose_project": "legacy-project"})), TARGET_ID)


class DockerScopeBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.authority = ApprovalAuthority("offline-scope-approval-" * 3)
        self.ledger = OperationLedger(Path(self.tmp.name) / "ops.sqlite", "ops")
        self.guarded = []

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def fixture(self, rows=None, scope=SCOPE):
        client = DockerStub(deepcopy(rows if rows is not None else [container(scope)]))
        policy = Policy(document(scope), approval_verifier=self.authority.verify)

        async def guard(name, **actual_scope):
            self.guarded.append((name, actual_scope))
            if name != scope["container_name"] or actual_scope != scope:
                raise PolicyRejected("wrong target")
            return TARGET_ID

        bridge = await Bridge(policy, {"docker": client, "route": client}, self.ledger,
                              "ops-scope-test", resource_guard=guard).initialize()
        return bridge, client

    def approve(self, command):
        command["approval"] = self.authority.issue(command, CALLER, approved_by="offline-test")
        return command

    async def test_observe_returns_fixed_target_state_and_discards_other_projects_and_services(self):
        other_project = {**SCOPE, "compose_project": "incident-pilot-team-cold"}
        other_service = {**SCOPE, "compose_service": "app-v1"}
        bridge, client = await self.fixture([container(other_project, state="running"), container(state="exited"),
                                             container(other_service, state="running")])
        result = await bridge.execute(task(), CALLER)
        self.assertEqual(result["status"], "ok", result)
        facts = {f["key"]: f["value"] for f in result["facts"]}
        self.assertEqual(facts["container_state"], "exited")
        self.assertEqual(facts["containers"], [{"id": TARGET_ID, "name": SCOPE["container_name"], "status": "exited"}])
        self.assertNotIn("do-not-return", json.dumps(result))
        arguments = client.calls[0][1]
        self.assertIs(arguments["all"], True)
        self.assertEqual(set(arguments["filters"]["label"]), {"incident-pilot",
            "com.docker.compose.project=" + SCOPE["compose_project"], "com.docker.compose.service=app-v2"})

    async def test_missing_unknown_or_ambiguous_target_never_manufactures_exited(self):
        for rows in ([], [container(state="paused")], [container({**SCOPE, "compose_project": "other"})]):
            bridge, _ = await self.fixture(rows)
            result = await bridge.execute(task(), CALLER)
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual(result["facts"][0]["value"], "unknown")
        bridge, _ = await self.fixture([container(), container(identity="b" * 64)])
        result = await bridge.execute(task(), CALLER)
        self.assertEqual(result["status"], "tool_error")
        self.assertEqual(result["facts"], [])

    async def test_restart_requires_approval_and_cannot_override_fixed_target(self):
        bridge, client = await self.fixture()
        command = task("ops.restart", act=True)
        self.assertEqual((await bridge.execute(command, CALLER))["status"], "rejected")
        overridden = self.approve(task("ops.restart", act=True, args={"container_id": "another-project-app-1"}))
        self.assertEqual((await bridge.execute(overridden, CALLER))["status"], "rejected")
        self.assertEqual(client.calls, [])
        self.assertEqual(self.guarded, [])

    async def test_malformed_container_reply_is_a_read_tool_error(self):
        for reply in ({"unexpected": "not-a-container-list"},
                      {"backend": "native", "container_state": "exited"}):
            bridge, _ = await self.fixture(reply)
            result = await bridge.execute(task(), CALLER)
            self.assertEqual(result["status"], "tool_error")
            self.assertEqual(result["facts"], [])

    async def test_scope_guard_denial_precedes_modifying_call(self):
        bridge, client = await self.fixture()
        bridge.resource_guard = AsyncMock(side_effect=PolicyRejected("outside fixed project"))
        result = await bridge.execute(self.approve(task("ops.restart", act=True)), CALLER)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(client.calls, [])
        self.assertIsNone(self.ledger.get("same-operation"))

    async def test_restart_uses_immutable_id_reobserves_real_state_and_replay_skips(self):
        bridge, client = await self.fixture()
        command = self.approve(task("ops.restart", act=True))
        applied = await bridge.execute(command, CALLER)
        replay = await bridge.execute(command, CALLER)
        self.assertEqual(applied["operation"]["state"], "applied", applied)
        self.assertEqual(applied["facts"][0]["value"], "running")
        self.assertEqual(replay["operation"]["state"], "skipped_already_applied")
        self.assertEqual([name for name, _ in client.calls], ["stop_container", "start_container", "list_containers"])
        self.assertEqual(client.calls[0][1], {"container_id": TARGET_ID})
        self.assertEqual(client.calls[1][1], {"container_id": TARGET_ID})
        self.assertEqual(self.guarded, [(SCOPE["container_name"], SCOPE)] * 2)

    async def test_operation_id_cannot_replay_or_modify_across_resource_scopes(self):
        bridge, first = await self.fixture()
        command = self.approve(task("ops.restart", act=True))
        self.assertEqual((await bridge.execute(command, CALLER))["operation"]["state"], "applied")
        different_scope = {**SCOPE, "compose_project": "separate-project",
                           "container_name": "separate-project-app-v2-1"}
        replacement, second = await self.fixture(scope=different_scope)
        rejected = await replacement.execute(command, CALLER)
        self.assertEqual(rejected["operation"]["state"], "rejected_parameter_mismatch", rejected)
        self.assertEqual(second.calls, [])
        self.assertEqual(len(first.calls), 3)

    async def test_native_observation_preserves_existing_contract(self):
        policy = Policy.load(ROOT / "domains/ops/policy.native.yaml", allowed_callers=[CALLER])
        client = DockerStub([])
        # Only the two relevant native observation tools are needed in this fixture.
        policy.tools = {"ops.containers": policy.tools["ops.containers"]}
        bridge = await Bridge(policy, {"native": client}, self.ledger, "native-test").initialize()
        result = await bridge.execute(task(), CALLER)
        self.assertEqual(result["facts"][0]["key"], "container_state")
        self.assertEqual(result["facts"][0]["value"], "exited")
        self.assertEqual(policy.container_scope, {})

    def test_scope_fields_are_all_or_none_and_ledger_parameters_include_all_three(self):
        original = document()
        for key in SCOPE:
            broken = deepcopy(original)
            broken["resources"].pop(key)
            with self.assertRaises(ValueError):
                Policy(broken)
        for value in (None, "", "invalid/name", True):
            broken = deepcopy(original)
            broken["resources"]["compose_project"] = value
            with self.assertRaises(ValueError):
                Policy(broken)
        legacy = deepcopy(original)
        for key in SCOPE:
            legacy["resources"].pop(key)
        self.assertEqual(Policy(legacy).container_scope, {})
        self.assertEqual(Policy(original).container_scope, SCOPE)


if __name__ == "__main__":
    unittest.main()
