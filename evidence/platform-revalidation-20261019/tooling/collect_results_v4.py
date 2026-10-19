"""Append-only, read-only acceptance evidence projections. No product imports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH / "checkout"
EXECUTIONS = (BATCH / "execution", BATCH / "execution-v2", BATCH / "execution-v3")
SUMMARY = BATCH / "plan-preparation/prepared-summary.json"
HEX = re.compile(r"[0-9a-f]{64}")
CLOSE = ("no_group_sessions", "no_inbound_groups", "inbox_cancelled", "connection_closed",
         "owned_group_disconnected", "no_cleanup_warnings")
H00 = ("status", "duration_seconds", "requests", "success", "failed", "unknown",
       "completed_workflows", "unresolved_intents", "resolved_unknown_intents", "passed")
COUNT = ("invocations", "returned", "returned_errors", "without_return")
HANDOVER = ("resume_ifc_payload_utf8_bytes", "handover_information_utf8_bytes",
    "handover_information_estimated_tokens_bytes_div_4", "token_estimate_method",
    "native_transmitted_ifc_text_bytes", "native_transmitted_ifc_text_sha256",
    "replacement_acknowledged_handover_sha256", "history_bytes_before_takeover",
    "transport", "model_calls", "model_tokens")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scalar_fields(value, names):
    value = value if isinstance(value, dict) else {}
    return {name: value.get(name) if isinstance(value.get(name), (str, int, float, bool)) else None
            for name in names}


def fence(value):
    return scalar_fields(value, ("coordinator_term", "takeover_version")) if isinstance(value, dict) else None


class Reader:
    def __init__(self):
        self.inputs = {}

    def raw(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(BATCH.resolve()):
            raise ValueError("Input outside this acceptance batch")
        if not path.is_file():
            return None
        data = path.read_bytes()
        # For live append files this binds the observed bytes, not a final seal.
        self.inputs[path.relative_to(BATCH).as_posix()] = {
            "sha256": sha(data), "bytes_observed": len(data)}
        return data

    def json(self, path):
        data = self.raw(path)
        if data is None:
            return None
        key = Path(path).resolve().relative_to(BATCH).as_posix()
        try:
            value = json.loads(data)
            if not isinstance(value, (dict, list)):
                raise ValueError("Expected object or array")
            self.inputs[key]["json_read_status"] = "parsed"
            return value
        except (UnicodeError, ValueError):
            self.inputs[key]["json_read_status"] = "invalid_or_concurrent_write"
            return None


def health(value):
    if not isinstance(value, dict):
        return None
    result = scalar_fields(value, H00)
    state = value.get("state")
    result["pending_intents"] = len(state["pending"]) if isinstance(state, dict) and isinstance(state.get("pending"), list) else None
    return result


def counts(value, identities):
    if not isinstance(value, dict):
        return None
    rows = []
    for row in value.get("operations", []):
        if not isinstance(row, dict):
            continue
        aic = row.get("executor_aic")
        role = next((role for role in ("database", "database-backup") if identities.get(role) == aic), "unmatched")
        rows.append({"worker_role": role,
            "operation_id_sha256": sha(str(row["operation_id"]).encode()) if row.get("operation_id") else None,
            **scalar_fields(row, COUNT)})
    return {**scalar_fields(value, ("transport", "counting")), "operations": rows,
        "limit": "Wrapper invocation/return counts do not establish physical modifications; without_return alone does not prove dispatch."}


def e1c(value, identities):
    if not isinstance(value, dict):
        return None
    result = scalar_fields(value, ("status", "same_process", "signals_sent", "old_request_sha256",
        "stale_request_state", "replay_attempts", "rejected_stale_fence", "error_class"))
    result["old_fence"] = fence(value.get("old_fence"))
    result["counts"] = counts(value.get("counts"), identities)
    ledger = value.get("ledger_before_revival")
    result["ledger_before_revival"] = {"state": ledger.get("state"),
        "active_fence": fence(ledger.get("active_fence")),
        "operation_fence": fence(ledger.get("operation_fence"))} if isinstance(ledger, dict) else None
    result["process_snapshots"] = [{**scalar_fields(row, ("state", "signal_sent")),
        "process_identity": scalar_fields(row.get("process_identity"), ("pid", "linux_start_ticks"))}
        for row in value.get("process_snapshots", []) if isinstance(row, dict)]
    result["approval_expiry_observed_field"] = None
    result["approval_expiry_contract"] = "Controller and pidfd PROCESS_CODE require the unchanged original approval to remain valid for more than five seconds before SIGCONT; no independent expiry metric is emitted."
    return result


def handover_evidence(reader, directory, plan, report):
    """Separate recorder sizes, after-publish capture, and acknowledged metrics."""
    metrics = reader.json(directory / "handover-metrics.json")
    prepared = scalar_fields(metrics, HANDOVER[:4] + ("model_calls", "model_tokens")) if isinstance(metrics, dict) else None
    acknowledged = report.get("handover")
    acknowledged = scalar_fields(acknowledged, HANDOVER) if isinstance(acknowledged, dict) else None
    raw = reader.raw(directory / "coordinator/messages.jsonl")
    if raw is None:
        captured = None
    else:
        matches, invalid = [], 0
        for line in raw.splitlines():
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError("capture record is not an object")
                message = entry.get("message", {})
                if not isinstance(message, dict):
                    raise ValueError("capture message is not an object")
                if entry.get("direction") != "send" or message.get("command") != "start":
                    continue
                items = message.get("dataItems") or []
                if not isinstance(items, list):
                    raise ValueError("capture items are not an array")
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError("capture item is not an object")
                    text = item.get("text")
                    if not isinstance(text, str):
                        continue
                    payload = json.loads(text)
                    if not isinstance(payload, dict) or payload.get("kind") != "resume":
                        continue
                    if (payload.get("incident_id") != plan["incident_id"]
                            or payload.get("operation_id") != plan["operation_id"]
                            or isinstance(metrics, dict) and payload.get("logical_task_id") != metrics.get("logical_task_id")):
                        continue
                    args = payload.get("args", {})
                    transfer = args.get("handover") if isinstance(args, dict) else None
                    if not isinstance(transfer, dict):
                        raise ValueError("captured handover is not an object")
                    encoded = text.encode("utf-8")
                    transfer_digest = sha(json.dumps(transfer, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False).encode("utf-8"))
                    matches.append({"resume_ifc_text_utf8_bytes": len(encoded),
                        "resume_ifc_text_sha256": sha(encoded),
                        "handover_information_utf8_bytes": len(json.dumps(transfer, ensure_ascii=False).encode("utf-8")),
                        "handover_sha256": transfer_digest, "case_and_operation_match": True,
                        "backup_target_match": entry.get("worker_aic") == plan["identities"].get("database-backup"),
                        "transport": entry.get("transport") if entry.get("transport") == "wutong-amqps" else "unexpected",
                        "package_in_args_resume_package_and_handover_package": "resume_package" in args and "package" in transfer,
                        "duplicated_package_values_equal": args["resume_package"] == transfer["package"]
                            if "resume_package" in args and "package" in transfer else None})
            except (UnicodeError, ValueError):
                invalid += 1
        captured = {"matching_resume_sends": len(matches), "capture_parse_errors": invalid,
            "capture_ends_with_newline": raw.endswith(b"\n"), "sends": matches,
            "stage": "send capture written after publisher returns; does not establish replacement acknowledgement or success"}
        if len(matches) == 1:
            one = matches[0]
            captured["prepared_ifc_bytes_match"] = prepared["resume_ifc_payload_utf8_bytes"] == one["resume_ifc_text_utf8_bytes"] if prepared else None
            captured["prepared_handover_bytes_match"] = prepared["handover_information_utf8_bytes"] == one["handover_information_utf8_bytes"] if prepared else None
            captured["acknowledged_metrics_match"] = (acknowledged["native_transmitted_ifc_text_bytes"] == one["resume_ifc_text_utf8_bytes"]
                and acknowledged["native_transmitted_ifc_text_sha256"] == one["resume_ifc_text_sha256"]
                and acknowledged["replacement_acknowledged_handover_sha256"] == one["handover_sha256"]) if acknowledged else None
    return {"prepared_handover_metrics": prepared, "captured_resume_send": captured,
        "acknowledged_handover_metrics": acknowledged}


def case_result(reader, directory, plan, kind):
    path = directory / ("result.json" if kind == "F12/E5" else "results.json")
    report = reader.json(path)
    if not isinstance(report, dict):
        return None
    result = scalar_fields(report, ("schema_version", "status", "task_phase_status", "passed",
        "started_at", "finished_at", "completed_at", "model_calls", "model_tokens",
        "resource_and_worker_restore", "independent_final_H00_status", "transport_closed", "restored", "h00_status"))
    result["errors"] = {key: value for key, value in report.items()
        if key.endswith("error_class") and isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,79}", value)}
    result["phase_errors"] = [scalar_fields(row, ("phase", "error_class"))
        for row in report.get("errors", []) if isinstance(row, dict)]
    result["close_checks"] = scalar_fields(report["close_checks"], CLOSE) if isinstance(report.get("close_checks"), dict) else None
    result["cleanup_warning_events"] = [name for name in report.get("cleanup_warning_events", [])
        if name in {"dissolve_notify_failed", "group_acl_delete_failed", "queue_cleanup_failed", "exchange_cleanup_failed"}]
    result["independent_final_H00"] = health(report.get("independent_final_H00"))
    result["business_verification"] = health(report.get("business_verification"))
    identities = plan.get("identities", {})
    worker = report.get("worker_exit_and_mcp")
    result["worker_exit_and_mcp"] = ({**scalar_fields(worker, ("expected_exit_code", "actual_exit_code")),
        "counts": counts(worker.get("counts"), identities)} if isinstance(worker, dict) else None)
    operations = reader.json(directory / "mcp-operation-counts.json")
    result["mcp_operation_counts"] = counts(operations, identities)
    revival = reader.json(directory / "e1c-revival-metrics.json") if kind == "E1-c" else None
    result["worker_revival_and_mcp"] = e1c(revival or report.get("worker_revival_and_mcp"), identities)
    if kind == "E1-c":
        result["e1c_restore"] = scalar_fields(reader.json(directory / "e1c-restore.json"),
            ("resume_before_restore", "parent_restore", "resume_error_class", "parent_error_class"))
    handover = report.get("handover")
    result["handover"] = scalar_fields(handover, HANDOVER) if isinstance(handover, dict) else None
    if kind == "E1-b":
        result.update(handover_evidence(reader, directory, plan, report))
    result.update(scalar_fields(report, ("additional_post_handover_observations", "remaining_workflow_including_verification_seconds")))
    journal = report.get("journal_resolution")
    result["journal_resolution"] = scalar_fields(journal, ("raw_in_flight_count", "expected_unacknowledged_primary_attempts",
        "unexpected_in_flight_count", "raw_journal_modified")) if isinstance(journal, dict) else None
    if kind == "F12/E5":
        result["checks"] = [scalar_fields(row, ("name", "passed")) for row in report.get("checks", []) if isinstance(row, dict)]
        restored = reader.json(directory / "restored-h00/result.json")
        result["restored_h00"] = {**scalar_fields(restored, ("status", "error_class")),
            "business": health(restored.get("business"))} if isinstance(restored, dict) else None
    # Bind raw local evidence, but never decode/copy its messages, products or keys.
    for relative in ("primary-trace.jsonl", "backup-trace.jsonl", "coordinator/messages.jsonl", "subprocess-exits.jsonl"):
        reader.raw(directory / relative)
    return result


def attempt(reader, execution, row):
    directory = execution / row["key"]
    receipt = reader.json(directory / "receipt.json")
    exit_record = reader.json(directory / "runner.exit.json")
    if not isinstance(receipt, dict) and not isinstance(exit_record, dict):
        return None
    receipt = receipt if isinstance(receipt, dict) else {}
    exit_record = exit_record if isinstance(exit_record, dict) else {}
    result = {"execution": execution.name, **scalar_fields(receipt, ("status", "started_at", "finished_at", "plan_sha256", "error_class",
        "cleanup_and_recovery_verified", "launcher_error_class")),
        **scalar_fields(exit_record, ("actual_exit_code", "terminal", "duration_seconds", "completed_at"))}
    stderr = reader.raw(directory / "runner.stderr.bin")
    reader.raw(directory / "runner.stdout.bin")
    result["classification"] = "case_attempt_or_unknown"
    if (execution.name == "execution" and exit_record.get("actual_exit_code") == 1
            and stderr and b"E1 input/output must stay inside this project" in stderr
            and b"authorize(plan" in stderr):
        result["classification"] = "launcher_pre_case_failure"
        result["case_entered"] = False
        result["fault_injected"] = False
        result["basis"] = "Captured traceback rejects the authorization locator in authorize/local before run_case."
    elif (execution.name == "execution-v2" and row["order"] == 1
            and exit_record.get("terminal") is True and exit_record.get("actual_exit_code") == 1):
        result["classification"] = "initial_formal_case_failure"
        result["basis"] = "Original formal case reached a terminal exit1; later environment recovery does not replace this verdict."
    return result


def environment_recovery(reader):
    stages = []
    base = BATCH / "environment-recovery"
    for name in ("resource-restore", "resource-restore-v2"):
        directory = base / name
        value = reader.json(directory / "result.json")
        if not isinstance(value, dict):
            continue
        result = {"locator": (directory / "result.json").relative_to(BATCH).as_posix(),
            **scalar_fields(value, ("status", "started_at", "completed_at", "error_class", "new_faults",
                "original_case_result_retained", "normal_database_workers_restored",
                "active_or_unknown_operations", "independent_h00_status"))}
        h00 = reader.json(directory / "independent-h00/result.json")
        result["independent_h00"] = ({**scalar_fields(h00, ("status", "error_class", "started_at", "completed_at")),
            "business": health(h00.get("business"))} if isinstance(h00, dict) else None)
        for relative in ("subprocess-exits.jsonl", "ledger-readonly.json", "injections.jsonl",
                         "01-injector-check.json", "02-injector-restore.json"):
            reader.raw(directory / relative)
        stages.append(result)
    closes = []
    for path in sorted((base / "owned-group-close").glob("attempt-*/result.json")):
        value = reader.json(path)
        if not isinstance(value, dict):
            continue
        checks = value.get("close_checks")
        closes.append({"locator": path.relative_to(BATCH).as_posix(),
            **scalar_fields(value, ("status", "completed_at", "error_class", "official_dissolve_returned",
                "new_groups", "new_tasks", "new_inbox_consumers", "original_failure_retained")),
            "cleanup_warning_events": [name for name in value.get("cleanup_warning_events", [])
                if name in {"dissolve_notify_failed", "group_acl_delete_failed", "queue_cleanup_failed", "exchange_cleanup_failed"}],
            "close_checks": {k: v for k, v in checks.items() if isinstance(v, bool)}
                if isinstance(checks, dict) else None})
        reader.raw(path.parent / "sdk.log")
    launch_exit = reader.json(base / "owned-group-close/launch-attempt-1/official-close.exit.json")
    close_process = scalar_fields(launch_exit, ("actual_exit_code", "terminal", "duration_seconds", "completed_at")) if isinstance(launch_exit, dict) else None
    verifications = []
    for name in ("passive-verification", "passive-verification-v2"):
        path = base / "owned-group-close" / name / "result.json"
        value = reader.json(path)
        if not isinstance(value, dict):
            continue
        resources = [{**scalar_fields(row, ("kind", "mode", "state", "error_class")),
            "resource_name_sha256": sha(row["name"].encode("utf-8")) if isinstance(row.get("name"), str) else None}
            for row in value.get("resources", []) if isinstance(row, dict)]
        verified_all = (name == "passive-verification-v2" and value.get("status") == "passed"
            and value.get("connection_closed") is True and len(resources) == 8
            and sum(row["kind"] == "exchange" for row in resources) == 1
            and sum(row["kind"] == "queue" for row in resources) == 7
            and len({row["resource_name_sha256"] for row in resources}) == 8
            and all(row["state"] == "absent" and row["mode"] == "passive_assert_only" for row in resources))
        verifications.append({"locator": path.relative_to(BATCH).as_posix(),
            **scalar_fields(value, ("status", "completed_at", "connection_closed", "new_groups", "new_queues",
                "new_tasks", "new_inbox_consumers", "prior_close_status_retained", "notification_warning_retained",
                "acl_delete_acknowledged_204", "prior_result_sha256", "previous_partial_probe_sha256")),
            "coverage": "all_seven_bound_identities" if name == "passive-verification-v2" else "coordinator_and_forced_initial_database_only",
            "resources": resources,
            "resource_counts": {kind: sum(row["kind"] == kind for row in resources) for kind in ("exchange", "queue")},
            "disposition": "resources_verified_absent" if verified_all else "partial_or_unconfirmed",
            "meaning": "Passive absence includes names that may never have been created; it does not convert the prior failed close or notify warning into success."})
    return {"resource_restoration_attempts": stages, "original_owned_group_close_attempts": closes,
        "original_owned_group_close_process": close_process,
        "independent_group_resource_verifications": verifications,
        "scope": "Separate recovery evidence; it does not change the original formal-case failure or supply missing in-case close/H00 metrics."}


def collect():
    reader = Reader()
    prepared = reader.json(SUMMARY)
    if not isinstance(prepared, dict) or len(prepared.get("plans", [])) != 22:
        raise ValueError("Expected the actual prepared 22-plan summary")
    v2_source = reader.raw(EXECUTIONS[1] / "execute_authorized.py")
    f12_last = bool(v2_source and b"F12 runs last" in v2_source and b'if row["case"] == "F12/E5"' in v2_source)
    v3_source = reader.raw(EXECUTIONS[2] / "continue_authorized.py")
    continuation_f12_last = bool(v3_source and b"first = rows[1:7]" in v3_source
        and b"rest = rows[8:] + [rows[7]]" in v3_source)
    execution_order = [row["key"] for row in prepared["plans"] if row["case"] != "F12/E5"] + [row["key"] for row in prepared["plans"] if row["case"] == "F12/E5"]
    cases = []
    for row in prepared["plans"]:
        plan_path = (ROOT / row["plan"]).resolve()
        if not plan_path.is_relative_to(ROOT.resolve()):
            raise ValueError("Plan outside checkout")
        plan = reader.json(plan_path)
        if not isinstance(plan, dict) or sha(plan_path.read_bytes()) != row["plan_sha256"]:
            raise ValueError("Prepared plan hash mismatch")
        output = (ROOT / row["output"]).resolve()
        if not output.is_relative_to((ROOT / "eval/results/platform/acceptance-20261019").resolve()):
            raise ValueError("Case output outside this batch")
        attempts = [value for execution in EXECUTIONS if (value := attempt(reader, execution, row)) is not None]
        official = [value for value in attempts if value["classification"] != "launcher_pre_case_failure"]
        latest = official[-1] if official else None
        result = case_result(reader, output, plan, row["case"])
        terminal = bool(latest and latest.get("terminal") is True and type(latest.get("actual_exit_code")) is int)
        reported_pass = (result.get("passed") is True if row["case"] == "F12/E5" else result.get("status") == "completed") if result else None
        if terminal:
            status = "passed" if latest["actual_exit_code"] == 0 and reported_pass is True else "failed"
        elif latest and latest.get("status") == "running":
            status = "running_or_unconfirmed"
        elif result is not None or official or output.exists():
            status = "unknown_awaiting_terminal_receipt"
        else:
            status = "not_attempted"
        cases.append({**scalar_fields(row, ("key", "case", "point", "method", "repeat")),
            "prepared_order": row["order"], "execution_order": execution_order.index(row["key"]) + 1 if f12_last else None,
            "prepared_plan_sha256": row["plan_sha256"], "state": status,
            "actual_case_exit_code": latest.get("actual_exit_code") if terminal else None,
            "actual_case_process_terminal": terminal, "reported_passed": reported_pass,
            "attempts": attempts, "result": result})
    stages = []
    for execution in EXECUTIONS:
        paths = [execution / "startup/result.json", *sorted(execution.glob("stop-*/result.json"))]
        for path in paths:
            value = reader.json(path)
            if isinstance(value, dict):
                stage = {"locator": path.relative_to(BATCH).as_posix(), **scalar_fields(value,
                    ("status", "completed_at", "old_ids_preserved", "actual_startup_exit_code", "actual_stop_exit_code", "remaining_running_owned"))}
                process = reader.json(path.parent / ("compose-up.exit.json" if path.parent.name == "startup" else "compose-stop.exit.json"))
                stage["compose_process"] = scalar_fields(process, ("actual_exit_code", "terminal", "duration_seconds", "completed_at")) if isinstance(process, dict) else None
                stages.append(stage)
    recovery = environment_recovery(reader)
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Native Git needed only to read the checkout commit")
    commit = subprocess.run([git, "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, check=True).stdout.decode("ascii").strip()
    states = {state: sum(row["state"] == state for row in cases) for state in
        ("passed", "failed", "running_or_unconfirmed", "unknown_awaiting_terminal_receipt", "not_attempted")}
    return {"schema_version": "acceptance-public-snapshot/4", "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only point-in-time snapshot; absent values are null and do not imply zero or success.",
        "current_checkout_commit": commit, "project": prepared["project"], "ports": prepared["ports"],
        "image_id": prepared["image_id"], "prepared_summary_sha256": reader.inputs[SUMMARY.relative_to(BATCH).as_posix()]["sha256"],
        "prepared_source_file_count": len(prepared["source_sha256"]),
        "prepared_source_map_sha256": sha(json.dumps(prepared["source_sha256"], sort_keys=True, separators=(",", ":")).encode()),
        "ordering": {"original_plan_order_preserved": True, "f12_last_launcher_guard_present": f12_last,
            "continuation_f12_last_guard_present": continuation_f12_last,
            "continuation_phases": {"first": [row["key"] for row in prepared["plans"][1:7]],
                "rest": [row["key"] for row in prepared["plans"][8:]] + [prepared["plans"][7]["key"]]}
                if continuation_f12_last else None,
            "changed_reason": "Retained F12 one-off proxy must not precede later E1 ownership checks.", "execution_keys": execution_order if f12_last else None},
        "counts": {"prepared": 22, **states,
            "retained_launcher_pre_case_failures": sum(a["classification"] == "launcher_pre_case_failure" for row in cases for a in row["attempts"])},
        "cases": cases, "startup_and_stop_stages": stages, "environment_recovery": recovery, "inputs": reader.inputs,
        "limits": ["No raw AIP/AMP bodies, approvals, certificates, private keys, env values or private configuration are copied.",
            "All input hashes bind bytes observed during this collection; they do not seal an active writer or prove liveness.",
            "Task failure, normal-close failure, restoration failure and independent H00 are separate fields.",
            "Not-attempted cases retain null metrics. Historical launcher failure is separate from formal-case failure.",
            "A continuation launcher_error_class can describe the wrapper observing a nonzero formal-case exit; it does not by itself mean a pre-case failure.",
            "Failed cases may continue only when their receipt separately verifies cleanup and recovery. External recovery never changes the first case verdict."]}


def write_snapshot(report, *, freeze=False):
    if freeze and (report["counts"]["running_or_unconfirmed"] or report["counts"]["unknown_awaiting_terminal_receipt"]):
        raise ValueError("Cannot freeze cases without actual terminal receipts")
    directory = HERE / "snapshots-v4" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]) / "public-candidate"
    directory.mkdir(parents=True, exist_ok=False)
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    (directory / "summary.json").write_bytes(payload)
    lines = ["# Acceptance evidence snapshot", "", f"Checkout: `{report['current_checkout_commit']}`.", "",
        f"Prepared 22; passed {report['counts']['passed']}; failed {report['counts']['failed']}; not attempted {report['counts']['not_attempted']}; running/unconfirmed {report['counts']['running_or_unconfirmed']}; unknown {report['counts']['unknown_awaiting_terminal_receipt']}.", "",
        f"Retained launcher failures before entering a case: {report['counts']['retained_launcher_pre_case_failures']}.", "",
        "| Case | Method / point | Repeat | State | Actual case exit |", "|---|---|---:|---|---:|"]
    for row in report["cases"]:
        lines.append(f"| {row['case']} | {row['method'] or row['point'] or 'single'} | {row['repeat']} | {row['state']} | {row['actual_case_exit_code'] if row['actual_case_exit_code'] is not None else 'unknown'} |")
    lines += ["", "Execution moves F12 after all E1 cases; prepared plan hashes and original order remain unchanged.", "",
        "The original first formal failure is retained without retry. Environment restoration and original-group cleanup appear separately under environment_recovery; a later passed H00 does not make the failed case pass.", "",
        "The original group-close attempt remains failed and retains its dissolve_notify_failed warning. A separate passive verification can establish that the group's exchange and queues are absent; this is an independent resource disposition, not a successful rewrite of normal-close history.", "",
        "Continuation receipts preserve each actual runner exit and cleanup_and_recovery_verified independently; a terminal failed case may continue only after that separate recovery gate passes.", "",
        "E1-b separately reports prepared sizing metrics, captured sends, and acknowledged handover metrics. A send is not an acknowledgement or a passed case. Complete IFC text includes its full args; resume_package currently appears both in args.resume_package and args.handover.package, so handover-subobject size alone is not transmitted IFC size. No byte-saving or success claim is inferred across methods.", "",
        "This snapshot preserves reported close/restoration/H00 and worker evidence separately. Missing metrics remain null. Raw originals stay local and are referenced only by relative locator and observed SHA-256. No pass is inferred for unfinished work.", ""]
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")
    if freeze:
        (directory.parent / "freeze.json").write_text(json.dumps({"scope": "partial" if report["counts"]["not_attempted"] else "all_prepared_cases_terminal",
            "summary_sha256": sha(payload), "collector_sha256": sha(Path(__file__).read_bytes()), "counts": report["counts"]}, indent=2) + "\n", encoding="utf-8")
    return directory, sha(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Freeze this terminal snapshot, retaining not-attempted cases honestly")
    args = parser.parse_args()
    report = collect()
    directory, digest = write_snapshot(report, freeze=args.freeze)
    print(json.dumps({"status": "SNAPSHOT_WRITTEN", "directory": str(directory), "summary_sha256": digest,
        "counts": report["counts"], "frozen": args.freeze}, ensure_ascii=False))


if __name__ == "__main__":
    main()
