"""A leased batch returns identities only after every case is fully cleaned up."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval.leased_batch import cleanup_receipt, run_leased_batch
from eval.platform_batch import CLOSE_CHECKS
from ops.aic_lease import AicLease, LeaseBusy, LeaseQuarantined, load, save


def result(**changes):
    value = {"status": "completed", "resource_and_worker_restore": "completed",
             "close_checks": {key: True for key in CLOSE_CHECKS},
             "independent_final_H00": {"passed": True, "duration_seconds": 30, "completed_workflows": 10,
                 "failed": 0, "unknown": 0, "unresolved_intents": 0, "state": {"pending": []}}}
    value.update(changes)
    return value


class LeasedBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_clean_batch_pauses_inspection_and_resumes_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            leases, control = Path(temporary) / "leases", Path(temporary) / "control"
            holder = AicLease(["a", "b"], purpose="longrun", directory=leases).acquire()
            save(control / "host.json", dict(status="running", session_id="host", aics=["a", "b"]))

            async def host():
                while not (control / "handoff-request.json").exists():
                    await asyncio.sleep(.001)
                request = load(control / "handoff-request.json")
                holder.release()
                save(control / "host.json", dict(status="paused", session_id="host", aics=["a", "b"],
                     request_id=request["request_id"], consumers_closed=True, lease_released=True))

            async def run_case(case):
                with self.assertRaises(LeaseBusy):
                    AicLease(["a"], purpose="concurrent", directory=leases).acquire()
                return result(status="failed" if case["key"] == "second" else "completed")

            task = asyncio.create_task(host())
            report = await run_leased_batch([{"key": "first"}, {"key": "second"}], Path(temporary) / "batch",
                aics=["a", "b"], purpose="p4-revalidation", run_case=run_case, control_directory=control,
                lease_directory=leases, handoff_timeout=2, poll_seconds=.001)
            await task
            self.assertEqual(report["status"], "finished_with_failures")
            self.assertEqual(report["lease"]["after_batch"], "resume_inspection")
            self.assertEqual(load(control / "handoff-result.json")["action"], "resume")
            with AicLease(["a", "b"], purpose="inspection-resumed", directory=leases):
                pass

    async def test_unconfirmed_cleanup_quarantines_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            leases = Path(temporary) / "leases"
            execute = AsyncMock(side_effect=[result(close_error_class="GroupAclError"), result()])
            report = await run_leased_batch([{"key": "first"}, {"key": "second"}], Path(temporary) / "batch",
                aics=["a"], purpose="p4-revalidation", run_case=execute, lease_directory=leases)
            self.assertEqual(execute.await_count, 1)
            self.assertEqual(report["status"], "blocked_cleanup_or_restore")
            self.assertEqual(report["lease"]["after_batch"], "quarantine_for_manual_check")
            with self.assertRaises(LeaseQuarantined):
                AicLease(["a"], purpose="inspection", directory=leases).acquire()

    async def test_launcher_exception_never_returns_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            leases = Path(temporary) / "leases"
            report = await run_leased_batch([{"key": "only"}], Path(temporary) / "batch", aics=["a"],
                purpose="p4", run_case=AsyncMock(side_effect=RuntimeError("boom")), lease_directory=leases)
            self.assertEqual(report["cases"][0]["launcher_error_class"], "RuntimeError")
            self.assertFalse(report["lease"]["identities_returned"])
            with self.assertRaises(LeaseQuarantined):
                AicLease(["a"], purpose="inspection", directory=leases).acquire()

    async def test_cancelled_case_is_recorded_and_quarantined_before_host_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            leases, control = Path(temporary) / "leases", Path(temporary) / "control"
            output = Path(temporary) / "batch"
            holder = AicLease(["a"], purpose="longrun", directory=leases).acquire()
            save(control / "host.json", dict(status="running", session_id="host", aics=["a"]))
            started = asyncio.Event()

            async def host():
                while not (control / "handoff-request.json").exists():
                    await asyncio.sleep(.001)
                request = load(control / "handoff-request.json")
                holder.release()
                save(control / "host.json", dict(status="paused", session_id="host", aics=["a"],
                     request_id=request["request_id"], consumers_closed=True, lease_released=True))

            async def run_case(case):
                started.set()
                await asyncio.Future()

            host_task = asyncio.create_task(host())
            batch_task = asyncio.create_task(run_leased_batch([{"key": "first"}, {"key": "second"}],
                output, aics=["a"], purpose="p4", run_case=run_case, control_directory=control,
                lease_directory=leases, handoff_timeout=2, poll_seconds=.001))
            await asyncio.wait_for(started.wait(), timeout=2)
            batch_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await batch_task
            await host_task
            report = load(output / "summary.json")
            self.assertEqual(report["cases"][0]["launcher_error_class"], "CancelledError")
            self.assertEqual(report["status"], "blocked_cleanup_or_restore")
            self.assertEqual(report["unattempted"], ["second"])
            self.assertEqual(load(control / "handoff-result.json")["action"], "quarantine")
            # A quarantined error, rather than Busy, also proves the OS lock was released.
            with self.assertRaises(LeaseQuarantined):
                AicLease(["a"], purpose="inspection", directory=leases).acquire()

    def test_receipt_requires_every_case_safe(self):
        rows = [{"key": "a", "safe_to_continue": True}, {"key": "b", "safe_to_continue": True}]
        self.assertIsNotNone(cleanup_receipt({"status": "completed", "cases": rows, "unattempted": [],
                                              "quarantined_cases": []}))
        for report in ({"status": "completed", "cases": [], "unattempted": [], "quarantined_cases": []},
                       {"status": "completed", "cases": rows, "unattempted": ["c"], "quarantined_cases": []},
                       {"status": "blocked_cleanup_or_restore", "cases": rows, "unattempted": [],
                        "quarantined_cases": ["b"]},
                       {"status": "completed", "cases": rows[:1] + [{"key": "b", "safe_to_continue": False}],
                        "unattempted": [], "quarantined_cases": []}):
            self.assertIsNone(cleanup_receipt(report))


if __name__ == "__main__":
    unittest.main()
