"""E1-c defers only one owned primary removal and restores the normal method."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.platform_e1c_transport import DeferredPrimaryRemoval


class DeferredRemovalTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        original = AsyncMock()
        transport = SimpleNamespace(runtime=SimpleNamespace(force_remove_partner=original),
            session=SimpleNamespace(session_id="owned-group"), selected={"database": "backup"})
        return transport, original, DeferredPrimaryRemoval(transport, "primary", "backup")

    async def test_retains_old_handler_until_flush_and_then_uses_original_removal(self):
        transport, original, adapter = self.adapter()
        await transport.runtime.force_remove_partner("primary", session_id="owned-group")
        original.assert_not_awaited()
        self.assertTrue(adapter.pending)
        report = await adapter.flush()
        original.assert_awaited_once_with("primary", session_id="owned-group")
        self.assertIs(transport.runtime.force_remove_partner, original)
        self.assertEqual(report["completed_removals"], 1)
        with self.assertRaises(ValueError): await adapter.flush()

    async def test_foreign_session_unconfirmed_backup_and_double_deferral_refused(self):
        transport, original, adapter = self.adapter()
        with self.assertRaises(ValueError): await adapter.defer("primary", session_id="foreign-group")
        transport.selected["database"] = "primary"
        with self.assertRaises(ValueError): await adapter.defer("primary", session_id="owned-group")
        transport.selected["database"] = "backup"
        await adapter.defer("primary", session_id="owned-group")
        with self.assertRaises(ValueError): await adapter.defer("primary", session_id="owned-group")
        original.assert_not_awaited()
        adapter.detach()
        self.assertIs(transport.runtime.force_remove_partner, original)

    async def test_other_members_follow_normal_sdk_and_removal_failure_is_not_success(self):
        transport, original, adapter = self.adapter()
        await adapter.defer("other-member", session_id="owned-group")
        original.assert_awaited_once_with("other-member", session_id="owned-group")
        await adapter.defer("primary", session_id="owned-group")
        original.side_effect = RuntimeError("synthetic channel close failure")
        with self.assertRaises(RuntimeError): await adapter.flush()
        self.assertEqual(adapter.removed_count, 0)
        self.assertTrue(adapter.pending)
        adapter.detach()
        self.assertIs(transport.runtime.force_remove_partner, original)


if __name__ == "__main__":
    unittest.main()
