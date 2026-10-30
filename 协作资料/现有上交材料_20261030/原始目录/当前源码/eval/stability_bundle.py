"""Export a fixed-window stability bundle from explicit, recorded inputs only.

The existing stability_report.summarize API and its AMP JSON remain unchanged.
Scheduler records are native ops/schedule.py events; coordinator inputs are final
IncidentCoordinator incident JSON files. No service or network is contacted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.stability_report import percentile_95, summarize


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a timezone-aware string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).timestamp()


def _number(value):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0)


def _stats(values):
    return {"measured_count": len(values),
            "median_ms": statistics.median(values) if values else None,
            "p95_ms": percentile_95(values)}


def _identity(value):
    return isinstance(value, str) and bool(value.strip())


def _manifest(paths, kind):
    records = []
    for index, path in enumerate(paths, 1):
        raw = path.read_bytes()
        records.append({"source_id": f"{kind}-{index:03}", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return records


def _scheduler(paths, start, end):
    counters = Counter()
    records, seen = [], set()
    for path in paths:
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or not _identity(row.get("event")):
                        raise ValueError("invalid scheduler event")
                    at = _timestamp(row.get("at"))
                except (ValueError, TypeError, OverflowError):
                    counters["invalid_records"] += 1
                    continue
                if not start <= at < end:
                    counters["outside_window_records"] += 1
                    continue
                signature = json.dumps(row, sort_keys=True, separators=(",", ":"))
                if signature in seen:
                    counters["duplicate_records"] += 1
                    continue
                seen.add(signature)
                records.append((at, row))
    records.sort(key=lambda item: item[0])
    incident_runs = {}
    for _, row in records:
        if row["event"] == "job_started" and _identity(row.get("incident_id")) and _identity(row.get("run_id")):
            incident_runs.setdefault(row["incident_id"], set()).add(row["run_id"])
    jobs = {}
    for _, row in records:
        event = row["event"]
        if event not in {"job_started", "job_finished", "job_timeout", "dispatch_unknown",
                         "operator_required", "operator_required_pending_drill"}:
            counters["other_events"] += 1
            continue
        run_id = row.get("run_id")
        if not _identity(run_id):
            incident_id = row.get("incident_id")
            matches = incident_runs.get(incident_id, set()) if _identity(incident_id) else set()
            if len(matches) == 1:
                run_id = next(iter(matches))
        if not _identity(run_id):
            counters["unattributed_events"] += 1
            continue
        jobs.setdefault(run_id, []).append(row)
    result = []
    for run_id, rows in sorted(jobs.items()):
        starts = [row for row in rows if row["event"] == "job_started"]
        finishes = [row for row in rows if row["event"] == "job_finished"]
        kinds = {row.get("kind") if row.get("kind") in ("inspect", "drill") else "unknown" for row in starts}
        kind = next(iter(kinds)) if len(kinds) == 1 and kinds <= {"inspect", "drill"} else "unknown"
        terminal_values = {(row.get("status") if _identity(row.get("status")) else "unknown",
                            json.dumps(row.get("seconds"), sort_keys=True)) for row in finishes}
        incident_ids = {row.get("incident_id") if _identity(row.get("incident_id")) else None
                        for row in starts + finishes}
        identity_conflict = bool(starts and finishes) and (None in incident_ids or len(incident_ids) != 1)
        reversed_events = bool(starts and finishes) and (
            min(_timestamp(row["at"]) for row in finishes) < max(_timestamp(row["at"]) for row in starts))
        conflict = len(terminal_values) > 1 or len(kinds) > 1 or identity_conflict or reversed_events
        finish = finishes[-1] if finishes and not conflict else {}
        status = finish.get("status") if _identity(finish.get("status")) else "unknown"
        elapsed = finish.get("seconds")
        duration = elapsed if _number(elapsed) and not conflict else None
        counters["invalid_durations"] += sum(row.get("seconds") is not None and not _number(row["seconds"])
                                               for row in finishes)
        state = status if status in {"completed", "failed"} and starts and kind != "unknown" and not conflict else "unknown"
        result.append({"run_id": run_id, "kind": kind, "outcome": state,
                       "reported_status": status, "elapsed_seconds": duration,
                       "start_events": len(starts), "finish_events": len(finishes),
                       "missing_start": not bool(starts), "missing_finish": not bool(finishes),
                       "conflicting_records": conflict,
                       "signals": sorted({row["event"] for row in rows if row["event"] not in {"job_started", "job_finished"}})})
    by_kind = []
    for kind in ("inspect", "drill", "unknown"):
        selected = [row for row in result if row["kind"] == kind]
        by_kind.append({"kind": kind, "recorded_jobs": len(selected),
                        "completed": sum(row["outcome"] == "completed" for row in selected),
                        "failed": sum(row["outcome"] == "failed" for row in selected),
                        "unknown": sum(row["outcome"] == "unknown" for row in selected),
                        "evidence": "observed_jobs" if selected else "unknown_no_recorded_job"})
    return {"input_provided": bool(paths), "jobs": result, "by_kind": by_kind, "diagnostics": dict(counters),
            "counts": dict(Counter(row["outcome"] for row in result)),
            "interpretation": "Observed in-window events only; reported completed is not independent business recovery. Missing endpoints and conflicts remain unknown; no expected schedule denominator is inferred."}


def _coordinator(paths, start, end):
    counters, tasks = Counter(), {}
    for path in paths:
        incident = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(incident, dict) or not _identity(incident.get("id")) or not isinstance(incident.get("tasks"), list):
            raise ValueError("coordinator input must be a final incident JSON with id and tasks")
        for row in incident["tasks"]:
            try:
                if not isinstance(row, dict) or not _identity(row.get("logical_task_id")):
                    raise ValueError("invalid task")
                at = _timestamp(row.get("started_at"))
            except (ValueError, TypeError, OverflowError):
                counters["invalid_records"] += 1
                continue
            if not start <= at < end:
                counters["outside_window_tasks"] += 1
                continue
            raw_elapsed = row.get("elapsed_ms")
            if raw_elapsed is not None and not _number(raw_elapsed):
                counters["invalid_durations"] += 1
            status = row.get("status") if _identity(row.get("status")) else "unknown"
            # Approval may occur after started_at and before transport dispatch.
            # Never derive a task duration from AMP, wall-clock subtraction or a
            # whole incident's elapsed_seconds.
            measured = _number(raw_elapsed) and status not in {"pending", "awaiting_approval"}
            record = {"incident_id": incident["id"], "logical_task_id": row["logical_task_id"],
                      "kind": row.get("kind") if row.get("kind") in ("observe", "act", "verify") else "unknown",
                      "status": status, "started_at": row["started_at"],
                      "elapsed_ms": raw_elapsed if measured else None, "conflicting_records": False}
            key = (incident["id"], row["logical_task_id"])
            if key in tasks:
                old = tasks[key]
                if old == record:
                    counters["duplicate_records"] += 1
                else:
                    counters["conflicting_records"] += 1
                    old.update(status="unknown", elapsed_ms=None, conflicting_records=True)
            else:
                tasks[key] = record
    rows = [tasks[key] for key in sorted(tasks)]
    values = [row["elapsed_ms"] for row in rows if row["elapsed_ms"] is not None]
    return {"input_provided": bool(paths), "tasks": rows, "diagnostics": dict(counters),
            "recorded_count": len(rows), "unknown_duration_count": sum(row["elapsed_ms"] is None for row in rows),
            **_stats(values),
            "interpretation": "Tasks are selected by started_at in [start,end); final snapshot outcomes may finish beyond the window. elapsed_ms is coordinator-measured task elapsed, including approval waiting when present, transport and validation; not pure network RTT, fault-to-recovery time or AMP duration. Failed task measurements are retained."}


def summarize_bundle(directory, *, window_start, window_end, expected_aics=None,
                     heartbeat_interval_seconds=15, scheduler_files=(), coordinator_files=()):
    scheduler_files, coordinator_files = list(map(Path, scheduler_files)), list(map(Path, coordinator_files))
    amp_files = sorted(Path(directory).rglob("amp_*.jsonl"))
    before = _manifest(amp_files, "amp") + _manifest(scheduler_files, "scheduler") + _manifest(coordinator_files, "coordinator")
    amp = summarize(directory, window_start=window_start, window_end=window_end,
                    expected_aics=expected_aics, heartbeat_interval_seconds=heartbeat_interval_seconds)
    start, end = _timestamp(window_start), _timestamp(window_end)
    scheduler = _scheduler(scheduler_files, start, end)
    coordinator = _coordinator(coordinator_files, start, end)
    after = (_manifest(sorted(Path(directory).rglob("amp_*.jsonl")), "amp") +
             _manifest(scheduler_files, "scheduler") + _manifest(coordinator_files, "coordinator"))
    if before != after:
        raise ValueError("recorded inputs changed during analysis; use an immutable snapshot")
    latency = [
        {"metric": "AMP access send-or-handler duration", "median_ms": amp["median_access_ms"],
         "p95_ms": amp["p95_access_ms"], "measured_count": None},
        {"metric": "AMP partner handler duration", "median_ms": amp["median_partner_processing_ms"],
         "p95_ms": amp["p95_partner_processing_ms"], "measured_count": None},
        {"metric": "Coordinator task elapsed (approval may be included)",
         "median_ms": coordinator["median_ms"], "p95_ms": coordinator["p95_ms"],
         "measured_count": coordinator["measured_count"]}]
    return {"schema_version": 1, "amp": amp, "scheduler": scheduler, "coordinator": coordinator,
            "latency_metrics": latency,
            "inputs": before,
            "limitations": ["Recorded fixed window; neither uptime nor 24-hour/7-day acceptance is inferred.",
                            "Missing inputs, endpoints and durations remain unknown; zero events does not prove a disabled or healthy service.",
                            "No Kafka/Monitor ingestion, certificate/signature validation, scheduled-cycle completeness or physical-effect proof is inferred.",
                            "AMP send/handler duration and coordinator task elapsed are distinct measurements; AMP sample counts are unavailable in the unchanged legacy summary."]}


def _csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "unknown" if row.get(key) is None else (
                json.dumps(row[key], ensure_ascii=False) if isinstance(row[key], (list, dict)) else row[key]) for key in fields})


def _plot(bundle, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none",
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.4))
    agents = bundle["amp"]["agents"]
    if agents:
        values = [row["heartbeat_sampling_window"]["coverage_percent"] for row in agents]
        axes[0].barh(range(len(agents)), values, color="#2878b5")
        axes[0].set_yticks(range(len(agents)), [f"A{i+1}" for i in range(len(agents))])
        axes[0].set_xlim(0, 107)
        for i, value in enumerate(values):
            axes[0].text(value + 1, i, f"{value:g}%", va="center", fontsize=8)
        axes[0].invert_yaxis()
    else:
        axes[0].text(.5, .5, "unknown: no heartbeat identities", transform=axes[0].transAxes, ha="center", wrap=True)
    axes[0].set(title="Heartbeat sampling completeness", xlabel="Occupied fixed-window slots (%)")
    jobs = bundle["scheduler"]["jobs"]
    if jobs:
        kinds = ["inspect", "drill"] + (["unknown"] if any(row["kind"] == "unknown" for row in jobs) else [])
        left = [0] * len(kinds)
        for outcome, color in [("completed", "#2878b5"), ("failed", "#ad4938"), ("unknown", "#a5aab0")]:
            values = [sum(row["kind"] == kind and row["outcome"] == outcome for row in jobs) for kind in kinds]
            axes[1].barh(kinds, values, left=left, label=outcome, color=color)
            left = [a+b for a, b in zip(left, values)]
        axes[1].legend(frameon=False, fontsize=8, loc="upper right")
        axes[1].xaxis.get_major_locator().set_params(integer=True)
        for i, count in enumerate(left):
            if not count:
                axes[1].text(.02, i, "unknown: no recorded job", transform=axes[1].get_yaxis_transform(), va="center", fontsize=8)
    else:
        axes[1].text(.5, .5, "unknown: no scheduler jobs", transform=axes[1].transAxes, ha="center")
    axes[1].set(title="Observed scheduler outcomes", xlabel="Jobs (no expected-cycle denominator)")
    labels = ["AMP send / handler", "AMP partner handler", "Coordinator task elapsed"]
    for i, row in enumerate(bundle["latency_metrics"]):
        if row["median_ms"] is None:
            axes[2].text(.02, i, "unknown", transform=axes[2].get_yaxis_transform(), va="center", color="#7b4d33")
        else:
            axes[2].plot([row["median_ms"], row["p95_ms"]], [i, i], color="#a9b6c0", lw=2)
            axes[2].scatter([row["median_ms"]], [i], color="#2878b5", marker="o", label="median" if i == 0 else None)
            axes[2].scatter([row["p95_ms"]], [i], color="#c87022", marker="|", s=100, label="p95" if i == 0 else None)
    axes[2].set_yticks(range(3), labels)
    axes[2].set_ylim(2.6, -.6)
    axes[2].set_xlim(left=0)
    axes[2].set(title="Distinct latency measurements", xlabel="Milliseconds; nearest-rank p95")
    axes[2].legend(handles=[Line2D([], [], marker="o", linestyle="none", color="#2878b5", label="median"),
                           Line2D([], [], marker="|", markersize=12, linestyle="none", color="#c87022", label="p95")],
                   frameon=False, fontsize=8, loc="upper right")
    for axis in axes:
        axis.grid(axis="x", alpha=.2)
        axis.set_axisbelow(True)
    window = bundle["amp"]["acceptance_window"]
    fig.suptitle(f"Stability evidence — recorded window {window['duration_seconds']:g} s", x=.03, ha="left", fontsize=15)
    fig.text(.03, .905, f"{window['start']}  to  {window['end']}  [start, end)", fontsize=9, color="#48515c")
    fig.text(.03, .035, "Sampling is not uptime. Missing evidence remains unknown. Coordinator elapsed may include approval and is not pure network RTT.\n"
             "Observed scheduler completion is not independent recovery. No platform ingestion or long-duration acceptance is inferred.", fontsize=8, color="#48515c")
    fig.subplots_adjust(left=.055, right=.985, top=.79, bottom=.22, wspace=.75)
    for suffix in ("png", "svg"):
        fig.savefig(output / ("stability-overview." + suffix), dpi=180, facecolor="white")
    plt.close(fig)


def write_bundle(bundle, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    heartbeats = [{"agent_alias": f"A{i+1}", "aic": row["aic"], **row["heartbeat_sampling_window"]}
                  for i, row in enumerate(bundle["amp"]["agents"])]
    _csv(output / "heartbeats.csv", heartbeats, ["agent_alias", "aic", "expected_slot_count", "observed_slot_count", "missing_slot_count", "coverage_percent"])
    _csv(output / "scheduler-jobs.csv", bundle["scheduler"]["jobs"], ["run_id", "kind", "outcome", "reported_status", "elapsed_seconds", "start_events", "finish_events", "missing_start", "missing_finish", "conflicting_records", "signals"])
    _csv(output / "coordinator-tasks.csv", bundle["coordinator"]["tasks"], ["incident_id", "logical_task_id", "kind", "status", "started_at", "elapsed_ms", "conflicting_records"])
    _csv(output / "latency.csv", bundle["latency_metrics"], ["metric", "measured_count", "median_ms", "p95_ms"])
    _plot(bundle, output)
    artifacts = [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                 for path in sorted(output.iterdir())]
    (output / "artifact-manifest.json").write_text(json.dumps({"files": artifacts}, indent=2)+"\n", encoding="utf-8")
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Recorded AMP directory; only amp_*.jsonl files are read")
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing outputs are never overwritten")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--expected-aic", action="append", dest="expected_aics")
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=15)
    parser.add_argument("--scheduler", action="append", type=Path, default=[], help="Native scheduler events.jsonl; repeat for explicit inputs")
    parser.add_argument("--coordinator", action="append", type=Path, default=[], help="Final coordinator incident JSON with tasks[].elapsed_ms")
    args = parser.parse_args()
    bundle = summarize_bundle(args.directory, window_start=args.window_start, window_end=args.window_end,
                              expected_aics=args.expected_aics, heartbeat_interval_seconds=args.heartbeat_interval_seconds,
                              scheduler_files=args.scheduler, coordinator_files=args.coordinator)
    files = write_bundle(bundle, args.output)
    print(json.dumps({"written_files": len(files)+1, "window_seconds": bundle["amp"]["acceptance_window"]["duration_seconds"],
                      "scheduler_jobs": len(bundle["scheduler"]["jobs"]), "coordinator_tasks": bundle["coordinator"]["recorded_count"]}))


if __name__ == "__main__":
    main()
