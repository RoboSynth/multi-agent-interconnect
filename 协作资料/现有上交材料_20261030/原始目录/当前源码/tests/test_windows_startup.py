"""Offline Windows task configuration and real OS scheduler-lock checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.schedule import ScheduleLock


class ScheduleProcessLockTests(unittest.TestCase):
    def test_another_process_is_rejected_and_release_allows_a_new_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            ready = Path(directory) / "ready"
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"directory": str(state), "workbench_url": "http://127.0.0.1:1"}))
            holder_code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ops.schedule import ScheduleLock
with ScheduleLock(sys.argv[2]):
    Path(sys.argv[3]).write_text('locked')
    sys.stdin.readline()
print('released', flush=True)
"""
            holder = subprocess.Popen([sys.executable, "-B", "-u", "-c", holder_code, str(ROOT), str(state), str(ready)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 15
                while not ready.exists() and holder.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(ready.exists(), "lock-holder process did not become ready")
                rejected = subprocess.run([sys.executable, "-B", str(ROOT / "ops/schedule.py"), "--config", str(config)],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(rejected.returncode, 2, rejected.stderr)
                rejection = json.loads(rejected.stderr)
                self.assertEqual(rejection["status"], "already_running")
                self.assertEqual(rejection["resource_calls_performed"], 0)
                stdout, stderr = holder.communicate("\n", timeout=15)
                self.assertEqual(holder.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), "released")
                probe = "import sys;sys.path.insert(0,sys.argv[1]);from ops.schedule import ScheduleLock\nwith ScheduleLock(sys.argv[2]): print('acquired')"
                acquired = subprocess.run([sys.executable, "-B", "-c", probe, str(ROOT), str(state)],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(acquired.returncode, 0, acquired.stderr)
                self.assertEqual(acquired.stdout.strip(), "acquired")
            finally:
                if holder.poll() is None:
                    holder.communicate("\n", timeout=15)

    def test_exception_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with ScheduleLock(directory):
                    raise RuntimeError("fixture")
            with ScheduleLock(directory):
                pass


@unittest.skipUnless(os.name == "nt", "Windows task configuration")
class WindowsStartupConfigurationTests(unittest.TestCase):
    def prepare(self, output, *, what_if=False, config=None):
        def quoted(value): return "'" + str(value).replace("'", "''") + "'"
        # These guards fail if configuration preparation tries to use the task
        # service or launch a scheduler. WhatIf must also avoid those actions.
        guards = "\n".join("function " + name + " { throw 'unexpected task service or process action' }"
            for name in ("Get-ScheduledTask", "Register-ScheduledTask", "Unregister-ScheduledTask", "Start-Process"))
        command = guards + "\n& " + quoted(ROOT / "ops/install_startup.ps1") + " -OutputDirectory " + quoted(output)
        if config is not None:
            command += " -ConfigPath " + quoted(config)
        if what_if:
            command += " -Register -WhatIf"
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        # Process-scoped policy only; a Restricted machine policy would otherwise block the script.
        return subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

    def test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task(self):
        for what_if in (False, True):
            with self.subTest(what_if=what_if), tempfile.TemporaryDirectory() as directory:
                result = self.prepare(directory, what_if=what_if)
                self.assertEqual(result.returncode, 0, result.stderr)
                summary = json.loads((Path(directory) / "startup-plan.json").read_text(encoding="utf-8-sig"))
                self.assertEqual(summary["status"], "prepared_only")
                self.assertFalse(summary["fault_drills_enabled"])
                self.assertFalse(summary["high_auto_approval"])
                self.assertFalse(summary["task_started"])
                self.assertFalse(summary["resource_services_started"])
                self.assertFalse(summary["network_attempted"])
                task = ET.parse(Path(directory) / "inspect-task.xml")
                ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
                self.assertEqual(task.findtext("t:Settings/t:MultipleInstancesPolicy", namespaces=ns), "IgnoreNew")
                self.assertEqual(task.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=ns), "PT0S")
                self.assertEqual(task.findtext("t:Settings/t:Hidden", namespaces=ns), "true")
                self.assertEqual(task.findtext("t:Principals/t:Principal/t:LogonType", namespaces=ns), "InteractiveToken")
                self.assertEqual(task.findtext("t:Principals/t:Principal/t:RunLevel", namespaces=ns), "LeastPrivilege")
                self.assertEqual(task.findtext("t:Triggers/t:LogonTrigger/t:UserId", namespaces=ns), summary["user_sid"])
                self.assertEqual(task.findtext("t:Principals/t:Principal/t:UserId", namespaces=ns), summary["user_sid"])
                arguments = task.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns)
                self.assertIn('-WindowStyle Hidden -File "' + str(ROOT / "ops/run_startup.ps1") + '"', arguments)
                self.assertNotIn("--enable-fault-drills", arguments)
                self.assertNotIn("--allow-local", arguments)
                self.assertNotIn("password", arguments.lower())
                self.assertNotIn("token", arguments.lower())

    def test_invalid_scheduler_config_is_rejected_without_task_service_or_processes(self):
        for invalid in ({"workbench_url": "https://example.com", "directory": "state"},
                        {"workbench_url": "http://127.0.0.1:8767", "directory": "state", "inspect_interval_seconds": 1}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.json"
                config.write_text(json.dumps(invalid))
                result = self.prepare(Path(directory) / "output", config=config)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((Path(directory) / "output/inspect-task.xml").exists())


if __name__ == "__main__":
    unittest.main()
