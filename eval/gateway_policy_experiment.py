"""E2-c: real Bridge policy refusals, stdio MCP and read-back signed AMP audit.

Default invocation describes the experiment. --run uses only temporary keys,
SQLite and the existing local MCP fixture; it does not contact the platform or
operate a database/container. Approval secrets/proofs never enter the output.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]

CALLER = "e2c-coordinator-fixture"
OTHER_CALLER = "e2c-other-authorized-coordinator-fixture"
EXECUTOR = "e2c-database-fixture"
APPROVAL_REASON = "high risk tool requires a valid independent approval proof"
REQUIRED_GROUPS = ("unauthorized_caller", "non_allowlisted_sql", "high_without_approval", "stale_fence")
SOURCE_FILES = (
    "eval/gateway_policy_experiment.py", "tests/test_gateway_policy_experiment.py",
    "acps_mcp_bridge/policy.py", "acps_mcp_bridge/bridge.py", "acps_mcp_bridge/approval.py",
    "acps_mcp_bridge/audit.py", "acps_mcp_bridge/client.py", "domains/database/policy.yaml",
    "tests/fixtures/bridge_mcp_server.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/emitter.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/signer.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/models.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/ledger.py",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def create_identity(directory):
    """Self-signed test material remains inside the caller's TemporaryDirectory."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.x509.oid import NameOID
    key = Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, EXECUTOR)])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier("acps://" + EXECUTOR)]), critical=False)
        .sign(key, None))
    certificate_path, key_path = directory / "identity.pem", directory / "identity.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    return certificate, certificate_path, key_path


def audit_expectation(command, caller, *, accepted=False):
    return {"executor_aic": EXECUTOR, "caller_aic": caller, "tool": command["tool"],
            "target": command.get("operation_id") or command["tool"],
            "incident_id": command["incident_id"], "logical_task_id": command["logical_task_id"],
            "result_status": "success" if accepted else "failure",
            "result_reason": "applied" if accepted else "rejected"}


def verify_audit_records(records, certificate, expected, evidence_ref):
    """Do not trust emit()'s returned ID: require exactly one persisted signed row."""
    import jcs
    from acps_sdk.amp.models import AuditLogRecord
    flags = {name: False for name in ("exactly_one_record", "schema_valid", "signature_valid",
        "certificate_kid_and_algorithm_match", "semantic_fields_match", "evidence_ref_matches")}
    flags["exactly_one_record"] = len(records) == 1
    if len(records) != 1:
        return {"passed": False, "checks": flags, "record_count": len(records), "log_id": None}
    record = records[0]
    if not isinstance(record, dict):
        return {"passed": False, "checks": flags, "record_count": 1, "log_id": None}
    try:
        AuditLogRecord.model_validate(record)
        flags["schema_valid"] = True
    except Exception:
        pass
    integrity = record.get("integrity") if isinstance(record.get("integrity"), dict) else {}
    flags["certificate_kid_and_algorithm_match"] = (
        integrity.get("kid") == format(certificate.serial_number, "X") and integrity.get("alg") == "EdDSA")
    try:
        unsigned = {key: value for key, value in record.items() if key != "integrity"}
        signature = base64.urlsafe_b64decode(integrity["sig"] + "=" * (-len(integrity["sig"]) % 4))
        certificate.public_key().verify(signature, jcs.canonicalize(unsigned))
        flags["signature_valid"] = True
    except Exception:
        pass
    body = record.get("body") if isinstance(record.get("body"), dict) else {}
    flags["semantic_fields_match"] = (
        record.get("log_type") == "audit" and record.get("aic") == expected["executor_aic"]
        and record.get("trace_id") == expected["incident_id"]
        and record.get("correlation_id") == expected["logical_task_id"]
        and body.get("actor") == {"id": expected["caller_aic"], "type": "agent"}
        and body.get("action") == {"name": expected["tool"], "type": "mcp_bridge"}
        and body.get("target") == {"type": "resource_domain", "id": expected["target"]}
        and body.get("result") == {"status": expected["result_status"], "reason": expected["result_reason"]})
    flags["evidence_ref_matches"] = evidence_ref == "amp:audit:" + str(record.get("log_id"))
    return {"passed": all(flags.values()), "checks": flags, "record_count": 1,
            "log_id": record.get("log_id"), "record_jcs_sha256": sha(jcs.canonicalize(record))}


