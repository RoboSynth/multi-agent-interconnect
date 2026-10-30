"""Verify live Docker label denial using one new, never-started test container."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from acps_mcp_bridge import Bridge, McpStdioClient, Policy, ServerConfig
from acps_sdk.aip.resumable import OperationLedger
from domains.ops.guard import labeled_container


async def run(config):
    output = ROOT / "output" / ("docker-label-denial-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    result = {"passed": False, "target_started": False, "cleanup_removed": False}
    created_id = None
    async def docker(*args):
        proc = await asyncio.create_subprocess_exec(*config["docker_command"], *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await asyncio.wait_for(proc.communicate(), 30)
        if proc.returncode:
            raise RuntimeError("Docker test-container command failed")
        return stdout.decode("utf-8", errors="strict").strip()
    try:
        # No network, volume, credential, daemon socket, or start is requested.
        created_id = await docker("create", "--name", "incident-pilot-unlabeled-probe-" + secrets.token_hex(4),
                                  "incident-pilot-docker-mcp:0.3.0")
        if not re.fullmatch(r"[a-f0-9]{64}", created_id):
            raise RuntimeError("Docker create did not return one immutable container ID")
        policy = Policy.load(Path(__file__).with_name("policy.yaml"), allowed_callers=["label-verification"])
        policy.tools = {"ops.logs": policy.tools["ops.logs"]}
        async with McpStdioClient(ServerConfig(**config["server"])) as client:
            bridge = await Bridge(policy, {"docker": client}, OperationLedger(output / "ledger.sqlite", "label-test"),
                "local-label-test", resource_guard=partial(labeled_container, command=config["docker_command"])).initialize()
            payload = {"schema_version": "ifc/1.0", "incident_id": "inc-label-test", "logical_task_id": "lt-label",
                       "kind": "observe", "tool": "ops.logs", "args": {"container_id": created_id},
                       "budget": {"deadline_ms": 30000}}
            denied = await bridge.execute(payload, "label-verification")
            result["denial"] = denied
            result["test_container_id"] = created_id
            result["passed"] = denied["status"] == "rejected" and "label" in denied.get("reason", "")
            if not result["passed"]:
                raise AssertionError("The live unlabeled container was not rejected")
    finally:
        if created_id and re.fullmatch(r"[a-f0-9]{64}", created_id):
            await docker("rm", created_id)
            result["cleanup_removed"] = True
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "cleanup_removed": result["cleanup_removed"], "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    asyncio.run(run(json.loads(parser.parse_args().config.read_text(encoding="utf-8-sig"))))
