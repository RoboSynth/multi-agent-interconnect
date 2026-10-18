import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.schedule import Scheduler


class ScheduleTests(unittest.IsolatedAsyncioTestCase):
    def configuration(self, directory):
        return {"directory": directory, "workbench_url": "http://127.0.0.1:8767", "poll_seconds": .001}

    async def test_lost_dispatch_reply_restores_lab_and_does_not_repost(self):
        posts = []
        def respond(request):
            if request.method == "POST":
                posts.append(json.loads(request.content))
                raise httpx.ReadTimeout("fixture", request=request)
            return httpx.Response(200, json={"connected": True, "mode": "wutong-amqps",
                "resource_credential_count": 0, "incidents": [], "incident": None})
        with tempfile.TemporaryDirectory() as directory:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                scheduler = Scheduler(self.configuration(directory), client=client, enable_fault_drills=True)
                scheduler.inject = AsyncMock()
                await scheduler.run_job("drill")
                self.assertEqual([call.args[0] for call in scheduler.inject.await_args_list], ["apply", "restore"])
                resumed = Scheduler(self.configuration(directory), client=client, enable_fault_drills=True)
                resumed.inject = AsyncMock()
                await resumed.run_job("drill")
                self.assertEqual(len(posts), 1)
                resumed.inject.assert_awaited_once_with("restore")

    async def test_inspection_never_approves_a_high_action(self):
        paths = []
        def respond(request):
            paths.append((request.method, request.url.path))
            if request.url.path == "/api/state":
                value = {"connected": True, "mode": "wutong-amqps", "resource_credential_count": 0,
                         "incidents": [], "incident": None}
            elif request.method == "POST":
                value = {"id": "incident"}
            else:
                value = {"status": "awaiting_approval", "approvals": [{"id": "high", "status": "pending",
                         "tool": "db.restore_writes", "args": {}}]}
            return httpx.Response(200, json=value)
        with tempfile.TemporaryDirectory() as directory:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                scheduler = Scheduler(self.configuration(directory), client=client)
                await scheduler.run_job("inspect")
                self.assertFalse(any(path.startswith("/api/approvals/") for _, path in paths))
                self.assertIsNotNone(scheduler.state["active"])

    async def test_local_transport_is_explicit_and_checked_before_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(self.configuration(directory), enable_fault_drills=True)
            scheduler.request = AsyncMock(return_value={"connected": True, "mode": "local-aip-stdio",
                "resource_credential_count": 0})
            scheduler.inject = AsyncMock()
            with self.assertRaises(ValueError):
                await scheduler.run_job("drill")
            scheduler.inject.assert_not_awaited()

    async def test_inspection_does_not_resume_or_restore_a_pending_drill(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(self.configuration(directory))
            active = {"id": "pending-drill", "kind": "drill", "symptom": "unknown prior drill"}
            scheduler.state["active"] = active
            scheduler.request = AsyncMock(return_value={"connected": True, "mode": "wutong-amqps",
                "resource_credential_count": 0})
            scheduler.inject = AsyncMock()
            await scheduler.run_job("inspect")
            scheduler.inject.assert_not_awaited()
            self.assertEqual(scheduler.request.await_count, 1)
            self.assertEqual(scheduler.state["active"], active)


if __name__ == "__main__":
    unittest.main()
