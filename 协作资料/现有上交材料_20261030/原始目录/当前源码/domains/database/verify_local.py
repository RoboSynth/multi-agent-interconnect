"""Real PostgreSQL MCP integration. --write requires an exclusive lab test window."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_mcp_bridge.bridge import mcp_value
from acps_sdk.aip.resumable import OperationLedger
from domains.database.provision_local import read_env


async def run(write=False):
    env = read_env(ROOT / "runtime/private/database-bridge.env")
    caller = "local-integration-coordinator"
    authority = ApprovalAuthority(secrets.token_bytes(32))
    policy = Policy.load(Path(__file__).with_name("policy.yaml"), allowed_callers=[caller],
                         approval_verifier=authority.verify)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "output" / f"database-bridge-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    ledger_path = output / "operations.sqlite"
    audit_events = []
    def audit(event):
        audit_events.append(event)
    config = ServerConfig(str(ROOT / ".venv-mcp-postgres/Scripts/postgres-mcp.exe"),
                          ["--access-mode=unrestricted"], env={"DATABASE_URI": env["DATABASE_URI"]}, timeout_seconds=30)
    results = {"transport": "official MCP SDK stdio", "upstream": "postgres-mcp==0.3.0",
               "database": "loopback PostgreSQL16 orders", "write_executed": write, "checks": {}}
    def command(tool, kind="observe", **extra):
        return {"schema_version": "ifc/1.0", "incident_id": "inc-live-db", "logical_task_id": "lt-" + tool,
                "kind": kind, "tool": tool, "args": {}, "budget": {"deadline_ms": 30000}, **extra}
    async with McpStdioClient(config) as client:
        bridge = await Bridge(policy, {"postgres": client}, OperationLedger(ledger_path, "db"), "db-primary",
                              audit=audit, secret_values=[env["PGPASSWORD"], env["DATABASE_URI"]]).initialize()
        for tool in ("db.health", "db.read_only_status", "db.blocking_sessions"):
            result = await bridge.execute(command(tool), caller)
            results["checks"][tool] = result
            if result["status"] != "ok":
                raise RuntimeError(f"Real MCP integration failed for {tool}: {result.get('reason')}")
        direct_error = mcp_value(await client.call("execute_sql", {"sql": "SELECT has_database_privilege(current_user, 'orders', 'CREATE') AS can_create"}))
        results["checks"]["minimum_privilege"] = direct_error
        if direct_error != [{"can_create": False}]:
            raise RuntimeError("bridge_operator unexpectedly has CREATE privileges")
        if write:
            action = command("db.restore_writes", "act", operation_id="op-live-restore",
                             fence={"coordinator_term": 1, "takeover_version": 0})
            action["approval"] = authority.issue(action, caller, approved_by="exclusive-local-integration")
            first = await bridge.execute(action, caller)
            backup = Bridge(policy, {"postgres": client}, OperationLedger(ledger_path, "db"), "db-backup", audit=audit)
            replay = await backup.execute(action, caller)
            results["checks"].update(restore=first, backup_replay=replay)
            if first["operation"]["state"] != "applied" or replay["operation"]["state"] != "skipped_already_applied":
                raise RuntimeError("Real MCP recovery / backup replay failed")
    results["audit_event_count"] = len(audit_events)
    results["platform_group_tested"] = False
    (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "audit-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in audit_events), encoding="utf-8")
    print(json.dumps({"ok": True, "write_executed": write, "output": str(output),
                      "check_count": len(results["checks"]), "audit_event_count": len(audit_events)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(run(parser.parse_args().write))
