"""Formal E1 interface checks with synthetic AIP/IFC captures and fake transport."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aip.resumable import Fence, ResumePackage
from eval.handover_experiment import HandoverRecorder
from eval.resume_support import formal_semantic_history
from incident.wutong_transport import WutongTransport


def request(**changes):
    return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
            "kind": "act", "tool": "db.restore_writes", "operation_id": "operation",
            "fence": {"coordinator_term": 1, "takeover_version": 0},
            "approval": {"proof": "synthetic"}, "budget": {"deadline_ms": 15000}, "args": {}, **changes}


def product(**changes):
    return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
            "executor_aic": "primary", "status": "ok", "facts": [], **changes}


def start(payload, *, session="formal-group-session", task="aip-task", structured=False):
    item = {"data": payload} if structured else {"text": json.dumps(payload, ensure_ascii=False)}
    return {"direction": "send", "message": {"sessionId": session, "taskId": task,
            "command": "start", "dataItems": [item]}}


def receive(value, *, session="formal-group-session", task="aip-task", text=False):
    item = {"text": json.dumps(value, ensure_ascii=False)} if text else {"data": value}
    return {"direction": "receive", "message": {"sessionId": session, "taskId": task,
            "products": [{"dataItems": [item]}]}}


def capture(path, rows):
    data = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(data)
    return len(data)


class FormalFactoryTests(unittest.IsolatedAsyncioTestCase):
    def transport(self, directory, factory=None):
        config = {"leader": {"aic": "coordinator", "cert": "unused", "key": "unused"},
                  "term_journal_path": str(Path(directory) / "terms.sqlite"),
                  "skills": {"database": "db.observe"}}
        with patch("incident.wutong_transport.AmpRuntime"):
            transport = WutongTransport(config, Path(directory) / "transport", resume_payload_factory=factory)
        return transport

    def envelope(self, transport):
        package = ResumePackage("logical", "goal", operations=[{"operation_id": "operation", "status": "delivery_unknown"}],
                                fence=Fence(transport.term, 1))
        default = request(kind="resume", fence=package.fence.to_dict(),
                          args={"advance_fence": True, "resume_package": package.to_dict()})
        return default, package

    def handover(self, payload):
        return {"strategy": "from_scratch", "control": {"operation_id": payload["operation_id"],
                "original_fence": {**payload["fence"], "takeover_version": 0},
                "replacement_fence": deepcopy(payload["fence"])}}

    async def test_default_factory_keeps_original_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            default, package = self.envelope(transport)
            self.assertIs(await transport._resume_payload(default, package), default)

    async def test_async_information_factory_receives_copies_and_preserves_envelope(self):
        async def factory(value, package):
            value["args"].pop("resume_package")
            value["args"]["handover"] = self.handover(value)
            package.evidence_refs.append({"synthetic": True})
            return value
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory, factory)
            default, package = self.envelope(transport)
            before, package_before = deepcopy(default), deepcopy(package.to_dict())
            result = await transport._resume_payload(default, package,
                original_fence={"coordinator_term": transport.term, "takeover_version": 0})
            self.assertEqual(default, before)
            self.assertEqual(package.to_dict(), package_before)
            self.assertNotIn("resume_package", result["args"])
            self.assertEqual({k: v for k, v in result.items() if k != "args"},
                             {k: v for k, v in before.items() if k != "args"})

    async def test_control_approval_budget_identity_and_package_mutations_are_rejected(self):
        mutations = {
            "kind": lambda p: p.update(kind="act"),
            "operation": lambda p: p.update(operation_id="other"),
            "fence": lambda p: p["fence"].update(takeover_version=99),
            "incident": lambda p: p.update(incident_id="other"),
            "logical": lambda p: p.update(logical_task_id="other"),
            "tool": lambda p: p.update(tool="ops.restore_route"),
            "schema": lambda p: p.update(schema_version="other"),
            "approval": lambda p: p["approval"].update(proof="other"),
            "budget": lambda p: p["budget"].update(deadline_ms=15001),
            "advance_false": lambda p: p["args"].update(advance_fence=False),
            "advance_int": lambda p: p["args"].update(advance_fence=1),
            "control_operation": lambda p: p["args"]["handover"]["control"].update(operation_id="other"),
            "control_original_fence": lambda p: p["args"]["handover"]["control"]["original_fence"].update(takeover_version=99),
            "control_replacement_fence": lambda p: p["args"]["handover"]["control"]["replacement_fence"].update(takeover_version=99),
            "package_operations": lambda p: p["args"]["resume_package"].update(operations=[]),
            "package_logical": lambda p: p["args"]["resume_package"].update(logical_task_id="other"),
            "package_fence": lambda p: p["args"]["resume_package"]["fence"].update(takeover_version=99),
        }
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            for label, mutation in mutations.items():
                with self.subTest(field=label):
                    def factory(value, package):
                        value["args"]["handover"] = self.handover(value)
                        mutation(value)
                        return value
                    transport.resume_payload_factory = factory
                    default, package = self.envelope(transport)
                    with self.assertRaises(ValueError):
                        await transport._resume_payload(default, package,
                            original_fence={"coordinator_term": transport.term, "takeover_version": 0})

    async def test_takeover_uses_factory_and_freezes_history_before_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            payload = request(fence={"coordinator_term": transport.term, "takeover_version": 0})
            path = transport.output / "messages.jsonl"
            cutoff = capture(path, [start(payload)])
            transport.selected = {"database": "primary"}
            transport.descriptions = {"database": {"resource_scope": {"database": "orders"}}}
            transport.session = SimpleNamespace(session_id="formal-group-session")
            transport.runtime = SimpleNamespace(force_remove_partner=AsyncMock())
            transport._describe = AsyncMock(return_value={"executor_aic": "backup",
                "resource_scope": {"database": "orders"}, "tools": ["db.restore_writes"]})
            def history_reader(incident, logical):
                return formal_semantic_history(path, incident,
                    before_bytes=transport.takeover_history_cutoffs[(incident, logical)])
            recorder = HandoverRecorder("full_history", transport, Path(directory), history_reader=history_reader)
            transport.resume_payload_factory = recorder
            async def discover(role, skill):
                # Simulates post-failure traffic, not a real request or resource action.
                with path.open("ab") as stream:
                    late = request(logical_task_id="post-failure", kind="observe", operation_id=None)
                    stream.write((json.dumps(start(late, task="late")) + "\n").encode())
                return [{"aic": "backup"}]
            transport._discover_candidates = AsyncMock(side_effect=discover)
            async def send(value, target):
                if target == "primary":
                    # The in-flight operation retains its original fence while
                    # another confirmed action has advanced current authority.
                    transport.active_fences["database"] = Fence(transport.term, 1)
                    raise TimeoutError()
                return {"status": "ok", "operation": {"state": "skipped_already_applied"},
                        "active_fence": {"coordinator_term": transport.term, "takeover_version": 2}, "facts": []}
            transport._send = AsyncMock(side_effect=send)
            result = await transport.call(payload)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(transport._send.await_count, 2)
            sent = transport._send.call_args_list[1].args[0]
            self.assertEqual(sent["kind"], "resume")
            self.assertEqual(sent["args"]["handover"]["control"]["original_fence"], payload["fence"])
            self.assertEqual(sent["fence"]["takeover_version"], 2)
            self.assertEqual(sent["args"]["handover"]["conversation"],
                [{"direction": "request", "aip_session_id": "formal-group-session", "aip_task_id": "aip-task", "payload": payload}])
            self.assertEqual(transport.takeover_history_cutoffs[("incident", "logical")], cutoff)
            events = [json.loads(line) for line in (transport.output / "events.jsonl").read_text().splitlines()]
            self.assertEqual(next(row for row in events if row["event"] == "takeover_started")["history_bytes_before_takeover"], cutoff)
            self.assertEqual(recorder.metrics["model_calls"], 0)
            self.assertEqual(sent["operation_id"], payload["operation_id"])
            self.assertEqual(sent["approval"], payload["approval"])
            self.assertEqual(sent["budget"], payload["budget"])


class FormalHistoryTests(unittest.TestCase):
    def test_group_incident_separation_out_of_order_and_duplicate_products(self):
        wanted = request(args={"label": "合成"})
        result = product()
        rows = [receive(result, text=True), start(wanted, structured=True), start(wanted), receive(result),
                start(request(incident_id="foreign"), session="other-group"),
                receive(product(incident_id="foreign"), session="other-group")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.jsonl"
            cutoff = capture(path, rows)
            history = formal_semantic_history(path, "incident", before_bytes=cutoff)
        self.assertEqual([row["direction"] for row in history], ["product", "request"])
        self.assertEqual(history[0]["product"], result)
        self.assertEqual(history[1]["payload"], wanted)
        self.assertTrue(all(row["aip_session_id"] == "formal-group-session" for row in history))

    def test_orphan_wrong_session_incident_and_logical_products_are_excluded(self):
        rows = [start(request()), receive(product(), task="orphan"),
                receive(product(), session="foreign-session"), receive(product(incident_id="foreign")),
                receive(product(logical_task_id="other")), receive(product()),
                start({"incident_id": "incident", "logical_task_id": "describe-uuid", "kind": "describe"}, task="describe")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.jsonl"
            cutoff = capture(path, rows)
            history = formal_semantic_history(path, "incident", before_bytes=cutoff)
        self.assertEqual([row["direction"] for row in history], ["request", "product"])

    def test_cutoff_ignores_later_bytes_and_rejects_invalid_or_partial_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.jsonl"
            cutoff = capture(path, [start(request())])
            with path.open("ab") as stream:
                stream.write(b"later non-JSON bytes")
            self.assertEqual(len(formal_semantic_history(path, "incident", before_bytes=cutoff)), 1)
            self.assertEqual(formal_semantic_history(path, "incident", before_bytes=0), [])
            for invalid in (True, -1, "1", cutoff - 1, path.stat().st_size + 1):
                with self.subTest(cutoff=invalid), self.assertRaises(ValueError):
                    formal_semantic_history(path, "incident", before_bytes=invalid)

    def test_conflicting_reuse_of_group_task_cannot_supply_another_incident_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.jsonl"
            cutoff = capture(path, [start(request(incident_id="foreign")), start(request())])
            with self.assertRaisesRegex(ValueError, "conflicting"):
                formal_semantic_history(path, "incident", before_bytes=cutoff)

    def test_recorder_default_preserves_local_history_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / "messages.jsonl"
            original = request()
            capture(path, [start(original, session="incident")])
            transport = SimpleNamespace(messages_path=path, config={})
            recorder = HandoverRecorder("from_scratch", transport, output)
            package = ResumePackage("logical", "goal", fence=Fence(1, 1))
            default = request(kind="resume", fence={"coordinator_term": 1, "takeover_version": 1},
                args={"advance_fence": True, "resume_package": package.to_dict()})
            result = recorder(default, package)
            self.assertEqual(result["args"]["handover"]["control"]["original_fence"], original["fence"])
            self.assertEqual(recorder.metrics["model_calls"], 0)
            self.assertEqual(recorder.metrics["model_tokens"], 0)

    def test_recorder_requires_original_incident_and_logical_task_even_for_same_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = SimpleNamespace(config={})
            package = ResumePackage("logical", "goal", fence=Fence(1, 1))
            default = request(kind="resume", fence={"coordinator_term": 1, "takeover_version": 1},
                args={"advance_fence": True, "resume_package": package.to_dict()})
            for field in ("incident_id", "logical_task_id"):
                with self.subTest(field=field):
                    reader = lambda incident, logical: [{"direction": "request", "payload": request(**{field: "foreign"})}]
                    recorder = HandoverRecorder("full_history", transport, Path(directory), history_reader=reader)
                    with self.assertRaisesRegex(ValueError, "not captured"):
                        recorder(default, package)


if __name__ == "__main__":
    unittest.main(verbosity=2)
