"""Fixed-seed workload with persistent original intents and unknown outcomes.

One HTTP request per second: create -> query -> cancel, hence 10 complete
workflows in the default 30-second healthy observation window.
"""
import argparse
import asyncio
import hashlib
import json
import random
import time
import uuid
from pathlib import Path

import httpx

if __package__:
    from .receipts import validate_committed_receipt
else:
    from receipts import validate_committed_receipt


class VersionedClient:
    """Require the public response contract before advancing an order intent."""
    def __init__(self, client, expected_api_version="v2"):
        self.client, self.expected_api_version = client, expected_api_version

    async def request(self, *args, **kwargs):
        response = await self.client.request(*args, **kwargs)
        if response.status_code < 400:
            body = response.json()
            if not isinstance(body, dict) or body.get("order_api_version") != self.expected_api_version:
                raise ValueError("public_order_contract_version_missing_or_mismatched")
        return response


class OrderObserver:
    def __init__(self, base_url, *, seed=17, run_id=None, state=None, client=None, expected_api_version=None):
        self.base_url = base_url.rstrip("/")
        self.random = random.Random(seed)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.state = state or {"pending": [], "completed": [], "next_index": 0}
        self.client = client
        self.expected_api_version = expected_api_version

    def _intent(self):
        index = self.state["next_index"]
        self.state["next_index"] += 1
        key = f"load-{self.run_id}-{index:06d}"
        # Both create and cancel keys must fit the order API's 128-character limit.
        # Use a distinct prefix so an unchanged short run ID cannot alias a hash.
        if len(key + "-cancel") > 128:
            key = "loadh-" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        return {"request_key": key, "operation_key": key + "-cancel", "item": self.random.choice(["book", "pen", "keyboard"]),
                "quantity": self.random.randint(1, 3), "phase": "create", "was_unknown": False}

    async def observe(self, *, duration=30, requests_per_second=1, min_complete=10, stop_after_completed=None,
                      pad_to_duration=True):
        if duration <= 0 or requests_per_second <= 0:
            raise ValueError("duration and requests_per_second must be positive")
        if stop_after_completed is not None and (type(stop_after_completed) is not int or stop_after_completed < 1):
            raise ValueError("stop_after_completed must be a positive integer")
        started = time.monotonic()
        events = []
        before = len(self.state["completed"])
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=4, trust_env=False)
        request_client = VersionedClient(client, self.expected_api_version) if self.expected_api_version is not None else client
        try:
            for tick in range(int(duration * requests_per_second)):
                await asyncio.sleep(max(0, started + tick / requests_per_second - time.monotonic()))
                if not self.state["pending"]:
                    self.state["pending"].append(self._intent())
                intent = self.state["pending"][0]
                phase = intent["phase"]
                if phase == "create":
                    method, path = "POST", "/orders"
                    payload = {k: intent[k] for k in ("request_key", "item", "quantity")}
                elif phase == "query":
                    method, path, payload = "GET", "/orders/" + intent["order_id"], None
                elif phase == "cancel":
                    method, path = "POST", "/orders/" + intent["order_id"] + "/cancel"
                    payload = {"operation_key": intent["operation_key"]}
                else:
                    method, path, payload = "GET", "/receipts/" + intent["unknown_key"], None
                sample = {"request_key": intent["request_key"], "phase": phase, "method": method, "path": path,
                          "elapsed_seconds": round(time.monotonic() - started, 3)}
                try:
                    response = await request_client.request(method, self.base_url + path, **({"json": payload} if payload is not None else {}))
                    sample["http_status"] = response.status_code
                    if response.status_code >= 500 or (phase == "resolve" and response.status_code == 404):
                        sample["outcome"] = "unknown"
                    elif response.status_code >= 400:
                        sample["outcome"] = "failed"
                    else:
                        body = response.json()
                        if phase == "resolve":
                            validate_committed_receipt(body, intent["unknown_key"],
                                operation_kind=intent["resume_phase"],
                                order_id=intent.get("order_id") if intent["resume_phase"] == "cancel" else None)
                        if phase == "query" and body.get("order", {}).get("id") != intent["order_id"]:
                            raise ValueError("query_order_id_mismatch")
                        sample["outcome"] = "success"
                        if phase == "create" or (phase == "resolve" and intent["resume_phase"] == "create"):
                            intent["order_id"] = body["order_id"]
                            intent["phase"] = "query"
                        elif phase == "query":
                            intent["phase"] = "cancel"
                        else:
                            if body.get("order", {}).get("status") != "CANCELLED":
                                raise ValueError("cancel_not_confirmed")
                            self.state["completed"].append(dict(intent))
                            self.state["pending"].pop(0)
                except httpx.TransportError as exc:
                    sample.update(outcome="unknown", error=type(exc).__name__)
                except (ValueError, KeyError, TypeError) as exc:
                    sample.update(outcome="failed", error=type(exc).__name__)
                    if str(exc) == "public_order_contract_version_missing_or_mismatched":
                        sample["public_contract_error"] = True
                if sample["outcome"] == "unknown":
                    intent["was_unknown"] = True
                    if phase in {"create", "cancel"}:
                        intent.update(phase="resolve", resume_phase=phase,
                                      unknown_key=intent["request_key"] if phase == "create" else intent["operation_key"])
                    elif phase == "resolve":
                        # Missing receipt cannot prove non-execution; continue the SAME original key.
                        intent["phase"] = intent["resume_phase"]
                events.append(sample)
                if stop_after_completed is not None and len(self.state["completed"]) - before >= stop_after_completed:
                    break
            if pad_to_duration:
                await asyncio.sleep(max(0, started + duration - time.monotonic()))
        finally:
            if owned:
                await client.aclose()
        completed = len(self.state["completed"]) - before
        counts = {key: sum(x["outcome"] == key for x in events) for key in ("success", "failed", "unknown")}
        summary = {"run_id": self.run_id, "duration_seconds": round(time.monotonic() - started, 3),
                   "requests": len(events), **counts, "completed_workflows": completed,
                   "unresolved_intents": len(self.state["pending"]),
                   "resolved_unknown_intents": sum(i["was_unknown"] for i in self.state["completed"]),
                   "passed": duration >= 30 and completed >= min_complete and counts["failed"] == 0
                             and not self.state["pending"], "events": events, "state": self.state}
        return summary


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8088")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--rps", type=float, default=1)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--run-id")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8")) if args.state and args.state.exists() else None
    observer = OrderObserver(args.url, seed=args.seed, run_id=args.run_id, state=state)
    result = await observer.observe(duration=args.duration, requests_per_second=args.rps)
    if args.state:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(result["state"], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"events", "state"}}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
