"""Summarize real AMP records; short local runs are never labelled 7x24."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics


def percentile_95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1] if values else None


def summarize(directory, *, heartbeat_interval_seconds=15, window_start=None, window_end=None,
              expected_aics=None):
    if (type(heartbeat_interval_seconds) not in (int, float)
            or not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0):
        raise ValueError("heartbeat interval must be a finite positive number")
    window = None
    if window_start is not None or window_end is not None:
        if window_start is None or window_end is None:
            raise ValueError("window_start and window_end must be provided together")
        bounds = []
        for value in (window_start, window_end):
            if not isinstance(value, str):
                raise ValueError("window bounds must be timezone-aware ISO8601 strings")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("window bounds must include a timezone")
            bounds.append(parsed.astimezone(timezone.utc))
        start, end = (value.timestamp() for value in bounds)
        if start >= end:
            raise ValueError("window_end must be after window_start")
        window = {"start": bounds[0].isoformat().replace("+00:00", "Z"),
                  "end": bounds[1].isoformat().replace("+00:00", "Z"),
                  "duration_seconds": end-start,
                  "expected_slots_per_agent": math.ceil((end-start)/heartbeat_interval_seconds)}
    expected = None
    if expected_aics is not None:
        if isinstance(expected_aics, str):
            raise ValueError("expected_aics must be a collection of AIC strings")
        expected = set()
        for aic in expected_aics:
            if not isinstance(aic, str) or not aic.strip() or aic != aic.strip():
                raise ValueError("expected AICs must be nonempty strings without surrounding whitespace")
            expected.add(aic)
    counts, heartbeats, latencies, processing = defaultdict(int), defaultdict(list), [], []
    aic_records = defaultdict(int)
    seen = set()
    invalid = duplicates = invalid_durations = outside_window = 0
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
                if window is not None and not start <= stamp < end:
                    # Count valid envelopes before ID deduplication; outside rows
                    # do not reserve an ID or enter any in-window metric.
                    outside_window += 1
                    continue
                # Invalid rows must not suppress a later valid row with this ID.
                if row["log_id"] in seen:
                    duplicates += 1
                    continue
                seen.add(row["log_id"])
                counts[kind] += 1
                aic_records[row["aic"]] += 1
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
    for aic in sorted(set(heartbeats) | (expected or set())):
        records = heartbeats.get(aic, [])
        samples = sorted(set(records))
        span = samples[-1] - samples[0] if len(samples) > 1 else 0
        # AICs have individual observation windows; never extrapolate uptime.
        # Round to the nearest cadence; ordinary scheduling jitter must not turn
        # a 29.9-second gap into a single 15-second interval.
        lost = sum(max(0, math.floor((b-a)/heartbeat_interval_seconds + .5)-1)
                   for a,b in zip(samples, samples[1:]))
        agent = {"aic": aic, "heartbeat_count": len(records), "unique_heartbeat_count": len(samples),
                       "duplicate_timestamp_count": len(records)-len(samples), "observed_seconds": round(span, 3),
                       "estimated_missing_heartbeats": lost,
                       "coverage_percent_in_observed_window": round(100*len(samples)/(len(samples)+lost), 3) if span else None}
        if expected is not None:
            agent.update(expected=aic in expected, valid_record_count=aic_records.get(aic, 0))
        if window is not None:
            occupied = len({math.floor((stamp-start)/heartbeat_interval_seconds) for stamp in samples})
            total = window["expected_slots_per_agent"]
            agent["heartbeat_sampling_window"] = {
                "expected_slot_count": total, "observed_slot_count": occupied,
                "missing_slot_count": total-occupied, "coverage_percent": round(100*occupied/total, 3),
                "start_to_first_heartbeat_seconds": round(samples[0]-start, 3) if samples else None,
                "last_heartbeat_to_end_seconds": round(end-samples[-1], 3) if samples else None}
        agents.append(agent)
    result = {"unique_records": len(seen), "log_types": dict(counts), "invalid_records": invalid,
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
    if expected is not None:
        result.update(expected_aics=sorted(expected),
            expected_aics_without_records=sorted(expected-set(aic_records)),
            expected_aics_without_heartbeat=sorted(expected-set(heartbeats)),
            unexpected_observed_aics=sorted(set(aic_records)-expected))
    if window is not None:
        result.update(acceptance_window=window, outside_window_records_ignored=outside_window,
            primary_heartbeat_metric="agents[].heartbeat_sampling_window.coverage_percent",
            heartbeat_sampling_estimator="[start,end); slots anchored at window start; floor((timestamp-start)/interval); one hit per slot; final partial slot counts once",
            coverage_limit="Fixed-window sampling completeness, not uptime or TTL liveness. Cadence jitter across slot boundaries can create adjacent-slot misses. Internal first/last coverage is secondary. No platform ingestion, signature verification, 24-hour operation or Monitor evidence is inferred.")
        if expected is not None:
            total = window["expected_slots_per_agent"] * len(expected)
            occupied = sum(agent["heartbeat_sampling_window"]["observed_slot_count"]
                           for agent in agents if agent["expected"])
            result["expected_aic_sampling_window"] = {"expected_agent_count": len(expected),
                "expected_slot_count": total, "observed_slot_count": occupied,
                "missing_slot_count": total-occupied,
                "coverage_percent": round(100*occupied/total, 3) if total else None,
                "unexpected_agents_excluded": True}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=15)
    parser.add_argument("--window-start", help="Inclusive ISO8601 timestamp with timezone; pair with --window-end")
    parser.add_argument("--window-end", help="Exclusive ISO8601 timestamp with timezone; pair with --window-start")
    parser.add_argument("--expected-aic", action="append", dest="expected_aics",
                        help="Expected heartbeat identity; repeat for each AIC, including absent identities")
    args = parser.parse_args()
    result = summarize(args.directory, heartbeat_interval_seconds=args.heartbeat_interval_seconds,
        window_start=args.window_start, window_end=args.window_end, expected_aics=args.expected_aics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
