"""Reconciliation failure paths using local text fixtures; no collector starts."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy/fluent-bit/verify_collection.py"
spec = importlib.util.spec_from_file_location("collection_verification", SOURCE)
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


class CollectionReconciliationTests(unittest.TestCase):
    def test_batches_append_to_stable_files_and_create_distinct_new_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            output = Path(directory)
            for role in verification.fluent.COLLECTION_ROLES:
                (output / "inputs" / role).mkdir(parents=True)
                for batch in verification.BATCHES:
                    records = output / "records" / batch / role
                    records.mkdir(parents=True)
                    for kind in verification.fluent.KINDS:
                        (records / f"amp_{kind}_routing.jsonl").write_bytes((batch + "\n").encode())
            for batch in verification.BATCHES:
                verification.append_batch(output, batch)
            for role in verification.fluent.COLLECTION_ROLES:
                for kind in verification.fluent.KINDS:
                    files = output / "inputs" / role
                    self.assertEqual((files / f"amp_{kind}_routing.jsonl").read_bytes(),
                                     b"seed\nlive_append\noffline_append\n")
                    self.assertEqual((files / f"amp_{kind}_routing_2.jsonl").read_bytes(),
                                     b"live_new_file\noffline_existing\n")
                    self.assertEqual((files / f"amp_{kind}_routing_3.jsonl").read_bytes(), b"offline_new_file\n")
            with self.assertRaises(FileExistsError):
                verification.append_batch(output, "live_new_file")

    def readiness(self, members, *, exit_code=None):
        clock = [0.0]
        child = SimpleNamespace(pid=22, poll=lambda: exit_code)
        def sleep(seconds): clock[0] += seconds
        with patch.object(verification.os, "getpid", return_value=11), \
             patch.object(verification, "console_members", side_effect=members), \
             patch.object(verification.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(verification.time, "sleep", side_effect=sleep) as pauses:
            result = verification.wait_console_pair(None, child)
        return result, pauses.call_count

    def test_console_wait_allows_only_host_until_child_attaches(self):
        result, pauses = self.readiness([{11}, {11}, {11, 22}])
        self.assertTrue(result["ready"])
        self.assertEqual(result["initial_members"], [11])
        self.assertEqual([row["members"] for row in result["observations"]], [[11], [11], [11, 22]])
        self.assertEqual(pauses, 2)

    def test_console_wait_rejects_third_pid_or_early_exit_without_waiting(self):
        for members, exit_code, reason in (([{11, 33}], None, "unexpected_console_member"),
                                           ([{11}], 1, "child_exited")):
            with self.subTest(reason=reason):
                result, pauses = self.readiness(members, exit_code=exit_code)
                self.assertFalse(result["ready"])
                self.assertEqual(result["reason"], reason)
                self.assertEqual(pauses, 0)

    def test_console_wait_times_out_within_five_seconds(self):
        result, pauses = self.readiness(lambda unused: {11})
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "console_attachment_timeout")
        self.assertLessEqual(result["wait_seconds"], 5)
        self.assertGreater(pauses, 0)

    def test_rejects_duplicate_changed_unknown_and_incomplete_final_records(self):
        record = {"log_id": "synthetic-one", "body": {"retained": True}}
        expected = {record["log_id"]: {"record": record}}
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            phase = Path(directory)
            def output(records, ending="\n"):
                (phase / "stdout.log").write_text("\n".join(json.dumps(row) for row in records) + ending, encoding="utf-8")
            output([record])
            self.assertEqual(verification.observed(phase, expected, final=True), {"synthetic-one": 1})
            for records in ([record, record], [{**record, "body": {"retained": False}}], [{"log_id": "unknown"}]):
                output(records)
                with self.subTest(records=records), self.assertRaises(RuntimeError):
                    verification.observed(phase, expected, final=True)
            output([record], ending="")
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                verification.observed(phase, expected, final=True)

    def test_live_wait_rejects_old_phase_replay_before_claiming_completion(self):
        record = {"log_id": "old-phase", "body": {}}
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            phase = Path(directory)
            (phase / "stdout.log").write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "replay"):
                verification.wait_records(phase, {"old-phase": {"record": record}}, {"new-phase"})


if __name__ == "__main__":
    unittest.main()
