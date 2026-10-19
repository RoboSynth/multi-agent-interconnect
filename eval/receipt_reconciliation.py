"""Observe preserved unknown order intents with bounded, GET-only local requests."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.load import VersionedClient
from business.receipts import validate_committed_receipt

KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
DIGEST = re.compile(r"[0-9a-f]{64}")
TOTAL_DEADLINE_SECONDS = 8


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def local_base_url(value):
    """Only the explicitly selected loopback service; no DNS or URL credentials."""
    try:
        url = urlsplit(value)
        valid = (url.scheme == "http" and url.hostname == "127.0.0.1" and url.port is not None
                 and not url.username and not url.password and url.path in ("", "/")
                 and not url.query and not url.fragment)
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("base_url_must_be_explicit_http_127_0_0_1_port")
    return value.rstrip("/")


def original_intent(summary, trace):
    """Derive the operation from preserved observer state and replay its trace."""
    pending = summary["state"]["pending"]
    if len(pending) != 1 or summary["unresolved_intents"] != 1:
        raise ValueError("exactly_one_preserved_pending_intent_required")
    intent = pending[0]
    create_key, cancel_key = intent["request_key"], intent["operation_key"]
    if (not isinstance(create_key, str) or not KEY.fullmatch(create_key)
            or not isinstance(cancel_key, str) or not KEY.fullmatch(cancel_key)
            or cancel_key != create_key + "-cancel"
            or not isinstance(intent["item"], str) or not 1 <= len(intent["item"]) <= 200
            or type(intent["quantity"]) is not int or not 1 <= intent["quantity"] <= 10000
            or type(intent["was_unknown"]) is not bool):
        raise ValueError("invalid_preserved_order_intent")
    order_id = intent.get("order_id")
    if order_id is not None:
        if not isinstance(order_id, str):
            raise ValueError("invalid_preserved_order_id")
        uuid.UUID(order_id)
    if any(row["request_key"] == create_key for row in summary["state"]["completed"]):
        raise ValueError("pending_intent_already_in_completed_state")
    count = summary["requests"]
    if type(count) is not int or not 0 <= count <= len(trace):
        raise ValueError("summary_trace_counts_mismatch")
    # ContinuousObserver records warmup too, but its summary counts only the
    # suffix after fault_at. Direct OrderObserver summaries count the whole trace.
    continuous = {"requests_per_second", "http_timeout_seconds", "observation_deadline_exhausted"} <= set(summary)
    relevant = trace[len(trace) - count:] if continuous else trace
    if len(relevant) != count or any(
            sum(row["outcome"] == outcome for row in relevant) != summary[outcome]
            for outcome in ("success", "failed", "unknown")):
        raise ValueError("summary_trace_counts_mismatch")
    own = [row for row in trace if row["request_key"] == create_key]
    if not own:
        raise ValueError("original_intent_has_no_trace")
    phase, resume, was_unknown = "create", None, False
    posts = {"create": [], "cancel": []}
    for row in own:
        if phase == "terminal" or row["phase"] != phase:
            raise ValueError("original_trace_phase_mismatch")
        key = create_key if resume == "create" else cancel_key
        expected = {"create": ("POST", "/orders"), "query": ("GET", f"/orders/{order_id}"),
                    "cancel": ("POST", f"/orders/{order_id}/cancel"),
                    "resolve": ("GET", "/receipts/" + key)}[phase]
        if (row["method"], row["path"]) != expected or (phase in {"query", "cancel"} and not order_id):
            raise ValueError("original_trace_method_path_mismatch")
        outcome, status = row["outcome"], row.get("http_status")
        if outcome not in {"success", "failed", "unknown"}:
            raise ValueError("invalid_original_trace_outcome")
        if phase in posts:
            posts[phase].append(row)
        if outcome == "success":
            if type(status) is not int or not 200 <= status < 300:
                raise ValueError("original_trace_success_without_success_response")
            if phase == "create" or (phase == "resolve" and resume == "create"):
                if not order_id:
                    raise ValueError("original_create_success_missing_order_id")
                phase = "query"
            else:
                phase = "cancel" if phase == "query" else "terminal"
        elif outcome == "unknown":
            if not ((status is None and isinstance(row.get("error"), str))
                    or (type(status) is int and (status >= 500 or (phase == "resolve" and status == 404)))):
                raise ValueError("original_trace_unknown_without_unknown_response")
            was_unknown = True
            if phase in posts:
                resume, phase = phase, "resolve"
            elif phase == "resolve":
                phase = resume
    if phase != intent["phase"] or was_unknown != intent["was_unknown"]:
        raise ValueError("preserved_intent_disagrees_with_trace")
    if intent.get("resume_phase") != resume:
        raise ValueError("preserved_resume_phase_disagrees_with_trace")
    if resume is not None and intent.get("unknown_key") != (create_key if resume == "create" else cancel_key):
        raise ValueError("preserved_unknown_key_disagrees_with_trace")
    operation = resume if phase == "resolve" else phase
    if operation not in posts:
        raise ValueError("pending_phase_is_not_an_unknown_order_operation")
    unsent_cancel = operation == "cancel" and not posts["cancel"]
    if not unsent_cancel and not any(row["outcome"] == "unknown" for row in posts[operation]):
        raise ValueError("pending_operation_has_no_original_unknown_POST")
    return {"intent": intent, "operation_kind": operation,
            "operation_key": create_key if operation == "create" else cancel_key,
            "unsent_cancel": unsent_cancel, "original_POST_attempts": len(posts[operation])}


def prepare(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if set(manifest) != {"schema_version", "base_url", "entries"} or manifest["schema_version"] != 1:
        raise ValueError("unsupported_manifest")
    base_url = local_base_url(manifest["base_url"])
    entries = manifest["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError("manifest_requires_1_to_64_entries")
    inputs = {str(manifest_path): sha(raw)}
    jobs, labels, keys = [], set(), set()
    for entry in entries:
        if set(entry) != {"label", "summary", "trace"} or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", entry["label"]):
            raise ValueError("invalid_manifest_entry")
        if entry["label"] in labels:
            raise ValueError("duplicate_entry_label")
        values = {}
        paths = []
        for kind in ("summary", "trace"):
            spec = entry[kind]
            if set(spec) != {"path", "sha256"} or not DIGEST.fullmatch(spec["sha256"]):
                raise ValueError("source_path_and_sha256_required")
            path = (manifest_path.parent / spec["path"]).resolve()
            data = path.read_bytes()
            if sha(data) != spec["sha256"]:
                raise ValueError("preserved_input_sha256_mismatch")
            inputs[str(path)] = spec["sha256"]
            paths.append(path)
            values[kind] = (json.loads(data) if kind == "summary" else
                            [json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()])
        if len(set(paths + [manifest_path])) != 3:
            raise ValueError("manifest_summary_trace_must_be_distinct")
        job = original_intent(values["summary"], values["trace"])
        if job["operation_key"] in keys:
            raise ValueError("duplicate_original_operation_key")
        labels.add(entry["label"])
        keys.add(job["operation_key"])
        jobs.append(dict(job, label=entry["label"]))
    return {"base_url": base_url, "inputs": inputs, "jobs": jobs}


def sources_unchanged(prepared):
    try:
        return all(sha(Path(path).read_bytes()) == digest for path, digest in prepared["inputs"].items())
    except OSError:
        return False


def describe(prepared):
    return {"status": "PREPARED_NO_REQUESTS_SENT", "base_url": prepared["base_url"],
            "maximum_GETs": sum(not job["unsent_cancel"] for job in prepared["jobs"]), "POSTs": 0,
            "GET_total_deadline_seconds": TOTAL_DEADLINE_SECONDS,
            "input_sha256": prepared["inputs"],
            "intents": [{"label": job["label"], "operation_kind": job["operation_kind"],
                         "operation_key_sha256": sha(job["operation_key"].encode()),
                         "original_POST_attempts": job["original_POST_attempts"],
                         "unsent_cancel": job["unsent_cancel"]} for job in prepared["jobs"]]}


async def observe(prepared, client):
    rows = []
    checked = VersionedClient(client, expected_api_version="v2")
    for job in prepared["jobs"]:
        row = {"label": job["label"], "operation_kind": job["operation_kind"],
               "operation_key_sha256": sha(job["operation_key"].encode()), "observed_at_utc": utc(),
               "GET_attempts": 0, "operation_commit_confirmed": False, "workflow_terminal_confirmed": False,
               "status": "unknown", "manual_required": True}
        if job["unsent_cancel"]:
            row.update(status="not_submitted", reason="original_cancel_never_submitted_in_trace")
            rows.append(row)
            continue
        row["GET_attempts"] = 1
        try:
            response = await asyncio.wait_for(
                checked.request("GET", prepared["base_url"] + "/receipts/" + quote(job["operation_key"], safe="")),
                timeout=TOTAL_DEADLINE_SECONDS)
            row.update(http_status=response.status_code, response_sha256=sha(response.content))
            if response.status_code != 200:
                row["reason"] = "receipt_not_found_execution_not_disproved" if response.status_code == 404 else "receipt_query_inconclusive"
            else:
                intent = job["intent"]
                body = validate_committed_receipt(response.json(), job["operation_key"],
                    operation_kind=job["operation_kind"], order_id=intent.get("order_id"))
                order = body["order"]
                if (order["request_key"] != intent["request_key"] or order.get("item") != intent["item"]
                        or type(order.get("quantity")) is not int or order["quantity"] != intent["quantity"]):
                    raise ValueError("receipt_original_order_content_mismatch")
                terminal = job["operation_kind"] == "cancel"
                row.update(status="committed", reason="original_cancel_commit_confirmed" if terminal else "original_create_commit_only",
                           operation_commit_confirmed=True, workflow_terminal_confirmed=terminal,
                           manual_required=not terminal, receipt_order_id_sha256=sha(body["order_id"].encode()))
        except TimeoutError:
            row.update(reason="receipt_total_deadline_exceeded", error_class="TimeoutError")
        except httpx.TransportError as error:
            row.update(reason="receipt_transport_error", error_class=type(error).__name__)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            row.update(reason="receipt_contract_or_original_binding_invalid", error_class=type(error).__name__)
        rows.append(row)
    return rows


async def run(prepared, output, *, transport=None):
    """The transport argument is for offline MockTransport tests, never a CLI option."""
    if not sources_unchanged(prepared):
        raise ValueError("preserved_inputs_changed_before_run")
    output = Path(output).resolve()
    if any(output == Path(path) or output in Path(path).parents for path in prepared["inputs"]):
        raise ValueError("output_would_contain_preserved_input")
    output.mkdir(parents=True, exist_ok=False)
    with (output / "scope.json").open("x", encoding="utf-8") as handle:
        json.dump(describe(prepared), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    # HTTPTransport has zero retries; MockTransport is used only by offline tests.
    async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False,
                                  transport=transport or httpx.AsyncHTTPTransport(retries=0)) as client:
        rows = await observe(prepared, client)
    result = {"status": "READ_ONLY_RECEIPTS_OBSERVED", "observed_at_utc": utc(), "intents": rows,
              "actual_GET_attempts": sum(row["GET_attempts"] for row in rows), "POSTs": 0,
              "GET_total_deadline_seconds": TOTAL_DEADLINE_SECONDS,
              "original_inputs_unchanged": sources_unchanged(prepared),
              "input_sha256": prepared["inputs"], "base_url": prepared["base_url"],
              "original_results_rewritten": False, "raw_keys_order_ids_response_bodies_included": False,
              "interpretation": "A receipt confirms an original commit snapshot. A create commit is not a complete workflow; 404 does not prove non-execution. Original results remain unchanged."}
    with (output / "result.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="one GET per sent-unknown intent; unsent cancels are skipped")
    parser.add_argument("--output", type=Path, help="new, previously nonexistent output directory")
    args = parser.parse_args(argv)
    if args.run and args.output is None:
        parser.error("--run requires --output")
    if not args.run and args.output is not None:
        parser.error("--output is only used with --run")
    prepared = prepare(args.manifest)
    result = asyncio.run(run(prepared, args.output)) if args.run else describe(prepared)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if args.run:
        return 0 if result["original_inputs_unchanged"] and all(
            row.get("reason") not in {"receipt_transport_error", "receipt_total_deadline_exceeded", "receipt_contract_or_original_binding_invalid", "receipt_query_inconclusive"}
            for row in result["intents"]) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