def build_cases(authority, forger):
    cases = []

    def add(key, group, *, tool="db.restore_writes", kind="act", args=None, caller=CALLER,
            approval=True, reason=APPROVAL_REASON, layer="approval", accepted=False):
        command = {"schema_version": "ifc/1.0", "incident_id": "inc-e2c-" + key,
            "logical_task_id": "lt-e2c-" + key, "kind": kind, "tool": tool,
            "args": {} if args is None else args}
        if kind == "act":
            command.update(operation_id="op-e2c-" + key, fence={"coordinator_term": 2, "takeover_version": 0})
        if approval:
            command["approval"] = authority.issue(command, caller, approved_by="e2c-independent-approval-fixture")
        row = {"key": key, "group": group, "command": command, "caller": caller,
               "expected_reason": reason, "expected_layer": layer, "accepted": accepted}
        cases.append(row)
        return command

    add("unauthorized-caller", "unauthorized_caller", tool="db.read_only_status", kind="observe",
        caller="e2c-unlisted-caller-fixture", approval=False,
        reason="caller_aic is not authorized for this resource domain", layer="caller_allowlist")
    add("raw-sql-alias", "non_allowlisted_sql", tool="execute_sql", kind="observe",
        args={"sql": "DROP TABLE fixture_orders"}, approval=False,
        reason="tool is not in the allowlist", layer="tool_allowlist")
    add("sql-argument-injection", "non_allowlisted_sql", tool="db.read_only_status", kind="observe",
        args={"sql": "DROP TABLE fixture_orders"}, approval=False,
        reason="arguments do not match the registered tool schema", layer="argument_schema")
    add("high-without-approval", "high_without_approval", approval=False)
    stale = add("stale-fence", "stale_fence", reason=None, layer="operation_ledger")
    stale["fence"] = {"coordinator_term": 1, "takeover_version": 0}
    operation = add("approval-operation-binding", "approval_boundaries")
    operation["operation_id"] += "-changed"
    add("approval-caller-binding", "approval_boundaries")
    cases[-1]["caller"] = OTHER_CALLER
    incident = add("approval-incident-binding", "approval_boundaries")
    incident["incident_id"] += "-changed"
    arguments = add("approval-argument-binding", "approval_boundaries", tool="db.terminate_blocker", args={"pid": 123})
    arguments["args"] = {"pid": 124}
    for key, approved_at, expires_at in (("approval-expired", int(time.time()) - 301, int(time.time()) - 1),
                                       ("approval-future-issued", int(time.time()) + 600, int(time.time()) + 900)):
        command = add(key, "approval_boundaries")
        record = {k: v for k, v in command["approval"].items() if k != "proof"}
        record.update(approved_at=approved_at, expires_at=expires_at)
        # Create authentic old/future proofs; verify() must reject their time bounds.
        command["approval"] = {**record, "proof": authority._proof(record)}
    forged = add("approval-forged", "approval_boundaries")
    forged["approval"] = forger.issue(forged, CALLER, approved_by="e2c-independent-approval-fixture")
    disguised = add("write-disguised-as-observe", "risk_and_schema_boundaries",
                    reason="task kind does not match tool risk", layer="risk_kind")
    disguised["kind"] = "observe"
    add("pid-out-of-range", "risk_and_schema_boundaries", tool="db.terminate_blocker", args={"pid": 0},
        reason="arguments do not match the registered tool schema", layer="argument_schema")
    add("valid-approved-write", "positive_control", reason=None, layer="authorized_write", accepted=True)
    return cases


class CountedMcp:
    """Count every actual Bridge->McpStdioClient call; probes use the raw client."""
    def __init__(self, client):
        self.client, self.calls = client, []

    async def tools(self):
        return await self.client.tools()

    async def call(self, tool, arguments):
        self.calls.append({"tool": tool, "modification": tool == "execute_sql"
                           and arguments.get("sql") == "SELECT incident_ops.restore_writes() AS read_only"})
        return await self.client.call(tool, arguments)


def safe_write(path, raw, forbidden):
    if any(value and value in raw for value in forbidden):
        raise ValueError("Private fixture material would enter output")
    path.write_bytes(raw)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


