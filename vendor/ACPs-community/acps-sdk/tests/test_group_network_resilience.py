"""Offline HTTP fault and cleanup-order regressions; no platform connections."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from acps_sdk.aip.aip_group_auth import GroupAclClient, GroupAclError
from acps_sdk.aip.aip_group_leader import (
    GroupCleanupError, GroupLeader, GroupLeaderMqClient, GroupLeaderSession, GroupLeaderState,
)
from acps_sdk.aip.aip_group_model import ACSObject


class AclRetryTests(unittest.IsolatedAsyncioTestCase):
    async def request_sequence(self, sequence, *, method="PUT"):
        requests = []
        def handle(request):
            requests.append(request)
            value = sequence[len(requests)-1]
            if isinstance(value, type) and issubclass(value, Exception):
                raise value("synthetic failure", request=request)
            return httpx.Response(value)
        client = GroupAclClient(base_url="https://acl.invalid", transport=httpx.MockTransport(handle))
        with patch("acps_sdk.aip.aip_group_auth.asyncio.sleep", new_callable=AsyncMock) as sleep, \
                patch("acps_sdk.aip.aip_group_auth.random.uniform", return_value=0):
            try:
                await client._request(method, "/groups/leader/group")
            except Exception as error:
                return requests, sleep, error
            finally:
                await client.aclose()
        return requests, sleep, None

    async def test_connect_timeouts_then_success(self):
        requests, sleep, error = await self.request_sequence([httpx.ConnectTimeout, httpx.ConnectTimeout, 200])
        self.assertIsNone(error)
        self.assertEqual(len(requests), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.5, 1])

    async def test_server_errors_then_success(self):
        requests, sleep, error = await self.request_sequence([503, 502, 204])
        self.assertIsNone(error)
        self.assertEqual(len(requests), 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_delete_missing_group_is_idempotent(self):
        requests, sleep, error = await self.request_sequence([404], method="DELETE")
        self.assertIsNone(error)
        self.assertEqual(len(requests), 1)
        sleep.assert_not_awaited()

    async def test_exhausted_transport_failure_is_wrapped_and_bounded(self):
        requests, sleep, error = await self.request_sequence([httpx.ConnectError] * 4)
        self.assertEqual(len(requests), 4)
        self.assertEqual(sleep.await_count, 3)
        self.assertIsInstance(error, GroupAclError)
        self.assertIsInstance(error.__cause__, httpx.ConnectError)
        self.assertEqual(error.attempts, 4)

    async def test_no_retry_for_client_error_protocol_failure_or_post(self):
        for sequence, method in (([403], "PUT"), ([httpx.RemoteProtocolError], "PUT"),
                                 ([httpx.ConnectTimeout], "POST")):
            with self.subTest(sequence=sequence, method=method):
                requests, sleep, error = await self.request_sequence(sequence, method=method)
                self.assertEqual(len(requests), 1)
                sleep.assert_not_awaited()
                self.assertIsInstance(error, GroupAclError)

    async def test_explicit_environment_and_phase_timeouts(self):
        with patch("acps_sdk.aip.aip_group_auth.httpx.AsyncClient") as factory:
            GroupAclClient(base_url="https://acl.invalid")
            options = factory.call_args.kwargs
            self.assertIs(options["trust_env"], False)
            self.assertEqual(options["timeout"].connect, 5)
            self.assertEqual(options["timeout"].read, 10)
            GroupAclClient(base_url="https://acl.invalid", trust_env=True, timeout=3)
            self.assertIs(factory.call_args.kwargs["trust_env"], True)
            self.assertEqual(factory.call_args.kwargs["timeout"], 3)
        for attempts in (0, 5, True):
            with self.assertRaises(ValueError):
                GroupAclClient(base_url="https://acl.invalid", max_attempts=attempts)


class GroupCleanupTests(unittest.IsolatedAsyncioTestCase):
    def leader(self):
        leader = GroupLeader("leader", {"host": "unused.invalid", "port": 5671, "vhost": "acps"})
        leader._group_acl_client = SimpleNamespace(delete_group=AsyncMock(), aclose=AsyncMock())
        return leader

    def session(self, leader):
        mq = GroupLeaderMqClient(leader_aic="leader")
        mq._state = GroupLeaderState.READY
        mq.broadcast_group_shutdown = AsyncMock()
        mq.cleanup_group_resources = AsyncMock()
        mq._channel = SimpleNamespace(is_closed=False, close=AsyncMock())
        session = GroupLeaderSession("session", "group-session", mq)
        leader.group_sessions["session"] = session
        return session, mq

    async def test_acl_network_failure_does_not_skip_mq_cleanup_or_claim_success(self):
        leader = self.leader()
        _, mq = self.session(leader)
        leader._group_acl_client.delete_group.side_effect = httpx.ConnectError("synthetic")
        with self.assertRaises(GroupCleanupError) as caught:
            await leader.dissolve_group_session("session")
        mq.cleanup_group_resources.assert_awaited_once()
        mq._channel.close.assert_awaited_once()
        self.assertEqual(caught.exception.acl_state, "unknown")
        self.assertEqual(caught.exception.resource_state, "removed")
        self.assertIn("session", leader.group_sessions)

    async def test_all_cleanup_phases_are_attempted_and_failures_retained(self):
        leader = self.leader()
        _, mq = self.session(leader)
        mq.broadcast_group_shutdown.side_effect = RuntimeError("notify")
        mq.cleanup_group_resources.side_effect = RuntimeError("resources")
        mq._channel.close.side_effect = RuntimeError("channel")
        with self.assertRaises(GroupCleanupError) as caught:
            await leader.dissolve_group_session("session")
        leader._group_acl_client.delete_group.assert_awaited_once()
        self.assertEqual(set(caught.exception.failures), {"notification", "resources", "channel"})
        self.assertEqual(caught.exception.acl_state, "removed")
        self.assertEqual(caught.exception.resource_state, "unknown")

    async def test_success_removes_session(self):
        leader = self.leader()
        self.session(leader)
        await leader.dissolve_group_session("session")
        self.assertEqual(leader.group_sessions, {})

    async def test_cleanup_retry_does_not_notify_through_closed_channel(self):
        leader = self.leader()
        _, mq = self.session(leader)
        leader._group_acl_client.delete_group.side_effect = [httpx.ConnectError("synthetic"), None]
        with self.assertRaises(GroupCleanupError) as caught:
            await leader.dissolve_group_session("session")
        self.assertEqual(caught.exception.acl_state, "unknown")
        mq._channel.is_closed = True
        await leader.dissolve_group_session("session")
        self.assertEqual(leader.group_sessions, {})
        self.assertEqual(mq.broadcast_group_shutdown.await_count, 1)
        self.assertEqual(mq.cleanup_group_resources.await_count, 2)
        # The first failure receipt remains truthful after subsequent cleanup.
        self.assertEqual(caught.exception.acl_state, "unknown")

    async def test_creation_rollback_preserves_original_and_unknown_acl(self):
        leader = self.leader()
        leader._ensure_connection = AsyncMock()
        leader._group_acl_client.add_member = AsyncMock()
        leader._group_acl_client.delete_group.side_effect = httpx.ConnectError("delete failed")
        mq = MagicMock()
        mq.connect = AsyncMock()
        original = RuntimeError("create failed")
        mq.create_group = AsyncMock(side_effect=original)
        mq.cleanup_group_resources = AsyncMock()
        mq._channel = SimpleNamespace(is_closed=False, close=AsyncMock())
        with patch("acps_sdk.aip.aip_group_leader.GroupLeaderMqClient", return_value=mq):
            with self.assertRaises(RuntimeError) as caught:
                await leader.create_group_session("session", [])
        self.assertIs(caught.exception, original)
        mq.create_group.assert_awaited_once()
        mq.cleanup_group_resources.assert_awaited_once()
        self.assertEqual(original.cleanup_error.acl_state, "unknown")
        self.assertIn("session", leader.group_sessions)

    async def test_resource_failure_keeps_names_and_attempts_both_deletions(self):
        mq = GroupLeaderMqClient(leader_aic="leader")
        mq._group_id = "owned-group"
        queue = SimpleNamespace(name="owned-queue")
        mq._leader_queue, mq._exchange_name = queue, "owned-exchange"
        mq._channel = SimpleNamespace(queue_delete=AsyncMock(side_effect=RuntimeError("queue")),
                                      exchange_delete=AsyncMock(side_effect=RuntimeError("exchange")))
        with self.assertRaises(GroupCleanupError) as caught:
            await mq.cleanup_group_resources()
        self.assertEqual(set(caught.exception.failures), {"queue", "exchange"})
        mq._channel.exchange_delete.assert_awaited_once()
        self.assertIs(mq._leader_queue, queue)
        self.assertEqual(mq._exchange_name, "owned-exchange")

    async def test_close_finishes_other_sessions_and_connections(self):
        leader = self.leader()
        leader.group_sessions = {"first": object(), "second": object()}
        leader.dissolve_group_session = AsyncMock(side_effect=[RuntimeError("first"), None])
        leader._connection = SimpleNamespace(is_closed=False, close=AsyncMock())
        leader._inbox_channel = SimpleNamespace(is_closed=False, close=AsyncMock())
        with self.assertRaises(GroupCleanupError):
            await leader.close()
        self.assertEqual(leader.dissolve_group_session.await_count, 2)
        leader._connection.close.assert_awaited_once()
        leader._inbox_channel.close.assert_awaited_once()
        leader._group_acl_client.aclose.assert_awaited_once()

    async def test_invite_rollback_retains_original_error_without_reinviting(self):
        leader = self.leader()
        session, mq = self.session(leader)
        leader._group_acl_client.add_member = AsyncMock()
        leader._group_acl_client.remove_member = AsyncMock(side_effect=httpx.ConnectError("remove failed"))
        original = RuntimeError("invitation unconfirmed")
        mq.invite_partner = AsyncMock(side_effect=original)
        with self.assertRaises(RuntimeError) as caught:
            await leader._invite_partner_via_rpc(session=session, partner_acs=ACSObject(aic="partner"),
                                                 rpc_url="https://unused.invalid/invite")
        self.assertIs(caught.exception, original)
        self.assertIsInstance(original.cleanup_error, httpx.ConnectError)
        mq.invite_partner.assert_awaited_once()
