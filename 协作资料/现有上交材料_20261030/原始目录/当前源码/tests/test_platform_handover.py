"""Formal handover checks use only fake transports and synthetic history."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aip.resumable import Fence, ResumePackage
from eval.platform_handover import bind_handover, verify_handover
from incident.contracts import handover_evidence


def original(**changes):
    return {"incident_id": "incident", "logical_task_id": "repair", "operation_id": "op",
        "kind": "act", "tool": "db.restore_writes", "args": {},
        "fence": {"coordinator_term": 4, "takeover_version": 0}, **changes}


def send(payload, task="aip-original", target="primary", **changes):
    return {"direction": "send", "transport": "wutong-amqps", "worker_aic": target,
        "message": {"command": "start", "sessionId": "group-session", "senderId": "coordinator",
            "taskId": task, "dataItems": [{"text": json.dumps(payload, ensure_ascii=False)}]}, **changes}


def write(path, rows):
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(raw)
    return len(raw)


class PlatformHandoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "artifacts").mkdir(exist_ok=True)

    def fixture(self, directory, method="full_history"):
        output = Path(directory)
        fact = {"key": "application_pool_revision", "value": 7, "source": "application.status",
            "observed_at": datetime.fromtimestamp(100, timezone.utc).isoformat()}
        observation = original(kind="observe", logical_task_id="status", operation_id=None,
                               tool="application.status")
        rows = [send(observation, "aip-status"),
            {"direction": "receive", "message": {"sessionId": "group-session", "taskId": "aip-status",
                "products": [{"dataItems": [{"data": {"incident_id": "incident", "logical_task_id": "status",
                    "status": "ok", "facts": [fact]}}]}]}}, send(original())]
        cutoff = write(output / "messages.jsonl", rows)
        # These are genuine post-boundary capture rows but cannot enter history.
        rows.append(send(original(logical_task_id="late"), "aip-late"))
        write(output / "messages.jsonl", rows)
        transport = SimpleNamespace(mode="wutong-amqps", output=output, config={"evidence_ttl_seconds": 60},
            aic="coordinator", session=SimpleNamespace(session_id="group-session"),
            resume_payload_factory=None, takeover_history_cutoffs={("incident", "repair"): cutoff})
        recorder = bind_handover(transport, method, output / "handover")
        package = ResumePackage("repair", "goal", evidence_refs=handover_evidence([fact], 60),
            operations=[{"operation_id": "op", "status": "delivery_unknown"}], fence=Fence(4, 1))
        default = original(kind="resume", fence=package.fence.to_dict(),
            args={"advance_fence": True, "resume_package": package.to_dict()})
        payload = transport.resume_payload_factory(default, package)
        rows.append(send(payload, "aip-resume", "backup"))
        write(output / "messages.jsonl", rows)
        digest = hashlib.sha256(json.dumps(payload["args"]["handover"], ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        product = {"status": "ok", "incident_id": "incident", "logical_task_id": "repair",
                   "executor_aic": "backup", "handover_sha256": digest}
        return transport, recorder, payload, product, rows

    def verify(self, transport, recorder, product, **changes):
        return verify_handover(transport, recorder, original(), product, backup_aic="backup", now=150, **changes)

    def test_all_three_methods_use_actual_send_and_same_pre_boundary_control(self):
        for method in ("from_scratch", "full_history", "resume_package"):
            with self.subTest(method=method), tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
                transport, recorder, payload, product, _ = self.fixture(directory, method)
                result = self.verify(transport, recorder, product)
                self.assertIs(transport.resume_payload_factory, recorder)
                self.assertEqual(result["fresh_facts"], {} if method == "from_scratch" else
                    {"application_pool_revision": {"key": "application_pool_revision", "value": 7,
                    "source": "application.status", "observed_at": datetime.fromtimestamp(100, timezone.utc).isoformat()}})
                metrics = result["metrics"]
                self.assertEqual(metrics["native_transmitted_ifc_text_bytes"],
                    len(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
                self.assertEqual(metrics["replacement_acknowledged_handover_sha256"], product["handover_sha256"])
                self.assertEqual(metrics["native_resume_session_id"], "group-session")
                prior = json.loads((recorder.output / "prior-business-conversation.json").read_text(encoding="utf-8"))
                self.assertEqual(len(prior), 3)
                self.assertFalse(any(row.get("payload", {}).get("logical_task_id") == "late" for row in prior))
                self.assertEqual(metrics["model_calls"], 0)

    def test_missing_cutoff_and_partial_prefix_cannot_fall_back_to_full_history(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            transport, recorder, payload, _, _ = self.fixture(directory)
            package = ResumePackage("repair", "goal", fence=Fence(4, 1))
            for cutoff in (None, True, -1, 1):
                with self.subTest(cutoff=cutoff):
                    transport.takeover_history_cutoffs.clear()
                    if cutoff is not None:
                        transport.takeover_history_cutoffs[("incident", "repair")] = cutoff
                    with self.assertRaises(ValueError):
                        recorder(payload, package)

    def test_missing_duplicate_and_non_text_resume_cannot_claim_actual_transfer(self):
        for mutation in (lambda rows: rows.pop(), lambda rows: rows.append(deepcopy(rows[-1])),
                         lambda rows: rows[-1]["message"].update(dataItems=[{"data": original(kind="resume") }])):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
                transport, recorder, _, product, rows = self.fixture(directory)
                mutation(rows)
                write(transport.output / "messages.jsonl", rows)
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    self.verify(transport, recorder, product)

    def test_actual_resume_correlation_session_sender_and_target_are_bound(self):
        mutations = [lambda row: row.update(worker_aic="other"),
            lambda row: row.update(transport="local-aip-stdio"),
            lambda row: row["message"].update(sessionId="incident"),
            lambda row: row["message"].update(senderId="other"),
            lambda row: row["message"].update(taskId=""),
            lambda row: row["message"]["dataItems"][0].update(text=json.dumps(original(kind="resume", operation_id="other")))]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
                transport, recorder, _, product, rows = self.fixture(directory)
                mutation(rows[-1])
                write(transport.output / "messages.jsonl", rows)
                with self.assertRaises(ValueError):
                    self.verify(transport, recorder, product)

    def test_byte_count_and_actual_handover_digest_must_match_acknowledgement(self):
        for field in ("bytes", "digest", "product_identity", "transfer"):
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
                transport, recorder, _, product, _ = self.fixture(directory)
                if field == "bytes":
                    recorder.metrics["resume_ifc_payload_utf8_bytes"] += 1
                elif field == "digest":
                    product["handover_sha256"] = "0" * 64
                elif field == "product_identity":
                    product["executor_aic"] = "primary"
                else:
                    recorder.transfer = {**recorder.transfer, "goal": "different"}
                with self.assertRaises(ValueError):
                    self.verify(transport, recorder, product)

    def test_expired_facts_are_not_renewed_by_formal_handover(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            transport, recorder, _, product, _ = self.fixture(directory, "resume_package")
            result = verify_handover(transport, recorder, original(), product, backup_aic="backup", now=161)
            self.assertEqual(result["fresh_facts"], {})


if __name__ == "__main__":
    unittest.main()
