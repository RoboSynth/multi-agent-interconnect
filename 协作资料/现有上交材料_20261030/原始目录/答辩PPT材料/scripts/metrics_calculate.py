"""Recalculate only existing sanitized evidence; performs no network requests."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def summarize(rows):
    durations = [r["body"].get("durationMs") for r in rows]
    valid = sorted(v for v in durations if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0)
    assert len(valid) + sum(v is None for v in durations) == len(rows), "Unexpected duration value"
    return {
        "records": len(rows), "timed_records": len(valid), "missing_duration": sum(v is None for v in durations),
        "median_ms": round(statistics.median(valid), 6) if valid else None,
        "p90_ms": round(valid[math.ceil(len(valid) * 0.9) - 1], 6) if valid else None,
        "max_ms": round(max(valid), 6) if valid else None,
        "statuses": dict(Counter(str((r["body"].get("response") or {}).get("statusCode", "missing")) for r in rows)),
        "errors": dict(Counter(str(r["body"]["error"].get("code")) for r in rows if r["body"].get("error"))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-root", type=Path, default=Path(__file__).resolve().parents[3] / "演示视频")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "5-量化指标")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    groups, summaries = [], {}
    for case in ["V3-f10", "V4-takeover"]:
        summaries[case] = {}
        for side in ["coordinator", "domain"]:
            path = args.video_root / case / "access" / (side + ".jsonl")
            records = load_jsonl(path)
            summaries[case][side] = summarize(records)
            buckets = defaultdict(list)
            for record in records:
                request = record["body"]["request"]
                buckets[(request.get("route", ""), request.get("method", ""))].append(record)
            for (route, method), rows in sorted(buckets.items()):
                groups.append({"case": case, "side": side, "route": route, "method": method,
                               **summarize(rows), "source": path.relative_to(args.video_root).as_posix()})
        domain_rows = load_jsonl(args.video_root / case / "access/domain.jsonl")
        counts = dict(sorted(Counter(r["body"]["callee"]["aic"] for r in domain_rows).items()))
        paired = load_json(args.video_root / case / "access/pairing-summary.json")
        assert counts == paired["domain_roles"]
        assert len(domain_rows) == paired["domain_count"] == paired["paired_count"]
        summaries[case]["roles"] = counts

    with (args.output / "指标.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["案例", "记录端", "route", "method", "记录数", "有耗时记录数", "耗时缺失数", "中位数_ms", "P90_ms", "最大值_ms", "状态码计数", "错误计数", "来源"])
        for group in groups:
            writer.writerow([group[key] if group[key] is not None else "" for key in
                             ["case", "side", "route", "method", "records", "timed_records", "missing_duration", "median_ms", "p90_ms", "max_ms"]]
                            + [json.dumps(group["statuses"], ensure_ascii=False), json.dumps(group["errors"], ensure_ascii=False), group["source"]])

    events = load_jsonl(args.video_root / "V3-f10/events.jsonl")
    active, intervals, maximum = {}, [], 0
    native = sorted((e for e in events if e.get("event") in ["task_started", "task_returned"]), key=lambda e: e["at"])
    for event in native:
        key = event["logical_task_id"]
        if event["event"] == "task_started":
            assert key not in active
            active[key] = event
            maximum = max(maximum, len(active))
        else:
            start = active.pop(key)
            duration = (datetime.fromisoformat(event["at"]) - datetime.fromisoformat(start["at"])).total_seconds()
            assert duration >= 0
            intervals.append({"logical_task_id": key, "tool": event["tool"], "started_at_utc": start["at"],
                              "returned_at_utc": event["at"], "seconds": round(duration, 6), "status": event["status"]})
    assert not active
    summaries["f10_task_intervals"] = {"count": len(intervals), "peak_observed_inflight": maximum,
                                      "source": "V3-f10/events.jsonl", "clock": "same coordinator native at timestamp",
                                      "boundary": "Only task_started to task_returned; excludes discovery and worker internals", "intervals": intervals}
    capture = load_json(args.video_root / "V2-discovery/capture.json")
    summaries["v2_capture_window"] = {
        "seconds": round((datetime.fromisoformat(capture["finished_at_utc"]) - datetime.fromisoformat(capture["started_at_utc"])).total_seconds(), 6),
        "discovery_responses": capture["discovery_responses"], "described_roles": capture["described_roles"],
        "boundary": "capture start to finish; not an ADP request latency"}
    latest = load_json(args.video_root / "V5-access/status-observation.json")
    summaries["latest_platform_observations"] = [{"role": r["alias"], "observed_at": r["observedAtBeijing"],
        "caller": int(r["values"]["queryCaller"].replace(",", "")),
        "caller_external": int(r["values"]["queryCallerExternal"].replace(",", "")),
        "callee": int(r["values"]["queryCallee"].replace(",", "")),
        "callee_external": int(r["values"]["queryCalleeExternal"].replace(",", "")),
        "displayed_window": r["values"]["queryStatsRange"]} for r in latest["observations"]]
    result = {"schema": "ppt-existing-evidence-metrics/1", "calculation": "median; P90 nearest rank ceil(0.9*n); milliseconds; missing durations not imputed",
              "summaries": summaries, "groups": groups}
    (args.output / "计算结果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"groups": len(groups), "summaries": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
