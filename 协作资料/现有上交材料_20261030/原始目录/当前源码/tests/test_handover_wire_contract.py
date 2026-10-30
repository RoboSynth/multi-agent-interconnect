"""Offline regressions for formal history and actual AIP rejection parsing."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]

from acps_mcp_bridge import ApprovalAuthority, Bridge, Policy
from acps_sdk.aip import Product, StructuredDataItem, TaskResult, TaskState, TaskStatus
from acps_sdk.aip.resumable import Fence, OperationLedger, ResumePackage
from eval.platform_handover import bind_handover
from eval.resume_support import formal_semantic_history
from incident.wutong_transport import WutongTransport


CALLER = "coordinator"


class MemoryMcp:
    def __init__(self):
        self.calls = []
        self.read_only = True

    async def tools(self):
        return [{"name": name, "inputSchema": {"type": "object"}}
                for name in ("analyze_db_health", "execute_sql")]

    async def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if "restore_writes" in arguments.get("sql", ""):
            self.read_only = False
        return {"content": [{"type": "text", "text": json.dumps([{"read_only": self.read_only}])}]}


def action(term=1):
    return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
            "kind": "act", "tool": "db.restore_writes", "args": {}, "operation_id": "operation",
            "fence": {"coordinator_term": term, "takeover_version": 0}}


class HistoryBridgeContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.authority = ApprovalAuthority("offline-history-approval-" * 3)
        self.policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER],
                                  approval_verifier=self.authority.verify)
        self.mcp = MemoryMcp()
        self.ledger = OperationLedger(self.directory / "ledger.sqlite", "orders")
        self.primary = await Bridge(self.policy, {"postgres": self.mcp}, self.ledger, "primary").initialize()
        self.backup = await Bridge(self.policy, {"postgres": self.mcp},
            OperationLedger(self.directory / "ledger.sqlite", "orders"), "backup").initialize()
        self.original = action()
        self.original["approval"] = self.authority.issue(self.original, CALLER, approved_by="offline-test")

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def resume(self, conversation):
        return {**self.original, "kind": "resume", "fence": Fence(1, 1).to_dict(),
                "args": {"advance_fence": True, "handover": {"strategy": "full_history",
                    "control": {"operation_id": "operation", "original_fence": Fence(1, 0).to_dict(),
                                "replacement_fence": Fence(1, 1).to_dict()},
                    "conversation": conversation}}}

    async def test_formal_multisession_history_reaches_real_bridge_and_shared_ledger(self):
        applied = await self.primary.execute(self.original, CALLER)
        self.assertEqual(applied["operation"]["state"], "applied")
        calls_before_resume = deepcopy(self.mcp.calls)
        observation = {**action(), "kind": "observe", "logical_task_id": "status",
                       "tool": "application.status", "operation_id": None}
        observed = {"incident_id": "incident", "logical_task_id": "status", "status": "ok", "facts": []}

        def start(payload, session):
            return {"direction": "send", "message": {"sessionId": session, "taskId": "shared-task-id",
                "command": "start", "dataItems": [{"text": json.dumps(payload)}]}}

        def received(value, session):
            return {"direction": "receive", "message": {"sessionId": session, "taskId": "shared-task-id",
                "products": [{"dataItems": [{"data": value}]}]}}

        rows = [start(observation, "prior-session"), received(observed, "prior-session"),
                received(observed, "orphan-session"),
                start({**observation, "incident_id": "foreign"}, "foreign-session"),
                received({**observed, "incident_id": "foreign"}, "foreign-session"),
                start(self.original, "current-session")]
        path = self.directory / "messages.jsonl"
        raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
        path.write_bytes(raw)
        cutoff = len(raw)
        with path.open("ab") as stream:
            stream.write((json.dumps(start({**observation, "logical_task_id": "late"}, "late-session")) + "\n").encode())
        history = formal_semantic_history(path, "incident", before_bytes=cutoff)
        self.assertEqual([item["aip_session_id"] for item in history],
                         ["prior-session", "prior-session", "current-session"])
        self.assertEqual([item["direction"] for item in history], ["request", "product", "request"])
        self.assertEqual(history[-1]["payload"], self.original)
        transport = SimpleNamespace(mode="wutong-amqps", output=self.directory, config={},
            resume_payload_factory=None, takeover_history_cutoffs={("incident", "logical"): cutoff})
        recorder = bind_handover(transport, "full_history", self.directory / "handover")
        package = ResumePackage("logical", "continue", operations=[{"operation_id": "operation"}], fence=Fence(1, 1))
        command = recorder({**self.original, "kind": "resume", "fence": Fence(1, 1).to_dict(),
                            "args": {"advance_fence": True, "resume_package": package.to_dict()}}, package)
        self.assertEqual(command["args"]["handover"]["conversation"], history)
        result = await self.backup.execute(command, CALLER)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["operation"]["state"], "skipped_already_applied")
        self.assertEqual(result["operation"]["operation_id"], self.original["operation_id"])
        self.assertEqual(result["active_fence"], Fence(1, 1).to_dict())
        digest = hashlib.sha256(json.dumps(command["args"]["handover"], ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(result["handover_sha256"], digest)
        self.assertEqual(self.mcp.calls, calls_before_resume)
        self.assertEqual(sum("restore_writes" in arguments.get("sql", "")
                             for _, arguments in self.mcp.calls), 1)

    async def test_legacy_entries_still_work_and_only_valid_optional_session_is_allowed(self):
        self.ledger.record_received("operation", {"tool": self.original["tool"], "args": {},
            "resources": self.policy.resources}, Fence(1, 0))
        legacy = [{"direction": "request", "aip_task_id": "task", "payload": self.original}]
        accepted = await self.backup.execute(self.resume(legacy), CALLER)
        self.assertEqual(accepted["status"], "ok", accepted)
        self.assertEqual(accepted["operation"]["state"], "received")
        cases = [{"aip_session_id": value} for value in (None, "", "  ", 1, [], {})]
        cases += [{"unexpected": True}, {"aip_session_id": "valid-session", "unexpected": True}]
        for change in cases:
            with self.subTest(change=change):
                command = self.resume([{**deepcopy(legacy[0]), **change}])
                result = await self.backup.execute(command, CALLER)
                self.assertEqual(result["status"], "rejected", result)
                self.assertIn("invalid handover conversation", result["reason"])
                self.assertEqual(self.ledger.current_fence(), Fence(1, 1))
                self.assertEqual(self.ledger.get("operation")["state"], "received")
        self.assertEqual(self.mcp.calls, [])


class ResumeControlParsingTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, status, reason=None, *, confirmed_fence=False):
        with tempfile.TemporaryDirectory() as directory:
            config = {"leader": {"aic": CALLER, "cert": "unused", "key": "unused"},
                      "term_journal_path": str(Path(directory) / "terms.sqlite")}
            with patch("incident.wutong_transport.AmpRuntime"):
                transport = WutongTransport(config, Path(directory) / "transport")
            transport.amp.sampler.active = 0
            transport.selected = {"database": "primary"}
            transport.descriptions = {"database": {"resource_scope": {"database": "orders"}}}
            transport.session = SimpleNamespace(session_id="session", group_id="group", message_history=[])
            transport._discover_candidates = AsyncMock(return_value=[{"aic": "backup"}])
            transport._describe = AsyncMock(return_value={"executor_aic": "backup",
                "resource_scope": {"database": "orders"}, "tools": ["db.restore_writes"]})
            starts, returned = [], []
            original_timeout = TimeoutError("primary reply unavailable")

            async def start(session, *, task_id, task_content, target_partners, **kwargs):
                value = json.loads(task_content)
                starts.append((target_partners[0], value))
                if target_partners == ["primary"]:
                    raise original_timeout
                body = {"schema_version": "ifc/1.0", "incident_id": value["incident_id"],
                        "logical_task_id": value["logical_task_id"], "executor_aic": "backup", "status": status}
                if reason is not None:
                    body["reason"] = reason
                if confirmed_fence:
                    body["active_fence"] = value["fence"]
                timestamp = datetime.now(timezone.utc).isoformat()
                transport.session.message_history.append(TaskResult(id="reply", sentAt=timestamp,
                    senderId="backup", senderRole="partner", sessionId=session, groupId="group", taskId=task_id,
                    status=TaskStatus(state=TaskState.AwaitingCompletion, stateChangedAt=timestamp),
                    products=[Product(id="product", dataItems=[StructuredDataItem(data=body)])]))

            transport.runtime = SimpleNamespace(start_task=AsyncMock(side_effect=start),
                complete_task=AsyncMock(), force_remove_partner=AsyncMock())
            actual_send = transport._send

            async def observed_send(payload, target):
                result = await actual_send(payload, target)
                returned.append(result)
                return result

            transport._send = observed_send
            with patch("incident.wutong_transport.native.wait_for_state", AsyncMock()):
                if status in {"rejected", "tool_error"}:
                    with self.assertRaises(TimeoutError) as caught:
                        await transport.call(action(transport.term))
                    self.assertIs(caught.exception, original_timeout)
                    self.assertIsInstance(caught.exception.__cause__, RuntimeError)
                    self.assertIsInstance(caught.exception.__cause__.__cause__, RuntimeError)
                    self.assertIn(reason, str(caught.exception.__cause__.__cause__))
                    self.assertEqual(transport.selected["database"], "primary")
                    self.assertEqual(transport.active_fences, {})
                    transport.runtime.force_remove_partner.assert_not_awaited()
                    events = [json.loads(line) for line in (transport.output / "events.jsonl").read_text().splitlines()]
                    rejection = next(row for row in events if row["event"] == "takeover_control_rejected")
                    self.assertEqual((rejection["status"], rejection["reason"]), (status, reason))
                    self.assertFalse(any(row.get("error_class") == "AttributeError" for row in events))
                else:
                    result = await transport.call(action(transport.term))
                    self.assertEqual(result["status"], "unknown")
                    self.assertEqual(transport.selected["database"], "backup")
                    transport.runtime.force_remove_partner.assert_awaited_once()
            self.assertEqual([target for target, _ in starts], ["primary", "backup"])
            self.assertEqual(starts[-1][1]["kind"], "resume")
            self.assertEqual(starts[-1][1]["operation_id"], "operation")
            self.assertIsNone(returned[0]["operation"])
            transport.runtime.complete_task.assert_awaited_once()

    async def test_rejected_sdk_product_with_null_operation_preserves_reason(self):
        await self.exercise("rejected", "invalid handover conversation entry")

    async def test_tool_error_does_not_activate_candidate_even_with_a_reported_fence(self):
        await self.exercise("tool_error", "replacement tool unavailable", confirmed_fence=True)

    async def test_unknown_null_operation_keeps_existing_no_retry_semantics(self):
        await self.exercise("unknown", confirmed_fence=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
