"""F19: an owned local ops worker exits while the independent business is healthy.

This runner creates its own stdio workers and read-only public-HTTP MCP adapter.
It never discovers/kills an existing PID or touches a resource fault injector.
The real coordinator diagnoses failure; EOF is channel_lost, not task timeout.
Run only after reviewing the command and reserving the public order endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE_FILES = ("eval/participant_failure_experiment.py", "incident/local_worker.py",
                "incident/local_transport.py", "incident/amp_setup.py", "incident/contracts.py",
                "incident/coordinator/engine.py", "incident/coordinator/amp_facts.py",
                "incident/partners.py", "business/load.py")


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def public_order_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port not in {18088, 28088, 38088} or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Use an explicit isolated loopback order endpoint on 18088/28088/38088")
    return value.rstrip("/")


async def public_health(url):
    """HTTP facts only: no claim about Nginx configuration or Docker state."""
    import httpx
    async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
        response = await client.get(public_order_url(url) + "/health")
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict) or body.get("api_version") != "v2":
        raise ValueError("The isolated public HTTP endpoint is not v2")
    return {"public_http_status": response.status_code, "public_api_version": body["api_version"],
            "observation_scope": "public HTTP /health only; no Nginx configuration or Docker observation"}


def build_config(output, experiment_id, order_url, *, crash=True):
    """All identities/state are generated locally; no existing coordinator config."""
    if not experiment_id.startswith("owned-"):
        raise ValueError("An explicit isolated experiment id is required")
    output = Path(output).resolve()
    order_url = public_order_url(order_url)
    leader, ops = "local-" + experiment_id + "-leader", "local-" + experiment_id + "-ops"
    private = output / "private"
    policy = {"domain": "ops", "allowed_callers": [leader],
              "resources": {"application": "orders", "observation_scope": "public-http-health-only"},
              "tools": {"ops.route_status": {"server": "public-health", "mcp_tool": "public_health",
                  "risk": "read", "description": "Experiment-only public HTTP health adapter; does not read routing configuration",
                  "input_schema": {"type": "object", "additionalProperties": False, "properties": {}}}}}
    bridge = {"executor_aic": ops, "allowed_callers": [leader], "policy": str(private / "ops-policy.json"),
              "ledger_path": str(private / "ops-operations.sqlite"), "ledger_domain": experiment_id,
              "env_files": [], "servers": {"public-health": {"command": sys.executable,
                  "args": [str(ROOT / "eval/participant_failure_experiment.py"), "--mcp-observer", "--order-url", order_url],
                  "env_names": []}}}
    worker = {"name": "owned-ops", "role": "ops", "aic": ops, "bridge_config": str(private / "ops-bridge.json")}
    if crash:
        worker.update(crash_point="after_observation", crash_tool="ops.route_status")
    config = {"python": sys.executable, "coordinator_aic": leader, "group_id": "local-" + experiment_id,
              "experiment_id": experiment_id, "allow_experiment_crash": bool(crash), "automatic_takeover": False,
              "directory": str(output / ("transport" if crash else "restarted-transport")),
              "journal_path": str(output / ("attempts.sqlite" if crash else "restarted-attempts.sqlite")),
              "term_journal_path": str(private / "terms.sqlite"), "amp_directory": str(output / "amp"),
              "participant_health_timeout_seconds": 2, "participant_health_wait_seconds": 50,
              "participant_heartbeat_ttl_seconds": 45, "participant_access_ttl_seconds": 60,
              "workers": [worker, {"name": "owned-verification", "role": "verification",
                  "aic": "local-" + experiment_id + "-verification", "base_url": order_url,
                  "verification_duration": 30}]}
    return config, policy, bridge


def assert_owned_ops(transport, owned):
    """The handle must be the object spawned into this runner's fresh transport."""
    worker, process = owned
    if (transport.workers.get("owned-ops") is not worker or worker.process is not process
            or worker.spec.get("role") != "ops"
            or worker.spec.get("aic") != transport.config["workers"][0]["aic"]):
        raise ValueError("The ops process handle is outside this experiment")
    return process


