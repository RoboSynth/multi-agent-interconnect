"""Use immutable container IDs after checking live labels, not caller claims."""
from __future__ import annotations

import asyncio
import json
import os

from acps_mcp_bridge.policy import PolicyRejected


async def labeled_container(container_id: str, *, command=None) -> str:
    process = None
    try:
        command = command or json.loads(os.environ.get("INCIDENT_DOCKER_COMMAND", '["docker"]'))
        if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("Docker command must be a local argv list")
        process = await asyncio.create_subprocess_exec(*command, "inspect", "--type", "container", container_id,
                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await asyncio.wait_for(process.communicate(), 5)
        records = json.loads(stdout)
        if process.returncode or len(records) != 1:
            raise ValueError("not one container")
        entry = records[0]
        if "incident-pilot" not in (entry.get("Config", {}).get("Labels") or {}):
            raise PolicyRejected("container lacks the incident-pilot resource label")
        return entry["Id"]
    except PolicyRejected:
        raise
    except (OSError, ValueError, KeyError, TimeoutError) as exc:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        raise PolicyRejected("Docker resource label could not be verified") from exc
