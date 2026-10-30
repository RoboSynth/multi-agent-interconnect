"""Read recorded scheduler/AMP activity; never connect or start services."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.stability_bundle import _scheduler, _timestamp
from eval.stability_report import summarize
from eval.reconcile_access import platform_pairing


def heartbeat_continuity(amp, start, end, expected_aics, cadence=15):
    """Consecutive jointly occupied sample slots, never actual process uptime."""
    slots = {aic: set() for aic in expected_aics}
    seen = set()
    for path in Path(amp).rglob("amp_heartbeat_*.jsonl"):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            try:
                row = json.loads(line)
                stamp, aic, identity = _timestamp(row["timestamp"]), row["aic"], row["log_id"]
                if aic in slots and start <= stamp < end and identity not in seen:
                    slots[aic].add(math.floor((stamp-start)/cadence))
                    seen.add(identity)
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                continue
    count = math.ceil((end-start)/cadence)
    common = set.intersection(*slots.values()) if slots else set()
    def spans(indices):
        rows = []
        for index in sorted(indices):
            if rows and rows[-1][1] == index:
                rows[-1][1] = index+1
            else:
                rows.append([index, index+1])
        return [dict(start=datetime.fromtimestamp(start+a*cadence, timezone.utc).isoformat(),
                     end=datetime.fromtimestamp(min(end, start+b*cadence), timezone.utc).isoformat(),
                     seconds=min(end, start+b*cadence)-(start+a*cadence)) for a, b in rows]
    runs, gaps = spans(common), spans(set(range(count))-common)
    return dict(longest_joint_heartbeat_coverage_seconds=max((row["seconds"] for row in runs), default=0),
                observed_joint_slot_count=len(common), expected_joint_slot_count=count,
                missing_joint_slot_count=count-len(common), interruptions=gaps,
                basis="15-second slots anchored at window start; every expected AIC must have a local heartbeat; not uptime or Discovery liveness")


def planned_interruptions(events_path, start, end):
    pending, result = {}, []
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8-sig").splitlines():
            try:
                row = json.loads(line)
                stamp = _timestamp(row["at"])
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                continue
            if stamp >= end:
                continue
            key = (row.get("host_session"), row.get("request_id"))
            if row.get("event") == "planned_pause_started":
                pending[key] = stamp, row.get("reason")
            elif row.get("event") == "planned_pause_quarantined" and key in pending:
                pending[key] = pending[key][0], row.get("reason", "cleanup unknown")
            elif row.get("event") == "planned_pause_finished" and key in pending:
                began, reason = pending.pop(key)
                if stamp > start:
                    result.append(dict(start=max(start, began), end=stamp, seconds=stamp-max(start, began), reason=reason, closed=True))
    for began, reason in pending.values():
        result.append(dict(start=max(start, began), end=end, seconds=end-max(start, began), reason=reason, closed=False))
    return result


def status(schedule_directory, amp_directory, *, window_start, window_end, expected_aics, team_aics=()):
    start, end = _timestamp(window_start), _timestamp(window_end)
    if start >= end:
        raise ValueError("window must have positive duration")
    directory, amp = Path(schedule_directory), Path(amp_directory)
    if not directory.is_dir() or not amp.is_dir():
        raise ValueError("scheduler and AMP directories must already exist")
    events_path = directory / "events.jsonl"
    scheduler = _scheduler([events_path] if events_path.is_file() else [], start, end)
    metrics = summarize(amp, window_start=window_start, window_end=window_end, expected_aics=expected_aics)
    failures, latest_activity, failed_runs, finished_runs = [], None, {}, {}
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8-sig").splitlines():
            try:
                event = json.loads(line)
                stamp = _timestamp(event.get("at"))
            except (ValueError, TypeError, AttributeError, OverflowError):
                continue
            if not start <= stamp < end:
                continue
            if latest_activity is None or stamp > latest_activity[0]:
                latest_activity = stamp, event["at"]
            if (event.get("event") in {"job_failed", "job_timeout", "dispatch_unknown", "operator_required"}
                    or event.get("event") == "job_finished" and event.get("status") != "completed"):
                failures.append((stamp, {key: event[key] for key in ("at", "event", "kind", "status", "error_class", "run_id") if key in event}))
            if event.get("event") == "job_failed":
                key = event.get("run_id") or "unattributed-"+str(len(failed_runs))
                if key not in failed_runs or stamp > failed_runs[key][0]:
                    failed_runs[key] = stamp, event.get("kind", "unknown")
            if event.get("event") == "job_finished" and event.get("run_id"):
                finished_runs[event["run_id"]] = max(stamp, finished_runs.get(event["run_id"], stamp))
    jobs_by_id = {row["run_id"]: row for row in scheduler["jobs"]}
    for identity, (stamp, kind) in failed_runs.items():
        if finished_runs.get(identity, float("-inf")) > stamp:
            continue
        job = jobs_by_id.setdefault(identity, dict(run_id=identity, kind=kind, outcome="failed"))
        job["outcome"] = "failed"
    active = (json.loads((directory / "schedule.json").read_text(encoding="utf-8-sig"))
              if (directory / "schedule.json").is_file() else {}).get("active") or {}
    if active.get("finished") and active.get("id") in jobs_by_id:
        # A terminal incident is not a finished drill until restoration succeeds.
        job = jobs_by_id[active["id"]]
        if job["outcome"] != "failed":
            job["outcome"] = "unknown"
    # Count external completed handler records, not caller-side send logs or all
    # commands of a task. A fixed log_id is already the AMP deduplication key.
    team, external_tasks, seen = set(team_aics), set(), set()
    access_rows, pairing_rows = 0, []
    access_files = list(amp.rglob("amp_access_*.jsonl"))
    for path in access_files:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            try:
                row = json.loads(line)
                stamp = _timestamp(row.get("timestamp"))
                body, identity = row["body"], row["log_id"]
                if not start <= stamp < end or identity in seen:
                    continue
                caller, callee = body.get("caller", {}).get("aic"), body.get("callee", {}).get("aic")
                seen.add(identity)
                access_rows += 1
                pairing_rows.append(row)
                request = body.get("request", {})
                if (team and row.get("aic") == callee and callee in team and caller not in team
                        and isinstance(caller, str) and caller and request.get("method", "").lower() == "start"
                        and request.get("route") == "aip.onboarding.check" and row.get("correlation_id")):
                    external_tasks.add((caller, callee, row.get("trace_id"), row["correlation_id"]))
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                continue
    state_path = directory / "schedule.json"
    state = json.loads(state_path.read_text(encoding="utf-8-sig")) if state_path.is_file() else {}
    jobs = []
    for kind in ("inspect", "drill"):
        selected = [row for row in jobs_by_id.values() if row["kind"] == kind]
        completed = sum(row["outcome"] == "completed" for row in selected)
        jobs.append(dict(kind=kind, recorded=len(selected), completed=completed,
                         success_percent=round(100 * completed / len(selected), 3) if selected else None,
                         failed=sum(row["outcome"] == "failed" for row in selected),
                         unknown=sum(row["outcome"] == "unknown" for row in selected)))
    return dict(schema_version="longrun-status/1", observation_start=window_start, observation_end=window_end,
        observation_seconds=end-start, actual_process_uptime_seconds=None, process_liveness="not_probed",
        latest_scheduler_activity=latest_activity[1] if latest_activity else None,
        jobs=jobs, latest_failure=max(failures, key=lambda item: item[0])[1] if failures else None,
        active_run=(state.get("active") or {}).get("id"), next_due=state.get("next_due", {}),
        heartbeat_agents=metrics["agents"], local_access_records=metrics["log_types"].get("access", 0),
        heartbeat_continuity=heartbeat_continuity(amp, start, end, expected_aics),
        planned_interruptions=planned_interruptions(events_path, start, end),
        local_task_pairing=platform_pairing(pairing_rows) if access_files else None,
        external_onboarding_tasks=len(external_tasks) if team and access_files else None,
        external_call_basis="unique callee Start/correlation_id in supplied team AIC namespace",
        invalid_amp_records=metrics["invalid_records"], scheduler_diagnostics=scheduler["diagnostics"],
        continuous_24h_accepted=False, platform_ingestion_verified=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule-directory", type=Path, required=True)
    parser.add_argument("--amp-directory", type=Path, required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", default=None)
    parser.add_argument("--expected-aic", action="append", required=True)
    parser.add_argument("--team-aic", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = status(args.schedule_directory, args.amp_directory, window_start=args.window_start,
        window_end=args.window_end or datetime.now(timezone.utc).isoformat(),
        expected_aics=args.expected_aic, team_aics=args.team_aic)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
