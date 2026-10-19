"""ADP candidates need a group describe roundtrip before resource selection."""
from __future__ import annotations
import asyncio
import math
import random
from urllib.parse import urlparse
import httpx


async def _discovery_request(client, url, request, record):
    # ADP filtered discovery is a read-only query even though its HTTP verb is POST.
    for attempt in range(1, 5):
        try:
            response = await client.post(url, json=request)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            if attempt == 4:
                raise
            failure = {"error_class": type(exc).__name__}
        else:
            if response.status_code < 500 or attempt == 4:
                response.raise_for_status()
                return response
            failure = {"status_code": response.status_code}
        delay = .5 * (2 ** (attempt - 1)) + random.uniform(0, .1)
        if record:
            record("official_discovery_retry", attempt=attempt, delay_seconds=delay, **failure)
        await asyncio.sleep(delay)


async def discover_candidates(url, skill_id, *, client=None, record=None):
    from acps_sdk.adp import DiscoveryFilter, DiscoveryRequest, DiscoveryResponse, FilterCondition
    request = DiscoveryRequest(type="filtered", limit=50, filter=DiscoveryFilter(conditions=[
        FilterCondition(field="active", op="eq", value=True),
        FilterCondition(field="skills.id", op="eq", value=skill_id)])).to_dict()
    request["extFilter"] = {"logic": "and", "conditions": [
        {"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}]}
    if client is None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=10, write=10, pool=5),
                                     trust_env=False) as owned:
            response = await _discovery_request(owned, url, request, record)
    else:
        response = await _discovery_request(client, url, request, record)
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


async def select_participant(candidates, *, resource, tool, describe, excluded=(),
                             trusted_aics=None, describe_timeout_seconds=30, record=None):
    if (type(describe_timeout_seconds) not in (int, float)
            or not math.isfinite(describe_timeout_seconds) or describe_timeout_seconds <= 0):
        raise ValueError("describe_timeout_seconds must be finite and positive")
    if trusted_aics is not None:
        if (isinstance(trusted_aics, (str, bytes))
                or not all(isinstance(aic, str) and aic.strip() for aic in trusted_aics)):
            raise ValueError("trusted_aics must contain nonempty AIC strings")
        trusted_aics = set(trusted_aics)
    matches = []
    for acs in sorted(candidates, key=lambda c: c["aic"]):
        if acs["aic"] in excluded:
            continue
        if trusted_aics is not None and acs["aic"] not in trusted_aics:
            if record:
                record("participant_excluded", aic=acs["aic"], reason="not_in_trusted_aics")
            continue
        try:
            description = await asyncio.wait_for(describe(acs), describe_timeout_seconds)
        except (TimeoutError, OSError, RuntimeError) as exc:
            if record:
                record("participant_not_confirmed", aic=acs["aic"],
                       error_class=type(exc).__name__, describe_timeout_seconds=describe_timeout_seconds)
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
