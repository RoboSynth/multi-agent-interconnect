"""Offline control-contract checks; no real workbench, process or network."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workbench_host_under_test", ROOT / "tools/workbench_host.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


class WorkbenchHostTests(unittest.TestCase):
    def test_stop_requires_exact_pid_and_nonce(self):
        value = {"action": "stop_when_idle", "pid": 45, "session_nonce": "abc"}
        self.assertTrue(host.valid_stop(value, 45, "abc"))
        for changed in ({**value, "pid": 46}, {**value, "pid": True}, {**value, "session_nonce": "other"},
                        {**value, "action": "stop"}, None):
            self.assertFalse(host.valid_stop(changed, 45, "abc"))

    def test_idle_waits_for_active_approval_and_journal(self):
        journal = SimpleNamespace(list_tasks=lambda **kwargs: [])
        state = SimpleNamespace(active=None, engine=SimpleNamespace(runs={"old": {"status": "needs_attention", "approvals": []}}),
                                transport=SimpleNamespace(journal=journal))
        app = SimpleNamespace(state=state)
        self.assertTrue(host.idle_status(app)["idle"])
        state.active = SimpleNamespace(done=lambda: False)
        self.assertFalse(host.idle_status(app)["idle"])
        state.active = None
        state.engine.runs["old"]["approvals"] = [{"status": "pending"}]
        self.assertFalse(host.idle_status(app)["idle"])
        state.engine.runs["old"]["approvals"] = []
        journal.list_tasks = lambda **kwargs: [{"state": "delivery_unknown"}]
        self.assertFalse(host.idle_status(app)["idle"])

    def test_clean_environment_preserves_model_but_excludes_resource_credentials(self):
        source = {"Path": "fixture", "SYSTEMROOT": "fixture", "PGPASSWORD": "private",
                  "DATABASE_URI": "private", "APP_ADMIN_TOKEN": "private", "DOCKER_HOST": "private",
                  "INCIDENT_LLM_MODEL": "existing-model", "INCIDENT_LLM_API_KEY": "existing-key"}
        result = host.clean_environment(source)
        self.assertEqual(result["INCIDENT_LLM_MODEL"], "existing-model")
        self.assertEqual(result["INCIDENT_LLM_API_KEY"], "existing-key")
        self.assertFalse(set(result) & {"PGPASSWORD", "DATABASE_URI", "APP_ADMIN_TOKEN", "DOCKER_HOST"})
        self.assertEqual(result["PYTHONUTF8"], "1")

    def test_readiness_requires_updated_api_and_preserved_model_configuration(self):
        expected = {"config_sha256": "fixed", "llm_enabled": True}
        ready = {"runtime_pid": 45}
        state = {"pid": 45, "connected": True, "mode": "local-aip-stdio", "config_sha256": "fixed",
                 "participants": [{} for _ in range(5)], "model_config": {"enabled": True},
                 "incident": {"access_reconciliation": {}}, "resource_credential_count": 0}
        host.validate_readiness(state, ready, expected)
        bad_states = [{**state, "pid": 46}, {**state, "config_sha256": "changed"},
                      {**state, "connected": False}, {**state, "participants": [{}]},
                      {**state, "model_config": {"enabled": False}}, {**state, "incident": {}},
                      {**state, "resource_credential_count": 1}]
        for bad in bad_states:
            with self.subTest(state=list(bad)):
                with self.assertRaises(RuntimeError):
                    host.validate_readiness(bad, ready, expected)

    def test_stop_file_has_owned_session_and_never_overwrites(self):
        nonce = "a" * 32
        with tempfile.TemporaryDirectory(prefix=".workbench-host-test-", dir=ROOT) as temporary:
            control = Path(temporary)
            directory = control / nonce
            directory.mkdir()
            host.save(directory / "started.json", {"runtime_pid": 45, "session_nonce": nonce})
            with patch.object(host, "CONTROL", control):
                with self.assertRaises(ValueError):
                    host.request_stop(46, nonce)
                self.assertFalse((directory / "stop-request.json").exists())
                with self.assertRaises(ValueError):
                    host.request_stop(45, "../outside")
                result = host.request_stop(45, nonce)
                self.assertEqual(result["status"], "OWNED_IDLE_STOP_REQUESTED_NOT_YET_CLOSED")
                self.assertTrue(host.valid_stop(host.load(directory / "stop-request.json"), 45, nonce))
                with self.assertRaises(FileExistsError):
                    host.request_stop(45, nonce)

    def test_normal_validation_writes_nothing_and_imports_no_server(self):
        with tempfile.TemporaryDirectory(prefix=".workbench-host-test-", dir=ROOT) as temporary:
            root = Path(temporary)
            config = root / "config.json"
            host.save(config, {"mode": "local-aip-stdio", "workers": [{} for _ in range(5)], "llm_enabled": True})
            (root / ".venv/Scripts").mkdir(parents=True)
            (root / ".venv/Scripts/python.exe").write_bytes(b"fixture")
            (root / "source.py").write_bytes(b"fixture")
            original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with patch.object(host, "ROOT", root), patch.object(host, "CONFIG", config), patch.object(host, "OUTPUT", root / "absent-output"), \
                    patch.object(host, "SOURCE_PATHS", ("source.py",)), patch.object(host, "incident_hashes", return_value={}):
                result = host.validation()
            self.assertEqual(result["status"], "LOCAL_HOST_CONFIGURATION_VALIDATED_NO_RUNTIME_ACTION")
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}, original)
            self.assertFalse((root / "absent-output").exists())

    def test_owned_idle_request_exits_server_and_records_worker_close(self):
        import sys
        nonce = "b" * 32
        with tempfile.TemporaryDirectory(prefix=".workbench-host-test-", dir=ROOT) as temporary:
            directory = Path(temporary)
            expected = {"config_sha256": "fixed", "source_sha256": {}, "incident_sha256": {}, "llm_enabled": True}
            host.save(directory / "launch.json", {"validation": expected})
            host.save(directory / "stop-request.json", {"action": "stop_when_idle", "pid": host.os.getpid(), "session_nonce": nonce})
            worker = SimpleNamespace(process=SimpleNamespace(pid=123, returncode=None))
            transport = SimpleNamespace(mode="local-aip-stdio", participants=[{} for _ in range(5)], term=3,
                                        workers={"fixture": worker}, started=True,
                                        journal=SimpleNamespace(list_tasks=lambda **kwargs: []))
            app = SimpleNamespace(state=SimpleNamespace(active=None, transport=transport,
                                                        engine=SimpleNamespace(runs={})),
                                  middleware=lambda kind: lambda function: function)

            class FakeServer:
                def __init__(self, config):
                    self.started = False
                    self.should_exit = False

                async def serve(self):
                    self.started = True
                    while not self.should_exit:
                        await asyncio.sleep(0)
                    worker.process.returncode = 0
                    transport.started = False

            modules = {"uvicorn": SimpleNamespace(Server=FakeServer, Config=lambda *args, **kwargs: None),
                       "workbench_server": SimpleNamespace(create_app=lambda *args: app),
                       "fastapi.responses": SimpleNamespace(JSONResponse=lambda *args, **kwargs: None)}
            with patch.dict(sys.modules, modules), patch.object(host, "validation", return_value=expected), \
                    patch.object(host, "sha", return_value="fixed"), patch.object(host, "incident_hashes", return_value={}):
                result = asyncio.run(host.run_session(directory, nonce))
            report = host.load(directory / "finished.json")
            self.assertEqual(result, 0)
            self.assertEqual(report["status"], "LOCAL_CONTROLLED_WORKBENCH_NORMAL_CLOSE")
            self.assertEqual(report["worker_exit_codes"], {"fixture": 0})
            self.assertEqual(report["new_incidents_started_by_host"], 0)
            self.assertTrue(report["idle_stop_checks"]["idle"])


if __name__ == "__main__":
    unittest.main()
