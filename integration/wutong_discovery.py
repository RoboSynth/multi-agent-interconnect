"""Discover incident skills through Wutong's public ADP service."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import httpx

SDK = Path(__file__).resolve().parents[1] / "vendor/ACPs-community/acps-sdk"
sys.path.insert(0, str(SDK))
from acps_sdk.adp import DiscoveryFilter, DiscoveryRequest, DiscoveryResponse, FilterCondition

DEFAULT_URL = "https://wt.ioa.pub/discovery/acps-adp-v2/discover"


def skill_request(skill_id):
    payload = DiscoveryRequest(type="filtered", limit=50,
        filter=DiscoveryFilter(conditions=[
            FilterCondition(field="active", op="eq", value=True),
            FilterCondition(field="skills.id", op="eq", value=skill_id),
        ])).to_dict()
    # The hosted service has moved availability out of the ACS filter. New
    # identities stay unknown until monitoring reports their runtime state.
    payload["extFilter"] = {"logic": "and", "conditions": [
        {"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}
    ]}
    return payload


async def discover_skill(discovery_url, skill_id, *, record=None):
    request = skill_request(skill_id)
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(discovery_url, json=request)
        response.raise_for_status()
        raw = response.json()
    parsed = DiscoveryResponse.from_dict(raw)
    if parsed.is_error() or parsed.result is None:
        raise RuntimeError(f"Official ADP returned an error: {parsed.error}")
    candidates = []
    for aic, acs in parsed.result.acs_map.items():
        if acs.get("aic") != aic or not acs.get("active"):
            continue
        if not any(skill.get("id") == skill_id for skill in acs.get("skills", [])):
            continue
        if not any(ep.get("transport") == "AMQP" and ep.get("url", "").startswith("amqps://")
                   for ep in acs.get("endPoints", [])):
            continue
        candidates.append(acs)
    if record:
        record("official_discovery", skill_id=skill_id, http_status=response.status_code,
               request=request, response=raw, candidate_aics=[acs["aic"] for acs in candidates])
    if len(candidates) != 1:
        raise RuntimeError(f"Official ADP found {len(candidates)} AMQPS agents for {skill_id}; expected one")
    return candidates[0]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    events = []
    def record(event, **data):
        events.append({"at": datetime.now(timezone.utc).isoformat(), "event": event, **data})
    report = {"events": events, "success": False}
    try:
        report["agent"] = await discover_skill(args.url, args.skill, record=record)
        report["success"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"success": report["success"], "aic": report.get("agent", {}).get("aic"),
                      "error": report.get("error"), "output": str(args.output)}, ensure_ascii=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
