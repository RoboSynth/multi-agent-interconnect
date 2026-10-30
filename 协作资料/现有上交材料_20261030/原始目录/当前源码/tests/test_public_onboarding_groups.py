"""Public metadata groups coexist without widening private resource admission."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from incident.platform_worker import DomainGroupRuntime
from integration import wutong_smoke as native

SERVICE = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JU5"
INTERNAL = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
EXTERNAL = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"


class Partner:
    group_id = None
    is_joined = False

    def set_command_handler(self, handler):
        self.handler = handler

    def set_disconnect_handler(self, handler):
        self.disconnected = handler

    async def join_group_from_invitation(self, invitation):
        self.group_id, self.is_joined = invitation.groupId, True
        self._group_info = invitation.group
        return True

    async def send_status_result(self, **kwargs):
        pass

    async def close(self):
        self.is_joined = False
        self.disconnected(self, self.group_id)


class PublicGroupsTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self, public):
        adapter = SimpleNamespace(bind_partner=lambda client: AsyncMock())
        runtime = DomainGroupRuntime(bridge=adapter, leader_aic=SERVICE,
            allowed_leaders=[INTERNAL], public_metadata_service=public,
            record=lambda *a, **k: None,
            rabbitmq_config={"host": "localhost", "port": 5671, "vhost": "/"})
        runtime._partner_client = Partner
        runtime._reject_invitation = AsyncMock()
        return runtime

    def invitation(self, group_id, leader=EXTERNAL):
        return SimpleNamespace(groupId=group_id,
            expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            group=SimpleNamespace(leader=SimpleNamespace(aic=leader),
                                  partners=[SimpleNamespace(aic=SERVICE)]),
            amqp=SimpleNamespace(exchange=native.build_group_exchange_name(leader, group_id)))

    async def test_public_internal_and_external_groups_coexist_with_bounded_capacity(self):
        runtime = self.runtime(True)
        for index in range(4):
            await runtime._accept_probe_invitation(self.invitation(f"group-{index}", INTERNAL if index == 0 else EXTERNAL))
        self.assertEqual(len(runtime._inbound_groups), 4)
        self.assertEqual(set(runtime.bridge_handlers), set(runtime._inbound_groups))
        await runtime._accept_probe_invitation(self.invitation("group-0", INTERNAL))
        runtime._reject_invitation.assert_not_awaited()
        await runtime._accept_probe_invitation(self.invitation("overflow"))
        runtime._reject_invitation.assert_awaited_once()
        self.assertNotIn("overflow", runtime._inbound_groups)
        await runtime._inbound_groups["group-1"].close()
        self.assertNotIn("group-1", runtime.bridge_handlers)
        await runtime._accept_probe_invitation(self.invitation("replacement"))
        self.assertIn("replacement", runtime._inbound_groups)
        self.assertEqual(len(runtime._inbound_groups), 4)

    async def test_private_domain_retains_allowlist_and_one_group(self):
        runtime = self.runtime(False)
        await runtime._accept_probe_invitation(self.invitation("external"))
        self.assertFalse(runtime._inbound_groups)
        await runtime._accept_probe_invitation(self.invitation("internal", INTERNAL))
        await runtime._accept_probe_invitation(self.invitation("second", INTERNAL))
        self.assertEqual(set(runtime._inbound_groups), {"internal"})
        self.assertEqual(runtime._reject_invitation.await_count, 2)

    async def test_different_leader_cannot_adopt_existing_group_id(self):
        runtime = self.runtime(True)
        await runtime._accept_probe_invitation(self.invitation("internal", INTERNAL))
        original = runtime._inbound_groups["internal"]
        await runtime._accept_probe_invitation(self.invitation("internal", EXTERNAL))
        runtime._reject_invitation.assert_awaited_once()
        self.assertIs(runtime._inbound_groups["internal"], original)
        self.assertEqual(original._group_info.leader.aic, INTERNAL)

    async def test_public_mode_retains_exchange_identity_check(self):
        runtime = self.runtime(True)
        invitation = self.invitation("external")
        invitation.amqp.exchange = native.build_group_exchange_name(INTERNAL, "external")
        await runtime._accept_probe_invitation(invitation)
        runtime._reject_invitation.assert_awaited_once()
        self.assertFalse(runtime._inbound_groups)


if __name__ == "__main__":
    unittest.main()
