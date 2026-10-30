import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.startup import prepare_tasks


class ManagedStartupTests(unittest.TestCase):
    def test_three_xml_tasks_are_templates_with_recovery_and_explicit_frequency(self):
        for minutes in (30, 10):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                schedule = root/"input-schedule.json"
                schedule.write_text(json.dumps(dict(directory=str(root/"state"), workbench_url="http://127.0.0.1:8877")))
                config = root/"input-host.json"
                config.write_text(json.dumps(dict(scheduler_config=str(schedule), schedule_directory=str(root/"state"),
                    control_directory=str(root/"control"), port=8877)))
                with patch("ops.startup.subprocess.Popen", side_effect=AssertionError("must not start")), \
                     patch("ops.startup.subprocess.run", side_effect=AssertionError("must not run")):
                    report = prepare_tasks(config, root/"output", user_sid="S-1-5-21-123", python=root/"pythonw.exe",
                                           inspect_minutes=minutes, template_only=True)
                self.assertEqual(report["inspect_interval_seconds"], minutes*60)
                self.assertFalse(report["tasks_registered"])
                self.assertFalse(report["processes_started"])
                self.assertEqual(len(report["tasks"]), 3)
                ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
                for file in report["tasks"]:
                    tree = ET.parse(file)
                    self.assertEqual(tree.findtext("t:Settings/t:RestartOnFailure/t:Interval", namespaces=ns), "PT1M")
                    self.assertEqual(tree.findtext("t:Settings/t:RestartOnFailure/t:Count", namespaces=ns), "5")
                    self.assertEqual(tree.findtext("t:Principals/t:Principal/t:LogonType", namespaces=ns), "InteractiveToken")
                    self.assertEqual(tree.findtext("t:Settings/t:MultipleInstancesPolicy", namespaces=ns), "IgnoreNew")
                    args = tree.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns)
                    self.assertNotIn("--enable-fault-drills", args)
                original = json.loads(schedule.read_text())
                self.assertNotIn("inspect_interval_seconds", original)
                generated = json.loads((root/"output/schedule.json").read_text())
                self.assertEqual(generated["longrun_control_directory"], str(root/"control"))


if __name__ == "__main__":
    unittest.main()