async def run_experiment(output):
    from cryptography.hazmat.primitives import serialization
    from jsonschema import Draft202012Validator
    from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
    from acps_mcp_bridge.audit import AmpAuditSink
    from acps_mcp_bridge.bridge import mcp_value
    from acps_sdk.aip.resumable import Fence, OperationLedger
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    source_hashes = {name: sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    rows = []
    with tempfile.TemporaryDirectory(prefix="e2c-policy-") as temporary:
        private = Path(temporary)
        authority, forger = ApprovalAuthority(secrets.token_hex(32)), ApprovalAuthority(secrets.token_hex(32))
        certificate, certificate_path, key_path = create_identity(private)
        cases = build_cases(authority, forger)
        forbidden = [authority.secret, forger.secret, key_path.read_bytes()]
        forbidden += [line for line in key_path.read_bytes().splitlines() if not line.startswith(b"-----")]
        forbidden += [case["command"]["approval"]["proof"].encode() for case in cases if "approval" in case["command"]]
        audit_file = private / "amp-audit.jsonl"
        sink = AmpAuditSink.from_certificate(audit_file, EXECUTOR, certificate_path, key_path)
        ledger = OperationLedger(private / "operations.sqlite", "e2c-orders-fixture")
        await ledger.activate_fence(Fence(2, 0))
        config = ServerConfig(sys.executable, [str(ROOT / "tests/fixtures/bridge_mcp_server.py")])
        async with McpStdioClient(config) as transport:
            counted = CountedMcp(transport)
            policy = Policy.load(ROOT / "domains/database/policy.yaml", allowed_callers=[CALLER, OTHER_CALLER],
                                 approval_verifier=authority.verify)
            bridge = await Bridge(policy, {"postgres": counted}, ledger, EXECUTOR, audit=sink).initialize()
            fixture_writes = mcp_value(await transport.call("analyze_db_health", {}))["writes"]
            probe_count = 1
            for case in cases:
                command, caller = case["command"], case["caller"]
                spec = policy.tools.get(command["tool"])
                schema_valid = (not list(Draft202012Validator(spec["input_schema"]).iter_errors(command["args"]))) if spec else None
                input_summary = {"schema_version_valid": command["schema_version"] == "ifc/1.0",
                    "envelope_identifiers_valid": all(isinstance(command[k], str) and command[k] for k in ("incident_id", "logical_task_id")),
                    "caller_allowed": caller in policy.allowed_callers, "tool_allowlisted": spec is not None,
                    "arguments_schema_valid": schema_valid, "kind_matches_tool_risk": (
                        command["kind"] == ("observe" if spec["risk"] == "read" else "act")) if spec else None,
                    "approval_present": "approval" in command, "approval_verifies": authority.verify(command, caller),
                    "fence": command.get("fence"), "active_fence_before": ledger.current_fence().to_dict()}
                calls_before, writes_before = len(counted.calls), fixture_writes
                audit_before = audit_file.read_bytes().splitlines() if audit_file.exists() else []
                result = await bridge.execute(command, caller)
                audit_raw = audit_file.read_bytes() if audit_file.exists() else b""
                persisted = [json.loads(line) for line in audit_raw.splitlines()[len(audit_before):]]
                fixture_writes = mcp_value(await transport.call("analyze_db_health", {}))["writes"]
                probe_count += 1
                calls = counted.calls[calls_before:]
                operation_state = result.get("operation", {}).get("state")
                expected = audit_expectation(command, caller, accepted=case["accepted"])
                if case["expected_layer"] == "operation_ledger":
                    expected["result_reason"] = "rejected_stale_fence"
                audit = verify_audit_records(persisted, certificate, expected, result.get("evidence_ref"))
                entry = ledger.get(command["operation_id"]) if command.get("operation_id") else None
                if case["accepted"]:
                    behavior = (result["status"] == "ok" and operation_state == "applied" and len(calls) == 3
                        and sum(call["modification"] for call in calls) == 1 and fixture_writes - writes_before == 1
                        and entry is not None and entry["state"] == "applied")
                else:
                    layer_matches = (operation_state == "rejected_stale_fence" if case["expected_layer"] == "operation_ledger"
                                     else result.get("reason") == case["expected_reason"])
                    behavior = (result["status"] == "rejected" and layer_matches and len(calls) == 0
                                and fixture_writes == writes_before and entry is None)
                row = {"key": case["key"], "group": case["group"], "expected_rejection_layer": case["expected_layer"],
                    "accepted_control": case["accepted"], "input_summary": input_summary,
                    "result": {"status": result["status"], "reason": result.get("reason"), "operation_state": operation_state},
                    "policy_execution_mcp_calls": len(calls), "policy_execution_mcp_modification_calls": sum(c["modification"] for c in calls),
                    "fixture_writes_before": writes_before, "fixture_writes_after": fixture_writes,
                    "verification_probe_calls": 1, "operation_ledger_entry_state": entry["state"] if entry else None,
                    "behavior_passed": behavior, "audit": audit, "passed": behavior and audit["passed"]}
                rows.append(row)
                safe_write(output / "cases.jsonl", b"".join((json.dumps(item, ensure_ascii=False) + "\n").encode() for item in rows), forbidden)
                safe_write(output / "amp-audit.jsonl", audit_raw, forbidden)
        certificate_der = certificate.public_bytes(serialization.Encoding.DER)
        safe_write(output / "audit-certificate.json", json_bytes({"type": "self_signed_test_certificate",
            "certificate_der_base64": base64.b64encode(certificate_der).decode(), "sha256": sha(certificate_der),
            "aic": EXECUTOR, "private_key_included": False, "registry_or_CA_trust_claimed": False}), forbidden)
        group_rows = {group: [row for row in rows if row["group"] == group] for group in REQUIRED_GROUPS}
        required = {group: {"cases": len(items), "passed": bool(items) and all(row["passed"] for row in items)}
                    for group, items in group_rows.items()}
        negatives = [row for row in rows if not row["accepted_control"]]
        controls = [row for row in rows if row["accepted_control"]]
        passed = all(row["passed"] for row in rows) and all(row["passed"] for row in required.values())
        report = {"schema_version": "gateway-policy-e2c/1", "status": "passed" if passed else "failed",
            "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
            "scope": "Actual Policy/Bridge/OperationLedger, official stdio MCP fixture, AmpAuditSink and CertificateAuditSigner; temporary self-signed Ed25519 certificate; JCS verification of persisted rows.",
            "required_groups": required, "case_count": len(rows), "rejection_cases": len(negatives),
            "rejections_with_verified_signed_audit": sum(row["passed"] for row in negatives),
            "required_group_interception_rate": sum(row["behavior_passed"] for group in group_rows.values() for row in group) / sum(map(len, group_rows.values())),
            "required_group_signed_audit_rate": sum(row["audit"]["passed"] for group in group_rows.values() for row in group) / sum(map(len, group_rows.values())),
            "positive_controls": len(controls), "positive_controls_passed": sum(row["passed"] for row in controls),
            "rejected_policy_execution_mcp_calls": sum(row["policy_execution_mcp_calls"] for row in negatives),
            "policy_execution_mcp_calls": len(counted.calls), "fixture_modifications": fixture_writes,
            "independent_verification_probe_calls": probe_count, "stdio_context_closed": True,
            "all_sources_unchanged_during_run": all(sha((ROOT / name).read_bytes()) == digest for name, digest in source_hashes.items()),
            "source_sha256": source_hashes, "cases": rows,
            "audit_file_sha256": sha((output / "amp-audit.jsonl").read_bytes()),
            "audit_records": len((output / "amp-audit.jsonl").read_bytes().splitlines()),
            "private_keys_and_approval_values_in_output": False,
            "limits": ["Fixture tool-call counts exclude tools/list and separately counted health verification probes.",
                "One authorized fixture modification proves the positive path; no real business/database/container/platform operation occurs.",
                "Self-signed fixture verification does not prove platform CA trust, Monitor ingestion or production certificate validity.",
                "Historical platform cases, T05 failures and pending acceptance are unchanged."]}
        report["status"] = "passed" if passed and report["all_sources_unchanged_during_run"] else "failed"
        safe_write(output / "results.json", json_bytes(report), forbidden)
    report["temporary_private_material_cleaned"] = not private.exists()
    (output / "results.json").write_bytes(json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps({"status": "DESCRIBE_ONLY", "required_groups": REQUIRED_GROUPS,
            "requires": "--run --output <new directory>", "resources_or_fixture_started": False}))
        return 0
    if args.output is None:
        parser.error("--run requires --output")
    if args.output.exists():
        parser.error("--output must be a new directory; previous evidence is preserved")
    try:
        report = asyncio.run(run_experiment(args.output))
    except Exception as error:
        if args.output.is_dir() and not (args.output / "failure.json").exists():
            (args.output / "failure.json").write_bytes(json_bytes({"status": "failed", "error_class": type(error).__name__,
                "private_values_or_exception_text_included": False}))
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}))
        return 1
    print(json.dumps({key: report[key] for key in ("status", "case_count", "rejection_cases",
        "rejections_with_verified_signed_audit", "positive_controls_passed", "fixture_modifications",
        "rejected_policy_execution_mcp_calls", "temporary_private_material_cleaned")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
