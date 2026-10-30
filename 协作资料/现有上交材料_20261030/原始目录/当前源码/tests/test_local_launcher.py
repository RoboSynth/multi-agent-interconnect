"""Real PowerShell entry points with isolated process/HTTP/resource stubs."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
if not PWSH and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PowerShell/7/pwsh.exe"
    PWSH = str(candidate) if candidate.exists() else None


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@contextmanager
def fixture_directory():
    # tempfile's owner-only Windows ACL excludes the desktop sandbox identity.
    base = ROOT / "artifacts/local-startup-launcher-20261018/fixtures"
    base.mkdir(parents=True, exist_ok=True)
    directory = base / uuid.uuid4().hex
    directory.mkdir()
    try:
        yield directory
    finally:
        if directory.resolve().parent != base.resolve() or directory.is_symlink():
            raise AssertionError("Fixture cleanup escaped its own artifact directory")
        shutil.rmtree(directory)


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell 7 launcher")
class WorkbenchLauncherTests(unittest.TestCase):
    def run_fixture(self, scenario):
        with fixture_directory() as directory:
            root = Path(directory)
            for folder in ("tools", ".venv/Scripts", "runtime", "base-python"):
                (root / folder).mkdir(parents=True)
            shutil.copyfile(ROOT / "tools/start_workbench.ps1", root / "tools/start_workbench.ps1")
            (root / ".venv/Scripts/python.exe").write_bytes(b"must not execute")
            (root / "base-python/python.exe").write_bytes(b"must not execute")
            (root / ".venv/pyvenv.cfg").write_text("home = " + str(root / "base-python") + "\nexecutable = " + str(root / "base-python/python.exe") + "\n", encoding="utf-8")
            config = root / "runtime/local-coordinator.json"
            config.write_text(json.dumps({"mode": "local-aip-stdio", "llm_enabled": True,
                "llm_base_url": "http://127.0.0.1:8089/v1", "llm_model": "chosen-local-model"}))
            metadata = root / "runtime/workbench-server.json"
            if scenario.startswith("existing"):
                metadata.write_text('{"retain":"existing metadata"}')
            wrapper = root / "fixture.ps1"
            wrapper.write_text(r"""