async def wait_for_heartbeat(directory, aic, *, timeout=20, after=None):
    """Wait for an actual Emitter record, with real wall time and no fabricated now."""
    limit = time.monotonic() + timeout
    path = Path(directory) / "amp_heartbeat_owned-ops.jsonl"
    while time.monotonic() < limit:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
                except (ValueError, KeyError, TypeError):
                    continue
                if (row.get("aic") == aic and row.get("log_type") == "heartbeat"
                        and (after is None or stamp >= after)):
                    return {"timestamp": row["timestamp"], "record_seen_at": time.time()}
        await asyncio.sleep(.05)
    raise TimeoutError("No real ops heartbeat record was observed")


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def inspect_outcome(state):
    """Read the coordinator's conclusion; never manufacture a harness diagnosis."""
    result = state.get("result") or {}
    observation = result.get("order_observation") or {}
    assessments = state.get("participant_health") or []
    assessment = assessments[-1] if assessments else {}
    return {"incident_status": state.get("status"), "participant_assessment": assessment,
            "business_observation": {k: observation.get(k) for k in
                ("duration_seconds", "requests", "success", "failed", "unknown", "completed_workflows", "unresolved_intents", "passed")},
            "participant_failure_confirmed": result.get("participant_failure_confirmed") is True,
            "participant_recovered": result.get("participant_recovered"),
            "incident_resolved": result.get("incident_resolved"),
            "manual_required": result.get("manual_required"),
            "act_tasks": sum(t.get("kind") == "act" for t in state.get("tasks", [])),
            "approval_count": len(state.get("approvals", [])),
            "model_calls": state.get("model_calls"), "model_tokens": state.get("tokens")}


def outcome_passed(outcome):
    observation, assessment = outcome["business_observation"], outcome["participant_assessment"]
    return (outcome["incident_status"] == "needs_attention" and outcome["participant_failure_confirmed"]
            and outcome["participant_recovered"] is False and outcome["incident_resolved"] is False
            and outcome["manual_required"] is True and assessment.get("confirmed") is True
            and assessment.get("participant_state") == "unreachable"
            and assessment.get("task_status") == "channel_lost"
            and observation.get("passed") is True and observation.get("duration_seconds", 0) >= 30
            and observation.get("completed_workflows", 0) >= 10 and observation.get("unknown") == 0
            and observation.get("unresolved_intents") == 0 and outcome["act_tasks"] == 0
            and outcome["approval_count"] == 0 and outcome["model_calls"] == 0 and outcome["model_tokens"] == 0)


async def describe(transport, aic, incident):
    return await transport.call_on_worker(aic, {"schema_version": "ifc/1.0", "incident_id": incident,
        "logical_task_id": "lt-" + uuid.uuid4().hex, "kind": "describe", "tool": "aip.describe",
        "args": {}, "budget": {"deadline_ms": 10000}})


async def management_control(transport, worker):
    """Actual official Get only; never construct failure TaskEvidence here."""
    evidence, phase, session = await transport._participant_management(worker, timeout=2)
    try:
        return {**asdict(evidence), "phase": phase, "probe_session": session}
    finally:
        pending = transport._management_pending.pop(session, None)
        if pending is not None:
            future = pending["future"]
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()


