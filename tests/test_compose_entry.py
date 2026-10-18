"""Exercise the real PowerShell entry with a file-only WSL command substitute."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
if not PWSH and os.name == "nt":
    candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PowerShell/7/pwsh.exe"
    PWSH = str(candidate) if candidate.is_file() else None


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@contextmanager
def fixture_directory():
    base = ROOT / "artifacts/isolated-compose-h00-20261018/entry-fixtures"
    base.mkdir(parents=True, exist_ok=True)
    root = base / (uuid.uuid4().hex + " 中文 检出")
    root.mkdir()
    try:
        yield root
    finally:
        if root.resolve().parent != base.resolve() or root.is_symlink():
            raise AssertionError("Fixture cleanup escaped its artifact directory")
        shutil.rmtree(root)


def wsl_path(path):
    absolute = str(path.resolve())
    return "/mnt/" + absolute[0].lower() + absolute[2:].replace(chr(92), "/")


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell 7 Compose entry")
class ComposeEntryTests(unittest.TestCase):
    def run_fixture(self, *, agents=False, validate_only=False, config_exit=0):
        with fixture_directory() as root:
            deploy = root / "deploy"
            deploy.mkdir()
            shutil.copyfile(ROOT / "deploy/up.ps1", deploy / "up.ps1")
            env = root / "环境 配置.env"
            env.write_text("COMPOSE_PROFILES=\n", encoding="utf-8")
            for name in ("compose.yml", "agents.yml"):
                (deploy / name).write_text("# fixture only\n", encoding="utf-8")
            route = deploy / "nginx/runtime/route.conf"
            if not validate_only and not config_exit:
                route.parent.mkdir(parents=True)
                route.write_text("set $order_upstream app-v2:8000;\n", encoding="utf-8")
            log = root / "argv.jsonl"
            fake_wsl = root / "fake-wsl.ps1"
            fake_wsl.write_text(
                "$record=@{argv=@($args)} | ConvertTo-Json -Compress\n"
                "[IO.File]::AppendAllText(" + quote(log) + ", $record+[Environment]::NewLine, [Text.UTF8Encoding]::new($false))\n"
                "$global:LASTEXITCODE=" + str(config_exit) + "\n", encoding="utf-8")
            arguments = ["-EnvFile", quote(env), "-ProjectName", quote("incident-pilot-h00-fixture"),
                         "-WslDistro", quote("Fixture Ubuntu 中文")]
            if agents:
                arguments.append("-Agents")
            if validate_only:
                arguments.append("-ValidateOnly")
            wrapper = root / "wrapper.ps1"
            wrapper.write_text(
                "$ErrorActionPreference='Stop'\n"
                "function Get-Command {\n"
                " param([string]$Name,$ErrorAction)\n"
                " if($Name -eq 'docker'){return $null}\n"
                " if($Name -eq 'wsl.exe'){return [pscustomobject]@{Source=" + quote(fake_wsl) + "}}\n"
                " throw 'Unexpected command lookup'\n"
                "}\n"
                "try { & " + quote(deploy / "up.ps1") + " " + " ".join(arguments) + " }\n"
                "catch { [Console]::Error.WriteLine($_.Exception.Message);exit 1 }\n",
                encoding="utf-8")
            result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(wrapper)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            calls = [json.loads(line)["argv"] for line in log.read_text(encoding="utf-8").splitlines()]
            expected = ["-d", "Fixture Ubuntu 中文", "--exec", "docker", "compose", "-p",
                        "incident-pilot-h00-fixture", "--env-file", wsl_path(env), "-f", wsl_path(deploy / "compose.yml")]
            if agents:
                expected += ["-f", wsl_path(deploy / "agents.yml"), "--profile", "agents"]
            return result, calls, expected, route.exists()

    def test_validate_agents_preserves_three_unicode_spaced_wsl_paths(self):
        result, calls, expected, route_exists = self.run_fixture(agents=True, validate_only=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [expected + ["config", "--quiet"]])
        self.assertFalse(route_exists)
        self.assertTrue(all(chr(92) not in value for value in calls[0]))

    def test_default_business_up_has_no_agent_or_fault_profile(self):
        result, calls, expected, _ = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [expected + ["config", "--quiet"], expected + ["up", "-d", "--build", "--wait"]])
        self.assertFalse(any("--profile" in call for call in calls))
        self.assertNotIn("agents.yml", " ".join(calls[-1]))

    def test_config_failure_stops_before_route_or_up(self):
        result, calls, expected, route_exists = self.run_fixture(config_exit=9)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Compose configuration failed", result.stderr)
        self.assertEqual(calls, [expected + ["config", "--quiet"]])
        self.assertFalse(route_exists)


if __name__ == "__main__":
    unittest.main()
