"""Platform taskId pairing at message and access instrumentation boundaries."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from acps_sdk.amp._message_tap import _message_correlation
from acps_sdk.amp.group_access import GroupAccessMiddleware


class CorrelationTests(unittest.IsolatedAsyncioTestCase):
    def test_task_and_management_correlations(self):
        for kind in ("task-command", "task-result"):
            self.assertEqual(_message_correlation({"type": kind, "sessionId": "session", "taskId": "task"}), "task")
            self.assertIsNone(_message_correlation({"type": kind, "sessionId": "session"}))
        self.assertEqual(_message_correlation({"type": "group-mgmt-command", "sessionId": "session", "taskId": "task"}), "session")

    async def test_single_recipient_access_has_matching_identity_and_task(self):
        sender, receiver = SimpleNamespace(emit=AsyncMock()), SimpleNamespace(emit=AsyncMock())
        command = SimpleNamespace(command="start", sessionId="session", taskId="task", groupId="group",
                                  mentions=["worker"], senderId="leader", commandParams={"tool": "db.health"})
        await GroupAccessMiddleware(sender, "leader").run(command, AsyncMock(return_value={"status": "ok"}), direction="send")
        await GroupAccessMiddleware(receiver, "worker").run(command, AsyncMock(return_value={"status": "ok"}))
        for emitted in (sender.emit.call_args, receiver.emit.call_args):
            self.assertEqual(emitted.kwargs["correlation_id"], "task")
            self.assertEqual(emitted.args[0].caller.aic, "leader")
            self.assertEqual(emitted.args[0].callee.aic, "worker")

    async def test_broadcast_start_warns_about_unpairable_access(self):
        command = SimpleNamespace(command="start", sessionId="session", taskId="task", groupId="group",
                                  mentions=["worker-a", "worker-b"], senderId="leader")
        emitter = SimpleNamespace(emit=AsyncMock())
        with self.assertLogs("acps_sdk.amp.group_access", level="WARNING") as captured:
            await GroupAccessMiddleware(emitter, "leader").run(command, AsyncMock(), direction="send")
        self.assertIn("group_access_unpairable_mentions", captured.output[0])
