"""Owned shutdown contracts; fixtures do not start project services or a model."""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import local_shutdown as down
import workbench_host as host
from domains.ops import native_supervisor as supervisor


@contextmanager
def fixture():
    parent = ROOT.parent / "fixtures"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="local-down-", dir=parent) as temporary:
        root = Path(temporary)
        (root / "runtime").mkdir()
        (root / "deploy").mkdir()
        with patch.object(down, "ROOT", root):
            yield root


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class FakeFamily:
    def __init__(self, *args):
        self.records = [{"pid": 45}]
        self.closed = False

    def close(self):
        self.closed = True


class ShutdownTests(unittest.TestCase):
    def workbench(self, root):
        nonce = "a" * 32
        directory = root / "artifacts/workbench-host-8766" / nonce
        path = root / "runtime/workbench-server.json"
        save(path, {"runtime_pid": 45, "launcher_pid": 44, "session_nonce": nonce,
                    "control_directory": str(directory)})
        save(directory / "started.json", {"runtime_pid": 45, "session_nonce": nonce})
        return path, directory, nonce

    def finished(self, directory, nonce, **changes):
        save(directory / "finished.json", {"runtime_pid": 45, "session_nonce": nonce,
             "status": "LOCAL_CONTROLLED_WORKBENCH_NORMAL_CLOSE", "normal_idle_stop_requested": True,
             "idle_stop_checks": {"idle": True}, "worker_exit_codes": {"fixture": 0}, **changes})

    def test_empty_checkout_is_noop_and_preserves_report(self):
        with fixture() as root, patch.object(down, "OwnedFamily") as family, patch.object(down.subprocess, "run") as run:
            self.assertEqual(down.shutdown(1, Path(sys.executable)), 0)
            family.assert_not_called()
            run.assert_not_called()
            report = down.load(next((root / "runtime/local-down").glob("*.json")))
            self.assertEqual(report["status"], "REGISTERED_LOCAL_SHUTDOWN_COMPLETED")
            self.assertEqual({v["status"] for v in report["stages"].values()}, {"NO_REGISTRATION"})

    def test_native_other_checkout_or_external_paths_prevent_any_stop(self):
        for changes in ({"project_root": str(ROOT)}, {"pgdata": str(ROOT / "runtime/pgdata")},
                        {"nginx_prefix": "relative"}, {"backend": "docker"}):
            with self.subTest(changes=changes), fixture() as root:
                config = {"backend": "native", "project_root": str(root), "pgdata": str(root / "runtime/pgdata"),
                          "postgres_bin": str(root / "tools/pg"), "nginx_bin": str(root / "tools/nginx.exe"),
                          "nginx_prefix": str(root / "runtime/nginx"), **changes}
                save(root / "deploy/native-runtime.json", config)
                with patch.object(down, "workbench_stop") as stop:
                    self.assertEqual(down.shutdown(1, Path(sys.executable)), 1)
                    stop.assert_not_called()

    def test_workbench_normal_close_waits_for_handle_and_receipt(self):
        with fixture() as root:
            path, directory, nonce = self.workbench(root)
            before = path.read_bytes()
            family = FakeFamily()
            family.wait = lambda deadline: self.finished(directory, nonce) or [{"pid": 45}]
            with patch.object(down, "OwnedFamily", return_value=family), patch.object(host, "CONTROL", directory.parent):
                result = down.workbench_stop(path, down.fingerprint(path), 1)
            self.assertEqual(result["status"], "NORMAL_CLOSED")
            self.assertTrue(family.closed)
            self.assertTrue(host.valid_stop(down.load(directory / "stop-request.json"), 45, nonce))
            self.assertEqual(path.read_bytes(), before)

    def test_workbench_timeout_preserves_request_and_stops_dependency_shutdown(self):
        with fixture() as root:
            path, directory, nonce = self.workbench(root)
            family = FakeFamily()
            family.wait = lambda deadline: (_ for _ in ()).throw(TimeoutError("fixture active approval"))
            with patch.object(down, "OwnedFamily", return_value=family), patch.object(host, "CONTROL", directory.parent), \
                    patch.object(down, "supervisor_stop") as next_stop:
                self.assertEqual(down.shutdown(1, Path(sys.executable)), 1)
                next_stop.assert_not_called()
            self.assertTrue(path.exists())
            self.assertTrue((directory / "stop-request.json").exists())
            self.assertTrue(family.closed)
            report = down.load(next((root / "runtime/local-down").glob("*.json")))
            self.assertEqual(report["failed_stage"], "workbench")

    def test_workbench_mismatch_and_failed_finished_never_request_stop(self):
        with fixture() as root:
            path, directory, nonce = self.workbench(root)
            ready = directory / "started.json"
            save(ready, {"runtime_pid": 46, "session_nonce": nonce})
            with self.assertRaises(ValueError):
                down.workbench_stop(path, down.fingerprint(path), 1)
            self.assertFalse((directory / "stop-request.json").exists())
            save(ready, {"runtime_pid": 45, "session_nonce": nonce})
            self.finished(directory, nonce, status="LOCAL_CONTROLLED_WORKBENCH_FAILED_PRESERVED")
            with self.assertRaises(RuntimeError):
                down.workbench_stop(path, down.fingerprint(path), 1)
            self.assertFalse((directory / "stop-request.json").exists())

    def test_workbench_existing_correct_request_reused_and_normal_finish_idempotent(self):
        with fixture() as root:
            path, directory, nonce = self.workbench(root)
            save(directory / "stop-request.json", {"action": "stop_when_idle", "pid": 45, "session_nonce": nonce})
            before = (directory / "stop-request.json").read_bytes()
            family = FakeFamily()
            family.wait = lambda deadline: self.finished(directory, nonce) or []
            with patch.object(down, "OwnedFamily", return_value=family):
                down.workbench_stop(path, down.fingerprint(path), 1)
            self.assertEqual((directory / "stop-request.json").read_bytes(), before)
            exited = FakeFamily()
            exited.records = []
            exited.wait = Mock(return_value=[])
            with patch.object(down, "OwnedFamily", return_value=exited) as opened:
                self.assertEqual(down.workbench_stop(path, down.fingerprint(path), 1)["status"], "ALREADY_NORMAL_CLOSED")
                opened.assert_called_once()
                exited.wait.assert_called_once()
                self.assertTrue(exited.closed)

    def test_finished_workbench_receipt_still_waits_for_live_process_exit(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), fixture() as root:
                path, directory, nonce = self.workbench(root)
                self.finished(directory, nonce)
                family = FakeFamily()
                family.wait = Mock(side_effect=TimeoutError("still exiting") if timeout else None,
                                   return_value=[{"pid": 45, "exit_code": 0}])
                with patch.object(down, "OwnedFamily", return_value=family):
                    if timeout:
                        with self.assertRaises(TimeoutError):
                            down.workbench_stop(path, down.fingerprint(path), 1)
                    else:
                        self.assertEqual(down.workbench_stop(path, down.fingerprint(path), 1)["status"], "NORMAL_CLOSED")
                family.wait.assert_called_once()
                self.assertTrue(family.closed)
                self.assertFalse((directory / "stop-request.json").exists())

    def test_registration_change_refuses_native_entry_and_preserves_failure(self):
        with fixture() as root:
            runtime = root / "deploy/native-runtime.json"
            save(runtime, {"backend": "native", "project_root": str(root),
                           **{key: str(root / key) for key in ("pgdata", "postgres_bin", "nginx_prefix", "nginx_bin")}})
            def change(*args):
                runtime.write_text("{}", encoding="utf-8")
                return {"status": "fixture"}
            with patch.object(down, "workbench_stop", side_effect=change), patch.object(down, "supervisor_stop", return_value={}), \
                    patch.object(down.subprocess, "run") as run:
                self.assertEqual(down.shutdown(1, Path(sys.executable)), 1)
                run.assert_not_called()
            report = down.load(next((root / "runtime/local-down").glob("*.json")))
            self.assertEqual(report["failed_stage"], "native")

    def test_native_exact_entry_exit_failure_and_registration_retained(self):
        for exit_code in (0, 7):
            with self.subTest(exit_code=exit_code), fixture() as root:
                runtime = root / "deploy/native-runtime.json"
                save(runtime, {"backend": "native", "project_root": str(root),
                               **{key: str(root / key) for key in ("pgdata", "postgres_bin", "nginx_prefix", "nginx_bin")}})
                original = runtime.read_bytes()
                with patch.object(down.subprocess, "run", return_value=subprocess.CompletedProcess([], exit_code)) as run:
                    self.assertEqual(down.shutdown(1, Path(sys.executable)), int(exit_code != 0))
                    self.assertEqual(run.call_args.args[0][-3:], ["stop", "-RuntimeFile", str(runtime)])
                self.assertEqual(runtime.read_bytes(), original)


