"""Offline batch guards and real cancellation protocol with fake workers only."""
import asyncio
import contextlib
import importlib.util
import io
import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


batch = module("cloud_batch_under_test", HERE / "cloud_batch.py")
entry = module("cloud_entry_under_test", HERE / "managed_entrypoint.py")
protocol = module("managed_protocol_under_test", batch.ROOT / "ops/domain_entry.py")


class GuardTests(unittest.TestCase):
    def test_exact_four_order_and_zero_model_description(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(batch, "product", side_effect=AssertionError("must not import runtime")):
            self.assertEqual(batch.main(["describe"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["model_calls"], 0)
        self.assertEqual([r["key"] for r in value["cases"]], ["f10-m0-r1", "e1a-after_observation-r1", "e1a-before_modification-r1", "e1a-after_applied-r1"])
        self.assertEqual(value["lease_directory"], batch.LEASES)

    def test_entrypoint_keeps_normal_docker_command_unchanged(self):
        value = batch.overlay(Path("/opt/incident-pilot/runtime/private/new-batch"), "session")
        self.assertEqual(set(value["services"]), set(batch.SERVICES))
        for role in batch.ROLES:
            service = value["services"][role + "-agent"]
            self.assertEqual(service["restart"], "no")
            self.assertEqual(service["entrypoint"], batch.entrypoint(role, "session"))
            self.assertTrue(all(m["read_only"] for m in service["volumes"]))
            self.assertEqual(entry.dispatch(service["command"])[0], "module" if role in {"database", "database-backup", "ops"} else "path")
        self.assertEqual(value["services"]["database-agent"]["command"], ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"])

    def test_unknown_command_cannot_enter_signal_wrapper(self):
        for command in (["python", "-c", "print('arbitrary')"], ["sh", "-c", "arbitrary"],
                        ["python", "-m", "acps_mcp_bridge", "--config", "/other/config.json"]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                entry.dispatch(command)

    def test_experimental_command_keeps_original_script_and_args(self):
        command = ["python", "/experiment/source/eval/platform_database_worker.py", "--config", "/domain/bridge.json", "--experiment", "/experiment/primary.json", "--serve"]
        self.assertEqual(entry.dispatch(command), ("path", command[1], command[2:]))

    def test_e1_cleanup_adopts_only_exact_receipted_database_replacements(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            initial = {service: dict(id="original-" + service) for service in batch.SERVICES}
            batch.save(output / "restored-domains.json", {"database-agent": dict(container_id="restored-db"),
                "database-backup-agent": dict(container_id="restored-backup"),
                "application-agent": dict(container_id="must-not-adopt")})
            allowed = batch.registered_after(initial, output, dict(case="E1-a"))
            self.assertEqual(allowed["database-agent"], {"original-database-agent", "restored-db"})
            self.assertEqual(allowed["application-agent"], {"original-application-agent"})

    def test_authorization_binds_plan_hash_and_rejects_boolean_as_model_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            batch.save(path, dict(batch_id="fixture-batch"))
            auth = dict(schema_version="cloud-four-authorization/1", authorized=True,
                batch_plan_sha256=batch.sha(path), batch_id="fixture-batch", project=batch.PROJECT, model_calls=0,
                inspection_handoff=True, fault_and_restore=True, original_journal_offline_recovery=True,
                normal_owned_sdk_cleanup=True, stop_owned_consumers=True,
                received_at_utc="2026-10-20T00:00:00Z", user_confirmation="Fixture authorization")
            target = Path(temporary) / "authorization.json"
            batch.save(target, auth)
            self.assertEqual(batch.validate_authorization(path, target), auth)
            auth["model_calls"] = False
            batch.save(target, auth)
            with self.assertRaises(ValueError):
                batch.validate_authorization(path, target)


class SignalProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, fail_cleanup=False):
        ready, closed = asyncio.Event(), asyncio.Event()
        async def worker():
            try:
                ready.set()
                await asyncio.Event().wait()
            finally:
                closed.set()
                if fail_cleanup:
                    raise RuntimeError("fake cleanup failure")
        handlers = []
        loop = asyncio.get_running_loop()
        output = io.StringIO()
        with patch.object(loop, "add_signal_handler", side_effect=lambda number, callback: handlers.append(callback)), contextlib.redirect_stdout(output):
            task = asyncio.create_task(entry.managed(worker(), role="database", session="fixture", run_managed=protocol.run_managed))
            await ready.wait()
            handlers[0]()
            if fail_cleanup:
                with self.assertRaisesRegex(RuntimeError, "fake cleanup failure"):
                    await task
            else:
                await task
        self.assertTrue(closed.is_set())
        return output.getvalue()

    async def test_signal_waits_for_original_finally_before_exact_cleanup_receipt(self):
        output = await self.exercise()
        self.assertEqual(json.loads(output), dict(status="managed_consumer_closed", role="database", session="fixture", sdk_cleanup_completed=True))

    async def test_cleanup_exception_does_not_emit_success_receipt(self):
        self.assertEqual(await self.exercise(fail_cleanup=True), "")

    async def test_reused_f10_wrapper_loads_result_and_completes_after_real_close_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "f10-result"
            output.mkdir()
            checks = {name: True for name in ("no_group_sessions", "no_inbound_groups", "inbox_cancelled",
                "connection_closed", "owned_group_disconnected", "no_cleanup_warnings")}
            class Warnings(logging.Handler):
                def __init__(self):
                    super().__init__()
                    self.events = []
                def emit(self, record):
                    pass
            async def close_owned(transport, warnings):
                await transport.close()
                return checks
            async def close():
                return None
            fake_e1 = SimpleNamespace(CleanupWarnings=Warnings, close_owned=close_owned, healthy=lambda summary: True)
            class Runner:
                DOMAIN_SOURCE_FILES = ()
                @staticmethod
                def build_parser():
                    return SimpleNamespace(parse_args=lambda args: args)
                @staticmethod
                def create_transport(*args, **kwargs):
                    return SimpleNamespace(close=close, session=object(), runtime=object())
                @staticmethod
                async def run(args):
                    transport = Runner.create_transport()
                    batch.save(output / "results.json", [dict(scenario="F10", method="M0", model_enabled=False, model_calls=0)])
                    await transport.close()
                    return 0
                @staticmethod
                async def inject(*args, **kwargs):
                    return dict(target_proof=dict(compose_sha256={}, domains={}))
            class Observer:
                def __init__(self, *args, **kwargs):
                    pass
                async def observe(self, **kwargs):
                    return dict(passed=True)
            plan = dict(config="fixture-config.json", target_config="fixture-target.json", output=str(output), file_sha256={})
            original_local = batch.local
            def fixture_local(value):
                return Path(value) if value == str(output) else original_local(value)
            with patch.object(batch, "product", return_value=(fake_e1,)), patch.object(batch, "local", fixture_local):
                result = await batch.f10_case(plan, SimpleNamespace(order_url="http://fixture.invalid"), runner=Runner, observer_factory=Observer)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["resource_and_worker_restore"], "completed")
            self.assertEqual(result["close_checks"], checks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
