"""Evaluator-only continuous business traffic; contains no resource credentials."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time

import httpx
from business.load import OrderObserver


class VersionedClient:
    def __init__(self, client):
        self.client = client

    async def request(self, *args, **kwargs):
        response = await self.client.request(*args, **kwargs)
        if response.status_code < 400 and response.json().get("order_api_version") != "v2":
            raise ValueError("public_order_contract_version_missing")
        return response


class ContinuousObserver:
    """One scheduled request/second, preserving intents across one-second chunks.

    The bounded HTTP timeout prevents a blocked request from accumulating bursts.
    Domain verification is a distinct, identical-for-all-methods traffic stream.
    """
    def __init__(self, url, directory, *, seed, run_id, clock=time.monotonic, client=None):
        self.url, self.directory = url, Path(directory)
        self.seed, self.run_id, self.clock = seed, run_id, clock
        self.client = client
        self.stop_event = asyncio.Event()
        self.events = []
        self.fault_at = None
        self.started = self.clock()
        self.observer = None
        self.task = None

    async def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.task = asyncio.create_task(self._run())
        return self

    def mark_fault(self):
        self.fault_at = self.clock()
        return self.fault_at

    async def _run(self):
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=.8, trust_env=False)
        self.observer = OrderObserver(self.url, seed=self.seed, run_id=self.run_id,
                                      client=VersionedClient(client))
        try:
            while not self.stop_event.is_set():
                chunk_start = self.clock()
                before = len(self.observer.state["completed"])
                chunk = await self.observer.observe(duration=1, requests_per_second=1, min_complete=0)
                for event in chunk["events"]:
                    event = {**event, "at_monotonic": chunk_start + event["elapsed_seconds"],
                             "completed_workflows": len(self.observer.state["completed"]) - before}
                    self.events.append(event)
                    with (self.directory / "requests.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        finally:
            if owned:
                await client.aclose()

    def summary(self):
        relevant = [e for e in self.events if self.fault_at is not None and e["at_monotonic"] >= self.fault_at]
        bad = [e for e in relevant if e["outcome"] != "success"]
        last_bad = bad[-1]["at_monotonic"] if bad else self.fault_at
        healthy = [e for e in relevant if e["outcome"] == "success" and e["at_monotonic"] > last_bad] if last_bad is not None else []
        count = sum(e["completed_workflows"] for e in healthy)
        span = healthy[-1]["at_monotonic"] - healthy[0]["at_monotonic"] + 1 if healthy else 0
        pending = len(self.observer.state["pending"]) if self.observer else 0
        confirmed = bool(bad and len(healthy) >= 30 and count >= 10 and span >= 30 and not pending)
        recovery = healthy[0]["at_monotonic"] - self.fault_at if healthy and bad else None
        return {"run_id": self.run_id, "seed": self.seed, "requests_per_second": 1,
            "http_timeout_seconds": .8, "requests": len(relevant),
            "success": sum(e["outcome"] == "success" for e in relevant),
            "failed": sum(e["outcome"] == "failed" for e in relevant),
            "unknown": sum(e["outcome"] == "unknown" for e in relevant),
            "fault_observed": bool(bad), "recovery_observed_seconds": round(recovery, 3) if recovery is not None else None,
            "recovery_confirmed_seconds": round(healthy[-1]["at_monotonic"] + 1 - self.fault_at, 3) if confirmed else None,
            "healthy_window_seconds": round(span, 3), "healthy_completed_workflows": count,
            "unresolved_intents": pending,
            "resolved_unknown_intents": sum(intent["was_unknown"] for intent in self.observer.state["completed"]) if self.observer else 0,
            "recovery_confirmed": confirmed,
            "state": self.observer.state if self.observer else None}

    async def finish(self, *, grace_seconds=35):
        until = self.clock() + grace_seconds
        while self.clock() < until and not self.summary()["recovery_confirmed"]:
            await asyncio.sleep(.1)
        self.stop_event.set()
        if self.task:
            await self.task
        result = self.summary()
        (self.directory / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
