"""Inspect a saved Discovery response, or explicitly query public AIC liveness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx


def request_for(aics):
    if not aics or any(not isinstance(aic, str) or not aic.strip() for aic in aics):
        raise ValueError("Provide nonempty AICs")
    return {"type": "filtered", "limit": len(set(aics)),
            "filter": {"logic": "and", "conditions": [{"field": "aic", "op": "in", "value": sorted(set(aics))}]},
            "extFilter": {"logic": "and", "conditions": [{"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}]}}


def summarize(raw, aics):
    request_for(aics)
    if not isinstance(raw, dict) or raw.get("error") or not isinstance(raw.get("result"), dict):
        raise ValueError("Discovery response has no successful result")
    alive = raw["result"].get("aliveMap") or {}
    if not isinstance(alive, dict):
        raise ValueError("Discovery aliveMap is invalid")
    rows = {}
    for aic in sorted(set(aics)):
        value = alive.get(aic)
        status = value.get("alive") if isinstance(value, dict) else None
        if type(status) is bool:
            status = "online" if status else "offline"
        elif not isinstance(status, str):
            status = None
        rows[aic] = {"alive": status if status in {"online", "offline", "unknown"} else "unknown",
                     "present": aic in alive,
                     "last_seen_at": value.get("aliveLastSeenAt", value.get("lastSeenAt")) if isinstance(value, dict) else None}
    return {"aics": rows, "online_count": sum(row["alive"] == "online" for row in rows.values()),
            "expected_count": len(rows), "all_online": all(row["alive"] == "online" for row in rows.values()),
            "access_ingestion_confirmed": None, "rank_confirmed": None,
            "scope": "Discovery aliveMap is evidence for heartbeat synchronization only; it does not establish access pairing, rank, or which collector supplied the heartbeat."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aic", action="append", required=True)
    parser.add_argument("--response", type=Path, help="Read an existing JSON response without connecting")
    parser.add_argument("--url", help="Public Discovery HTTPS endpoint")
    parser.add_argument("--query", action="store_true", help="Explicit read-only Discovery POST; never starts an AIC")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Use a new output file to preserve prior results")
    request = request_for(args.aic)
    if args.response:
        if args.query:
            parser.error("Choose --response or --query")
        raw = json.loads(args.response.read_text(encoding="utf-8-sig"))
        result = summarize(raw, args.aic)
        result["mode"] = "saved-response"
    elif args.query:
        endpoint = urlparse(args.url or "")
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
            parser.error("--query requires a public HTTPS --url without embedded credentials")
        with httpx.Client(timeout=httpx.Timeout(25, connect=5), trust_env=False) as client:
            response = client.post(args.url, json=request)
            response.raise_for_status()
            raw = response.json()
        result = summarize(raw, args.aic)
        result.update(mode="discovery-read-only", observed_at_utc=datetime.now(timezone.utc).isoformat(), response=raw)
    else:
        result = {"mode": "PREPARED_NOT_QUERIED", "request": request}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "response"}, ensure_ascii=False))
    return 0 if result.get("all_online", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
