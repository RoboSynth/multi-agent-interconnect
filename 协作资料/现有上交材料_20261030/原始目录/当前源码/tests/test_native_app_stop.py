"""Native app stop: mocked handles, real PowerShell, optional harmless venv child."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_stop_under_test", ROOT / "business/native_process.py")
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)
PWSH = shutil.which("pwsh")


class KernelFixture:
    def __init__(self, *, failed_pid=None, timeout_pid=None):
        self.live = {10, 11, 12}
        self.stopped = []
        self.closed = []
        self.failed_pid = failed_pid
        self.timeout_pid = timeout_pid

    def WaitForSingleObject(self, handle, timeout):
        if timeout and handle == self.timeout_pid:
            return 0x102
        return 0x102 if handle in self.live else 0

    def TerminateProcess(self, handle, code):
        if handle == self.failed_pid:
            return False
        self.stopped.append(handle)
        self.live.discard(handle)
        return True

    def CloseHandle(self, handle):
        self.closed.append(handle)


def record(pid, *, created=None, launcher=False, parent_pid=10):
    return {"pid": pid, "handle": pid, "created": created or pid, "launcher": launcher, "parent_pid": parent_pid}


class AppFamilyTests(unittest.TestCase):
    def invoke(self, records, rows, *, terminate=True, kernel=None):
        kernel = kernel or KernelFixture()
        python_executable = ROOT / ".venv/Scripts/python.exe"
        def open_record(_kernel, _ntdll, pid, version, port, configured_python, stopping):
            self.assertIs(_kernel, kernel)
            self.assertEqual((version, port, stopping), ("v1", 8081, terminate))
            self.assertEqual(configured_python, python_executable)
            value = records.get(pid)
            if isinstance(value, BaseException):
                raise value
            return value
        with patch.object(native, "_libraries", return_value=(kernel, object())), \
                patch.object(native, "_process_snapshot", return_value=rows), \
                patch.object(native, "_app_record", side_effect=open_record), \
                patch.object(native.ctypes, "get_last_error", return_value=5, create=True):
            result = native.managed_app_family(10, version="v1", port=8081,
                                               python_executable=python_executable, terminate=terminate)
        return result, kernel

    def test_direct_app_stops_one_verified_handle(self):
        result, kernel = self.invoke({10: record(10)}, [])
        self.assertEqual(result["process_ids"], [10])
        self.assertFalse(result["running"])
        self.assertEqual(kernel.stopped, [10])
        self.assertEqual(kernel.closed, [10])

    def test_venv_child_stops_before_launcher_using_the_verified_handles(self):
        result, kernel = self.invoke({10: record(10, launcher=True), 11: record(11)}, [(11, 10)])
        self.assertEqual(result["process_ids"], [11, 10])
        self.assertEqual(kernel.stopped, [11, 10])
        self.assertCountEqual(kernel.closed, [10, 11])

    def test_unrelated_child_is_never_stopped(self):
        _, kernel = self.invoke({10: record(10, launcher=True), 11: record(11),
                                 12: ValueError("wrong app")}, [(12, 10), (11, 10), (99, 98)])
        self.assertEqual(kernel.stopped, [11, 10])

    def test_query_has_no_termination(self):
        result, kernel = self.invoke({10: record(10, launcher=True), 11: record(11)}, [(11, 10)], terminate=False)
        self.assertTrue(result["running"])
        self.assertEqual(kernel.stopped, [])

    def test_missing_launcher_and_no_matching_child_is_idempotent(self):
        result, kernel = self.invoke({}, [])
        self.assertIsNone(result)
        self.assertEqual(kernel.stopped, [])

    def test_orphaned_matching_child_fails_without_stopping(self):
        kernel = KernelFixture()
        with self.assertRaisesRegex(RuntimeError, "matching app child remains"):
            self.invoke({11: record(11)}, [(11, 10)], kernel=kernel)
        self.assertEqual(kernel.stopped, [])
        self.assertEqual(kernel.closed, [11])

    def test_reused_parent_or_unready_launcher_is_refused(self):
        for records, rows in (({10: ValueError("wrong script")}, []),
                              ({10: record(10, launcher=True)}, []),
                              ({10: record(10, launcher=True), 11: record(11, created=5)}, [(11, 10)]),
                              ({10: record(10, launcher=True), 11: record(11, parent_pid=99)}, [(11, 10)]),
                              ({10: record(10, launcher=True), 11: record(11, launcher=True)}, [(11, 10)])):
            with self.subTest(records=records):
                kernel = KernelFixture()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.invoke(records, rows, kernel=kernel)
                self.assertEqual(kernel.stopped, [])

    def test_termination_or_wait_failure_preserves_error_and_closes_handles(self):
        for kernel in (KernelFixture(failed_pid=11), KernelFixture(timeout_pid=11)):
            with self.subTest(kernel=kernel), self.assertRaises(OSError):
                self.invoke({10: record(10, launcher=True), 11: record(11)}, [(11, 10)], kernel=kernel)
            self.assertNotIn(10, kernel.stopped)
            self.assertCountEqual(kernel.closed, [10, 11])

    def test_inaccessible_child_fails_before_any_stop(self):
        kernel = KernelFixture()
        with self.assertRaises(PermissionError):
            self.invoke({10: record(10, launcher=True), 11: PermissionError("cannot query")}, [(11, 10)], kernel=kernel)
        self.assertEqual(kernel.stopped, [])
        self.assertEqual(kernel.closed, [10])

    def test_configured_python_reads_its_own_venv_and_requires_absolute_paths(self):
        with fixture_directory() as root:
            executable = root / "custom-app-python/Scripts/python.exe"
            executable.parent.mkdir(parents=True)
            base = root / "separate-base"
            (root / "custom-app-python/pyvenv.cfg").write_text("home = " + str(base) + "\n", encoding="utf-8")
            launcher, images = native._python_images(executable)
            self.assertEqual(launcher, native._normalized_path(executable))
            self.assertEqual(images, {launcher, native._normalized_path(base / "python.exe")})
            self.assertNotIn(native._normalized_path(ROOT / ".venv/Scripts/python.exe"), images)
            self.assertEqual(native._python_images(base / "python.exe"),
                             (None, {native._normalized_path(base / "python.exe")}))
            with self.assertRaises(ValueError):
                native._python_images("relative/Scripts/python.exe")
            with self.assertRaises(FileNotFoundError):
                native._python_images(root / "missing-venv/Scripts/python.exe")

    @unittest.skipUnless(os.name == "nt", "Windows argv parsing")
    def test_exact_windows_argv_rejects_script_version_port_and_embedded_path(self):
        script = str(ROOT / "business/run_app.py")
        valid = ["python.exe", script, "--version", "v1", "--port", "8081"]
        self.assertTrue(native._app_command(subprocess.list2cmdline(valid), "v1", 8081))
        invalid = [valid[:1] + [script + ".other"] + valid[2:],
                   valid[:1] + ["business/run_app.py"] + valid[2:],
                   valid[:1] + [str(ROOT.parent / "other-checkout/business/run_app.py")] + valid[2:],
                   valid[:3] + ["v1x"] + valid[4:], valid[:-1] + ["8082"],
                   valid[:1] + [str(ROOT / "other.py"), script] + valid[2:],
                   valid + ["--extra"], ["python", "-c", script, "--version", "v1", "--port", "8081"]]
        for values in invalid:
            with self.subTest(values=values):
                self.assertFalse(native._app_command(subprocess.list2cmdline(values), "v1", 8081))


@contextmanager
def fixture_directory():
    base = ROOT.parent / "fixtures"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-app-stop-", dir=base) as temporary:
        yield Path(temporary)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell native-stop fixture")
class NativeStopEntryTests(unittest.TestCase):
    def run_fixture(self, failing_version=None, managed=True, *, nginx=False, failing_service=None):
        with fixture_directory() as root:
            (root / "deploy").mkdir()
            entry = root / "deploy/native.ps1"
            shutil.copyfile(ROOT / "deploy/native.ps1", entry)
            runtime = root / "runtime.json"
            saved = {"app_python": str(root / "stub-runtime/python.exe"), "postgres_bin": str(root / "stub-runtime/pg"),
                     "pgdata": str(root / "data"), "nginx_prefix": str((root / "nginx").relative_to(root)),
                     "nginx_bin": str(root / "stub-runtime/nginx.exe"),
                     "app_v1_port": 28081, "app_v2_port": 28082,
                     "managed": {"v1": 10, "v2": 20} if managed else {}}
            runtime.write_text(json.dumps(saved), encoding="utf-8")
            if nginx:
                (root / "nginx/logs").mkdir(parents=True)
                (root / "nginx/logs/nginx.pid").write_text("12345", encoding="ascii")
            events = root / "events.json"
            wrapper = root / "fixture.ps1"
            wrapper.write_text("""