$ErrorActionPreference='Stop'
$global:LauncherFixtureScenario=SCENARIO
$global:LauncherFixtureRequests=0
$global:LauncherFixtureLaunches=0
$global:LauncherFixtureMetadataBeforeReady=$false
$global:LauncherFixtureBlockedNames=@()
$global:LauncherFixtureExpectedSha=(Get-FileHash -LiteralPath CONFIG -Algorithm SHA256).Hash.ToLowerInvariant()
function Invoke-RestMethod {
    param($Uri,$TimeoutSec,[switch]$NoProxy)
    $global:LauncherFixtureRequests++
    if($global:LauncherFixtureScenario -notlike 'existing*' -and $global:LauncherFixtureRequests -eq 1){throw 'not listening'}
    $connected=$true
    if($global:LauncherFixtureScenario -eq 'existing-unconnected' -or $global:LauncherFixtureScenario -eq 'timeout'){$connected=$false}
    if($global:LauncherFixtureScenario -eq 'new-ready' -and $global:LauncherFixtureRequests -eq 2){$connected=$false}
    if(-not $connected -and (Test-Path -LiteralPath METADATA)){$global:LauncherFixtureMetadataBeforeReady=$true}
    $configSha=if($global:LauncherFixtureScenario -eq 'existing-stale'){'old-loaded-config'}else{$global:LauncherFixtureExpectedSha}
    $responsePid=if($global:LauncherFixtureScenario -eq 'wrong-pid' -or $global:LauncherFixtureScenario -like 'child-*'){5252}else{4242}
    return [pscustomobject]@{mode='local-aip-stdio';config_sha256=$configSha;connected=$connected;connection_error=$null;pid=$responsePid}
}
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,
          [switch]$UseNewEnvironment,$Environment,$RedirectStandardOutput,$RedirectStandardError)
    $global:LauncherFixtureLaunches++
    $global:LauncherFixtureBlockedNames=@($Environment.Keys | Where-Object {
        $_ -match '^(PG|DATABASE_URI$|APP_ADMIN_TOKEN$)' -and $null -ne $Environment[$_]
    })
    $process=[pscustomobject]@{Id=4242;HasExited=($global:LauncherFixtureScenario -eq 'early-exit');ExitCode=17}
    $process | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
    $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {}
    return $process
}
function Get-CimInstance {
    param($ClassName,$Filter,$ErrorAction)
    if($ClassName -ne 'Win32_Process' -or $Filter -ne 'ProcessId = 5252'){throw 'Unexpected process query'}
    $parent=if($global:LauncherFixtureScenario -eq 'wrong-pid' -or $global:LauncherFixtureScenario -eq 'child-wrong-parent'){3131}else{4242}
    $exe=if($global:LauncherFixtureScenario -eq 'child-wrong-exe'){'C:\unrelated\python.exe'}else{BASEPYTHON}
    $script=if($global:LauncherFixtureScenario -eq 'child-wrong-script'){JOINSCRIPT}else{WORKBENCHSCRIPT}
    $config=if($global:LauncherFixtureScenario -eq 'child-wrong-config'){JOINSCRIPT}else{CONFIG}
    $output=if($global:LauncherFixtureScenario -eq 'child-wrong-output'){JOINSCRIPT}else{OUTPUTDIR}
    $port=if($global:LauncherFixtureScenario -eq 'child-wrong-port'){'8767'}else{'8766'}
    $command='"'+BASEPYTHON+'" "'+$script+'" --port '+$port+' --config "'+$config+'" --output "'+$output+'"'
    return [pscustomobject]@{ProcessId=5252;ParentProcessId=$parent;ExecutablePath=$exe;CommandLine=$command}
}
function Start-Sleep { param($Milliseconds) }
$fixtureExit=0
try { & LAUNCHER -StartupTimeoutSeconds 1 }
catch { [Console]::Error.WriteLine($_.Exception.Message);$fixtureExit=1 }
@{requests=$global:LauncherFixtureRequests;launches=$global:LauncherFixtureLaunches;metadata_before_ready=$global:LauncherFixtureMetadataBeforeReady;
  blocked_environment_names=$global:LauncherFixtureBlockedNames} | ConvertTo-Json | Set-Content -LiteralPath SUMMARY -Encoding utf8