class SupervisorHttpTests(unittest.TestCase):
    def test_accepted_shutdown_is_scheduled_when_response_write_fails(self):
        from types import SimpleNamespace
        finished = threading.Event()
        handler = supervisor.Handler.__new__(supervisor.Handler)
        handler.server = SimpleNamespace(domain_token="t" * 32, shutdown=finished.set)
        handler.path = "/shutdown"
        handler.headers = {"Authorization": "Bearer " + "t" * 32, "Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        handler.wfile = SimpleNamespace(write=Mock(side_effect=BrokenPipeError("fixture disconnected")))
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        with self.assertRaises(BrokenPipeError):
            handler.do_POST()
        self.assertTrue(handler.server.shutdown_requested)
        self.assertTrue(finished.wait(2))

    def test_authenticated_idle_shutdown_and_unauthorized_or_busy_refusal(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), supervisor.Handler)
        server.domain_token = "t" * 32
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        url = f"http://127.0.0.1:{server.server_port}"
        def post(token):
            with opener.open(Request(url + "/shutdown", data=b"{}", headers={"Authorization": "Bearer " + token}), timeout=2) as response:
                return json.load(response)
        try:
            with patch.object(supervisor, "restart_registered_process", return_value={"fixture": "restart-returned"}) as restart:
                with opener.open(Request(url + "/restart", data=b"{}", headers={"Authorization": "Bearer " + server.domain_token}), timeout=2) as response:
                    self.assertEqual(json.load(response), {"fixture": "restart-returned"})
                restart.assert_called_once_with()
            with self.assertRaises(HTTPError) as denied:
                post("wrong")
            self.assertEqual(denied.exception.code, 403)
            with supervisor.LOCK:
                with self.assertRaises(HTTPError) as busy:
                    post(server.domain_token)
                self.assertEqual(busy.exception.code, 409)
            self.assertTrue(thread.is_alive())
            result = post(server.domain_token)
            self.assertEqual(result["status"], "SHUTDOWN_REQUESTED")
            self.assertEqual(result["pid"], os.getpid())
            thread.join(3)
            self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():
                server.shutdown()
                thread.join(3)
            server.server_close()

    def test_registered_supervisor_binds_health_and_waits_actual_exit(self):
        with fixture() as root:
            path = root / "runtime/ops-supervisor.pid"
            path.write_text("45", encoding="ascii")
            family = FakeFamily()
            family.wait = lambda deadline: [{"pid": 45}]
            class Response:
                def __init__(self, value):
                    self.data = json.dumps(value).encode()
                def __enter__(self):
                    import io
                    return io.BytesIO(self.data)
                def __exit__(self, *args):
                    return False
            class Opener:
                def __init__(self):
                    self.calls = []
                def open(self, request, **kwargs):
                    self.calls.append(request)
                    return Response({"ok": True, "service": "incident-pilot-native-ops", "pid": 45,
                                     "project_root": str(root), "status": "SHUTDOWN_REQUESTED"})
            opener = Opener()
            with patch.object(down, "OwnedFamily", return_value=family), patch.object(down, "build_opener", return_value=opener), \
                    patch.object(supervisor, "read_token", return_value="t" * 32):
                result = down.supervisor_stop(path, down.fingerprint(path), 1)
            self.assertEqual(result["status"], "NORMAL_CLOSED")
            self.assertEqual([call.full_url.rsplit("/", 1)[1] for call in opener.calls], ["health", "shutdown"])
            self.assertEqual(path.read_text(), "45")
            self.assertTrue(family.closed)


