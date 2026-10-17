"""Summarize real AMP records; short local runs are never labelled 7x24."""
import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import statistics


def summarize(directory):
    counts, heartbeats, latencies, processing = defaultdict(int), defaultdict(list), [], []
    seen = set()
    invalid = 0
    for path in Path(directory).rglob("amp_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if row["log_id"] in seen:
                    continue
                seen.add(row["log_id"])
                kind = row["log_type"]
                counts[kind] += 1
                if kind == "heartbeat":
                    heartbeats[row["aic"]].append(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp())
                if kind == "access":
                    latency = row.get("body", {}).get("durationMs")
                    if isinstance(latency, (int, float)):
                        latencies.append(latency)
                        body = row.get("body", {})
                        if body.get("callee", {}).get("aic") == row.get("aic") and body.get("caller", {}).get("aic") != row.get("aic"):
                            processing.append(latency)
            except (ValueError, KeyError, TypeError):
                invalid += 1
    agents = []
    for aic, samples in heartbeats.items():
        samples.sort()
        span = samples[-1] - samples[0] if len(samples) > 1 else 0
        # AICs have individual observation windows; never extrapolate uptime.
        lost = sum(max(0, int((b-a)/15)-1) for a,b in zip(samples, samples[1:]))
        agents.append({"aic": aic, "heartbeat_count": len(samples), "observed_seconds": round(span, 3),
                       "estimated_missing_heartbeats": lost,
                       "coverage_percent_in_observed_window": round(100*len(samples)/(len(samples)+lost), 3)})
    latencies.sort()
    processing.sort()
    return {"unique_records": len(seen), "log_types": dict(counts), "invalid_records": invalid,
            "agents": agents, "median_access_ms": statistics.median(latencies) if latencies else None,
            "p95_access_ms": latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None,
            "median_partner_processing_ms": statistics.median(processing) if processing else None,
            "p95_partner_processing_ms": processing[min(len(processing)-1,int(len(processing)*.95))] if processing else None,
            "task_roundtrip": "Use coordinator per-task elapsed_ms; AMP access includes send or handler duration only.",
            "evidence_level": "local AMP files; platform ingestion and continuous operation require separate evidence"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
