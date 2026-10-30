"""Actual third-party Docker MCP against explicitly selected labeled lab containers."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from acps_mcp_bridge.bridge import mcp_value
from acps_sdk.aip.resumable import OperationLedger
from domains.ops.guard import labeled_container


async def run(config):
    caller = "docker-mcp-exclusive-verification"
    authority = ApprovalAuthority(secrets.token_bytes(32))
    policy = Policy.load(Path(__file__).with_name("policy.yaml"), allowed_callers=[caller], approval_verifier=authority.verify)
    # This acceptance isolates the third-party container server. Route MCP has
    # its own native/container acceptance and is not impersonated here.
    policy.tools = {name: value for name, value in policy.tools.items() if value["server"] == "docker"}
    output = ROOT / "output" / ("docker-mcp-bridge-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    events = []
    result = {"passed": False, "third_party_server": "mcp-server-docker==0.3.0", "transport": "official MCP SDK stdio",
              "container_backend_tested": True, "platform_group_tested": False, "checks": {}}
    guard = partial(labeled_container, command=config["docker_command"])
    def command(alias, kind="observe", **extra):
        return {"schema_version": "ifc/1.0", "incident_id": "inc-real-docker", "logical_task_id": "lt-" + alias,
                "kind": kind, "tool": alias, "args": {}, "budget": {"deadline_ms": 30000}, **extra}
    try:
        immutable_id = await guard(config["target_container"], **policy.container_scope)
        async with McpStdioClient(ServerConfig(**config["server"])) as client:
            bridge = await Bridge(policy, {"docker": client}, OperationLedger(output / "operations.sqlite", "ops-docker"),
                "local-docker-acceptance", audit=lambda e: events.append(e), resource_guard=guard).initialize()
            inventory = await client.tools()
            result["tool_names"] = [tool["name"] for tool in inventory]
            for alias, args in (("ops.containers", {}), ("ops.logs", {"container_id": immutable_id})):
                observed = await bridge.execute(command(alias, args=args), caller)
                if observed["status"] != "ok":
                    raise RuntimeError("Container MCP observation failed: " + alias)
                result["checks"][alias] = observed
            action = command("ops.restart", "act", operation_id="op-real-docker-restart",
                             fence={"coordinator_term": 1, "takeover_version": 0})
            denied = await bridge.execute(action, caller)
            if denied["status"] != "rejected":
                raise AssertionError("Docker restart accepted without approval")
            result["checks"]["missing_approval"] = denied
            if config.get("unlabeled_container"):
                forbidden = command("ops.logs", args={"container_id": config["unlabeled_container"]})
                denied = await bridge.execute(forbidden, caller)
                if denied["status"] != "rejected":
                    raise AssertionError("An unlabeled container was accepted")
                result["checks"]["unlabeled_target"] = denied
            action["approval"] = authority.issue(action, caller, approved_by="exclusive-labeled-container-acceptance")
            applied = await bridge.execute(action, caller)
            replay = await bridge.execute(action, caller)
            if applied.get("operation", {}).get("state") != "applied" or replay.get("operation", {}).get("state") != "skipped_already_applied":
                raise AssertionError("Docker restart or duplicate suppression did not pass")
            result["checks"].update(restart=applied, duplicate=replay)
            observed = await bridge.execute(command("ops.containers"), caller)
            result["checks"]["after_containers"] = observed
            current = mcp_value(await client.call("list_containers", policy.tools["ops.containers"]["fixed_arguments"]))
            if not any((container.get("id", container.get("Id")) == immutable_id) and
                       container.get("status", container.get("State", {}).get("Status")) == "running" for container in current):
                raise AssertionError("Registered container was not running after MCP restart")
            result["passed"] = True
    finally:
        result["audit_event_count"] = len(events)
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "audit-events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "output": str(output), "audit_event_count": len(events)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    asyncio.run(run(json.loads(parser.parse_args().config.read_text(encoding="utf-8-sig"))))
