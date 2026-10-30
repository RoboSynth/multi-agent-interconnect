"""New batch orchestration retains failures and requires full cleanup evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval.platform_batch import CLOSE_CHECKS, REMOTE_CHECKS, run_batch


def result():
    return {"status": "completed", "resource_and_worker_restore": "completed",
            "close_checks": {key: True for key in CLOSE_CHECKS},
            "independent_final_H00": {"passed": True, "duration_seconds": 30, "completed_workflows": 10,
                "failed": 0, "unknown": 0, "unresolved_intents": 0, "state": {"pending": []}}}


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_close_failure_is_retained_and_third_runs_after_confirmed_owned_cleanup(self):
        cases = [{"key": key} for key in ("first", "second", "third")]
        results = [result(), result(), result()]
        results[1].update(status="failed", close_error_class="GroupAclError")
        original = deepcopy(results[1])
        execute = AsyncMock(side_effect=results)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"

            async def cleanup(case, failed):
                saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["cases"][-1]["key"], "second")
                self.assertEqual(saved["cases"][-1]["result"], original)
                return {key: True for key in REMOTE_CHECKS}

            report = await run_batch(cases, output, run_case=execute, cleanup_owned=cleanup)
            self.assertEqual(execute.await_count, 3)
            self.assertEqual(report["status"], "finished_with_failures")
            self.assertEqual(report["cases"][1]["result"], original)
            self.assertTrue(report["cases"][1]["safe_to_continue"])
            self.assertEqual(report["unattempted"], [])

    async def test_healthy_business_does_not_override_unknown_acl(self):
        failed = result()
        failed.update(status="failed", close_error_class="GroupAclError")
        cleanup = AsyncMock(return_value={**{key: True for key in REMOTE_CHECKS}, "acl_removed": None})
        execute = AsyncMock(return_value=failed)
        isolated = []
        with tempfile.TemporaryDirectory() as directory:
            report = await run_batch([{"key": "one"}, {"key": "two"}], Path(directory) / "batch",
                run_case=execute, cleanup_owned=cleanup, quarantine=lambda case, _: isolated.append(case["key"]))
            self.assertEqual(execute.await_count, 1)
            self.assertEqual(report["unattempted"], ["two"])
            self.assertEqual(report["quarantined_cases"], ["one"])
            self.assertEqual(isolated, ["one"])
            self.assertEqual(report["status"], "blocked_cleanup_or_restore")

    async def test_launcher_exception_receipt_is_written_even_if_quarantine_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"

            def quarantine(*_):
                raise OSError("local fixture")

            report = await run_batch([{"key": "one"}, {"key": "two"}], output,
                run_case=AsyncMock(side_effect=TimeoutError()), quarantine=quarantine)
            saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            self.assertEqual(saved["cases"][0]["launcher_error_class"], "TimeoutError")
            self.assertEqual(saved["cases"][0]["quarantine_error_class"], "OSError")
            self.assertEqual(saved["unattempted"], ["two"])


if __name__ == "__main__":
    unittest.main()