class FamilyPreflightTests(unittest.TestCase):
    def test_incomplete_or_reused_family_is_refused_and_all_open_handles_close(self):
        from types import SimpleNamespace
        script = ROOT / "domains/ops/native_supervisor.py"
        valid = ["python", str(script)]
        cases = [({10: ["python", str(script) + ".other"]}, [], {}, {}),
                 ({10: valid}, [], {}, {}),
                 ({10: valid, 11: valid}, [(11, 10)], {10: 20, 11: 10}, {}),
                 ({10: valid, 11: valid}, [(11, 10)], {}, {11: 99})]
        for commands, rows, times, parents in cases:
            with self.subTest(commands=commands, rows=rows):
                closed = []
                kernel = SimpleNamespace(OpenProcess=lambda rights, inherit, pid: pid,
                                         WaitForSingleObject=lambda handle, timeout: 0x102,
                                         CloseHandle=closed.append)
                with patch.object(down.native, "_libraries", return_value=(kernel, object())), \
                        patch.object(down.native, "_python_images", return_value=("launcher", {"launcher", "base"})), \
                        patch.object(down.native, "_command_line", side_effect=lambda ntdll, handle: handle), \
                        patch.object(down.native, "_argv", side_effect=lambda handle: commands[handle]), \
                        patch.object(down.native, "_image_path", side_effect=lambda k, handle: "launcher" if handle == 10 else "base"), \
                        patch.object(down.native, "_creation_time", side_effect=lambda k, handle: times.get(handle, handle)), \
                        patch.object(down.native, "_parent_pid", side_effect=lambda n, handle: parents.get(handle, 10)), \
                        patch.object(down.native, "_process_snapshot", return_value=rows):
                    with self.assertRaises(ValueError):
                        down.OwnedFamily(10, script, [], Path(sys.executable))
                self.assertCountEqual(closed, commands)


