"""Offline contracts only: fake identities and fake transport, no platform I/O."""
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("INCIDENT_REPO", str(HERE.parents[1])))
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location("cloud_health_helper", HERE / "deployment-20261020" / "cloud_healthy.py")
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class Fixture:
    def __init__(self, root):
        self.root = root
        self.domain = root / "runtime/private/cloud/domains"
        self.config = self.domain / "coordinator/config.json"
        self.deployment = root / "runtime/private/cloud/deployment.json"
        self.identities = {role: "fake-" + role for role in ["coordinator", *health.ROLES]}
        trusted = {role: [self.identities[role]] for role in health.SKILLS}
        trusted["database"].append(self.identities["database-backup"])
        self.source = dict(mode="wutong-amqps", skills=health.SKILLS, discovery_url="https://example.invalid/adp",
            leader=dict(aic=self.identities["coordinator"], endpoint="amqps://example.invalid"),
            trusted_participant_aics=trusted, initial_participant_aics=dict(database=self.identities["database"]),
            approval_env_file="THIS-FILE-MUST-NOT-BE-READ")
        save(self.config, self.source)
        save(self.deployment, dict(mode="seven", wsl_distro=None, project="fake-cloud",
            coordinator_config=self.config.relative_to(root).as_posix()))
        for role in health.ROLES:
            identity = dict(aic=self.identities[role], endpoint="amqps://example.invalid")
            bridge = role in {"database", "database-backup", "ops"}
            save(self.domain / role / ("bridge.json" if bridge else "config.json"),
                 dict(platform=identity) if bridge else identity)

    def prepared(self):
        # eval.targets and deploy.verify belong to the canonical project. The
        # fixture project contains only fake JSON, no credentials or key files.
        return health.prepare_inputs(self.root, self.config, self.deployment)


class FakeTransport:
    def __init__(self, config, output, identities, *, fail_close=False, unhealthy=False, warning=False):
        self.config = config
        self.identities = identities
        self.sent = []
        self.fail_close, self.unhealthy, self.warning = fail_close, unhealthy, warning
        self.closed = False
        self.selected, self.descriptions, self.participants = {}, {}, []
        self.journal = SimpleNamespace(list_tasks=lambda **kwargs: [])
        self.runtime = SimpleNamespace(group_sessions={"fake-group": object()}, _pending_invitations={},
            _inbound_groups={}, _inbox_consumer_tag="fake-consumer", _connection=SimpleNamespace(is_closed=False))
        self.session = SimpleNamespace(session_id="fake-group", group_id="fake-group-id",
            leader_mq_client=SimpleNamespace(_state=SimpleNamespace(value="connected")))

    async def _send(self, payload, target):
        self.sent.append((payload, target))
        result = dict(status="ok", executor_aic=target, facts=[])
        tool = payload["tool"]
        if tool == "application.status":
            facts = dict(application_reachable=True)
        elif tool == "db.read_only_status":
            facts = dict(read_only=False)
        elif tool == "ops.route_status":
            facts = dict(route_version="v2")
        elif tool == "aip.onboarding.check":
            facts = dict(onboarding_report=dict(target_aic=self.identities["application"], passed=True, active_target_probe=False))
        elif tool == "incident.verification":
            facts = dict(business_recovered=True, original_request_resolution="not_required",
                order_observation=dict(passed=True, duration_seconds=30.01, requests=30, success=30,
                    completed_workflows=10, failed=0, unknown=0, unresolved_intents=0, state=dict(pending=[])))
            if self.unhealthy:
                facts["order_observation"]["unknown"] = 1
        else:
            facts = {}
        result["facts"] = [dict(key=key, value=value) for key, value in facts.items()]
        return result

    async def start(self):
        for role, skill in health.SKILLS.items():
            candidates = await self._discover_candidates(role, skill)
            if any(row["aic"] == "foreign-team" for row in candidates):
                raise AssertionError("Foreign candidate was not filtered")
            self.selected[role] = self.identities[role]
            self.descriptions[role] = dict(resource_scope=dict(compose_project="fake-cloud",
                compose_service="app-v2", container_name="fake-cloud-app-v2-1"))
            await self._send(self.payload("describe", "describe", {}), self.identities[role])

    def payload(self, kind, tool, args):
        return dict(schema_version="ifc/1.0", incident_id="fake", logical_task_id="lt-" + str(len(self.sent)),
                    kind=kind, tool=tool, args=args, budget=dict(deadline_ms=15000))

    async def _select_participant(self, role, candidates, tool, *, initial=False):
        self.assert_backup = [row["aic"] for row in candidates]
        row = candidates[0]
        await self._send(self.payload("describe", "describe", {}), row["aic"])
        return row, dict(executor_aic=row["aic"])

    async def call(self, payload):
        prefix = payload["tool"].split(".")[0]
        role = {"application": "application", "db": "database", "ops": "ops", "aip": "onboarding", "incident": "verification"}[prefix]
        return await self._send(payload, self.selected[role])

    async def close(self):
        self.closed = True
        if self.fail_close:
            raise OSError("fake cleanup failed")
        if self.warning:
            logging.getLogger("fake-sdk").warning("event=queue_cleanup_failed")
        self.runtime.group_sessions.clear()
        self.runtime._inbox_consumer_tag = None
        self.runtime._connection.is_closed = True
        self.session.leader_mq_client._state.value = "disconnected"


class CloudHealthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    async def exercise(self, **options):
        prepared = self.fixture.prepared()
        transport = FakeTransport(prepared["config"], None, self.fixture.identities, **options)
        async def discover(url, skill, **kwargs):
            return [dict(aic=aic) for aic in [*self.fixture.identities.values(), "foreign-team"]]
        report = await health.execute(prepared, self.fixture.root / "result",
                                      transport_factory=lambda config, output: transport, discover=discover)
        return report, transport

    async def test_six_descriptions_six_normal_tasks_then_normal_close(self):
        original = self.fixture.config.read_bytes()
        report, transport = await self.exercise()
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(report["confirmed_domains"]), 6)
        self.assertEqual(len(report["completed_products"]), 12)
        self.assertEqual(sum(payload["kind"] == "describe" for payload, _ in transport.sent), 6)
        self.assertEqual(report["healthy_business"]["completed_workflows"], 10)
        self.assertEqual(transport.assert_backup, [self.fixture.identities["database-backup"]])
        self.assertEqual(transport.selected["database"], self.fixture.identities["database"])
        self.assertNotIn("approval_env_file", transport.config)
        self.assertIs(transport.config["automatic_takeover"], False)
        self.assertEqual(original, self.fixture.config.read_bytes())
        self.assertNotIn("foreign-team", json.dumps(report))
        self.assertTrue(transport.closed)

    async def test_close_failure_preserves_completed_task_phase(self):
        report, transport = await self.exercise(fail_close=True)
        self.assertEqual(report["task_phase_status"], "completed")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["close_status"], "failed")
        self.assertEqual(report["close_error_class"], "OSError")

    async def test_unknown_workflow_fails_and_still_closes(self):
        report, transport = await self.exercise(unhealthy=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["task_phase_status"], "failed")
        self.assertEqual(report["close_status"], "completed")
        self.assertTrue(transport.closed)

    async def test_sdk_cleanup_warning_cannot_report_success(self):
        report, transport = await self.exercise(warning=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["close_status"], "failed")
        self.assertFalse(report["close_checks"]["no_sdk_cleanup_warning_events"])

    def test_payload_guard_rejects_actions_foreign_targets_and_fences(self):
        identities = self.fixture.identities
        payload = dict(schema_version="ifc/1.0", incident_id="fake", logical_task_id="fake",
                       kind="observe", tool="db.read_only_status", args={}, budget=dict(deadline_ms=15000))
        for changed, target in [({**payload, "kind": "act", "tool": "db.restore_writes"}, identities["database"]),
                                (payload, "foreign-team"), ({**payload, "fence": {}}, identities["database"])]:
            with self.assertRaises(ValueError):
                health.guard_payload(changed, target, identities)

    def test_configuration_refuses_changed_primary(self):
        self.fixture.source["initial_participant_aics"]["database"] = self.fixture.identities["database-backup"]
        save(self.fixture.config, self.fixture.source)
        with self.assertRaisesRegex(ValueError, "primary"):
            self.fixture.prepared()

    def test_configuration_refuses_resource_credentials(self):
        self.fixture.source["extra"] = dict(database_uri="postgresql://user:secret@example.invalid/orders")
        save(self.fixture.config, self.fixture.source)
        with self.assertRaisesRegex(ValueError, "credentials"):
            self.fixture.prepared()

    def test_resource_environment_is_rejected(self):
        health.check_environment({"PATH": "fake", "NO_PROXY": "wt.ioa.pub"})
        with self.assertRaises(ValueError):
            health.check_environment({"DATABASE_URI": "never-print-this"})

    def test_offline_cli_does_not_execute_or_create_output(self):
        output = self.fixture.root / "offline-output"
        with patch.object(health, "execute", side_effect=AssertionError("must not execute")):
            result = health.main(["--project-root", str(self.fixture.root), "--config", str(self.fixture.config),
                                  "--deployment", str(self.fixture.deployment), "--output", str(output)])
        self.assertEqual(result, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
