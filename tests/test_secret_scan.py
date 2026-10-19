"""Log release checks reject malformed or unreadable inputs without echoing data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eval.secret_scan import scan


class SecretScanTests(unittest.TestCase):
    def test_valid_logs_are_parsed_and_overlapping_paths_count_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "amp_access.jsonl"
            log.write_text('{"correlation_id":"task-1"}\n\n{"body":{"method":"start"}}\n', encoding="utf-8")
            report = scan([root, log])
            self.assertTrue(report["machine_checks_passed"])
            self.assertEqual(report["scanned_files"], 1)
            self.assertEqual(report["json_records"], 2)
            self.assertEqual(report["parse_errors"], 0)

    def test_malformed_json_and_jsonl_are_not_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"unfinished":', encoding="utf-8")
            (root / "amp_system.jsonl").write_text('{"event":"ok"}\n{"unfinished":', encoding="utf-8")
            report = scan([root])
            self.assertFalse(report["machine_checks_passed"])
            self.assertEqual(report["hits"], 0)
            self.assertEqual(report["parse_errors"], 2)
            self.assertEqual({row["line"] for row in report["parse_findings"]}, {1, 2})

    def test_secret_findings_expose_locations_only_even_in_invalid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "amp_system.jsonl"
            secret = "synthetic-private-value"
            log.write_text('DATABASE_URL=postgresql://test:fixture@localhost/db\n' + secret, encoding="utf-8")
            report = scan([log], known_secrets=[secret])
            self.assertGreater(report["hits"], 0)
            self.assertFalse(report["machine_checks_passed"])
            self.assertNotIn(secret, json.dumps(report))
            self.assertNotIn("test:fixture", json.dumps(report))

    def test_missing_invalid_encoding_and_empty_inputs_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for inputs in ([], [root], [root / "missing.jsonl"]):
                with self.subTest(inputs=inputs):
                    self.assertFalse(scan(inputs)["machine_checks_passed"])
            (root / "amp_system.jsonl").write_bytes(b'\xff')
            report = scan([root])
            self.assertFalse(report["machine_checks_passed"])
            self.assertEqual(report["read_errors"], 1)

    def test_cli_rejects_malformed_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "amp_access.jsonl"
            log.write_text('{"unfinished":', encoding="utf-8")
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "eval/secret_scan.py"), str(log)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(completed.stdout)["parse_errors"], 1)


if __name__ == "__main__":
    unittest.main()
