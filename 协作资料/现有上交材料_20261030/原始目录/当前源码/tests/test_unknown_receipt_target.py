"""Real coordinator/verifier/observer over mock HTTP and a temporary SQL ledger."""
import asyncio
from contextlib import ExitStack
import copy
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
import httpx
import business.load as load
import eval.inject as injection
import eval.platform_resume_experiment as shared
import eval.run as matrix
import eval.targets as targets
import eval.unknown_receipt_experiment as runner
from incident.coordinator.planner import PROBES
from acps_mcp_bridge.bridge import Bridge
from acps_mcp_bridge.policy import Policy
from acps_sdk.aip.resumable import Fence, OperationLedger
from domains.ops import route_mcp

REAL_CLIENT, REAL_SLEEP = httpx.AsyncClient, asyncio.sleep


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    async def sleep(self, duration):
        self.now += max(duration, 0)
        await REAL_SLEEP(0)


class Fixture:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.project = "incident-pilot-f12-fixture"
        self.route = self.directory / "route.conf"
        self.original_route = b"set $order_upstream app-v2:8000;\r\n"
        self.route.write_bytes(self.original_route)
        self.compose = self.directory / "compose.yml"
        self.compose.write_text("services: {}\n", encoding="utf-8")
        self.env = self.directory / "compose.env"
        self.env.write_text("ORDER_PORT=58088\n", encoding="utf-8")
        self.target_path = self.directory / "target.json"
        self.target_path.write_text(json.dumps({"schema_version": "incident-evaluator-target/1.0", "backend": "docker",
            "project": self.project, "wsl_distro": None, "compose_files": [str(self.compose)], "env_file": str(self.env),
            "route_file": str(self.route), "ports": {"app_v1": 58081, "app_v2": 58082, "order": 58088, "reply_drop": 58090}}), encoding="utf-8")
        self.target = targets.DockerTarget.from_file(self.target_path)
        self.domains = {service: {"aic": service + "-fixture"} for service in targets.DOMAIN_SERVICES}
        self.config = {"leader": {"aic": "coordinator-fixture"},
            "skills": {role: role for role in ("application", "database", "ops", "verification")},
            "trusted_participant_aics": {role: [row["aic"] for name, row in self.domains.items()
                if targets.DOMAIN_SERVICES[name] == role] for role in ("application", "database", "ops", "verification")},
            "initial_participant_aics": {role: self.domains[service]["aic"] for service, role in
                (("application-agent", "application"), ("database-agent", "database"), ("ops-agent", "ops"), ("verification-agent", "verification"))}}
        for key in ("cert", "key"):
            path = self.directory / ("leader." + key)
            path.write_text("offline fixture", encoding="utf-8")
            self.config["leader"][key] = str(path)
        for key in ("trust_bundle", "approval_env_file"):
            path = self.directory / key
            path.write_text("offline fixture", encoding="utf-8")
            self.config[key] = str(path)
        self.config_path = self.directory / "coordinator.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.output = self.directory / "eval/results/platform/f12-fixture"
        self.plan = {"target_config": str(self.target_path), "config": str(self.config_path), "output": str(self.output),
                     "experiment_id": "f12-e5-" + "a" * 32}
        self.db = sqlite3.connect(self.directory / "ledger.sqlite")
        self.db.execute("CREATE TABLE orders(id TEXT PRIMARY KEY, request_key TEXT UNIQUE, item TEXT, quantity INTEGER, status TEXT)")
        self.db.execute("CREATE TABLE receipts(operation_key TEXT PRIMARY KEY, body TEXT)")
        self.db.execute("CREATE TABLE actions(operation_id TEXT PRIMARY KEY)")
        self.http_calls, self.tasks, self.controller_calls = [], [], []
        self.lifecycle = []
        self.fault_active = self.started = self.closed = False
        self.receipt_corruption = None
        self.fail_apply = self.fail_restore = False
        self.leave_group_on_close = False
        self.direct_healthy = True
        self.route_process_calls = []
        self.route_health_headers = []
        self.route_health_reads = 0
        self.change_on_direct_ready = None
        self.route_ledger = OperationLedger(self.directory / "ops-ledger.sqlite", "ops")

    def receipt(self, key, order, kind="create"):
        return {"order_api_version": "v2", "operation_key": key, "operation_kind": kind, "outcome": "committed",
                "order_id": order["id"], "changed": True, "order": order}

    def order(self, *, key=None, order_id=None):
        row = self.db.execute("SELECT id,request_key,item,quantity,status FROM orders WHERE " +
                              ("request_key=?" if key else "id=?"), (key or order_id,)).fetchone()
        return dict(zip(("id", "request_key", "item", "quantity", "status"), row)) if row else None

    def handle(self, request):
        self.assert_public(request)
        payload = json.loads(request.content) if request.content else None
        self.http_calls.append((request.method, request.url.path, payload))
        if request.url.path == "/ready":
            return httpx.Response(200, json={"ok": not self.fault_active, "api_version": "v2"})
        if request.url.path.startswith("/receipts/"):
            key = request.url.path.removeprefix("/receipts/")
            row = self.db.execute("SELECT body FROM receipts WHERE operation_key=?", (key,)).fetchone()
            if not row:
                return httpx.Response(404, json={"detail": "not found"})
            body = json.loads(row[0])
            if self.receipt_corruption and key.startswith("unknown-"):
                body = self.receipt_corruption(body)
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path == "/orders":
            key = payload["request_key"]
            order = self.order(key=key)
            if order is None:
                identity = str(uuid.uuid5(uuid.NAMESPACE_URL, key))
                self.db.execute("INSERT INTO orders VALUES(?,?,?,?,?)", (identity, key, payload["item"], payload["quantity"], "CREATED"))
                order = self.order(key=key)
                self.db.execute("INSERT INTO receipts VALUES(?,?)", (key, json.dumps(self.receipt(key, order))))
                self.db.commit()
            if self.fault_active:
                raise httpx.ReadTimeout("fixture lost reply after SQL commit", request=request)
            body = json.loads(self.db.execute("SELECT body FROM receipts WHERE operation_key=?", (key,)).fetchone()[0])
            return httpx.Response(200, json=body)
        order_id = request.url.path.split("/")[2]
        order = self.order(order_id=order_id)
        if not order:
            raise AssertionError("Unexpected order identity")
        if request.method == "GET":
            return httpx.Response(200, json={"order_api_version": "v2", "order": order})
        if request.url.path != "/orders/" + order_id + "/cancel":
            raise AssertionError("Unexpected write path")
        self.db.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
        body = self.receipt(payload["operation_key"], self.order(order_id=order_id), "cancel")
        self.db.execute("INSERT OR IGNORE INTO receipts VALUES(?,?)", (payload["operation_key"], json.dumps(body)))
        self.db.commit()
        return httpx.Response(200, json=body)

    def assert_public(self, request):
        if str(request.url).split("/", 3)[2] != "127.0.0.1:58088":
            raise AssertionError("Evaluator/observer bypassed the public target")

    def controller(self, **kwargs):
        fixture = self
        if kwargs != {"backend": "docker", "target_config": self.target_path}:
            raise AssertionError("Injector scope mismatch")

        class Controller:
            target_proof = {"domains": fixture.domains}

            def apply(self, scenario):
                fixture.controller_calls.append(("apply", scenario))
                fixture.fault_active = True
                fixture.route.write_text("set $order_upstream reply-drop:8090;\n", encoding="utf-8")
                self.f12_proof = {"route_restored": False, "proxy_stopped": False}
                if fixture.fail_apply:
                    raise RuntimeError("fixture apply failed after owned mutation")

            def restore(self, scenario):
                fixture.lifecycle.append("restore")
                fixture.controller_calls.append(("restore", scenario))
                if fixture.fail_restore:
                    raise RuntimeError("fixture restore failed")
                if hasattr(self, "f12_proof"):
                    fixture.route.write_bytes(fixture.original_route)
                    fixture.fault_active = False
                    self.f12_proof.update(route_restored=True, proxy_stopped=True)

            def sql(self, statement):
                row = fixture.db.execute(statement).fetchone()
                return "|".join(str(value) for value in row)

        return Controller()

    def transport(self, mode, config, config_path, output):
        from incident.partners import VerificationPartner
        fixture = self
        partner = VerificationPartner("verification-agent-fixture", base_url=self.target.order_url, allowed_callers=["coordinator-fixture"])

        class Transport:
            tools = [p.tool for p in PROBES] + ["ops.route_rollback", "incident.verification"]
            term = 1
            selected = fixture.config["initial_participant_aics"]
            descriptions = {"ops": {"resource_scope": {"compose_project": fixture.project,
                "compose_service": "app-v2", "container_name": fixture.project + "-app-v2-1"}}}

            def __init__(self):
                self.session = SimpleNamespace(session_id="fixture-owned-group",
                    leader_mq_client=SimpleNamespace(_state="connected"))
                self.runtime = SimpleNamespace(group_sessions={"fixture-owned-group": self.session},
                    _inbound_groups={}, _inbox_consumer_tag="fixture-inbox", _connection=SimpleNamespace(is_closed=False))

            async def start(self):
                fixture.started = True
                self.route_bridge = await fixture.make_route_bridge()

            async def close(self):
                fixture.lifecycle.append("transport_close")
                fixture.closed = True
                if not fixture.leave_group_on_close:
                    self.runtime.group_sessions.clear()
                self.runtime._inbox_consumer_tag = None
                self.runtime._connection.is_closed = True
                self.session.leader_mq_client._state = "disconnected"

            async def call(self, payload):
                fixture.tasks.append(copy.deepcopy(payload))
                if payload["tool"] == "incident.verification":
                    return await partner.execute(payload, "coordinator-fixture")
                if payload["tool"] in {"ops.route_status", "ops.route_rollback"}:
                    if payload["kind"] == "act":
                        fixture.db.execute("INSERT INTO actions VALUES(?)", (payload["operation_id"],))
                        fixture.db.commit()
                    return await self.route_bridge.execute(payload, "coordinator-fixture")
                observed = {"ops.containers": ("container_state", "running"),
                    "ops.route_status": ("route_version", "unknown" if fixture.fault_active else "v2"),
                    "application.status": ("application_reachable", True), "db.read_only_status": ("read_only", False),
                    "db.blocking_sessions": ("blocking_sessions", [])}
                key, value = observed[payload["tool"]]
                facts = [{"key": key, "value": value, "source": "fixture-normal-observation"}]
                return {"schema_version": "ifc/1.0", "incident_id": payload["incident_id"],
                        "logical_task_id": payload["logical_task_id"], "executor_aic": "fixture-domain", "status": "ok", "facts": facts}

        return Transport()

    async def make_route_bridge(self, policy_name="policy.yaml"):
        class RouteClient:
            async def tools(self):
                return [{"name": name} for name in ("route_status", "route_rollback", "process_status", "process_restart",
                    "list_containers", "fetch_container_logs", "start_container")]

            async def call(self, tool, arguments):
                function = {"route_status": route_mcp.route_status, "route_rollback": route_mcp.route_rollback}[tool]
                return {"structuredContent": function(**arguments)}

        client = RouteClient()
        policy = Policy.load(ROOT / "domains/ops" / policy_name, allowed_callers=["coordinator-fixture"])
        return await Bridge(policy, {server: client for server in ("route", "native", "docker")},
                            self.route_ledger, "ops-agent-fixture").initialize()

    def route_process(self, argv, **kwargs):
        self.route_process_calls.append(list(argv))
        if "reload" in argv and b"app-v2:8000" in self.route.read_bytes():
            self.fault_active = False
        return SimpleNamespace(returncode=0, stdout="true\n", stderr="")

    def route_opener(self, *args):
        fixture = self

        class Opener:
            def open(self, request, timeout):
                url = request if isinstance(request, str) else request.full_url
                if url == "http://app-v2:8000/ready":
                    if fixture.change_on_direct_ready is not None:
                        fixture.route.write_bytes(fixture.change_on_direct_ready)
                    return io.BytesIO(json.dumps({"ok": fixture.direct_healthy, "api_version": "v2"}).encode())
                if url != "http://nginx/health":
                    raise AssertionError("Route tool used an unregistered health URL: " + url)
                fixture.route_health_reads += 1
                response = io.BytesIO(json.dumps({"api_version": "v2"}).encode())
                response.headers = fixture.route_health_headers.pop(0) if fixture.route_health_headers else {}
                return response

        return Opener()

    def patches(self):
        stack, clock = ExitStack(), Clock()
        stack.enter_context(patch.object(shared, "ROOT", self.directory))
        stack.enter_context(patch.object(runner, "ROOT", self.directory))
        stack.enter_context(patch.object(injection, "Injector", side_effect=self.controller))
        stack.enter_context(patch.object(matrix, "create_transport", side_effect=self.transport))
        factory = lambda *args, **kwargs: REAL_CLIENT(transport=httpx.MockTransport(self.handle))
        stack.enter_context(patch.object(httpx, "AsyncClient", side_effect=factory))
        stack.enter_context(patch.object(load, "time", SimpleNamespace(monotonic=clock.monotonic)))
        stack.enter_context(patch.object(load, "asyncio", SimpleNamespace(sleep=clock.sleep)))
        stack.enter_context(patch.object(route_mcp, "ROUTE", self.route))
        stack.enter_context(patch.object(route_mcp, "NATIVE", False))
        stack.enter_context(patch.object(route_mcp, "VERSIONS", {"v1": "app-v1:8000", "v2": "app-v2:8000"}))
        stack.enter_context(patch.object(route_mcp.subprocess, "run", side_effect=self.route_process))
        stack.enter_context(patch.object(route_mcp.urllib.request, "build_opener", side_effect=self.route_opener))
        def advance(duration):
            clock.now += max(0, duration)
        stack.enter_context(patch.object(route_mcp, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=advance)))
        return stack


class FormalUnknownReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_receipt_resolver_requires_matching_committed_v2_identity(self):
        key, order_id = "original/key", str(uuid.uuid4())
        valid = {"order_api_version": "v2", "operation_key": key, "operation_kind": "create", "outcome": "committed",
                 "order_id": order_id, "order": {"id": order_id, "request_key": key, "status": "CREATED"}}
        cases = [([], False), ({**valid, "operation_key": "different"}, False),
                 ({**valid, "outcome": "unknown"}, False), ({**valid, "order_api_version": "v1"}, False),
                 ({**valid, "order_id": "not-a-uuid"}, False), (valid, True)]
        for body, accepted in cases:
            with self.subTest(receipt=body):
                calls = []

                def handler(request):
                    calls.append(request)
                    return httpx.Response(200, json=body)

                async with REAL_CLIENT(transport=httpx.MockTransport(handler)) as client:
                    result = await runner.resolve_unknown(client, "http://mock-order", key)
                self.assertEqual(result["status"] == "committed", accepted)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].method, "GET")
                self.assertTrue(str(calls[0].url).endswith("/receipts/original%2Fkey"))

    async def test_real_coordinator_repairs_then_verifier_resolves_original_and_abstains_without_key(self):
        self.assertTrue(Path(runner.__file__).resolve().is_relative_to(ROOT))
        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
            f = Fixture(temporary)
            try:
                with f.patches():
                    self.assertEqual(await runner.run_target(f.plan), 0)
                result = json.loads((f.output / "result.json").read_text(encoding="utf-8"))
                self.assertTrue(result["passed"])
                self.assertTrue(all(row["passed"] for row in result["checks"]))
                self.assertEqual(f.controller_calls, [("apply", "F12"), ("restore", "F12")])
                self.assertEqual(f.lifecycle, ["transport_close", "restore"])
                self.assertEqual(f.route.read_bytes(), f.original_route)
                self.assertTrue(f.closed)
                originals = json.loads((f.output / "private/original-intents.json").read_text(encoding="utf-8"))
                first, hidden = [row["payload"]["request_key"] for row in originals]
                creates = [row[2]["request_key"] for row in f.http_calls if row[:2] == ("POST", "/orders")]
                self.assertEqual((creates.count(first), creates.count(hidden)), (2, 1))
                verifications = [row for row in f.tasks if row["kind"] == "verify"]
                self.assertEqual([row["args"] for row in verifications], [
                    {"original_request_key": first, "original_request_unknown": True},
                    {"original_request_key": None, "original_request_unknown": True}])
                self.assertNotIn(hidden, json.dumps(f.tasks))
                self.assertNotIn("F12", json.dumps(f.tasks))
                tools = [row["tool"] for row in f.tasks]
                repair = tools.index("ops.route_rollback")
                self.assertEqual(tools[repair + 1], "ops.route_status")
                self.assertLess(repair, tools.index("incident.verification"))
                h00 = json.loads((f.output / "restored-h00/h00.json").read_text(encoding="utf-8"))
                self.assertEqual((h00["requests"], h00["success"], h00["completed_workflows"], h00["unknown"]), (30, 30, 10, 0))
                self.assertEqual(f.db.execute("SELECT count(*) FROM actions").fetchone()[0], 1)
            finally:
                f.db.close()

    async def test_invalid_receipt_keeps_actual_coordinator_unresolved_and_still_restores(self):
        invalid = {"wrong_key": lambda b: {**b, "operation_key": "foreign"},
                   "wrong_id": lambda b: {**b, "order_id": str(uuid.uuid4())},
                   "uncommitted": lambda b: {**b, "outcome": "unknown"},
                   "wrong_kind": lambda b: {**b, "operation_kind": "cancel"}}
        for name, corrupt in invalid.items():
            with self.subTest(receipt=name), tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
                f = Fixture(temporary)
                try:
                    f.receipt_corruption = corrupt
                    with f.patches():
                        self.assertEqual(await runner.run_target(f.plan), 1)
                    result = json.loads((f.output / "result.json").read_text(encoding="utf-8"))
                    self.assertFalse(result["passed"])
                    self.assertEqual(result["errors"][0]["phase"], "case")
                    self.assertTrue(result["restored"])
                    self.assertEqual(f.route.read_bytes(), f.original_route)
                    self.assertTrue(f.closed)
                    self.assertFalse((f.output / "restored-h00").exists())
                    incidents = list((f.output / "private/incidents").glob("*.json"))
                    state = json.loads(incidents[0].read_text(encoding="utf-8"))
                    self.assertEqual(state["status"], "needs_attention")
                    self.assertTrue(state["result"]["manual_required"])
                    self.assertFalse(state["result"]["original_request_resolved"])
                finally:
                    f.db.close()

    async def test_apply_failure_and_restore_failure_are_both_retained(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
            f = Fixture(temporary)
            try:
                f.fail_apply = f.fail_restore = True
                with f.patches():
                    self.assertEqual(await runner.run_target(f.plan), 1)
                result = json.loads((f.output / "result.json").read_text(encoding="utf-8"))
                self.assertEqual([row["phase"] for row in result["errors"]], ["case", "restore"])
                self.assertEqual(f.controller_calls, [("apply", "F12"), ("restore", "F12")])
                self.assertTrue(f.closed)
                self.assertEqual(f.http_calls, [])
            finally:
                f.db.close()

    async def test_normal_close_return_with_retained_group_cannot_pass(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
            f = Fixture(temporary)
            try:
                f.leave_group_on_close = True
                with f.patches():
                    self.assertEqual(await runner.run_target(f.plan), 1)
                result = json.loads((f.output / "result.json").read_text(encoding="utf-8"))
                self.assertTrue(f.closed)
                self.assertFalse(result["passed"])
                self.assertNotIn("transport_closed", result)
                self.assertEqual(result["errors"][0]["phase"], "transport_close")
                self.assertTrue(result["restored"])
                self.assertEqual(f.lifecycle, ["transport_close", "restore"])
                self.assertFalse((f.output / "restored-h00").exists())
            finally:
                f.db.close()

    async def test_foreign_platform_binding_is_rejected_before_connection_or_fault(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
            f = Fixture(temporary)
            try:
                f.config["trusted_participant_aics"]["ops"] = ["foreign-ops"]
                f.config_path.write_text(json.dumps(f.config), encoding="utf-8")
                with f.patches():
                    self.assertEqual(await runner.run_target(f.plan), 1)
                self.assertFalse(f.started)
                self.assertEqual(f.controller_calls, [("restore", "F12")])
                self.assertEqual(f.http_calls, [])
                self.assertEqual(f.route.read_bytes(), f.original_route)
            finally:
                f.db.close()

    async def test_existing_output_and_missing_proxy_port_refuse_before_controller(self):
        for failure in ("existing_output", "missing_port"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
                f = Fixture(temporary)
                try:
                    if failure == "existing_output":
                        f.output.mkdir(parents=True)
                    else:
                        body = json.loads(f.target_path.read_text(encoding="utf-8"))
                        del body["ports"]["reply_drop"]
                        f.target_path.write_text(json.dumps(body), encoding="utf-8")
                    with f.patches(), patch.object(injection, "Injector") as controller:
                        with self.assertRaises((ValueError, FileExistsError)):
                            await runner.run_target(f.plan)
                        controller.assert_not_called()
                finally:
                    f.db.close()


class FormalPlanTests(unittest.TestCase):
    def test_error_evidence_preserves_initial_and_cleanup_failures(self):
        error = ExceptionGroup("apply/cleanup", [ValueError("initial"), RuntimeError("cleanup")])
        evidence = runner.error_evidence(error)
        self.assertEqual(evidence["error_class"], "ExceptionGroup")
        self.assertEqual([(row["error_class"], row["message"]) for row in evidence["errors"]],
                         [("ValueError", "initial"), ("RuntimeError", "cleanup")])
        try:
            try:
                raise ValueError("initial apply")
            except ValueError:
                try:
                    raise RuntimeError("route restore")
                finally:
                    raise OSError("owned stop")
        except OSError as error:
            evidence = runner.error_evidence(error)
        self.assertEqual(evidence["message"], "owned stop")
        self.assertEqual(evidence["context"]["message"], "route restore")
        self.assertEqual(evidence["context"]["context"]["message"], "initial apply")

    def test_prepare_validate_authorize_are_offline_and_bind_sources_scope_and_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-") as temporary:
            f = Fixture(temporary)
            try:
                source = f.directory / "source.py"
                source.write_text("fixture source\n", encoding="utf-8")
                args = SimpleNamespace(target_config=f.target_path, config=f.config_path, output=f.output, plan=f.directory / "plan.json")
                with f.patches(), patch.object(shared, "source_paths", return_value={source}), \
                        patch.object(injection, "Injector") as controller:
                    plan = runner.prepare_target(args)
                    self.assertEqual(runner.validate_target_plan(args.plan), plan)
                    self.assertFalse(f.output.exists())
                    self.assertEqual(runner.main(["--plan", str(args.plan)]), 0)
                    with self.assertRaises(ValueError):
                        runner.authorize_target(plan, args.plan, None)
                    auth = {"schema_version": "platform-f12-authorization/1", "authorized": True,
                        "plan_sha256": shared.digest(args.plan), "experiment_id": plan["experiment_id"], "project": plan["project"],
                        "output": plan["output"], "effects": runner.EFFECTS, "exclusive_coordinator": True,
                        "no_other_identity_consumers": True, "no_active_or_unknown_operations": True}
                    auth_path = f.directory / "authorization.json"
                    shared.save(auth_path, auth)
                    with patch.dict(runner.os.environ, {}, clear=True):
                        self.assertEqual(runner.authorize_target(plan, args.plan, auth_path), auth)
                        auth["authorized"] = 1
                        shared.save(auth_path, auth)
                        with self.assertRaises(ValueError):
                            runner.authorize_target(plan, args.plan, auth_path)
                    source.write_text("changed source\n", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Frozen F12 input changed"):
                        runner.validate_target_plan(args.plan)
                    controller.assert_not_called()
            finally:
                f.db.close()


class GuardedRouteIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="f12-route-")
        self.fixture = Fixture(self.temporary.name)
        self.original = b"set $order_upstream reply-drop:8090;\r\n"
        self.fixture.route.write_bytes(self.original)

    async def asyncTearDown(self):
        self.fixture.db.close()
        self.temporary.cleanup()

    def command(self, *, operation="route-recover", guarded=True):
        return {"schema_version": "ifc/1.0", "incident_id": "original-request-incident", "logical_task_id": "route-task",
            "kind": "act", "tool": "ops.route_rollback", "operation_id": operation,
            "fence": {"coordinator_term": 1, "takeover_version": 0}, "args": {
                "expected_route_version": "unknown", "expected_route_sha256": route_mcp.route_status()["route_sha256"]} if guarded else {}}

    async def test_unknown_with_exact_snapshot_and_healthy_registered_v2_applies_once_through_real_ledger(self):
        f = self.fixture
        with f.patches():
            for policy_name in ("policy.yaml", "policy.native.yaml"):
                f.route.write_bytes(self.original)
                bridge = await f.make_route_bridge(policy_name)
                command = self.command(operation="recover-" + policy_name)
                result = await bridge.execute(command, "coordinator-fixture")
                self.assertEqual(result["status"], "ok", result)
                self.assertEqual(result["operation"]["state"], "applied", result)
                self.assertEqual(result["operation"]["before"]["value"], "unknown")
                self.assertEqual(result["operation"]["after"]["value"], "v2")
                self.assertEqual(result["facts"][0]["value"], "v2")
                self.assertEqual(f.route_ledger.get(command["operation_id"])["state"], "applied")
                calls_before = len(f.route_process_calls)
                replay = await bridge.execute(command, "coordinator-fixture")
                self.assertEqual(replay["operation"]["state"], "skipped_already_applied")
                self.assertEqual(len(f.route_process_calls), calls_before)

    async def test_v1_default_remains_guarded_and_unknown_without_pair_stays_rejected(self):
        f = self.fixture
        with f.patches():
            bridge = await f.make_route_bridge()
            result = await bridge.execute(self.command(guarded=False), "coordinator-fixture")
            self.assertEqual(result["operation"]["state"], "rejected_precondition")
            self.assertEqual(f.route_process_calls, [])
            f.route.write_bytes(b"set $order_upstream app-v1:8000;\n")
            result = await bridge.execute(self.command(guarded=False), "coordinator-fixture")
            self.assertEqual(result["operation"]["state"], "applied")
            self.assertEqual(result["operation"]["before"]["value"], "v1")

    async def test_stale_fence_and_changed_snapshot_cannot_modify_route(self):
        f = self.fixture
        with f.patches():
            bridge = await f.make_route_bridge()
            command = self.command()
            await f.route_ledger.activate_fence(Fence(2, 0))
            stale = await bridge.execute(command, "coordinator-fixture")
            self.assertEqual(stale["operation"]["state"], "rejected_stale_fence")
            self.assertEqual(f.route_process_calls, [])
            command["fence"]["coordinator_term"] = 2
            changed = b"# concurrent route owner\n" + self.original
            f.route.write_bytes(changed)
            result = await bridge.execute(command, "coordinator-fixture")
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(f.route.read_bytes(), changed)
            self.assertEqual(f.route_process_calls, [])

    async def test_unhealthy_v2_or_change_during_health_check_refuses_without_overwriting_new_owner(self):
        f = self.fixture
        with f.patches():
            bridge = await f.make_route_bridge()
            for condition in ("unhealthy", "concurrent_change"):
                f.route.write_bytes(self.original)
                f.direct_healthy = condition != "unhealthy"
                changed = b"# change after snapshot\n" + self.original
                f.change_on_direct_ready = changed if condition == "concurrent_change" else None
                command = self.command(operation=condition)
                result = await bridge.execute(command, "coordinator-fixture")
                self.assertEqual(result["status"], "unknown", result)
                self.assertEqual(f.route.read_bytes(), self.original if condition == "unhealthy" else changed)
                self.assertFalse(any("exec" in argv for argv in f.route_process_calls))

    async def test_policy_rejects_unpaired_or_non_unknown_override_before_resource_calls(self):
        f = self.fixture
        with f.patches():
            bridge = await f.make_route_bridge()
            for arguments in ({"expected_route_version": "unknown"}, {"expected_route_sha256": "a" * 64},
                              {"expected_route_version": "v1", "expected_route_sha256": "a" * 64},
                              {"target_version": "v1"}):
                command = {**self.command(), "args": arguments}
                result = await bridge.execute(command, "coordinator-fixture")
                self.assertEqual(result["status"], "rejected")
            self.assertEqual(f.route_process_calls, [])
            self.assertEqual(f.route.read_bytes(), self.original)

    async def test_route_convergence_waits_past_v2_response_still_served_by_reply_relay(self):
        f = self.fixture
        f.route_health_headers = [{"Via": "1.1 incident-pilot-relay"}, {}]
        with f.patches():
            bridge = await f.make_route_bridge()
            result = await bridge.execute(self.command(), "coordinator-fixture")
        self.assertEqual(result["operation"]["state"], "applied", result)
        self.assertEqual(f.route_health_reads, 2)


if __name__ == "__main__":
    unittest.main()
