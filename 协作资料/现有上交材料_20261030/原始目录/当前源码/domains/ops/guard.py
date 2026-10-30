"""Use immutable container IDs after checking live labels, not caller claims."""
from __future__ import annotations

import asyncio
import json
import os
import re

from acps_mcp_bridge.policy import PolicyRejected


def container_matches_scope(entry: dict, scope: dict) -> bool:
    """Match both inspect records and the upstream list_containers representation."""
    labels = entry.get("labels", entry.get("Config", {}).get("Labels")) or {}
    name = entry.get("name", entry.get("Name", ""))
    return (isinstance(labels, dict) and "incident-pilot" in labels
            and labels.get("com.docker.compose.project") == scope["compose_project"]
            and labels.get("com.docker.compose.service") == scope["compose_service"]
            and isinstance(name, str) and name.lstrip("/") == scope["container_name"])


async def labeled_container(container_id: str, *, command=None, compose_project=None,
                            compose_service=None, container_name=None) -> str:
    process = None
    try:
        scope = {"compose_project": compose_project, "compose_service": compose_service,
                 "container_name": container_name}
        scoped = any(value is not None for value in scope.values())
        if scoped and any(not isinstance(value, str) or not re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", value) for value in scope.values()):
            raise PolicyRejected("container scope must be configured completely")
        command = command or json.loads(os.environ.get("INCIDENT_DOCKER_COMMAND", '["docker"]'))
        if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("Docker command must be a local argv list")
        process = await asyncio.create_subprocess_exec(*command, "inspect", "--type", "container", container_id,
                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await asyncio.wait_for(process.communicate(), 5)
        records = json.loads(stdout)
        if process.returncode or not isinstance(records, list) or len(records) != 1:
            raise ValueError("not one container")
        entry = records[0]
        if "incident-pilot" not in (entry.get("Config", {}).get("Labels") or {}):
            raise PolicyRejected("container lacks the incident-pilot resource label")
        if scoped and not container_matches_scope(entry, scope):
            raise PolicyRejected("container is outside the configured project, service or target")
        if not isinstance(entry["Id"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["Id"]):
            raise ValueError("container inspect did not return an immutable ID")
        return entry["Id"]
    except PolicyRejected:
        raise
    except (OSError, ValueError, KeyError, TimeoutError) as exc:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        raise PolicyRejected("Docker resource label could not be verified") from exc
