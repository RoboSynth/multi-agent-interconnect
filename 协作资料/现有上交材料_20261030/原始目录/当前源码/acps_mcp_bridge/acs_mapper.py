"""Map tools/list through policy into stable coarse ACS skills."""
from __future__ import annotations

from copy import deepcopy
import json


def schema_example(schema):
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {name: schema_example(schema.get("properties", {}).get(name, {})) for name in schema.get("required", [])}
    if kind == "integer":
        return schema.get("minimum", 1)
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    return "experiment-resource"


def map_acs(base_document: dict, policy, inventory: dict) -> dict:
    document = deepcopy(base_document)
    available = policy.describe(inventory)["tools"]
    skills = []
    for suffix, risks in (("observe", {"read"}), ("act", {"write", "high"})):
        tools = [t for t in available if t["risk"] in risks]
        if not tools:
            continue
        example = {"schema_version": "ifc/1.0", "incident_id": "inc-example", "logical_task_id": "lt-example",
                   "kind": "observe" if suffix == "observe" else "act", "tool": tools[0]["name"],
                   "args": schema_example(tools[0]["inputSchema"])}
        if suffix == "act":
            example.update(operation_id="op-example", fence={"coordinator_term": 1, "takeover_version": 0})
        skills.append({"id": f"{policy.domain}.{suffix}", "name": f"{policy.domain} {suffix}", "version": "1.0.0",
                       "description": "；".join(t["description"] for t in tools),
                       "tags": ["incident-pilot", "MCP", policy.domain, suffix],
                       "examples": [json.dumps(example, ensure_ascii=False)],
                       "inputModes": ["application/json"], "outputModes": ["application/json"]})
    document.update(protocolVersion="02.02", skills=skills, version="1.0.0")
    return document


def validate_acs(document: dict) -> dict:
    from integration.validate_acs import validate_document
    return validate_document(document, submission=True)
