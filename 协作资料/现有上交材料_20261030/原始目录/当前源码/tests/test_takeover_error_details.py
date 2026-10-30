"""Both transports preserve task failures and explicit replacement rejection details."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from incident.local_transport import LocalAipStdioTransport
from incident.wutong_transport import WutongTransport


class TakeoverErrorDetailsTests(unittest.IsolatedAsyncioTestCase):
    def payload(self, term):
        return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
                "kind": "act", "tool": "db.restore_writes", "operation_id": "operation", "args": {},
                "fence": {"coordinator_term": term, "takeover_version": 0}}

    async def exercise(self, mode, status):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            reason = "invalid handover conversation entry"
            initial = TimeoutError("primary unavailable")
            scope = {"database": "orders"}
            if mode == "wutong":
                config = {"leader": {"aic": "leader", "cert": "unused", "key": "unused"},
                          "term_journal_path": str(directory / "terms.sqlite")}
                with patch("incident.wutong_transport.AmpRuntime"):
                    transport = WutongTransport(config, directory / "transport")
                transport.selected = {"database": "primary"}
                transport.descriptions = {"database": {"resource_scope": scope}}
                transport.session = SimpleNamespace(session_id="session")
                transport.runtime = SimpleNamespace(force_remove_partner=AsyncMock())
                transport._discover_candidates = AsyncMock(return_value=[{"aic": "backup"}])
                transport._describe = AsyncMock(return_value={"executor_aic": "backup",
                    "resource_scope": scope, "tools": ["db.restore_writes"]})
                async def send(payload, target):
                    if target == "primary":
                        raise initial
                    return {"status": status, "reason": reason, "operation": None,
                            "active_fence": payload["fence"], "facts": []}
                transport._send = AsyncMock(side_effect=send)
            else:
                config = {"coordinator_aic": "leader", "term_journal_path": str(directory / "terms.sqlite")}
                transport = LocalAipStdioTransport(config, directory / "transport")
                primary = SimpleNamespace(spec={"role": "database", "aic": "primary", "name": "primary"},
                    state="ready", tools=["db.restore_writes"], resource_scope=scope, failure_reason=None)
                backup = SimpleNamespace(spec={"role": "database", "aic": "backup", "name": "backup"},
                    state="ready", tools=["db.restore_writes"], resource_scope=scope)
                transport.workers = {"primary": primary, "backup": backup}
                transport.started = True
                transport.active_workers = {"database": "primary"}
                async def call(worker, payload):
                    if worker is primary:
                        raise initial
                    if payload["kind"] == "describe":
                        return {"status": "ok", "description": {"executor_aic": "backup",
                            "resource_scope": scope, "tools": ["db.restore_writes"]}}
                    return {"status": status, "reason": reason, "operation": None,
                            "active_fence": payload["fence"], "facts": []}
                transport._call_worker = AsyncMock(side_effect=call)
            if status == "rejected":
                with self.assertRaises(TimeoutError) as caught:
                    await transport.call(self.payload(transport.term))
                self.assertIs(caught.exception, initial)
                self.assertEqual(initial.initial_error_class, "TimeoutError")
                self.assertEqual(initial.takeover_error_class, "RuntimeError")
                self.assertIn(reason, initial.takeover_reason)
                self.assertEqual(initial.takeover_rejection,
                                 {"candidate_aic": "backup", "status": "rejected", "reason": reason})
                self.assertEqual(transport.active_fences, {})
                self.assertIsInstance(initial.__cause__.__cause__, RuntimeError)
            else:
                result = await transport.call(self.payload(transport.term))
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["initial_error_class"], "TimeoutError")
                self.assertIsNone(result["takeover_error_class"])

    async def test_local_rejection_with_null_operation_preserves_reason(self):
        await self.exercise("local", "rejected")

    async def test_platform_rejection_with_null_operation_preserves_reason(self):
        await self.exercise("wutong", "rejected")

    async def test_local_unknown_null_operation_does_not_replay_modification(self):
        await self.exercise("local", "unknown")

    async def test_platform_unknown_null_operation_does_not_replay_modification(self):
        await self.exercise("wutong", "unknown")
