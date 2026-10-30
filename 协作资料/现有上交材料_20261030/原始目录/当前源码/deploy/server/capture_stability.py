"""Snapshot existing cloud logs for a completed window; never opens identities.

Run once after the requested end time. Outputs are immutable evidence, not an
uptime certification. Missing samples and scheduler interruptions stay visible.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def validate_window(start, end, now=None):
    start, end = timestamp(start), timestamp(end)
    now = now or datetime.now(timezone.utc)
    if start >= end:
        raise ValueError("end must follow start")
    if end > now:
        raise ValueError("observation window has not finished")
    return start, end


def project_incident(value):
    return {
        "id": value["id"], "status": value.get("status"),
        "tasks": [{key: row.get(key) for key in
                   ("logical_task_id", "started_at", "elapsed_ms", "status", "kind")}
                  for row in value["tasks"]],
    }


def capture(root, output, start, end):
    start_at, end_at = validate_window(start, end)
    root, output = Path(root).resolve(), Path(output).resolve()
    sys.path.insert(0, str(root))
    from eval.stability_bundle import summarize_bundle

    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    plan = load(root / "artifacts/cloud-collector-20261019/collection-plan.json")
    host = load(root / "runtime/private/cloud-longrun/control/host.json")
    if len(set(host["aics"])) != 7:
        raise ValueError("expected seven distinct cloud identities")
    output.mkdir(parents=True, exist_ok=False)
    inputs, manifest = output / "inputs", []

    def save(source, target, projection=None):
        raw = source.read_bytes()
        saved = raw if projection is None else json.dumps(
            projection(json.loads(raw)), ensure_ascii=False, indent=2).encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(saved)
        manifest.append({
            "source": str(source), "destination": target.relative_to(output).as_posix(),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "saved_sha256": hashlib.sha256(saved).hexdigest(),
        })

    for source in plan["sources"]:
        if source["role"] == "coordinator":
            origin = root / source["host_project_relative_directory"]
        else:
            volume = json.loads(subprocess.check_output(
                ["docker", "volume", "inspect", source["named_volume"]], text=True))[0]
            origin = Path(volume["Mountpoint"]) / source["volume_subpath"]
        for path in sorted(origin.glob("amp_*.jsonl")):
            if path.name.startswith(("amp_heartbeat_", "amp_access_")):
                save(path, inputs / "amp" / source["role"] / path.name)
    save(root / "runtime/private/cloud-new7-schedule/events.jsonl", inputs / "scheduler.jsonl")
    incidents = []
    for path in sorted((root / "artifacts/cloud-longrun-workbench/incidents").glob("*.json")):
        if isinstance(load(path).get("tasks"), list):
            target = inputs / "incidents" / path.name
            save(path, target, project_incident)
            incidents.append(target)
    for path in sorted((root / "evidence/longrun-20261020").glob("*.json")):
        save(path, output / "daily" / path.name)
    summary = summarize_bundle(
        inputs / "amp", window_start=start, window_end=end,
        expected_aics=host["aics"], scheduler_files=[inputs / "scheduler.jsonl"],
        coordinator_files=incidents)
    timeline, invalid = [], 0
    for line in (inputs / "scheduler.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            at = timestamp(row["at"])
            if start_at <= at < end_at and row["event"] not in ("job_started", "job_finished"):
                timeline.append(row)
        except (ValueError, TypeError, KeyError):
            invalid += 1
    receipt = {
        "schema_version": "cloud-stability-snapshot/1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "window_start": start, "window_end": end,
        "window_seconds": (end_at - start_at).total_seconds(),
        "full_24h_window": (end_at - start_at).total_seconds() >= 86400,
        "scheduler_other_events": timeline,
        "invalid_scheduler_records": invalid,
        "scope": "Heartbeat sampling coverage and recorded jobs; not exact uptime. "
                 "A full observation window is not a pass verdict. Examine gaps, "
                 "failures and maintenance events. No external calls are initiated.",
        "files": manifest,
    }
    for name, value in (("summary.json", summary), ("source-manifest.json", receipt)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    # Written last: absent marker means the snapshot is incomplete.
    (output / "COMPLETE.json").write_text(json.dumps({
        "captured_at": receipt["captured_at"],
        "summary_sha256": hashlib.sha256((output / "summary.json").read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256((output / "source-manifest.json").read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    return {"output": str(output), "window_seconds": receipt["window_seconds"],
            "full_24h_window": receipt["full_24h_window"],
            "scheduler": summary["scheduler"]["counts"],
            "scheduler_other_events": len(timeline)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.repo_root, args.output, args.start, args.end)))


if __name__ == "__main__":
    main()
