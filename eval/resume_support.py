"""Evidence helpers shared by local E1 runners; never read resource env files."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import httpx

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def freeze_sources(output):
    """Copy the imported program and worker sources before any suite case."""
    manifest = {"frozen_at": datetime.now(timezone.utc).isoformat(), "source_sha256": {},
        "transport": "local-aip-stdio", "discovery": "local process directory",
        "platform_adp_verified": False, "model_calls": 0, "model_tokens": 0,
        "worker_imports": "fresh workers each case, unchanged source hashes checked before each case",
        "parent_imports": "suite imports engine, transports and both runners once before this freeze"}
    paths = []
    for directory in ("eval", "incident", "acps_mcp_bridge", "business", "vendor/ACPs-community/acps-sdk/acps_sdk"):
        paths.extend((ROOT / directory).rglob("*.py"))
    paths.extend((ROOT / "domains").rglob("*.yaml"))
    for relative in ("runtime/local-coordinator.json", "runtime/database-bridge.json",
                     "runtime/database-backup-bridge.json", "runtime/ops-bridge.json"):
        path = ROOT / relative
        if path.exists():
            paths.append(path)  # registered configuration paths; no env-file contents
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        content = path.read_bytes()
        manifest["source_sha256"][relative.as_posix()] = hashlib.sha256(content).hexdigest()
        target = Path(output) / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    save(Path(output) / "source-manifest.json", manifest)
    return manifest


def assert_worker_sources(manifest):
    # The suite parent has already imported engine. Root may develop a future
    # engine during this run; fresh resource workers never import that module.
    for relative, digest in manifest["source_sha256"].items():
        if (relative.startswith(("acps_mcp_bridge/", "vendor/", "business/", "domains/", "runtime/")) or
                relative in {"incident/local_worker.py", "incident/local_transport.py",
                             "incident/contracts.py", "incident/partners.py", "incident/amp_setup.py"}):
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
                raise RuntimeError("worker source changed during frozen suite: " + relative)


def authority_snapshot(transport, incident_id=None):
    """Read authority metadata without resetting shared terms or business rows."""
    rows = {"allocated_term": transport.term, "term_journal_path": transport.term_journal.path,
            "attempt_journal_path": transport.journal.path, "ledgers": []}
    with closing(sqlite3.connect(transport.term_journal.path)) as conn:
        rows["coordinator_terms"] = [list(row) for row in conn.execute("SELECT name,term FROM coordinator_terms")]
    seen = set()
    for worker in transport.config["workers"]:
        if worker.get("bridge_config"):
            config_path = Path(worker["bridge_config"])
            if not config_path.is_absolute():
                config_path = ROOT / config_path
            bridge = json.loads(config_path.read_text(encoding="utf-8-sig"))
            path = Path(bridge["ledger_path"])
            if not path.is_absolute():
                path = config_path.parent / path
        elif worker.get("ledger_path"):
            path = Path(worker["ledger_path"])
            if not path.is_absolute():
                path = ROOT / path
            bridge = {"ledger_domain": worker["role"]}
        else:
            continue
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        item = {"path": str(path), "domain": bridge.get("ledger_domain", "default"), "exists": path.exists()}
        if path.exists():
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as conn:
                item["active_fences"] = [list(row) for row in conn.execute("SELECT * FROM operation_fences")]
                item["operation_state_counts"] = [list(row) for row in conn.execute(
                    "SELECT resource_domain,state,count(*) FROM operations GROUP BY resource_domain,state")]
                if incident_id:
                    item["incident_operations"] = [list(row) for row in conn.execute(
                        "SELECT resource_domain,operation_id,state,coordinator_term,takeover_version FROM operations WHERE operation_id LIKE ?",
                        (incident_id+":%",))]
        rows["ledgers"].append(item)
    return rows


async def baseline_health(transport=None, *, incident_id="baseline"):
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "endpoints": [], "passed": True}
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        for port, path, version in ((8081, "/ready", "v1"), (8082, "/ready", "v2"),
                                    (8088, "/health", "v2"), (8088, "/ready", "v2")):
            try:
                response = await client.get(f"http://127.0.0.1:{port}{path}")
                data = response.json()
                actual = data.get("api_version", data.get("version", data.get("order_api_version")))
                ok = response.status_code == 200 and actual == version
                result["endpoints"].append({"port": port, "path": path, "status": response.status_code,
                                            "version": actual, "passed": ok})
                result["passed"] &= ok
            except Exception as exc:
                result["endpoints"].append({"port": port, "path": path, "error_class": type(exc).__name__})
                result["passed"] = False
    if transport is not None:
        product = await transport.call({"incident_id": incident_id, "logical_task_id": incident_id+":healthy-status",
            "kind": "observe", "tool": "application.status", "args": {}})
        facts = {fact["key"]: fact["value"] for fact in product.get("facts", [])}
        result["application_status"] = product
        result["passed"] &= (product["status"] == "ok" and facts.get("application_read_only") is False
                             and type(facts.get("application_pool_revision")) is int)
    return result


def semantic_history(messages_path, incident_id):
    """Actual Start payloads and completed business products, with AIP IDs.

    Lifecycle envelopes remain in messages.jsonl. No summaries or hypothetical
    messages are introduced, and duplicate terminal products are collapsed.
    """
    records, seen = [], set()
    if not Path(messages_path).exists():
        return records
    for line in Path(messages_path).read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        message = entry["message"]
        if message.get("sessionId") != incident_id:
            continue
        if entry["direction"] == "send" and message.get("command") == "start":
            for item in message.get("dataItems", []):
                payload = json.loads(item["text"]) if "text" in item else item.get("data")
                if isinstance(payload, dict) and payload.get("kind") == "describe" and ":describe:" in payload.get("logical_task_id", ""):
                    return records  # first replacement lookup: post-failure, not prior conversation
                if isinstance(payload, dict) and payload.get("kind") != "describe":
                    records.append({"direction": "request", "aip_task_id": message["taskId"], "payload": payload})
        elif entry["direction"] == "receive":
            for product in message.get("products", []):
                for item in product.get("dataItems", []):
                    data = item.get("data")
                    if not isinstance(data, dict):
                        continue
                    key = (message["taskId"], json.dumps(data, sort_keys=True, ensure_ascii=False))
                    if key not in seen:
                        seen.add(key)
                        records.append({"direction": "product", "aip_task_id": message["taskId"], "product": data})
    return records


def formal_semantic_history(messages_path, incident_id, *, before_bytes):
    """Read an exact pre-takeover capture prefix, matching IFC IDs to AIP tasks.

    Formal AIP session IDs identify the group and need not equal an incident.
    Only products matching an actual Start's session/task and IFC incident/logical
    IDs are included. Duplicate lifecycle products do not duplicate evidence.
    The caller must use the byte boundary recorded before ADP/takeover begins.
    """
    if type(before_bytes) is not int or before_bytes < 0:
        raise ValueError("history cutoff must be a nonnegative byte count")
    if before_bytes == 0:
        return []
    with Path(messages_path).open("rb") as stream:
        prefix = stream.read(before_bytes)
    if len(prefix) != before_bytes or not prefix.endswith(b"\n"):
        raise ValueError("history cutoff must end at a captured record boundary")
    entries = [json.loads(line) for line in prefix.decode("utf-8").splitlines() if line.strip()]

    def key(message):
        session, task = message.get("sessionId"), message.get("taskId")
        return (session, task) if isinstance(session, str) and session and isinstance(task, str) and task else None

    def item_value(item):
        if "text" in item:
            try:
                return json.loads(item["text"])
            except (TypeError, ValueError):
                return None
        return item.get("data")

    # A fast reply can be captured before publisher confirmation records Start.
    # Bind all captured Starts first, then retain their original capture order.
    starts, all_starts = {}, {}
    for entry in entries:
        message = entry.get("message", {})
        identity = key(message)
        if entry.get("direction") != "send" or message.get("command") != "start" or identity is None:
            continue
        for item in message.get("dataItems", []):
            payload = item_value(item)
            if (not isinstance(payload, dict) or not isinstance(payload.get("incident_id"), str)
                    or payload.get("kind") not in {"observe", "act", "verify", "resume"}
                    or not isinstance(payload.get("logical_task_id"), str) or not payload["logical_task_id"]):
                continue
            previous = all_starts.get(identity)
            if (previous is not None and previous != payload and
                    incident_id in {previous["incident_id"], payload["incident_id"]}):
                raise ValueError("one captured AIP task has conflicting IFC requests")
            all_starts[identity] = payload
            if payload["incident_id"] == incident_id:
                starts[identity] = payload

    records, seen = [], set()
    for entry in entries:
        message = entry.get("message", {})
        identity = key(message)
        request = starts.get(identity)
        if request is None:
            continue
        base = {"aip_session_id": identity[0], "aip_task_id": identity[1]}
        if entry.get("direction") == "send" and message.get("command") == "start":
            if not any(item_value(item) == request for item in message.get("dataItems", [])):
                continue
            dedupe = ("request", identity)
            if dedupe not in seen:
                seen.add(dedupe)
                records.append({"direction": "request", **base, "payload": request})
        elif entry.get("direction") == "receive":
            for product in message.get("products", []):
                for item in product.get("dataItems", []):
                    data = item_value(item)
                    if (not isinstance(data, dict) or data.get("incident_id") != incident_id
                            or data.get("logical_task_id") != request["logical_task_id"]):
                        continue
                    dedupe = ("product", identity, json.dumps(data, sort_keys=True, ensure_ascii=False))
                    if dedupe not in seen:
                        seen.add(dedupe)
                        records.append({"direction": "product", **base, "product": data})
    return records
