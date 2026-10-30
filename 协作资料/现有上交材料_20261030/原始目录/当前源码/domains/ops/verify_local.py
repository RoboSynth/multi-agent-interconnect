"""Verify native registered-process and route tools through real MCP stdio."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_sdk.aip.resumable import OperationLedger


async def run(write=False):
    caller = "local-integration-coordinator"
    authority = ApprovalAuthority(secrets.token_bytes(32))
    policy = Policy.load(Path(__file__).with_name("policy.native.yaml"), allowed_callers=[caller],
                         approval_verifier=authority.verify)
    output = ROOT / "output" / ("native-ops-bridge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    audit_events = []
    results = {"transport": "official MCP SDK stdio", "backend": "native Windows process/Nginx",
               "container_backend_tested": False, "platform_group_tested": False, "write_executed": write, "checks": {}}
    def command(tool, kind="observe", **extra):
        return {"schema_version": "ifc/1.0", "incident_id": "inc-live-ops", "logical_task_id": "lt-" + tool,
                "kind": kind, "tool": tool, "args": {}, "budget": {"deadline_ms": 30000}, **extra}
    async with AsyncExitStack() as stack:
        clients = {}
        for name, script in (("native", "native_mcp.py"), ("route", "route_mcp.py")):
            clients[name] = await stack.enter_async_context(McpStdioClient(ServerConfig(
                sys.executable, [str(Path(__file__).with_name(script))], timeout_seconds=30)))
        bridge = await Bridge(policy, clients, OperationLedger(output / "operations.sqlite", "ops"), "ops-local",
                              audit=lambda e: audit_events.append(e)).initialize()
        for alias in ("ops.containers", "ops.route_status"):
            result = await bridge.execute(command(alias), caller)
            results["checks"][alias] = result
            if result["status"] != "ok":
                raise RuntimeError("Native MCP observation failed: " + result.get("reason", result["status"]))
        if write:
            for index, alias in enumerate(("ops.route_rollback", "ops.restart"), 1):
                action = command(alias, "act", operation_id="op-ops-" + str(index),
                                 fence={"coordinator_term": 1, "takeover_version": 0})
                action["approval"] = authority.issue(action, caller, approved_by="exclusive-local-integration")
                first = await bridge.execute(action, caller)
                replay = await bridge.execute(action, caller)
                results["checks"][alias] = first
                results["checks"][alias + ".replay"] = replay
                if first["operation"]["state"] != "applied" or replay["operation"]["state"] != "skipped_already_applied":
                    raise RuntimeError("Native MCP recovery/replay failed: " + alias)
    results["audit_event_count"] = len(audit_events)
    (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "audit-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in audit_events), encoding="utf-8")
    print(json.dumps({"ok": True, "write_executed": write, "output": str(output), "checks": len(results["checks"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(run(parser.parse_args().write))