exit $fixtureExit
""".replace("SCENARIO", quote(scenario)).replace("CONFIG", quote(config))
                .replace("BASEPYTHON", quote(root / "base-python/python.exe"))
                .replace("WORKBENCHSCRIPT", quote(root / "workbench_server.py"))
                .replace("JOINSCRIPT", quote(root / "unrelated.py"))
                .replace("OUTPUTDIR", quote(root / "artifacts/high-score-workbench"))
                .replace("METADATA", quote(metadata)).replace("LAUNCHER", quote(root / "tools/start_workbench.ps1"))
                .replace("SUMMARY", quote(root / "summary.json")), encoding="utf-8")
            result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8-sig"))
            saved = json.loads(metadata.read_text(encoding="utf-8-sig")) if metadata.exists() else None
            self.assertEqual(summary["blocked_environment_names"], [])
            return result, summary, saved

    def test_existing_matching_config_reuses_without_new_process(self):
        result, summary, saved = self.run_fixture("existing-ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(summary["launches"], 0)
        self.assertEqual(saved, {"retain": "existing metadata"})

    def test_existing_stale_config_fails_without_process_or_metadata_changes(self):
        result, summary, saved = self.run_fixture("existing-stale")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Explicitly restart", result.stderr)
        self.assertEqual(summary["launches"], 0)
        self.assertEqual(saved, {"retain": "existing metadata"})

    def test_existing_disconnected_service_cannot_report_success(self):
        result, summary, saved = self.run_fixture("existing-unconnected")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(summary["launches"], 0)
        self.assertEqual(saved, {"retain": "existing metadata"})

    def test_new_process_waits_for_connected_hash_bound_state_before_metadata(self):
        result, summary, saved = self.run_fixture("new-ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(summary["launches"], 1)
        self.assertGreaterEqual(summary["requests"], 3)
        self.assertFalse(summary["metadata_before_ready"])
        self.assertEqual(saved["launcher_pid"], 4242)
        self.assertEqual(saved["runtime_pid"], 4242)
        self.assertEqual(len(saved["config_sha256"]), 64)
        self.assertIn("server-", saved["stderr"])

    def test_early_child_exit_retains_real_code_and_no_success_metadata(self):
        result, summary, saved = self.run_fixture("early-exit")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exited with code 17", result.stderr)
        self.assertEqual(summary["launches"], 1)
        self.assertIsNone(saved)

    def test_timeout_cannot_create_success_metadata(self):
        result, summary, saved = self.run_fixture("timeout")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not become connected", result.stderr)
        self.assertFalse(summary["metadata_before_ready"])
        self.assertIsNone(saved)

    def test_response_from_another_pid_cannot_report_new_process_ready(self):
        result, _, saved = self.run_fixture("wrong-pid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another process", result.stderr)
        self.assertIsNone(saved)

    def test_verified_venv_direct_child_can_become_runtime_and_records_both_pids(self):
        result, summary, saved = self.run_fixture("child-ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(summary["launches"], 1)
        self.assertEqual(saved["launcher_pid"], 4242)
        self.assertEqual(saved["runtime_pid"], 5252)

    def test_unrelated_child_or_wrong_workbench_arguments_cannot_report_ready(self):
        for field in ("parent", "exe", "script", "config", "output", "port"):
            with self.subTest(field=field):
                result, _, saved = self.run_fixture("child-wrong-" + field)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIsNone(saved)


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell 7 local entry")
class LocalStartupEntryTests(unittest.TestCase):
    def run_fixture(self, *, enable=False, reject_config=False, reject_host=False, nginx="default"):
        with fixture_directory() as directory:
            root = Path(directory)
            for folder in ("tools", "domains", "deploy", ".venv/Scripts",
                           ".venv-mcp-postgres/Scripts", "tools/runtime/pgsql/bin"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "deploy/local-up.ps1", root / "deploy/local-up.ps1")
            shutil.copyfile(sys.executable, root / ".venv/Scripts/python.exe")
            shutil.copyfile(Path(sys.prefix) / "pyvenv.cfg", root / ".venv/pyvenv.cfg")
            for name in (".venv-mcp-postgres/Scripts/postgres-mcp.exe", "tools/runtime/pgsql/bin/postgres.exe"):
                (root / name).write_bytes(b"fixture only")
            nginx_path = root / "tools/runtime" / ("nginx-1.30.6" if nginx == "default" else "nginx-fixture") / "nginx.exe"
            nginx_path.parent.mkdir(parents=True)
            if nginx != "configured-missing":
                nginx_path.write_bytes(b"fixture only")
            if nginx.startswith("configured"):
                (root / "deploy/native-runtime.json").write_text(json.dumps({"nginx_bin": str(nginx_path)}), encoding="utf-8")
            if reject_config:
                (root / "reject-config").touch()
            if reject_host:
                (root / "reject-host").touch()
            stub = """import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with (root/'events.jsonl').open('a',encoding='utf-8') as stream:
    stream.write(json.dumps({'stage':Path(__file__).stem,'args':sys.argv[1:]})+'\\n')
if Path(__file__).stem=='configure_local_coordinator' and '--check' in sys.argv and (root/'reject-config').exists():
    raise SystemExit(9)
if Path(__file__).stem=='workbench_host' and (root/'reject-host').exists():
    raise SystemExit(12)
if Path(__file__).stem=='download_native_runtime':
    nginx=root/'tools/runtime/nginx-1.30.6/nginx.exe'
    nginx.parent.mkdir(parents=True,exist_ok=True)
    nginx.write_bytes(b'fixture only')
