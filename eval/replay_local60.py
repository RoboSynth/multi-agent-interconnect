"""Replay recorded M2v2 model outputs through the current scheduler, offline.

Uses the unit-test fake resource domains: no services, model endpoint or platform.
Usage: python eval/replay_local60.py evidence/p5-local60-20261020/incident-ledger.json
"""
import asyncio, json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_mcp_bridge.approval import ApprovalAuthority
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine
from incident.coordinator.incident_planner import IncidentPlanner
from test_coordinator import FakeHttpClient
from test_p5_incident_scheduling import SchedulingTransport

ledger = json.load(open(sys.argv[1], encoding="utf-8"))

async def replay(entry):
    content = entry["model_requests"][0]["content"]
    body = {"usage": {"total_tokens": entry["model_requests"][0]["usage"]["total_tokens"]},
            "choices": [{"message": {"content": content}}]}
    authority = ApprovalAuthority("replay-only-approval-secret" * 3)
    transport = SchedulingTransport(entry["scenario"], authority)
    transport.authority = authority
    model = HypothesisEngine(enabled=True, base_url="http://model.test/v1", model="replay",
                             client=FakeHttpClient([body] * 3))
    with tempfile.TemporaryDirectory() as directory:
        engine = IncidentCoordinator(transport, directory, hypothesis=model, planner_factory=IncidentPlanner,
            incident_hypotheses=True,
            approval_issuer=lambda payload: authority.issue(payload, "coordinator-test", approved_by="offline"))
        state = engine.new("same symptom")
        task = asyncio.create_task(engine.run(state))
        while not task.done():
            for approval in list(engine.approvals):
                if not engine.approvals[approval][0].done():
                    engine.decide(approval, True)
            await asyncio.sleep(0)
        state = await task
    observe = [c["tool"] for c in transport.calls if c["kind"] == "observe"]
    acts = [c["tool"] for c in transport.calls if c["kind"] == "act"]
    return state["status"], acts, observe, state["model_calls"]

async def main():
    rows = []
    for e in (e for e in ledger if e["method"] == "M2v2"):
        status, acts, observe, calls = await replay(e)
        rows.append({"scenario": e["scenario"], "repeat": e["repeat"], "incident_id": e["incident_id"],
                     "original_status": e["status"], "replay_status": status, "model_calls": calls,
                     "actions": acts, "observations": observe})
    print(json.dumps({"scope": "offline replay of recorded model output; fake resource domains",
                      "completed": sum(r["replay_status"] == "completed" for r in rows), "cells": len(rows),
                      "rows": rows}, ensure_ascii=False, indent=2))
asyncio.run(main())
