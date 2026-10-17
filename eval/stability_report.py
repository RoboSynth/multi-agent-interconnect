"""Summarize real AMP records; short local runs are never labelled 7x24."""
import argparse
from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import statistics


def percentile_95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1] if values else None


def summarize(directory, *, heartbeat_interval_seconds=15):
    if (type(heartbeat_interval_seconds) not in (int, float)
            or not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0):
        raise ValueError("heartbeat interval must be a finite positive number")
    counts, heartbeats, latencies, processing = defaultdict(int), defaultdict(list), [], []
    seen = set()
    invalid = duplicates = invalid_durations = 0
    for path in sorted(Path(directory).rglob("amp_*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or any(
                        not isinstance(row.get(key), str) or not row[key].strip()
                        for key in ("log_id", "log_type", "aic", "timestamp")
                    ):
                        raise ValueError("invalid AMP envelope")
                    timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    if timestamp.tzinfo is None:
                        raise ValueError("timestamp must include a timezone")
                    stamp = timestamp.timestamp()
                    kind = row["log_type"]
                    body = row.get("body", {})
                    if kind == "access" and not isinstance(body, dict):
                        raise ValueError("access body must be an object")
                except (ValueError, KeyError, TypeError, OverflowError):
                    invalid += 1
                    continue
                # Invalid rows must not suppress a later valid row with this ID.
                if row["log_id"] in seen:
                    duplicates += 1
                    continue
                seen.add(row["log_id"])
                counts[kind] += 1
                if kind == "heartbeat":
                    heartbeats[row["aic"]].append(stamp)
                if kind == "access":
                    latency = body.get("durationMs")
                    if latency is None:
                        continue
                    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
                        invalid_durations += 1
                        continue
                    latencies.append(latency)
                    caller, callee = body.get("caller"), body.get("callee")
                    if (isinstance(callee, dict) and isinstance(caller, dict)
                            and callee.get("aic") == row["aic"]
                            and isinstance(caller.get("aic"), str) and caller["aic"] != row["aic"]):
                        processing.append(latency)
    agents = []
    for aic, records in sorted(heartbeats.items()):
        samples = sorted(set(records))
        span = samples[-1] - samples[0] if len(samples) > 1 else 0
        # AICs have individual observation windows; never extrapolate uptime.
        # Round to the nearest cadence; ordinary scheduling jitter must not turn
        # a 29.9-second gap into a single 15-second interval.
        lost = sum(max(0, math.floor((b-a)/heartbeat_interval_seconds + .5)-1)
                   for a,b in zip(samples, samples[1:]))
        agents.append({"aic": aic, "heartbeat_count": len(records), "unique_heartbeat_count": len(samples),
                       "duplicate_timestamp_count": len(records)-len(samples), "observed_seconds": round(span, 3),
                       "estimated_missing_heartbeats": lost,
                       "coverage_percent_in_observed_window": round(100*len(samples)/(len(samples)+lost), 3) if span else None})
    return {"unique_records": len(seen), "log_types": dict(counts), "invalid_records": invalid,
            "duplicate_records_ignored": duplicates, "invalid_access_durations": invalid_durations,
            "agents": agents, "median_access_ms": statistics.median(latencies) if latencies else None,
            "p95_access_ms": percentile_95(latencies),
            "median_partner_processing_ms": statistics.median(processing) if processing else None,
            "p95_partner_processing_ms": percentile_95(processing),
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
            "heartbeat_estimator": "nearest cadence, half-interval tolerance; unique timestamps between first and last heartbeat only",
            "latency_percentile_method": "nearest rank: ceil(0.95*n), one-based",
            "coverage_limit": "Cadence estimate within each observed span; not uptime. Boundary outages, absent agents and platform ingestion are unmeasured.",
            "task_roundtrip": "Use coordinator per-task elapsed_ms; AMP access includes send or handler duration only.",
            "evidence_level": "local AMP files; platform ingestion and continuous operation require separate evidence"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=15)
    args = parser.parse_args()
    result = summarize(args.directory, heartbeat_interval_seconds=args.heartbeat_interval_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
