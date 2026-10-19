"""Participant cleanup failure must reach the managed consumer's exit path."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

import httpx

from acps_sdk.aip.aip_group_partner import GroupPartnerMqClient, PartnerCleanupError, PartnerGroupState


class PartnerCleanupFailureTests(unittest.IsolatedAsyncioTestCase):
    def client(self, *, owns_connection):
        connection = SimpleNamespace(is_closed=False, close=AsyncMock())
        client = GroupPartnerMqClient("partner", connection=connection, connection_owner=owns_connection)
        client._state = PartnerGroupState.JOINED
        client._group_id, client._queue_name, client._consumer_tag = "owned-group", "owned-queue", "consumer-tag"
        client._queue = SimpleNamespace(name="owned-queue", cancel=AsyncMock(), delete=AsyncMock())
        client._channel = SimpleNamespace(is_closed=False, close=AsyncMock())
        client._inbox_channel = SimpleNamespace(is_closed=False, close=AsyncMock())
        client._exchange = MagicMock()  # Borrowed leader exchange must never be deleted.
        client._publish_message = AsyncMock()
        client.send_status_result = AsyncMock()
        client._disconnect_handler = AsyncMock()
        async def connection_closed():
            connection.is_closed = True
        connection.close.side_effect = connection_closed
        return client, connection

    async def test_queue_delete_connect_error_still_closes_owned_resources_and_raises(self):
        client, connection = self.client(owns_connection=True)
        queue = client._queue
        queue.delete.side_effect = httpx.ConnectError("synthetic queue delete failure")
        client._channel.close.side_effect = RuntimeError("synthetic channel close failure")
        with self.assertRaises(PartnerCleanupError) as caught:
            await client.close()
        group_error = caught.exception.failures["group"]
        self.assertIsInstance(group_error, PartnerCleanupError)
        self.assertEqual(set(group_error.failures), {"queue_delete", "channel"})
        self.assertIsInstance(group_error.failures["queue_delete"], httpx.ConnectError)
        self.assertEqual(caught.exception.queue_state, "unknown")
        self.assertEqual(caught.exception.queue_name, "owned-queue")
        self.assertEqual(client._group_id, "owned-group")
        self.assertIs(client._queue, queue)
        client._inbox_channel.close.assert_awaited_once()
        connection.close.assert_awaited_once()
        client._exchange.delete.assert_not_called()
        client._disconnect_handler.assert_not_awaited()

    async def test_cancel_failure_keeps_consumer_reference_and_does_not_close_borrowed_connection(self):
        client, connection = self.client(owns_connection=False)
        queue = client._queue
        queue.cancel.side_effect = RuntimeError("synthetic consumer cancel failure")
        with self.assertRaises(PartnerCleanupError) as caught:
            await client.close()
        self.assertEqual(caught.exception.consumer_state, "unknown")
        self.assertEqual(caught.exception.queue_state, "removed")
        self.assertEqual(client._consumer_tag, "consumer-tag")
        self.assertEqual(client.state, PartnerGroupState.LEAVING)
        self.assertIs(client._queue, queue)
        queue.delete.assert_awaited_once()
        client._inbox_channel.close.assert_awaited_once()
        connection.close.assert_not_awaited()
        client._exchange.delete.assert_not_called()
        client._disconnect_handler.assert_not_awaited()

    async def test_leave_deletes_queue_before_disconnected_status_revokes_permission(self):
        for requested in (False, True):
            with self.subTest(requested=requested):
                client, _ = self.client(owns_connection=True)
                queue = client._queue
                events = []
                allowed = True

                async def delete(**kwargs):
                    self.assertTrue(allowed, "leader revoked ACL before queue deletion")
                    events.append("queue_deleted")

                async def disconnected(**kwargs):
                    nonlocal allowed
                    self.assertFalse(kwargs["connected"])
                    self.assertEqual(events, ["queue_deleted"])
                    events.append("disconnected")
                    allowed = False

                queue.delete.side_effect = delete
                client.send_status_result.side_effect = disconnected
                if requested:
                    client._pending_leave_session_id = "requested-session"
                    await client._handle_leave_request()
                    self.assertIsNone(client._pending_leave_session_id)
                else:
                    await client.leave_group(session_id="active-session")
                self.assertEqual(events, ["queue_deleted", "disconnected"])
                self.assertEqual(client.state, PartnerGroupState.DISCONNECTED)
                client._disconnect_handler.assert_awaited_once()

    async def test_queue_failure_never_reports_disconnected_on_either_leave_path(self):
        for requested in (False, True):
            with self.subTest(requested=requested):
                client, connection = self.client(owns_connection=True)
                client._queue.delete.side_effect = PermissionError("synthetic access refused")
                with self.assertRaises(PartnerCleanupError) as caught:
                    if requested:
                        await client._handle_leave_request()
                    else:
                        await client.leave_group()
                self.assertIn("queue_delete", caught.exception.failures)
                client.send_status_result.assert_not_awaited()
                client._publish_message.assert_not_awaited()
                connection.close.assert_awaited_once()
                self.assertEqual(client.state, PartnerGroupState.LEAVING)

    async def test_notification_failure_still_closes_resources_and_remains_a_failure(self):
        client, connection = self.client(owns_connection=True)
        client.send_status_result.side_effect = RuntimeError("synthetic publish failure")
        with self.assertRaises(PartnerCleanupError) as caught:
            await client._handle_leave_request()
        self.assertEqual(set(caught.exception.failures), {"leave_notification"})
        self.assertEqual(caught.exception.queue_state, "removed")
        connection.close.assert_awaited_once()
        client._disconnect_handler.assert_not_awaited()