@unittest.skipUnless(os.name == "nt", "Windows owned-handle fixture")
class HandleFixtureTests(unittest.TestCase):
    def test_own_base_and_venv_handles_wait_for_real_exit_and_reject_other_command(self):
        for executable in dict.fromkeys((sys._base_executable, sys.executable)):
            with self.subTest(executable=Path(executable).parent.name):
                self.exercise_owned_fixture(Path(executable))

    def exercise_owned_fixture(self, executable):
        with fixture() as root:
            script = root / "sleeper.py"
            ready, stop = root / "ready", root / "stop"
            script.write_text("import pathlib,time\nr=pathlib.Path(__file__).parent\n(r/'ready').write_text('ready')\nwhile not (r/'stop').exists(): time.sleep(.02)\n", encoding="utf-8")
            process = subprocess.Popen([str(executable), str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
            family = None
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists())
                with self.assertRaises(ValueError):
                    down.OwnedFamily(process.pid, root / "different.py", [], executable)
                self.assertIsNone(process.poll())
                family = down.OwnedFamily(process.pid, script, [], executable)
                launcher, _ = down.native._python_images(executable)
                self.assertEqual(len(family.records), 2 if launcher else 1)
                self.assertEqual(family.records[0]["pid"], process.pid)
                stop.write_text("stop")
                exited = family.wait(time.monotonic() + 5)
                self.assertEqual(exited[0]["pid"], process.pid)
                self.assertTrue(all(r["exit_code"] == 0 for r in exited))
                self.assertEqual(process.wait(5), 0)
                print(json.dumps({"fixture": "owned_sleeping_python_normal_exit", "processes": exited}))
            finally:
                if family:
                    family.close()
                if process.poll() is None:
                    stop.write_text("stop")
                    process.wait(5)


@unittest.skipUnless(os.name == "nt" and shutil.which("pwsh"), "PowerShell entry fixture")
class PowerShellEntryTests(unittest.TestCase):
    def test_entry_calls_project_helper_with_timeout_and_propagates_failure(self):
        for code in (0, 7):
            with self.subTest(code=code), fixture() as root:
                entry = root / "deploy/local-down.ps1"
                shutil.copyfile(ROOT / "deploy/local-down.ps1", entry)
                python = root / ".venv/Scripts/python.exe"
                python.parent.mkdir(parents=True)
                python.write_bytes(b"fixture")
                wrapper = root / "fixture.ps1"
                event = root / "call.json"
                quote = lambda value: "'" + str(value).replace("'", "''") + "'"
                wrapper.write_text("$ErrorActionPreference='Stop'\nSet-Item -Path " + quote("Function:" + str(python)) +
                                   " -Value { @($args) | ConvertTo-Json | Set-Content -LiteralPath " + quote(event) +
                                   "; $global:LASTEXITCODE=" + str(code) + " }\n& " + quote(entry) + " -TimeoutSeconds 2\n", encoding="utf-8")
                result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(wrapper)],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, int(code != 0), result.stderr)
                argv = json.loads(event.read_text(encoding="utf-8-sig"))
                self.assertEqual(argv[:3], [str(root / "tools/local_shutdown.py"), "--timeout-seconds", 2])


if __name__ == "__main__":
    unittest.main()
