"""Exclusive F06 integration: only terminate a real experiment-role blocker."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import urllib.request

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_sdk.aip.resumable import OperationLedger
from domains.database.provision_local import read_env


async def run():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "output" / ("database-blocker-bridge-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    domain_env = read_env(ROOT / "runtime/private/database-bridge.env")
    application_env = read_env(ROOT / "runtime/private/application.env")
    connection_args = dict(host=application_env.get("PGHOST", "127.0.0.1"),
        port=int(application_env.get("PGPORT", "55432")), database="orders", user="orders_app",
        password=application_env["PGPASSWORD"])
    authority = ApprovalAuthority(secrets.token_bytes(32))
    caller = "local-exclusive-blocker-test"
    policy = Policy.load(Path(__file__).with_name("policy.yaml"), allowed_callers=[caller],
                         approval_verifier=authority.verify)
    events, results, connections, waiting = [], {"scenario": "F06-real-MCP", "checks": {}, "passed": False}, [], None
    def command(tool, kind="observe", **extra):
        return {"schema_version": "ifc/1.0", "incident_id": "inc-real-blocker", "logical_task_id": "lt-" + tool,
                "kind": kind, "tool": tool, "args": {}, "budget": {"deadline_ms": 15000}, **extra}
    def action(pid, operation_id, approve=True):
        value = command("db.terminate_blocker", "act", args={"pid": pid}, operation_id=operation_id,
                        fence={"coordinator_term": 1, "takeover_version": 0})
        if approve:
            value["approval"] = authority.issue(value, caller, approved_by="exclusive-F06-integration")
        return value
    try:
        async with McpStdioClient(ServerConfig(str(ROOT / ".venv-mcp-postgres/Scripts/postgres-mcp.exe"),
            ["--access-mode=unrestricted"], env={"DATABASE_URI": domain_env["DATABASE_URI"]}, timeout_seconds=30)) as client:
            bridge = await Bridge(policy, {"postgres": client}, OperationLedger(output / "operations.sqlite", "database"),
                "db-F06-test", audit=lambda e: events.append(e), secret_values=[domain_env["PGPASSWORD"],
                domain_env["DATABASE_URI"], application_env["PGPASSWORD"]]).initialize()
            for _ in range(3):
                connections.append(await asyncpg.connect(**connection_args))
            blocker, waiter, ordinary = connections
            await blocker.execute("BEGIN")
            await blocker.execute("LOCK TABLE public.orders IN ACCESS EXCLUSIVE MODE")
            waiting = asyncio.create_task(waiter.fetchval("SELECT count(*) FROM public.orders"))
            for _ in range(30):
                observation = await bridge.execute(command("db.blocking_sessions"), caller)
                rows = observation["facts"][0]["value"]
                if any(blocker.get_server_pid() in row.get("blocking_pids", []) for row in rows):
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("Real blocker did not appear in MCP observation")
            results["checks"]["blocking_observed"] = observation
            rejected = await bridge.execute(action(blocker.get_server_pid(), "op-missing-approval", False), caller)
            assert rejected["status"] == "rejected" and not blocker.is_closed()
            results["checks"]["without_approval"] = rejected
            ordinary_pid = ordinary.get_server_pid()
            rejected = await bridge.execute(action(ordinary_pid, "op-non-blocker"), caller)
            assert rejected["status"] == "rejected" and await ordinary.fetchval("SELECT 1") == 1
            results["checks"]["non_blocking_target"] = rejected
            operation = action(blocker.get_server_pid(), "op-authorized-blocker")
            restored = await bridge.execute(operation, caller)
            assert restored["status"] == "ok" and restored["operation"]["state"] == "applied"
            assert restored["facts"][0]["value"] is True
            results["checks"]["controlled_termination"] = restored
            rows_read = await asyncio.wait_for(waiting, 3)
            results["checks"]["waiter_released"] = {"completed": True, "count_is_nonnegative": rows_read >= 0}
            replay = await bridge.execute(operation, caller)
            assert replay["operation"]["state"] == "skipped_already_applied"
            results["checks"]["duplicate"] = replay
            results["passed"] = True
    finally:
        for connection in connections:
            if not connection.is_closed():
                try:
                    await connection.close(timeout=3)
                except Exception:
                    connection.terminate()
        if waiting and not waiting.done():
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        health = {}
        for port in (8082, 8088):
            try:
                with opener.open(f"http://127.0.0.1:{port}/ready", timeout=2) as response:
                    health[str(port)] = json.load(response)
            except OSError:
                health[str(port)] = {"ok": False}
        results["after_health"] = health
        results["passed"] = results["passed"] and all(v.get("ok") for v in health.values())
        results["audit_event_count"] = len(events)
        results["platform_group_tested"] = False
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "audit-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    print(json.dumps({"passed": results["passed"], "output": str(output), "audit_event_count": len(events)}))
    if not results["passed"]:
        raise AssertionError("F06 MCP integration or final health did not pass")


if __name__ == "__main__":
    asyncio.run(run())
