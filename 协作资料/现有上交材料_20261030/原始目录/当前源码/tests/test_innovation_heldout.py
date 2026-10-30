"""Offline G4 fixtures and scheduling checks; never live recovery evidence."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import httpx
from acps_mcp_bridge.approval import ApprovalAuthority
from business.order_app.main import make_app
from business.order_app.store import Conflict, PoolManager
from eval.inject import Injector
from eval.methods import FixedPlanner
from eval.scheduling_audit import audit_cell
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine, rule_hypotheses
from incident.partners import ApplicationPartner
from test_coordinator import FakeHttpClient, FakeIncidentTransport


class M2GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def run_method(self, scenario, *, optimized=False, fixed=False, approve=True):
        body = {"usage": {"total_tokens": 7}, "choices": [{"message": {"content": json.dumps({
            "hypotheses": [hypothesis.model_dump() for hypothesis in rule_hypotheses()]})}}]}
        client = FakeHttpClient([deepcopy(body) for _ in range(30)])
        model = HypothesisEngine(enabled=not fixed, base_url="http://model.test/v1", model="fake", client=client)
        authority = ApprovalAuthority("unit-test-only-approval-secret" * 2)
        transport = FakeIncidentTransport("F07" if scenario == "F01_F07" else scenario, authority)
        if scenario == "F01_F07":
            transport.container = "exited"
        with tempfile.TemporaryDirectory() as directory:
            options = {"planner_factory": FixedPlanner, "eager_actions": False} if fixed else {}
            engine = IncidentCoordinator(transport, directory, hypothesis=model,
                approval_issuer=lambda payload: authority.issue(payload, "coordinator-test", approved_by="unit-test"),
                skip_deterministic_model_calls=optimized, **options)
            state = engine.new("same symptom")
            pending = asyncio.create_task(engine.run(state))
            while not pending.done():
                for approval in list(engine.approvals):
                    if not engine.approvals[approval][0].done():
                        engine.decide(approval, approve)
                await asyncio.sleep(0)
            result = await pending
        return result, transport.calls, client.calls

    async def test_opt_in_skips_terminal_and_sole_choices_without_changing_fake_repair(self):
        old, old_tasks, _ = await self.run_method("F07")
        new, new_tasks, _ = await self.run_method("F07", optimized=True)
        self.assertEqual((old["status"], new["status"]), ("completed", "completed"))
        self.assertEqual([task["tool"] for task in old_tasks], [task["tool"] for task in new_tasks])
        self.assertLess(new["model_calls"], old["model_calls"])
        self.assertEqual(new["tokens"], 7 * new["model_calls"])
        self.assertNotIn("model_skip_events", old)
        self.assertTrue(any(event["reason"] == "verification" for event in new["model_skip_events"]))
        self.assertEqual(len([task for task in new_tasks if task["kind"] == "verify"]), 1)

    async def test_model_prompt_and_sampling_are_unchanged_at_actual_calls(self):
        _, _, old_calls = await self.run_method("healthy")
        _, _, new_calls = await self.run_method("healthy", optimized=True)
        self.assertTrue(old_calls and new_calls)
        old_payload, new_payload = old_calls[0][1]["json"], new_calls[0][1]["json"]
        self.assertEqual(old_payload, new_payload)

    async def test_opt_in_still_requires_approval_and_decline_does_not_modify(self):
        result, tasks, _ = await self.run_method("F07", optimized=True, approve=False)
        self.assertEqual(result["status"], "needs_attention")
        self.assertFalse(any(task["kind"] == "act" for task in tasks))

    async def test_m0_already_repairs_compound_in_resource_model(self):
        result, tasks, calls = await self.run_method("F01_F07", fixed=True)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(calls, [])
        self.assertEqual({task["tool"] for task in tasks if task["kind"] == "act"},
                         {"ops.restart", "db.restore_writes", "application.pool_rebuild"})


class FakePool:
    def __init__(self, capacity):
        self.capacity, self.in_use, self.closed = capacity, 0, False
    async def acquire(self, timeout=None):
        if self.in_use >= self.capacity:
            raise TimeoutError("application pool acquisition timed out")
        self.in_use += 1
        return object()
    async def release(self, connection):
        self.in_use -= 1
    async def close(self):
        self.closed = True
    def get_size(self):
        return self.capacity
    def get_idle_size(self):
        return self.capacity - self.in_use
    def get_max_size(self):
        return self.capacity


class PoolFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_diagnostics_is_shared_opt_in_and_legacy_facts_stay_identical(self):
        body = {"config_revision": 1, "config_version": "candidate", "read_only": None,
                "pool": {"max_size": 1, "idle": 0}, "pool_exhausted": True}
        def handler(request):
            return httpx.Response(200, json=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            old = ApplicationPartner("app-test", None, client=client, allowed_callers=["leader"], pool_diagnostics=False)
            new = ApplicationPartner("app-test", None, client=client, allowed_callers=["leader"], pool_diagnostics=True)
            payload = {"incident_id": "incident-test", "logical_task_id": "task-test", "kind": "observe", "tool": "application.status"}
            previous, extended = await old.execute(payload, "leader"), await new.execute(payload, "leader")
        self.assertEqual([fact["key"] for fact in previous["facts"]],
                         ["application_reachable", "application_pool_revision", "application_read_only", "application_error_codes"])
        added = {fact["key"]: fact["value"] for fact in extended["facts"] if fact["key"] not in {fact["key"] for fact in previous["facts"]}}
        self.assertEqual(added, {"application_config_version": "candidate", "application_pool_capacity": 1,
                                "application_pool_idle": 0, "application_pool_exhausted": True})

    async def test_bad_pool_rebuild_stays_exhausted_and_config_rollback_restores_capacity(self):
        pools = PoolManager()
        pools._create = AsyncMock(side_effect=lambda version: FakePool(1 if version == "candidate" else 8))
        await pools.start()
        baseline = pools.pool
        await pools.replace(0, "candidate")
        first = pools.pool
        self.assertTrue(pools.status()["pool_exhausted"])
        with self.assertRaises(TimeoutError):
            async with pools.connection():
                self.fail("occupied one-connection pool cannot admit an order")
        await pools.replace(1)
        self.assertTrue(pools.status()["pool_exhausted"])
        self.assertTrue(first.closed)
        self.assertEqual(first.in_use, 0)
        await pools.replace(2, "stable")
        self.assertFalse(pools.status()["pool_exhausted"])
        async with pools.connection():
            pass
        self.assertTrue(baseline.closed)
        await pools.close()

    async def test_stale_revision_does_not_replace_or_acquire_a_pool(self):
        pools = PoolManager()
        pools.pool = FakePool(8)
        pools._create = AsyncMock()
        with self.assertRaises(Conflict):
            await pools.replace(3, "candidate")
        pools._create.assert_not_awaited()
        self.assertEqual(pools.revision, 0)

    async def test_http_fixture_requires_auth_opt_in_and_revision(self):
        pools = Mock()
        pools.replace = AsyncMock(return_value={"config_revision": 2, "config_version": "candidate"})
        with patch.dict(os.environ, {"APP_ADMIN_TOKEN": "unit-test-domain-token", "INCIDENT_ENABLE_TEST_FAULTS": "0"}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app(pools=pools)), base_url="http://test") as client:
                path = "/admin/config/test-pool-exhaustion"
                self.assertEqual((await client.post(path, json={"expected_revision": 1})).status_code, 401)
                headers = {"Authorization": "Bearer unit-test-domain-token"}
                self.assertEqual((await client.post(path, json={"expected_revision": 1}, headers=headers)).status_code, 404)
                with patch.dict(os.environ, {"INCIDENT_ENABLE_TEST_FAULTS": "1"}):
                    self.assertEqual((await client.post(path, json={}, headers=headers)).status_code, 400)
                    self.assertEqual((await client.post(path, json={"expected_revision": 1}, headers=headers)).status_code, 200)
        pools.replace.assert_awaited_once_with(1, "candidate")


class HeldoutInjectorTests(unittest.TestCase):
    def test_compound_restore_starts_app_before_rebuilding_read_write_connections(self):
        injector = object.__new__(Injector)
        injector.target = None
        calls = []
        injector.readonly = lambda enabled: calls.append(("readonly", enabled))
        injector.application = lambda running: calls.append(("application", running))
        injector.apply("F01_F07")
        injector.restore("F01_F07")
        self.assertEqual(calls, [("readonly", True), ("application", False), ("application", True), ("readonly", False)])

    def test_f04_uses_fixed_endpoint_with_exact_revision_and_restores_only_its_config(self):
        injector = object.__new__(Injector)
        injector.runtime = {"app_v2_port": 60882}
        injector._environment = lambda key: "unit-test-domain-token"
        status = {"config_revision": 3, "config_version": "stable", "pool": {"max_size": 8}}
        calls = []
        def handler(request):
            calls.append(request)
            if request.method == "POST":
                self.assertEqual(json.loads(request.content)["expected_revision"], status["config_revision"])
                status.update(config_revision=status["config_revision"] + 1,
                              config_version="candidate" if request.url.path.endswith("exhaustion") else "stable",
                              pool={"max_size": 1}, pool_exhausted=True)
            return httpx.Response(200, json=status)
        client_type = httpx.Client
        with patch("eval.inject.httpx.Client", side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)):
            injector.pool_exhaustion(True)
            injector.pool_exhaustion(False)
        self.assertEqual([request.url.path for request in calls if request.method == "POST"],
                         ["/admin/config/test-pool-exhaustion", "/admin/config/rollback"])
        self.assertTrue(all(str(request.url).startswith("http://127.0.0.1:60882/") for request in calls))

    def test_f04_does_not_overwrite_an_unrelated_candidate(self):
        injector = object.__new__(Injector)
        injector.runtime = {}
        injector._environment = lambda key: "unit-test-domain-token"
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"config_revision": 2, "config_version": "candidate", "pool": {"max_size": 8}})
        client_type = httpx.Client
        with patch("eval.inject.httpx.Client", side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)):
            with self.assertRaises(ValueError):
                injector.pool_exhaustion(False)
        self.assertEqual(len(calls), 1)


class OfflineAccountingTests(unittest.TestCase):
    def test_idempotent_unrelated_calls_are_not_reported_as_physical_actions(self):
        row = {"scenario": "F02", "method": "M1", "repeat": 1, "status": "needs_attention",
            "continuous_recovery_confirmed": False, "diagnosis_exact_match": False,
            "seconds": 2, "tokens": 7, "model_calls": 1, "token_usage_complete": True}
        tasks = [{"kind": "act", "tool": "ops.restart", "status": "ok", "elapsed_ms": 10,
                  "product": {"operation": {"state": state}}} for state in ("applied", "skipped_already_applied")]
        result = audit_cell(row, {"tasks": tasks, "model_requests": [{"seconds": 1}], "approvals": []})
        self.assertEqual((result["unrelated_action_attempts"], result["unrelated_applied_products"], result["idempotent_skip_products"]), (2, 1, 1))
        self.assertIsNone(result["physical_side_effects"])
        self.assertIsNone(result["timing"]["broker_queue_seconds"])


if __name__ == "__main__":
    unittest.main()
