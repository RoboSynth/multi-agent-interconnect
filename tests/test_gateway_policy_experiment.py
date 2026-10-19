"""Check that E2-c cannot count returned IDs, unsigned rows or wrong bindings."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]

import jcs
from acps_mcp_bridge import Bridge, Policy
from acps_mcp_bridge.audit import AmpAuditSink
from acps_sdk.aip.resumable import OperationLedger
from acps_sdk.amp.emitter import AuditEmitter
from acps_sdk.amp.signer import CertificateAuditSigner
from eval.gateway_policy_experiment import (CALLER, EXECUTOR, audit_expectation,
    create_identity, verify_audit_records)


class GatewayPolicyEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.certificate, self.cert_path, self.key_path = create_identity(self.directory)
        self.audit_path = self.directory / "audit.jsonl"
        self.sink = AmpAuditSink.from_certificate(self.audit_path, EXECUTOR, self.cert_path, self.key_path)
        self.command = {"schema_version": "ifc/1.0", "incident_id": "inc-fixture", "logical_task_id": "lt-fixture",
                        "tool": "db.restore_writes", "kind": "act", "operation_id": "op-fixture", "args": {}}
        self.expected = audit_expectation(self.command, CALLER)

    def tearDown(self):
        self.temporary.cleanup()

    async def emit(self, sink=None):
        log_id = await (sink or self.sink)({"caller_aic": CALLER, "executor_aic": EXECUTOR,
            "incident_id": self.command["incident_id"], "logical_task_id": self.command["logical_task_id"],
            "tool": self.command["tool"], "operation_id": self.command["operation_id"],
            "status": "rejected", "operation_state": None})
        return "amp:audit:" + log_id

    def record(self):
        return json.loads(self.audit_path.read_bytes().splitlines()[-1])

    def verify(self, records, evidence_ref):
        return verify_audit_records(records, self.certificate, self.expected, evidence_ref)

    def sign(self, record):
        unsigned = {key: value for key, value in record.items() if key != "integrity"}
        signer = CertificateAuditSigner(self.key_path.read_text(), self.cert_path.read_text())
        record["integrity"] = {"alg": signer.alg, "kid": signer.kid,
            "sig": base64.urlsafe_b64encode(signer.sign(jcs.canonicalize(unsigned))).rstrip(b"=").decode()}
        return record

    async def test_valid_signature_cannot_hide_wrong_audit_binding_or_reference(self):
        evidence_ref = await self.emit()
        record = self.record()
        self.assertTrue(self.verify([record], evidence_ref)["passed"])
        for path, value in ((('body', 'actor', 'id'), "different-caller"),
                            (('body', 'action', 'name'), "different-tool"),
                            (('body', 'target', 'id'), "different-operation"),
                            (('body', 'result', 'status'), "success"),
                            (('body', 'result', 'reason'), "different-result"),
                            (('trace_id',), "different-incident"),
                            (('correlation_id',), "different-task"),
                            (('aic',), "different-executor")):
            with self.subTest(path=path):
                changed = deepcopy(record)
                parent = changed
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                check = self.verify([self.sign(changed)], evidence_ref)
                self.assertTrue(check["checks"]["signature_valid"])
                self.assertFalse(check["checks"]["semantic_fields_match"])
                self.assertFalse(check["passed"])
        self.assertFalse(self.verify([record], "amp:audit:another-record")["passed"])

    async def test_missing_duplicate_tampered_and_unsigned_readback_cannot_pass(self):
        evidence_ref = await self.emit()
        record = self.record()
        for rows in ([], [record, record]):
            self.assertFalse(self.verify(rows, evidence_ref)["passed"])
        tampered = deepcopy(record)
        tampered["body"]["result"]["reason"] = "tampered"
        checked = self.verify([tampered], evidence_ref)
        self.assertFalse(checked["checks"]["signature_valid"])
        self.assertFalse(checked["passed"])
        unsigned = deepcopy(record)
        unsigned.pop("integrity")
        self.assertFalse(self.verify([unsigned], evidence_ref)["passed"])

    async def test_silent_write_failure_is_failed_even_with_bridge_evidence_ref(self):
        blocker = self.directory / "ordinary-file"
        blocker.write_text("blocks parent directory creation", encoding="utf-8")
        sink = AmpAuditSink.from_certificate(blocker / "audit.jsonl", EXECUTOR, self.cert_path, self.key_path)
        policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER])
        bridge = Bridge(policy, {}, OperationLedger(self.directory / "ledger.sqlite"), EXECUTOR, audit=sink)
        command = {**self.command, "kind": "observe", "tool": "db.read_only_status"}
        with self.assertLogs("acps_sdk.amp.emitter", level="WARNING"):
            result = await bridge.execute(command, "e2c-unlisted-caller-fixture")
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(result["evidence_ref"].startswith("amp:audit:"))
        self.assertFalse((blocker / "audit.jsonl").exists())
        expected = audit_expectation(command, "e2c-unlisted-caller-fixture")
        self.assertFalse(verify_audit_records([], self.certificate, expected, result["evidence_ref"])["passed"])

    async def test_actual_signing_failure_fallback_is_not_verified_signed_audit(self):
        class BrokenSigner:
            alg = "EdDSA"
            kid = "test-only-broken-signer"
            def sign(self, data):
                raise RuntimeError("synthetic signing failure")
        sink = AmpAuditSink(AuditEmitter(self.audit_path, EXECUTOR, signer=BrokenSigner()))
        with self.assertLogs("acps_sdk.amp.emitter", level="WARNING"):
            evidence_ref = await self.emit(sink)
        record = self.record()
        self.assertNotIn("integrity", record)
        self.assertFalse(self.verify([record], evidence_ref)["passed"])


if __name__ == "__main__":
    unittest.main()