"""
            for name in ("tools/configure_local_coordinator.py", "tools/prepare_native_database.py",
                         "tools/download_native_runtime.py", "domains/setup_local.py", "tools/workbench_host.py"):
                (root / name).write_text(stub, encoding="utf-8")
            events = root / "events.jsonl"
            for name, stage in (("deploy/native.ps1", "native"), ("tools/start_workbench.ps1", "legacy_workbench")):
                (root / name).write_text("Add-Content -LiteralPath " + quote(events)
                    + " -Value " + quote(json.dumps({"stage": stage})) + "\nexit 0\n", encoding="utf-8")
            command = [PWSH, "-NoProfile", "-NonInteractive", "-File", str(root / "deploy/local-up.ps1")]
            if enable:
                command.append("-EnableLocalModel")
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
            rows = [json.loads(line) for line in events.read_text(encoding="utf-8-sig").splitlines()] if events.exists() else []
            return result, rows

    def test_invalid_config_stops_before_any_resource_stage(self):
        result, rows = self.run_fixture(reject_config=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], "configure_local_coordinator")
        self.assertIn("--check", rows[0]["args"])
        self.assertNotIn("Local workbench: http://", result.stdout)

    def test_default_preserves_existing_model_selection_and_checks_first(self):
        result, rows = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["stage"] for row in rows], ["configure_local_coordinator", "prepare_native_database", "native",
            "setup_local", "configure_local_coordinator", "workbench_host"])
        self.assertEqual(rows[-1]["args"], ["--launch"])
        self.assertIn("Local workbench: http://127.0.0.1:8766", result.stdout)
        configuration = [row["args"] for row in rows if row["stage"] == "configure_local_coordinator"]
        self.assertIn("--check", configuration[0])
        self.assertNotIn("--check", configuration[1])
        self.assertFalse(any(flag in arguments for arguments in configuration
            for flag in ("--enable-llm", "--disable-llm", "--model-base-url", "--model")))

    def test_workbench_host_failure_cannot_report_success_url(self):
        result, rows = self.run_fixture(reject_host=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([row["stage"] for row in rows], ["configure_local_coordinator", "prepare_native_database", "native",
            "setup_local", "configure_local_coordinator", "workbench_host"])
        self.assertEqual(rows[-1]["args"], ["--launch"])
        self.assertIn("workbench_host.py", result.stderr)
        self.assertNotIn("Local workbench: http://", result.stdout)

    def test_local_model_requires_opt_in_and_uses_fixed_loopback_arguments(self):
        result, rows = self.run_fixture(enable=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        configuration = [row["args"] for row in rows if row["stage"] == "configure_local_coordinator"]
        self.assertEqual(len(configuration), 2)
        for arguments in configuration:
            self.assertIn("--enable-llm", arguments)
            self.assertEqual(arguments[arguments.index("--model-base-url")+1], "http://127.0.0.1:8089/v1")
            self.assertEqual(arguments[arguments.index("--model")+1], "Qwen3-1.7B-Q8_0")

    def test_unconfigured_other_nginx_requires_the_preparation_default(self):
        result, rows = self.run_fixture(nginx="other")
        self.assertEqual(result.returncode, 0, result.stderr)
        stages = [row["stage"] for row in rows]
        self.assertEqual(stages[1:3], ["download_native_runtime", "prepare_native_database"])
        self.assertEqual(stages.count("download_native_runtime"), 1)

    def test_explicit_existing_nginx_path_is_preserved(self):
        result, rows = self.run_fixture(nginx="configured")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("download_native_runtime", [row["stage"] for row in rows])
        self.assertIn("native", [row["stage"] for row in rows])

    def test_missing_explicit_nginx_stops_before_database_or_download(self):
        result, rows = self.run_fixture(nginx="configured-missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Configured nginx executable is missing", result.stderr)
        self.assertEqual([row["stage"] for row in rows], ["configure_local_coordinator"])


if __name__ == "__main__":
    unittest.main()
