"""Handover strategy/control tests; resource-free, no model/network calls."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from incident.local_transport import LocalAipStdioTransport
from acps_sdk.aip.resumable import Fence, ResumePackage
from eval.handover_experiment import fresh_facts, HandoverRecorder
from eval.resume_support import semantic_history


class HandoverControlTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, directory, factory):
        transport = LocalAipStdioTransport({"coordinator_aic": "fixture", "workers": [],
            "term_journal_path": str(Path(directory)/"terms.sqlite")}, Path(directory)/"transport",
            resume_payload_factory=factory)
        package = ResumePackage("logical", "goal", operations=[{"operation_id": "op", "status": "delivery_unknown"}],
                                fence=Fence(transport.term, 1))
        payload = {"schema_version": "ifc/1.0", "incident_id": "inc", "logical_task_id": "logical", "kind": "resume",
            "tool": "db.restore_writes", "operation_id": "op", "fence": package.fence.to_dict(), "budget": {"deadline_ms": 15000},
            "args": {"advance_fence": True, "resume_package": package.to_dict()}}
        return transport, payload, package

    def handover(self, payload):
        return {"strategy": "from_scratch", "control": {"operation_id": payload["operation_id"],
            "replacement_fence": deepcopy(payload["fence"]),
            "original_fence": {**payload["fence"], "takeover_version": 0}}}

    async def test_factory_only_replaces_information_and_preserves_default_object(self):
        def factory(payload, package):
            payload["args"].pop("resume_package")
            payload["args"]["handover"] = self.handover(payload)
            return payload
        with tempfile.TemporaryDirectory() as directory:
            transport, payload, package = self.fixture(directory, factory)
            original = deepcopy(payload)
            result = await transport._resume_payload(payload, package, original_fence=Fence(transport.term, 0).to_dict())
            self.assertNotIn("resume_package", result["args"])
            self.assertEqual(payload, original)
            self.assertEqual(result["operation_id"], "op")
            self.assertEqual(result["fence"], original["fence"])

    async def test_all_authority_and_identity_mutations_rejected(self):
        mutations = [lambda p: p.update(kind="act"), lambda p: p.update(operation_id="another"),
            lambda p: p["fence"].update(takeover_version=99), lambda p: p.update(logical_task_id="another"),
            lambda p: p["args"].update(advance_fence=False), lambda p: p["args"]["handover"]["control"].update(operation_id="another"),
            lambda p: p["args"]["handover"]["control"]["original_fence"].update(takeover_version=99),
            lambda p: p["args"]["resume_package"].update(operations=[])]
        with tempfile.TemporaryDirectory() as directory:
            for mutation in mutations:
                def factory(payload, package):
                    payload["args"]["handover"] = self.handover(payload)
                    mutation(payload)
                    return payload
                transport, payload, package = self.fixture(directory, factory)
                with self.assertRaises(ValueError):
                    await transport._resume_payload(payload, package, original_fence=Fence(transport.term, 0).to_dict())

    async def test_default_factory_keeps_compatible_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, payload, package = self.fixture(directory, None)
            self.assertIs(await transport._resume_payload(payload, package), payload)

    async def test_custom_information_crosses_native_aip_and_shared_ledger_skips_effect(self):
        import test_resume_transport as fixtures
        with tempfile.TemporaryDirectory() as directory:
            config = fixtures.LocalTakeoverTests().configuration(directory, "after_applied")
            calls = []
            def factory(payload, package):
                calls.append(deepcopy(payload))
                payload["args"].pop("resume_package")
                payload["args"]["handover"] = self.handover(payload)
                return payload
            transport = LocalAipStdioTransport(config, Path(directory)/"transport", resume_payload_factory=factory)
            try:
                await transport.start()
                payload = {"incident_id": "hook", "logical_task_id": "original-logical", "kind": "act",
                    "tool": "db.restore_writes", "args": {}, "operation_id": "hook:original-operation",
                    "fence": {"coordinator_term": transport.term, "takeover_version": 0}}
                payload["approval"] = transport.issue_approval(payload)
                product = await transport.call(payload)
                self.assertEqual(product["status"], "ok")
                self.assertEqual(product["operation"]["state"], "skipped_already_applied")
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["operation_id"], payload["operation_id"])
                self.assertEqual(calls[0]["fence"]["takeover_version"], 1)
                self.assertEqual(json.loads((Path(directory)/"resource.json").read_text(encoding="utf-8"))["modifying_calls"], 1)
                messages = [json.loads(line) for line in transport.messages_path.read_text(encoding="utf-8").splitlines()]
                texts = [json.loads(item["text"]) for row in messages if row["direction"] == "send"
                         for item in row["message"].get("dataItems", []) if "text" in item]
                resume = next(value for value in texts if value["kind"] == "resume")
                self.assertEqual(resume["args"]["handover"]["strategy"], "from_scratch")
                self.assertEqual(resume["args"]["handover"]["control"]["original_fence"], payload["fence"])
                digest = hashlib.sha256(json.dumps(resume["args"]["handover"], ensure_ascii=False, sort_keys=True,
                                                   separators=(",", ":")).encode("utf-8")).hexdigest()
                self.assertEqual(product["handover_sha256"], digest)
                self.assertEqual(resume["logical_task_id"], payload["logical_task_id"])
            finally:
                await transport.close()


class HandoverEvidenceTests(unittest.TestCase):
    def test_history_and_package_share_original_ttl_and_do_not_refresh_missing_time(self):
        facts = [{"key": "application_pool_revision", "value": 7, "source": "application.status",
                  "observed_at": datetime.fromtimestamp(100, timezone.utc).isoformat()},
                 {"key": "untimed", "value": True, "source": "fixture"}]
        from incident.contracts import handover_evidence
        history = {"strategy": "full_history", "evidence_ttl_seconds": 60,
            "conversation": [{"direction": "product", "product": {"facts": facts}}]}
        package = {"strategy": "resume_package", "package": {"evidence_refs": handover_evidence(facts, 60)}}
        self.assertEqual(fresh_facts(history, 150), fresh_facts(package, 150))
        self.assertEqual(fresh_facts(history, 150)["application_pool_revision"]["value"], 7)
        self.assertNotIn("untimed", fresh_facts(history, 150))
        self.assertEqual(fresh_facts(history, 161), {})
        self.assertEqual(fresh_facts(package, 161), {})
        self.assertEqual(fresh_facts({"strategy": "from_scratch"}, 150), {})

    def test_latest_valid_revision_used_from_genuine_products(self):
        timestamp = datetime.fromtimestamp(100, timezone.utc).isoformat()
        history = {"strategy": "full_history", "evidence_ttl_seconds": 60,
            "conversation": [{"direction": "request", "payload": {"args": {"application_pool_revision": 999}}},
                {"direction": "product", "product": {"facts": [
                    {"key": "application_pool_revision", "value": 7, "observed_at": timestamp},
                    {"key": "application_pool_revision", "value": 8, "observed_at": timestamp}]}}]}
        self.assertEqual(fresh_facts(history, 150)["application_pool_revision"]["value"], 8)

    def test_history_exports_actual_payload_products_stops_at_replacement_lookup(self):
        request = {"incident_id": "inc", "logical_task_id": "status", "kind": "observe", "tool": "application.status"}
        product = {"incident_id": "inc", "logical_task_id": "status", "status": "ok", "facts": []}
        def send(payload, task="aip-actual"):
            return {"direction": "send", "message": {"sessionId": "inc", "taskId": task, "command": "start",
                "dataItems": [{"type": "text", "text": json.dumps(payload)}]}}
        receive = {"direction": "receive", "message": {"sessionId": "inc", "taskId": "aip-actual",
            "products": [{"dataItems": [{"data": product}]}]}}
        rows = [send(request), receive, receive,
                send({"kind": "describe", "logical_task_id": "status:describe:backup"}), send(request, "late")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"messages.jsonl"
            path.write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")
            actual = semantic_history(path, "inc")
        self.assertEqual(actual, [{"direction": "request", "aip_task_id": "aip-actual", "payload": request},
                                  {"direction": "product", "aip_task_id": "aip-actual", "product": product}])


if __name__ == "__main__":
    unittest.main()