async def run(args):
    from incident.local_transport import LocalAipStdioTransport
    from incident.coordinator.engine import IncidentCoordinator
    order_url = public_order_url(args.order_url)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    experiment_id = "owned-" + uuid.uuid4().hex[:12]
    config, policy, bridge = build_config(output, experiment_id, order_url)
    save(output / "private/ops-policy.json", policy)
    save(output / "private/ops-bridge.json", bridge)
    save(output / "config.json", config)
    hashes = source_hashes()
    save(output / "source-hashes.json", hashes)
    transport = LocalAipStdioTransport(config)
    restarted = None
    result = {"scenario": "F19", "experiment_id": experiment_id, "transport": "local-aip-stdio",
              "platform_adp_verified": False, "status": "failed", "started_at": datetime.now(timezone.utc).isoformat(),
              "ops_adapter": "experiment-only read-only public HTTP MCP; not Nginx config or third-party Docker MCP",
              "heartbeat_interval_seconds": 15, "heartbeat_ttl_seconds": 45,
              "access_ttl_seconds": 60,
              "participant_health_wait_seconds": 50, "fault_scope": "only this runner's newly spawned ops worker",
              "task_deadline_expiration_claimed": False}
    try:
        result["public_http_before"] = await public_health(order_url)
        await transport.start()
        worker = transport.workers["owned-ops"]
        owned = (worker, worker.process)
        result["owned_ops_pid"] = assert_owned_ops(transport, owned).pid
        result["describe_before"] = await describe(transport, worker.spec["aic"], experiment_id + "-before")
        result["management_before"] = await management_control(transport, worker)
        if result["management_before"]["outcome"] != "reply":
            raise RuntimeError("The owned healthy worker did not reply to official Get")
        result["heartbeat_before"] = await wait_for_heartbeat(transport.amp_directory, worker.spec["aic"])
        engine = IncidentCoordinator(transport, output / "incidents", term=transport.term,
                                     generate_hypotheses=False)
        state = engine.new("请执行运维巡检并独立核对订单流程，遇到未确认结果保留人工处理。")
        await asyncio.wait_for(engine.run(state), 150)
        result.update(incident_id=state["id"], outcome=inspect_outcome(state))
        result["ops_exit_code"] = await asyncio.wait_for(assert_owned_ops(transport, owned).wait(), 5)
        result["public_http_during_ops_absence"] = await public_health(order_url)
        # The instance is exclusively owned; close its sibling verifier normally.
        await transport.close()
        restored_config = deepcopy(config)
        restored_config["allow_experiment_crash"] = False
        restored_config["directory"] = str(output / "restarted-transport")
        restored_config["journal_path"] = str(output / "restarted-attempts.sqlite")
        restored_config["workers"][0].pop("crash_point")
        restored_config["workers"][0].pop("crash_tool")
        restarted = LocalAipStdioTransport(restored_config)
        restart_started_at = time.time()
        await restarted.start()
        restored_worker = restarted.workers["owned-ops"]
        if restored_worker.process is owned[1]:
            raise ValueError("Restoration did not create a new owned process handle")
        result["restoration"] = {"new_owned_ops_pid": restored_worker.process.pid,
            "describe": await describe(restarted, restored_worker.spec["aic"], experiment_id + "-restored"),
            "management": await management_control(restarted, restored_worker),
            "heartbeat": await wait_for_heartbeat(restarted.amp_directory, restored_worker.spec["aic"], after=restart_started_at),
            "scope": "new dedicated worker only; original incident remains for manual review"}
        result["public_http_after"] = await public_health(order_url)
        unchanged = source_hashes() == hashes
        result["source_unchanged"] = unchanged
        result["status"] = "passed" if (outcome_passed(result["outcome"]) and result["ops_exit_code"] == 81
            and result["restoration"]["describe"].get("status") == "ok"
            and result["restoration"]["management"]["outcome"] == "reply" and unchanged) else "failed"
    except Exception as exc:
        result["error_class"] = type(exc).__name__
    finally:
        for label, owned_transport in (("initial", transport), ("restarted", restarted)):
            if owned_transport is None:
                continue
            try:
                await owned_transport.close()
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append({"scope": label, "error_class": type(exc).__name__})
                result["status"] = "failed"
            result.setdefault("owned_direct_worker_cleanup", []).extend(
                {"scope": label, "role": w.spec["role"], "pid": w.process.pid, "returncode": w.process.returncode}
                for w in owned_transport.workers.values())
        result["all_owned_direct_workers_exited"] = all(
            row["returncode"] is not None for row in result.get("owned_direct_worker_cleanup", []))
        if not result["all_owned_direct_workers_exited"]:
            result["status"] = "failed"
        result["mcp_grandchild_cleanup_independently_measured"] = False
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["existing_processes_stopped_or_restarted"] = False
        result["business_load"] = "normal create/query/cancel workflows via the independent verifier"
        save(output / "results.json", result)
    print(json.dumps({k: result.get(k) for k in ("scenario", "experiment_id", "status", "error_class")}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-url", default="http://127.0.0.1:28088")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mcp-observer", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    public_order_url(args.order_url)
    if args.mcp_observer:
        from mcp.server.fastmcp import FastMCP
        server = FastMCP("isolated-public-health-read-only")
        @server.tool(name="public_health")
        async def observe():
            return await public_health(args.order_url)
        server.run(transport="stdio")
        return 0
    if args.output is None:
        parser.error("--output must be a new isolated experiment directory")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