$ErrorActionPreference='Stop'
$global:NativeStopEvents=@()
$global:NativeStopFailure=FAILURE
$global:NativeStopServiceFailure=SERVICEFAILURE
Set-Item -Path PYTHONFUNCTION -Value {
    $global:NativeStopEvents+=,@($args)
    $version=$args[([Array]::IndexOf($args,'--version')+1)]
    $global:LASTEXITCODE=if($version -eq $global:NativeStopFailure){9}else{0}
    '{"ProcessId":10,"running":false}'
}
Set-Item -Path POSTGRESFUNCTION -Value {
    $global:NativeStopEvents+=,@('pg_ctl',@($args))
    $global:LASTEXITCODE=if($global:NativeStopServiceFailure -eq 'postgres'){8}else{0}
}
Set-Item -Path NGINXFUNCTION -Value {
    $global:NativeStopEvents+=,@('nginx',@($args))
    $global:LASTEXITCODE=if($global:NativeStopServiceFailure -eq 'nginx'){7}else{0}
}
$fixtureExit=0
try { & ENTRY stop -RuntimeFile RUNTIME -EnvFile ABSENT }
catch { [Console]::Error.WriteLine($_.Exception.Message);$fixtureExit=1 }
ConvertTo-Json -InputObject @($global:NativeStopEvents) -Depth 5 | Set-Content -LiteralPath EVENTS -Encoding utf8
exit $fixtureExit
""".replace("SERVICEFAILURE", ps_quote(failing_service or "none"))
                .replace("FAILURE", ps_quote(failing_version or "none")).replace("ENTRY", ps_quote(entry))
                .replace("RUNTIME", ps_quote(runtime)).replace("ABSENT", ps_quote(root / "no-env"))
                .replace("PYTHONFUNCTION", ps_quote(f"Function:{os.sep}{saved['app_python']}"))
                .replace("POSTGRESFUNCTION", ps_quote(f"Function:{os.sep}{Path(saved['postgres_bin']) / 'pg_ctl.exe'}"))
                .replace("NGINXFUNCTION", ps_quote(f"Function:{os.sep}{saved['nginx_bin']}"))
                .replace("EVENTS", ps_quote(events)), encoding="utf-8")
            result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            rows = json.loads(events.read_text(encoding="utf-8-sig"))
            return result, rows, json.loads(runtime.read_text(encoding="utf-8-sig")), saved

    def test_stop_explicitly_binds_both_families_and_configured_ports(self):
        result, rows, saved, original = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(saved["managed"], {})
        self.assertEqual(rows[-1][0], "pg_ctl")
        for row, version, port in zip(rows[:2], ("v1", "v2"), (28081, 28082)):
            self.assertIn("--app-family", row)
            self.assertIn("--terminate", row)
            self.assertEqual(row[row.index("--version") + 1], version)
            self.assertEqual(str(row[row.index("--port") + 1]), str(port))
            self.assertEqual(row[row.index("--python-executable") + 1], original["app_python"])

    def test_family_failure_preserves_original_records_and_stops_before_database(self):
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                result, rows, saved, original = self.run_fixture(failing_version=version)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(saved, original)
                self.assertFalse(any(row[0] == "pg_ctl" for row in rows))

    def test_repeat_stop_without_managed_pids_has_no_app_termination(self):
        result, rows, saved, _ = self.run_fixture(managed=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(saved["managed"], {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "pg_ctl")

    def test_nginx_success_continues_to_database_and_saves_runtime(self):
        result, rows, saved, _ = self.run_fixture(nginx=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row[0] for row in rows[2:]], ["nginx", "pg_ctl"])
        self.assertIn("quit", rows[2][1])
        self.assertEqual(saved["managed"], {})

    def test_nginx_failure_preserves_runtime_and_stops_before_database(self):
        result, rows, saved, original = self.run_fixture(nginx=True, failing_service="nginx")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Nginx", result.stderr)
        self.assertIn("7", result.stderr)
        self.assertEqual(saved, original)
        self.assertEqual(rows[-1][0], "nginx")
        self.assertFalse(any(row[0] == "pg_ctl" for row in rows))

    def test_database_failure_preserves_runtime_after_nginx_success(self):
        result, rows, saved, original = self.run_fixture(nginx=True, failing_service="postgres")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PostgreSQL", result.stderr)
        self.assertIn("8", result.stderr)
        self.assertEqual(saved, original)
        self.assertEqual([row[0] for row in rows[2:]], ["nginx", "pg_ctl"])


@unittest.skipUnless(os.name == "nt" and os.environ.get("INCIDENT_NATIVE_STOP_FIXTURE") == "1",
                     "Explicit opt-in for a harmless fixture venv launcher and sleep child")
class RealVenvChildTests(unittest.TestCase):
    def test_real_venv_launcher_and_child_close_without_service_or_network(self):
        with fixture_directory() as root:
            (root / "custom-app-python/Scripts").mkdir(parents=True)
            (root / "business").mkdir()
            executable = root / "custom-app-python/Scripts/python.exe"
            shutil.copyfile(sys.executable, executable)
            shutil.copyfile(Path(sys.prefix) / "pyvenv.cfg", root / "custom-app-python/pyvenv.cfg")
            script = root / "business/run_app.py"
            script.write_text("import json,os,sys,time\nfrom pathlib import Path\n"
                              "Path(__file__).with_name('ready-'+sys.argv[-1]+'.json').write_text(json.dumps({'pid':os.getpid()}))\n"
                              "time.sleep(120)\n", encoding="utf-8")
            child_pid = None
            other_child_pid = None
            with (root / "stdout.log").open("wb") as out, (root / "stderr.log").open("wb") as err:
                process = subprocess.Popen([str(executable), str(script),
                                            "--version", "v1", "--port", "28081"], cwd=root,
                                           stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                other = subprocess.Popen([str(executable), str(script),
                                          "--version", "v1", "--port", "28082"], cwd=root,
                                         stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
            with patch.object(native, "ROOT", root):
                try:
                    deadline = time.monotonic() + 10
                    while not all((root / "business" / f"ready-{port}.json").exists() for port in (28081, 28082)):
                        if process.poll() is not None or other.poll() is not None or time.monotonic() >= deadline:
                            self.fail("Harmless fixture did not become ready: " + (root / "stderr.log").read_text(errors="replace"))
                        time.sleep(0.05)
                    child_pid = json.loads((root / "business/ready-28081.json").read_text())["pid"]
                    other_child_pid = json.loads((root / "business/ready-28082.json").read_text())["pid"]
                    before = native.managed_app_family(process.pid, version="v1", port=28081, python_executable=executable)
                    self.assertEqual(before["process_ids"], [child_pid, process.pid])
                    stopped = native.managed_app_family(process.pid, version="v1", port=28081,
                                                        python_executable=executable, terminate=True)
                    self.assertFalse(stopped["running"])
                    self.assertIsNotNone(process.wait(timeout=5))
                    self.assertIsNone(native.managed_app_family(process.pid, version="v1", port=28081,
                                                                python_executable=executable, terminate=True))
                    self.assertIsNone(other.poll())
                    sibling = native.managed_app_family(other.pid, version="v1", port=28082, python_executable=executable)
                    self.assertTrue(sibling["running"])
                    self.assertEqual(sibling["process_ids"], [other_child_pid, other.pid])
                    print(json.dumps({"fixture": "venv-launcher-and-sleep-child", "launcher_pid": process.pid,
                                      "configured_interpreter": "custom-app-python/Scripts/python.exe",
                                      "child_pid": child_pid, "stopped_in_order": stopped["process_ids"],
                                      "unrelated_port_sibling_still_running": sibling["process_ids"],
                                      "network_or_business_started": False}))
                finally:
                    for pid in (child_pid, process.pid, other_child_pid, other.pid):
                        if pid:
                            try:
                                native.managed_process(pid, script_name=str(script), version="v1", terminate=True)
                            except OSError:
                                pass
                    process.wait(timeout=5)
                    other.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
