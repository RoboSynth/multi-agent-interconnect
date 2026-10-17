"""ADP candidates need a group describe roundtrip before resource selection."""
from __future__ import annotations
from urllib.parse import urlparse
import httpx


async def discover_candidates(url, skill_id, *, client=None, record=None):
    from acps_sdk.adp import DiscoveryFilter, DiscoveryRequest, DiscoveryResponse, FilterCondition
    request = DiscoveryRequest(type="filtered", limit=50, filter=DiscoveryFilter(conditions=[
        FilterCondition(field="active", op="eq", value=True),
        FilterCondition(field="skills.id", op="eq", value=skill_id)])).to_dict()
    request["extFilter"] = {"logic": "and", "conditions": [
        {"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}]}
    if client is None:
        async with httpx.AsyncClient(timeout=25) as owned:
            response = await owned.post(url, json=request)
    else:
        response = await client.post(url, json=request)
    response.raise_for_status()
    raw = response.json()
    parsed = DiscoveryResponse.from_dict(raw)
    if parsed.is_error() or parsed.result is None:
        raise RuntimeError("ADP discovery failed")
    candidates = []
    for aic, acs in parsed.result.acs_map.items():
        if acs.get("aic") != aic or not acs.get("active"):
            continue
        if not any(s.get("id") == skill_id for s in acs.get("skills", [])):
            continue
        endpoints = [e for e in acs.get("endPoints", []) if e.get("transport") == "AMQP"]
        if any(urlparse(e.get("url", "")).scheme == "amqps" for e in endpoints):
            candidates.append(acs)
    if record:
        record("official_discovery", skill_id=skill_id, request=request, response=raw)
    return candidates


async def select_participant(candidates, *, resource, tool, describe, excluded=()):
    matches = []
    for acs in sorted(candidates, key=lambda c: c["aic"]):
        if acs["aic"] in excluded:
            continue
        try:
            description = await describe(acs)
        except (TimeoutError, OSError, RuntimeError):
            continue
        if not isinstance(description, dict) or description.get("executor_aic") != acs["aic"]:
            continue
        resources = description.get("resources", description.get("resource_scope", []))
        if isinstance(resources, dict):
            # Gateway policies describe named scope dimensions, while native
            # partners advertise an explicit list. Match only resource fields,
            # never arbitrary values such as users, ports or runtime backends.
            resources = [resources[key] for key in ("database", "application", "resource")
                         if isinstance(resources.get(key), str)]
        tools = description.get("tools", [])
        if not isinstance(resources, list) or not all(isinstance(r, str) for r in resources) or not isinstance(tools, list):
            continue
        tool_names = set()
        for item in tools:
            name = item if isinstance(item, str) else item.get("name", item.get("id")) if isinstance(item, dict) else None
            if isinstance(name, str):
                tool_names.add(name)
        if resource in resources and tool in tool_names:
            matches.append((acs, description))
    if not matches:
        raise RuntimeError(f"No confirmed participant for {resource}/{tool}")
    return matches[0]
