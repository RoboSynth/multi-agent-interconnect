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
