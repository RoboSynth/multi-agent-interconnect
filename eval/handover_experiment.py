"""E1-b local process handover comparison, optionally preceded by E1-a.

All strategies share resource ledgers, operation IDs, fences, approvals, tools,
budgets and remaining repairs. Only transferred evidence representation differs.
The deterministic continuation uses no model: model calls and tokens are zero.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from incident.contracts import handover_evidence
from incident.local_transport import LocalAipStdioTransport
from eval import resume_experiment
from eval.resume_support import (save, freeze_sources, assert_worker_sources, authority_snapshot,
                                 baseline_health, semantic_history)

METHODS = ("from_scratch", "full_history", "resume_package")


def fresh_facts(handover, now=None):
    """Same TTL and latest-observation rule for history and structured package."""
    now = time.time() if now is None else now
    strategy = handover["strategy"]
    if strategy == "from_scratch":
        references = []
    elif strategy == "full_history":
        facts = [fact for item in handover["conversation"] if item["direction"] == "product"
                 for fact in item["product"].get("facts", [])]
        references = handover_evidence(facts, handover["evidence_ttl_seconds"])
    elif strategy == "resume_package":
        references = handover["package"]["evidence_refs"]
    else:
        raise ValueError("unknown handover strategy")
    latest = {}
    for ref in references:
        if not isinstance(ref.get("expires_at"), (int, float)) or ref["expires_at"] <= now:
            continue
        fact = ref["fact"]
        previous = latest.get(fact["key"])
        if previous is None or fact["observed_at"] >= previous["observed_at"]:
            latest[fact["key"]] = fact
    return latest


class HandoverRecorder:
    def __init__(self, method, transport, output):
        self.method, self.transport, self.output = method, transport, output
        self.transfer = None
        self.metrics = None

    def __call__(self, default, package):
        history = semantic_history(self.transport.messages_path, default["incident_id"])
        # Native lifecycle messages are kept separately. This includes every
        # genuine business request/product before failure, including a request
        # that has no response because its participant exited.
        save(self.output / "prior-business-conversation.json", history)
        common = {"strategy": self.method, "goal": "Restore original order workflow and verify it",
                  "evidence_ttl_seconds": self.transport.config.get("evidence_ttl_seconds", 60)}
        original = next((item["payload"] for item in reversed(history) if item["direction"] == "request"
                         and item["payload"].get("operation_id") == default["operation_id"]), None)
        if original is None:
            raise ValueError("actual pre-crash operation request was not captured")
        common["control"] = {"operation_id": default["operation_id"], "original_fence": original["fence"],
                             "replacement_fence": default["fence"]}
        if self.method == "full_history":
            transfer = {**common, "conversation": history}
        elif self.method == "resume_package":
            package.remaining_tasks.extend([
                {"kind": "act", "tool": "application.pool_rebuild", "args": {},
                 "requires_fact": "application_pool_revision", "bind_argument": "expected_revision"},
                {"kind": "verify", "tool": "incident.verification", "args": {}}])
            transfer = {**common, "package": package.to_dict()}
        else:
            transfer = common
        args = {key: value for key, value in default["args"].items() if key != "resume_package"}
        args["handover"] = transfer
        if self.method == "resume_package":
            args["resume_package"] = transfer["package"]
        payload = {**default, "args": args}
        # Match _call_worker's exact JSON text serialization. Raw AIP envelope
        # overhead is captured separately in transport/messages.jsonl.
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        information = json.dumps(transfer, ensure_ascii=False).encode("utf-8")
        self.transfer = transfer
        self.metrics = {"resume_ifc_payload_utf8_bytes": len(encoded), "handover_information_utf8_bytes": len(information),
            "handover_information_estimated_tokens_bytes_div_4": len(information)/4,
            "token_estimate_method": "UTF-8 bytes / 4; not a tokenizer count or model usage",
            "model_calls": 0, "model_tokens": 0,
            "original_operation_id": common["control"]["operation_id"], "original_fence": original["fence"],
            "replacement_fence": payload["fence"], "logical_task_id": payload["logical_task_id"]}
        save(self.output / "handover-payload.json", payload)
        save(self.output / "handover-metrics.json", self.metrics)
        return payload


async def run_case(args, base, output, method, repeat):
    output.mkdir(parents=True, exist_ok=False)
    incident = "E1b-"+method+"-"+uuid.uuid4().hex[:10]
    config = resume_experiment.experiment_config(base, output, "after_applied", args.backup_bridge,
                                               incident, args.verification_duration)
    save(output / "coordinator-experiment.json", config)
    def event(row):
        with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
    transport = LocalAipStdioTransport(config, on_event=event)
    recorder = HandoverRecorder(method, transport, output)
    transport.resume_payload_factory = recorder
    products = []
    result = {"experiment_id": incident, "method": method, "repeat": repeat, "crash_point": "after_applied",
        "transport": transport.mode, "discovery": "local process directory", "platform_adp_verified": False,
        "status": "failed", "model_calls": 0, "model_tokens": 0,
        "budgets": {"tasks": 40, "deadline_seconds": 600, "model_calls": 0, "model_tokens": 0},
        "started_at": datetime.now(timezone.utc).isoformat()}
    started, setup = time.monotonic(), False
    async def call(label, kind, tool, arguments=None, *, operation_id=None, approve=False, deadline=15000):
        if len(products) >= 40 or time.monotonic()-started > 600:
            raise RuntimeError("shared task/time budget exhausted")
        payload = {"incident_id": incident, "logical_task_id": incident+":"+label,
                   "kind": kind, "tool": tool, "args": arguments or {}, "budget": {"deadline_ms": deadline}}
        if operation_id:
            payload.update(operation_id=operation_id, fence={"coordinator_term": transport.term, "takeover_version": 0})
        if approve:
            if not args.approve_high:
                raise RuntimeError("isolated high-risk repair not preauthorized")
            before = time.monotonic()
            payload["approval"] = transport.issue_approval(payload)
            result["approval_seconds"] = time.monotonic()-before
        product = await transport.call(payload)
        products.append({"payload": payload, "product": product})
        save(output / "business-products.json", products)
        if product["status"] != "ok":
            raise RuntimeError("business task did not complete: "+label+":"+product["status"])
        return payload, product
    try:
        await transport.start()
        setup = True
        await resume_experiment.inject("restore", args.runtime, output / "private/injections.jsonl")
        result["baseline_health"] = await baseline_health(transport, incident_id=incident+":baseline")
        result["authority_before"] = authority_snapshot(transport)
        if not result["baseline_health"]["passed"]:
            raise RuntimeError("healthy baseline was not established")
        await resume_experiment.inject("apply", args.runtime, output / "private/injections.jsonl")
        # Identical pre-crash information collection for every strategy.
        await call("application-status", "observe", "application.status")
        await call("database-status", "observe", "db.read_only_status")
        operation_id = incident+":restore-writes"
        original, db_result = await call("restore-writes", "act", "db.restore_writes", operation_id=operation_id, approve=True)
        if recorder.transfer is None:
            raise RuntimeError("declared interruption did not trigger handover")
        native_resume_sizes, transmitted = [], None
        for line in transport.messages_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry["direction"] != "send" or entry["message"].get("command") != "start":
                continue
            for item in entry["message"].get("dataItems", []):
                if "text" in item and json.loads(item["text"]).get("kind") == "resume":
                    native_resume_sizes.append(len(item["text"].encode("utf-8")))
                    transmitted = json.loads(item["text"])
        if native_resume_sizes != [recorder.metrics["resume_ifc_payload_utf8_bytes"]]:
            raise RuntimeError("handover byte count does not match native transmitted IFC text")
        recorder.metrics["native_transmitted_ifc_text_bytes"] = native_resume_sizes[0]
        received_handover = transmitted["args"]["handover"]
        received_digest = hashlib.sha256(json.dumps(received_handover, ensure_ascii=False, sort_keys=True,
                                                    separators=(",", ":")).encode("utf-8")).hexdigest()
        if db_result.get("handover_sha256") != received_digest:
            raise RuntimeError("replacement did not acknowledge this actual handover information")
        recorder.metrics["replacement_acknowledged_handover_sha256"] = received_digest
        save(output / "handover-metrics.json", recorder.metrics)
        resumed_at = time.monotonic()
        # Stateless deterministic continuation consumes the actual transmitted
        # representation acknowledged by the replacement, not recorder memory.
        reusable = fresh_facts(received_handover)
        revision_fact = reusable.get("application_pool_revision")
        additional_observations = 0
        if revision_fact is None or type(revision_fact["value"]) is not int:
            _, status = await call("resume-application-status", "observe", "application.status")
            additional_observations += 1
            revision_fact = next((fact for fact in status.get("facts", []) if fact["key"] == "application_pool_revision"), None)
        if revision_fact is None or type(revision_fact["value"]) is not int:
            raise RuntimeError("no valid application revision")
        _, pool = await call("pool-rebuild", "act", "application.pool_rebuild", {"expected_revision": revision_fact["value"]},
                             operation_id=incident+":pool-rebuild")
        _, verified = await call("verify", "verify", "incident.verification", deadline=120000)
        facts = {fact["key"]: fact["value"] for fact in verified.get("facts", [])}
        # Explicit old-token probe uses the original identity and never passes
        # through normal call()'s active-fence routing adjustment.
        stale = await transport.call_on_worker("local-database-backup", original)
        events = resume_experiment.system_events(transport.amp_directory)
        writes = [row for row in events if row["event"] == "mcp_modify_invocation" and row.get("operation_id") == operation_id]
        takeovers = [row for row in transport.events if row["event"] == "takeover_completed"]
        crashes = [row for row in events if row["event"] == "experiment_worker_crash"]
        rejected = stale.get("status") == "rejected" and stale.get("operation", {}).get("state") == "rejected_stale_fence"
        result.update(handover=recorder.metrics, additional_post_handover_observations=additional_observations,
            reused_fact_keys=sorted(reusable), revision_fact=revision_fact, database_result=db_result,
            pool_result=pool, business_verification=facts, old_fence_replay=stale, old_fence_rejected=rejected,
            db_mcp_modify_invocations=len(writes), duplicate_modifying_calls=max(0, len(writes)-1),
            modification_invocations=writes, takeovers=takeovers, crash_records=crashes,
            remaining_workflow_including_verification_seconds=time.monotonic()-resumed_at,
            actual_attempt_count=len(transport.journal.list_tasks()), task_count=len(products))
        result["status"] = "passed" if (facts.get("business_recovered") is True and len(writes) == 1 and
            len(takeovers) == len(crashes) == 1 and rejected and
            db_result.get("operation", {}).get("state") == "skipped_already_applied" and
            pool.get("operation", {}).get("state") == "applied") else "failed"
    except Exception as exc:
        result.update(status="failed", error_class=type(exc).__name__, error=str(exc))
    finally:
        try:
            if setup:
                await resume_experiment.inject("restore", args.runtime, output / "private/injections.jsonl")
                result["cleanup_health"] = await baseline_health(transport, incident_id=incident+":cleanup")
                result["authority_after"] = authority_snapshot(transport, incident)
                if not result["cleanup_health"]["passed"]:
                    raise RuntimeError("cleanup did not establish healthy baseline")
            result["cleanup"] = "restored" if setup else "not_needed"
        except Exception as exc:
            result.update(status="failed", cleanup="failed", cleanup_error=str(exc))
        await transport.close()
        result.setdefault("domain_system_events", resume_experiment.system_events(transport.amp_directory))
        result.setdefault("takeovers", [row for row in transport.events if row["event"] == "takeover_completed"])
        result["elapsed_seconds"] = time.monotonic()-started
        save(output / "results.json", result)
    return result


async def run(args):
    if args.repeats < 1 or args.verification_duration < 30:
        raise ValueError("positive repeats and at least 30 seconds of verification required")
    output = args.output or ROOT / "eval/results/local" / ("E1-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    manifest = freeze_sources(output)
    print(json.dumps({"event": "E1_SOURCE_PREPARED" if args.prepare_only else "E1_SOURCE_FROZEN", "manifest": str(output / "source-manifest.json"),
                      "frozen_at": manifest["frozen_at"]}), flush=True)
    if args.prepare_only:
        health = await baseline_health()
        save(output / "health-preflight.json", health)
        save(output / "preparation.json", {"state": "ready_for_explicit_resource_authorization",
            "resources_modified": False, "domain_workers_started": False,
            "scope": "E1a 3 crash points x 3 repeats plus E1b 3 information strategies x 3 repeats",
            "source_manifest": "source-manifest.json", "health_preflight": "health-preflight.json",
            "runtime_source_imports": "preparation process exits; execution will import and freeze its own source version"})
        return 0 if health["passed"] else 1
    base = json.loads(args.config.read_text(encoding="utf-8-sig"))
    save(output / "experiment.json", {"E1a": {"points": list(resume_experiment.POINTS), "repeats": args.repeats},
        "E1b": {"point": "after_applied", "methods": list(METHODS), "repeats": args.repeats,
            "ordering": "rotate starting method by repeat", "model_calls": 0, "model_tokens": 0,
            "shared_safety": "original identity/fence, signed approval, domain ledger, remaining pool repair and 30s/10 workflows",
            "payload_metric": "UTF8 bytes and bytes/4 estimated tokens, separate from zero actual model usage"},
        "source_manifest": "source-manifest.json"})
    e1a_status = 0
    if args.include_breakpoints:
        breakpoint_args = deepcopy(args)
        breakpoint_args.output = output / "E1a"
        breakpoint_args.crash_points = ",".join(resume_experiment.POINTS)
        breakpoint_args.frozen_manifest = manifest
        e1a_status = await resume_experiment.run(breakpoint_args)
        rows = json.loads((output / "E1a/results.json").read_text(encoding="utf-8"))
        if any(row.get("cleanup") != "restored" for row in rows):
            return 1
    results = []
    for repeat in range(args.repeats):
        methods = METHODS[repeat % len(METHODS):]+METHODS[:repeat % len(METHODS)]
        for method in methods:
            assert_worker_sources(manifest)
            result = await run_case(args, base, output / "E1b" / (method+"-"+str(repeat+1)), method, repeat+1)
            results.append(result)
            save(output / "E1b/results.json", results)
            print(json.dumps({key: result.get(key) for key in ("method", "repeat", "status", "db_mcp_modify_invocations",
                "additional_post_handover_observations", "elapsed_seconds", "cleanup", "error")}), flush=True)
            if result.get("cleanup") != "restored":
                return 1
    save(output / "summary.json", {"E1a_exit_code": e1a_status, "E1b_cases": len(results),
        "E1b_passed": sum(row["status"] == "passed" for row in results), "model_calls": 0, "model_tokens": 0,
        "platform_adp_verified": False})
    return 0 if e1a_status == 0 and all(row["status"] == "passed" for row in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/local-coordinator.json")
    parser.add_argument("--backup-bridge", type=Path, default=ROOT / "runtime/database-backup-bridge.json")
    parser.add_argument("--runtime", type=Path, default=ROOT / "deploy/native-runtime.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--verification-duration", type=float, default=30)
    parser.add_argument("--include-breakpoints", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Copy sources and GET public health endpoints; no workers or injection")
    parser.add_argument("--approve-high", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
