"""Read frozen acceptance captures; emit only hashed keys and bounded metadata."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
BATCH = PROJECT / "artifacts/p0-acceptance-prep-20261019"
CHECKOUT = BATCH / "checkout"
TEAM = PROJECT.parent / "team-repository-multi-agent-interconnect"
PUBLICATION = BATCH / "publication"
CACHE = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def raw(path):
    path = path.resolve()
    if path not in CACHE:
        before = path.stat()
        value = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Frozen source changed during read")
        CACHE[path] = value
    return CACHE[path]


def doc(path):
    return json.loads(raw(path))


def rows(path):
    return [(i, json.loads(line), sha(line)) for i, line in enumerate(raw(path).splitlines(), 1) if line.strip()]


def label(path):
    path = path.resolve()
    for prefix, root in (("batch", BATCH), ("team", TEAM)):
        if path.is_relative_to(root):
            return prefix + "/" + path.relative_to(root).as_posix()
    raise ValueError("Unexpected source root")


def location(path, number, digest):
    return {"source": label(path), "line": number, "line_sha256": digest}


def payload(message):
    for item in message.get("dataItems", []):
        text = item.get("text")
        if isinstance(text, str):
            try:
                value = json.loads(text)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return {}


def symbolic(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", value) else None


def main():
    original_path = PUBLICATION / "closed-access-credentials-windows-final/closed-access-credentials.json"
    original = doc(original_path)
    index = doc(BATCH / "plan-preparation/prepared-summary.json")
    manifest_path = PUBLICATION / "six-domains-collected-final/private-domain-snapshot-manifest.json"
    manifest = doc(manifest_path)
    domain_access, domain_messages = [], []
    for domain in manifest["domains"]:
        directory_text = domain["directory"]
        if re.match(r"^/mnt/[a-z]/", directory_text):
            directory_text = directory_text[5].upper() + ":/" + directory_text[7:]
        directory = Path(directory_text)
        for file in domain["files"]:
            if not file["name"].startswith(("amp_access_", "amp_message_")):
                continue
            path = directory / file["name"]
            if sha(raw(path)) != file["sha256"] or len(raw(path)) != file["bytes"]:
                raise ValueError("Frozen domain snapshot SHA mismatch")
            target = domain_access if file["name"].startswith("amp_access_") else domain_messages
            target.extend((domain["role"], path, n, row, h) for n, row, h in rows(path))
    findings, controls, case_totals = [], [], []
    reports = {r["key"]: r for r in original["access_reconciliations"]}
    for item in index["plans"]:
        run = CHECKOUT / item["output"]
        messages_path = run / ("private/transport/messages.jsonl" if item["case"] == "F12/E5" else "coordinator/messages.jsonl")
        coord_amp = run / ("private/transport/amp" if item["case"] == "F12/E5" else "coordinator/amp")
        # F12 has no missing endpoint; reuse its already-bound closed analysis.
        if item["case"] == "F12/E5":
            report = reports[item["key"]]
            assert report["missing_records"] == report["extra_records"] == 0
            controls.append({"key": item["key"], "missing_endpoints": 0, "basis": "unchanged_closed_analysis"})
            continue
        plan_path = CHECKOUT / item["plan"]
        plan = doc(plan_path)
        assert sha(raw(plan_path)) == item["plan_sha256"]
        roles = {aic: role for role, aic in plan["identities"].items()}
        coord_access_path = coord_amp / "amp_access_coordinator.jsonl"
        coord_message_path = coord_amp / "amp_message_coordinator.jsonl"
        access = [("coordinator", coord_access_path, n, r, h) for n, r, h in rows(coord_access_path)] + domain_access
        amp = [("coordinator", coord_message_path, n, r, h) for n, r, h in rows(coord_message_path)] + domain_messages
        captures = rows(messages_path)
        starts = {r["message"]["taskId"]: (n, r, h) for n, r, h in captures
                  if r.get("direction") == "send" and r["message"].get("type") == "task-command"
                  and r["message"].get("command") == "start"}
        actual = Counter((r.get("trace_id"), r.get("correlation_id"), r.get("aic")) for _, _, _, r, _ in access)
        missing = []
        for task, (number, entry, line_hash) in starts.items():
            message = entry["message"]
            for endpoint, aic in (("caller", message["senderId"]), ("callee", entry["worker_aic"])):
                if not actual[(message["sessionId"], task, aic)]:
                    missing.append((task, endpoint, aic, number, entry, line_hash))
        assert len(missing) == reports[item["key"]]["missing_records"]
        result = doc(run / "results.json")
        trace_path = run / "primary-trace.jsonl"
        trace = rows(trace_path) if trace_path.is_file() else []
        crashes = [(n, r, h) for n, r, h in trace if r.get("event") == "experiment_worker_crash"]
        for task, endpoint, aic, number, entry, line_hash in missing:
            message, request = entry["message"], payload(entry["message"])
            matching_crash = [(n, r, h) for n, r, h in crashes
                              if r.get("incident_id") == request.get("incident_id")
                              and r.get("logical_task_id") == request.get("logical_task_id")
                              and r.get("operation_id") == request.get("operation_id")
                              and r.get("tool") == request.get("tool")]
            exact = lambda r: r.get("trace_id") == message["sessionId"] and r.get("correlation_id") == task
            a_records = [(role, p, n, r, h) for role, p, n, r, h in access if exact(r)]
            # Official MessageEmitter correlation_id is sessionId; its trace_id
            # is W3C trace context. Access uses sessionId/taskId instead.
            m_records = [(role, p, n, r, h) for role, p, n, r, h in amp
                         if r.get("correlation_id") == message["sessionId"]
                         and r.get("body", {}).get("messageId") == message["id"]
                         and role in {"coordinator", roles.get(entry["worker_aic"])}]
            received = [(n, r, h) for n, r, h in captures if r.get("direction") == "receive"
                        and r["message"].get("taskId") == task and r["message"].get("sessionId") == message["sessionId"]]
            crash = matching_crash[0][1] if len(matching_crash) == 1 else {}
            findings.append({"key": item["key"], "case": item["case"], "fault_point": item["point"],
                "task_key_sha256": sha(json.dumps([message["sessionId"], task], separators=(",", ":")).encode()),
                "request_sha256": sha(canonical(request)), "missing_endpoint": endpoint,
                "missing_role": roles.get(aic), "sender_role": roles.get(message["senderId"]),
                "callee_role": roles.get(entry["worker_aic"]), "kind": symbolic(request.get("kind")),
                "skill": symbolic(request.get("skill")), "tool": symbolic(request.get("tool")),
                "start": {**location(messages_path, number, line_hash), "sent_at": message.get("sentAt")},
                "captured_result_states": [{**location(messages_path, n, h),
                    "state": r["message"].get("status", {}).get("state"), "sent_at": r["message"].get("sentAt")} for n, r, h in received],
                "access_present": [{**location(p, n, h), "role": role, "timestamp": r.get("timestamp"),
                    "response_status": r.get("body", {}).get("response", {}).get("statusCode")} for role, p, n, r, h in a_records],
                "amp_edges": [{**location(p, n, h), "role": role, "timestamp": r.get("timestamp"),
                    "event": r.get("body", {}).get("eventType"), "operation": r.get("body", {}).get("operationName")} for role, p, n, r, h in m_records],
                "crash_matches": [{**location(trace_path, n, h), "exit_code": r.get("exit_code"),
                    "fault_point": r.get("crash_point"), "ledger_state": r.get("ledger_state"),
                    "AIP_product_submitted": r.get("AIP_product_submitted")} for n, r, h in matching_crash],
                "worker_actual_exit_code": result.get("worker_exit_and_mcp", {}).get("actual_exit_code"),
                "case_verdict": result.get("status"),
                "recorded_error_classes": {k: v for k, v in result.items() if k.endswith("error_class")},
                "cause_classification": ("exact_planned_hard_exit_before_access_finally" if len(matching_crash) == 1 else
                    "environment_failed_verification_without_terminal_access" if roles.get(aic) == "verification" else
                    "primary_timeout_without_retained_crash_trace_cause_unresolved"),
                "evidence_checks": {"missing_addressed_callee": endpoint == "callee" and aic == entry["worker_aic"],
                    "caller_access_present": any(role == "coordinator" for role, *_ in a_records),
                    "no_callee_access_in_frozen_snapshots": not any(role == "database" for role, *_ in a_records),
                    "not_AIP_completed": not any(r["message"].get("status", {}).get("state") == "completed" for _, r, _ in received)},
                "causal_evidence": {"one_exact_crash_trace": len(matching_crash) == 1,
                    "crash_matches_planned_point": crash.get("crash_point") == item["point"],
                    "observed_worker_exit_matches_crash_marker": bool(crash) and result.get("worker_exit_and_mcp", {}).get("actual_exit_code") == crash.get("exit_code"),
                    "callee_Start_delivery_edge_present": any(role == roles.get(aic) and r.get("body", {}).get("eventType") == "receive" for role, _, _, r, _ in m_records)}})
        if item["case"] == "E1-c":
            markers = [(n, r, h) for n, r, h in trace if r.get("event") in {
                "experiment_worker_suspended", "experiment_worker_revived", "experiment_stale_request_result"}]
            original_message = next((r["message"] for _, r, _ in captures if r.get("direction") == "send"
                            and sha(canonical(payload(r["message"]))) == markers[0][1]["request_sha256"]), None)
            primary_access = [(p, n, r, h) for role, p, n, r, h in access if role == "database"
                              and r.get("trace_id") == original_message["sessionId"]
                              and r.get("correlation_id") == original_message["taskId"]] if original_message else []
            controls.append({"key": item["key"], "missing_endpoints": len(missing),
                "incomplete_AIP_lifecycle_count": reports[item["key"]]["incomplete_task_lifecycles"],
                "original_primary_access_count": len(primary_access),
                "original_primary_access": [{**location(p, n, h), "timestamp": r.get("timestamp")} for p, n, r, h in primary_access],
                "markers": [{**location(trace_path, n, h), "event": r["event"],
                    "request_sha256": r["request_sha256"], "operation_state": r.get("operation_state")} for n, r, h in markers]})
        case_totals.append({"key": item["key"], "missing_endpoints": len(missing)})
    code_paths = ["eval/reconcile_access.py", "acps_mcp_bridge/experiment.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/amp/access_emitter.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_leader.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_partner.py",
        "docs/高分方案_需求架构创新与任务_20261017.md"]
    code = [{"path": p, "team_sha256": sha(raw(TEAM / p)), "batch_sha256": sha(raw(CHECKOUT / p)),
             "same_bytes": raw(TEAM / p) == raw(CHECKOUT / p)} for p in code_paths]
    output = {"schema": "missing-access-endpoint-diagnosis/1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "team_baseline": "634c46d7404dc2f8cb7f57964367d5997bf8adb3", "original_T05_passed": doc(original_path)["endpoint_access_match_passed"],
        "original_totals": {k: sum(r[k] for r in reports.values()) for k in ("captured_start_tasks", "expected_access_records",
            "actual_access_records", "missing_records", "extra_records", "incomplete_task_lifecycles")},
        "missing_endpoints": findings, "contrast_controls": controls, "case_totals": case_totals,
        "summary": {"missing_count": len(findings), "missing_roles": dict(Counter(r["missing_role"] for r in findings)),
            "missing_sides": dict(Counter(r["missing_endpoint"] for r in findings)),
            "by_fault_point": dict(Counter(r["fault_point"] for r in findings)),
            "cause_classifications": dict(Counter(r["cause_classification"] for r in findings)),
            "all_checks_passed": all(all(r["evidence_checks"].values()) for r in findings)},
        "source_code": code,
        "inputs": [{"source": label(p), "sha256": sha(value), "bytes": len(value)} for p, value in sorted(CACHE.items())],
        "limits": ["Original closed T05 verdict remains false; no endpoint record is synthesized or removed.",
            "Trace markers have no wall-clock timestamp; their per-file order and exact request identity are retained without inventing times.",
            "AMP receive is transport-edge evidence, not an application completion or broker-wide inventory.",
            "No Docker, WSL, network, model, platform, fault or business request was invoked."],
        "script_sha256": sha(Path(__file__).read_bytes()), "raw_sources_unchanged": all(p.read_bytes() == value for p, value in CACHE.items())}
    assert len(findings) == output["original_totals"]["missing_records"] == 18
    with (HERE / "missing-access-diagnosis-final.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": output["summary"], "raw_sources_unchanged": output["raw_sources_unchanged"],
        "source_code_matches": all(r["same_bytes"] for r in code), "output_sha256": sha((HERE / "missing-access-diagnosis-final.json").read_bytes())}))
    return 0 if output["summary"]["all_checks_passed"] and output["raw_sources_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
