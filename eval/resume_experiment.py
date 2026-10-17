"""F15 native-process experiment with three precise database-worker crashes.

This is an explicit local-aip-stdio experiment using a local process directory.
It does not demonstrate platform ADP discovery or AMQPS/mTLS failover. Injection
truth and resource credentials stay in the separate evaluator/domain processes.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from incident.coordinator.engine import IncidentCoordinator
from incident.local_transport import LocalAipStdioTransport
from eval.resume_support import (save, freeze_sources, assert_worker_sources,
                                 authority_snapshot, baseline_health)

POINTS = ("after_observation", "before_modification", "after_applied")


def export_journal_transmissions(journal_path, destination):
    """Export existing evidence without inventing missing TaskCommand fields.

    Older runs retained outgoing IFC payloads and exact incoming TaskResults.
    They did not retain the outgoing command id/sentAt. New transport runs also
    capture exact send/receive messages in transport/messages.jsonl.
    """
    rows, resume_results = [], []
    with closing(sqlite3.connect(Path(journal_path).resolve().as_uri()+"?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        attempts = [dict(row) for row in conn.execute("SELECT * FROM task_attempts ORDER BY created_at")]
        for attempt in attempts:
            payload = json.loads(attempt["content"]) if attempt["content"] else None
            if payload is not None:
                rows.append({"direction": "send_payload", "evidence_source": "TaskJournal.content",
                    "worker_aic": attempt["partner_aic"], "attempt_id": attempt["attempt_id"],
                    "aip_task_id": attempt["task_id"], "ifc_payload": payload,
                    "limitation": "outgoing TaskCommand id and sentAt were not captured in this older run"})
            for event in conn.execute("SELECT * FROM task_events WHERE attempt_id=? AND artifact IS NOT NULL ORDER BY event_id", (attempt["attempt_id"],)):
                message = json.loads(event["artifact"])
                if not isinstance(message, dict) or message.get("type") != "task-result":
                    continue
                rows.append({"direction": "receive", "evidence_source": "TaskJournal.task_events.artifact",
                    "worker_aic": attempt["partner_aic"], "attempt_id": attempt["attempt_id"], "message": message})
                if payload and payload.get("kind") == "resume" and message.get("status", {}).get("state") == "awaiting-completion":
                    data = message["products"][0]["dataItems"][0]["data"]
                    resume_results.append({"logical_task_id": payload["logical_task_id"], "operation_id": payload.get("operation_id"),
                        "worker_aic": attempt["partner_aic"], "status": data["status"], "operation": data.get("operation"),
                        "active_fence": data.get("active_fence")})
    Path(destination).write_text("".join(json.dumps(row, ensure_ascii=False)+"\n" for row in rows), encoding="utf-8")
    return {"native_attempts": len(attempts), "outgoing_ifc_payloads": sum(r["direction"] == "send_payload" for r in rows),
            "exact_incoming_task_results": sum(r["direction"] == "receive" for r in rows), "resume_results": resume_results}


async def inject(action, runtime, record):
    process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "eval/inject.py"), "F07", action,
        "--backend", "native", "--runtime", str(runtime), "--record", str(record),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    # Separate evaluator diagnostics stay private; the coordinator receives no
    # resource credentials or fault truth from these files.
    diagnostics = Path(record).parent / ("inject-"+action+"-"+uuid.uuid4().hex[:8])
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.with_suffix(".stdout.log").write_bytes(stdout)
    diagnostics.with_suffix(".stderr.log").write_bytes(stderr)
    if process.returncode:
        # Injector stderr can contain process/resource diagnostics; preserve its
        # own logs rather than returning credentials through coordinator evidence.
        raise RuntimeError("separate F15 setup/cleanup injector failed")


def experiment_config(base, output, point, backup_bridge, experiment_id, verification_duration=30):
    config = deepcopy(base)
    config.update(experiment_id=experiment_id, allow_experiment_crash=True, automatic_takeover=True,
                  journal_path=str(output / "attempts.sqlite"), amp_directory=str(output / "amp"),
                  directory=str(output / "transport"))
    primary = next(w for w in config["workers"] if w["role"] == "database" and not w.get("standby"))
    primary.update(crash_point=point, crash_tool="db.read_only_status" if point == "after_observation" else "db.restore_writes")
    backup = {**primary, "name": "database-backup", "aic": "local-database-backup", "standby": True,
              "bridge_config": str(backup_bridge)}
    backup.pop("crash_point", None)
    backup.pop("crash_tool", None)
    config["workers"] = [w for w in config["workers"] if not (w["role"] == "database" and w.get("standby"))] + [backup]
    for worker in config["workers"]:
        if worker["role"] == "application":
            worker["ledger_path"] = str(ROOT / "runtime/application-operations.sqlite")
        if worker["role"] == "verification":
            worker["verification_duration"] = verification_duration
    return config


def system_events(directory):
    rows = []
    for path in directory.glob("amp_system_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("body", {}).get("event") in ("mcp_modify_invocation", "mcp_modify_returned", "experiment_worker_crash"):
                rows.append({"aic": row["aic"], "timestamp": row["timestamp"], **row["body"]})
    return rows


async def run_case(args, base, output, point):
    output.mkdir(parents=True, exist_ok=False)
    experiment_id = "F15-" + point + "-" + uuid.uuid4().hex[:10]
    config = experiment_config(base, output, point, args.backup_bridge, experiment_id, args.verification_duration)
    config_path = output / "coordinator-experiment.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    events_path = output / "events.jsonl"
    def on_event(event):
        with events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False)+"\n")
    transport = LocalAipStdioTransport(config_path, on_event=on_event)
    state = None
    setup_started = False
    result = {"experiment_id": experiment_id, "crash_point": point, "transport": transport.mode,
              "discovery": "local process directory", "platform_adp_verified": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "failed"}
    started = time.monotonic()
    try:
        await transport.start()
        setup_started = True
        await inject("restore", args.runtime, output / "private/injections.jsonl")
        result["baseline_health"] = await baseline_health(transport, incident_id=experiment_id+":baseline")
        result["authority_before"] = authority_snapshot(transport)
        if not result["baseline_health"]["passed"]:
            raise RuntimeError("healthy baseline was not established")
        await inject("apply", args.runtime, output / "private/injections.jsonl")
        engine = IncidentCoordinator(transport, output / "incidents", term=transport.term,
                                     approval_issuer=transport.issue_approval)
        state = engine.new("订单写入异常，请各资源域据观察诊断并恢复，确认原业务流程完成。")
        pending = asyncio.create_task(engine.run(state))
        while not pending.done():
            for approval in list(state["approvals"]):
                if approval["status"] == "pending":
                    engine.decide(approval["id"], bool(args.approve_high))
            await asyncio.sleep(0.05)
        await pending
        result.update(incident_id=state["id"], incident_status=state["status"], coordinator_term=transport.term,
                      model_source=state["model_source"], model_tokens=state["tokens"], model_calls=engine.hypothesis.calls)
        original = next(t for t in state["tasks"] if t["kind"] == "act" and t["tool"] == "db.restore_writes")
        operation_id = state["id"] + ":restore-writes"
        stale = {"schema_version": "ifc/1.0", "incident_id": state["id"], "logical_task_id": original["logical_task_id"],
            "kind": "act", "tool": original["tool"], "args": original["args"], "operation_id": operation_id,
            "fence": {"coordinator_term": transport.term, "takeover_version": 0}, "budget": {"deadline_ms": 15000}}
        stale["approval"] = transport.issue_approval(stale)
        replay = await transport.call_on_worker("local-database-backup", stale)
        result["old_fence_replay"] = replay
        events = system_events(transport.amp_directory)
        writes = [e for e in events if e["event"] == "mcp_modify_invocation" and e.get("operation_id") == operation_id]
        takeovers = [e for e in transport.events if e["event"] == "takeover_completed"]
        crashes = [e for e in events if e["event"] == "experiment_worker_crash"]
        result.update(db_mcp_modify_invocations=len(writes), duplicate_modifying_calls=max(0, len(writes)-1),
            modification_invocations=writes, crash_records=crashes, takeovers=takeovers,
            old_fence_rejected=replay.get("status") == "rejected" and replay.get("operation", {}).get("state") == "rejected_stale_fence",
            business_verification=state.get("result"), task_count=len(state["tasks"]),
            actual_attempt_count=len(transport.journal.list_tasks()))
        passed = (state["status"] == "completed" and len(writes) == 1 and len(crashes) == 1 and len(takeovers) == 1
                  and result["old_fence_rejected"] and state.get("result", {}).get("business_recovered") is True
                  and engine.hypothesis.calls == 0 and state["tokens"] == 0)
        result["status"] = "passed" if passed else "failed"
    except Exception as exc:
        result.update(status="failed", error_class=type(exc).__name__, error=str(exc))
        if state is not None:
            result.update(incident_id=state["id"], incident_status=state["status"], incident_error=state.get("error"))
    finally:
        try:
            if setup_started:
                await inject("restore", args.runtime, output / "private/injections.jsonl")
                result["cleanup_health"] = await baseline_health(transport, incident_id=experiment_id+":cleanup")
                result["authority_after"] = authority_snapshot(transport, state["id"] if state else None)
                if not result["cleanup_health"]["passed"]:
                    raise RuntimeError("cleanup did not establish healthy baseline")
            result["cleanup"] = "restored" if setup_started else "not_needed"
        except Exception as exc:
            result.update(cleanup="failed", cleanup_error_class=type(exc).__name__, status="failed")
        await transport.close()
        result.setdefault("domain_system_events", system_events(transport.amp_directory))
        result.setdefault("takeovers", [row for row in transport.events if row["event"] == "takeover_completed"])
        result["elapsed_seconds"] = round(time.monotonic()-started, 3)
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


async def run(args):
    points = args.crash_points.split(",")
    if any(point not in POINTS for point in points):
        raise ValueError("unknown crash point")
    if args.verification_duration < 30 or args.repeats < 1:
        raise ValueError("live F15 acceptance requires at least 30 seconds of business verification")
    base = json.loads(args.config.read_text(encoding="utf-8-sig"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    output = args.output or ROOT / "eval/results/local" / ("F15-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    manifest = getattr(args, "frozen_manifest", None) or freeze_sources(output)
    results = []
    for repeat in range(args.repeats):
        for point in points:
            assert_worker_sources(manifest)
            case_directory = output / point if args.repeats == 1 else output / (point+"-"+str(repeat+1))
            result = await run_case(args, base, case_directory, point)
            result["repeat"] = repeat+1
            save(case_directory / "results.json", result)
            results.append(result)
            save(output / "results.json", results)
            print(json.dumps({key: result.get(key) for key in ("crash_point", "repeat", "status", "db_mcp_modify_invocations",
                  "duplicate_modifying_calls", "old_fence_rejected", "elapsed_seconds", "cleanup")}, ensure_ascii=False), flush=True)
            if result.get("cleanup") != "restored":
                return 1
    return 0 if len(results) == len(points)*args.repeats and all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/local-coordinator.json")
    parser.add_argument("--backup-bridge", type=Path, default=ROOT / "runtime/database-backup-bridge.json")
    parser.add_argument("--runtime", type=Path, default=ROOT / "deploy/native-runtime.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--crash-points", default=",".join(POINTS))
    parser.add_argument("--verification-duration", type=float, default=30)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--approve-high", action="store_true", help="Pre-authorize only this isolated evaluator's declared high-risk repair")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
