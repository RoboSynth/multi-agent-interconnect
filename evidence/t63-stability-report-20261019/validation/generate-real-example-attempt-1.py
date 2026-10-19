"""Project an existing, hash-frozen 30-minute record and generate a T63 example.

This helper is local preparation, not a test or experiment runner. Raw inputs are
never modified. Public input projection keeps exact timestamps/status/durations,
replaces identifiers, and omits unrelated fields and out-of-window heartbeats.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "checkout"))
from eval.stability_bundle import summarize_bundle, write_bundle

START, END = "2026-10-18T06:55:21Z", "2026-10-18T07:25:21Z"
PREFIX = "new7-inspect-session-20261018/runs/01d3bfe8bc6145689c33271fbc366d65"
SNAPSHOT = "t05-fixed-sdk-access-reconciliation-20261018/attempt-2"
EXPECTED = {
    "application-agent/amp_heartbeat_application.jsonl": "5e65f483718b9626d189e9bf99199c170ab6ad2344ea3ff9df2c8e3a2adb1224",
    "coordinator/amp_heartbeat_coordinator.jsonl": "9cf7e47fbffc5b3fe0ac7055c0e6b9497a75715758d9ff13fa79595a2ee5adb4",
    "database-agent/amp_heartbeat_database.jsonl": "20decb10a62653a6391d667d124767b064a9267ac7fce13d4d5b31bf595266b0",
    "database-backup-agent/amp_heartbeat_database-backup.jsonl": "b812787ed49fad16a76f015d449f045d53f1e9df01ee8ab831a31a717b481eee",
    "onboarding-agent/amp_heartbeat_onboarding.jsonl": "d812ad9d191e92421afb3b964352ab68fa87f514d86dbe732dd75bf9ec78ffcb",
    "ops-agent/amp_heartbeat_ops.jsonl": "98026d2f61b465508a03099e21e77702e676fe8c933e1b402695920e3c436a68",
    "verification-agent/amp_heartbeat_verification.jsonl": "c1bb66f68ea22bcb4660bda6920abd665d81f76779d14b5a066ae0591f4c8c9e"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original_report_path = args.artifact_root / SNAPSHOT / "stability-report.json"
    assert sha(original_report_path) == "fd77fb300faa25dcf9e59cbaaab9b8f76fb38381120c4465c44a78468df0688d"
    original = json.loads(original_report_path.read_text(encoding="utf-8"))
    aliases = {aic: f"A{i+1}" for i, aic in enumerate(original["expected_aics"])}
    assert len(aliases) == 7
    start, end = [datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() for value in (START, END)]
    bindings = []
    for rel, expected in EXPECTED.items():
        path = args.artifact_root / SNAPSHOT / "private-heartbeat-inputs" / rel
        assert sha(path) == expected
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
            if start <= stamp < end:
                rows.append({"log_id": "heartbeat-"+hashlib.sha256(row["log_id"].encode()).hexdigest(),
                             "log_type": row["log_type"], "timestamp": row["timestamp"], "aic": aliases[row["aic"]], "body": {}})
        target = args.output / "inputs/amp" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")
        bindings.append({"source_artifact_relative": SNAPSHOT+"/private-heartbeat-inputs/"+rel,
                         "raw_sha256": expected, "raw_bytes": path.stat().st_size,
                         "projected_path": target.relative_to(args.output).as_posix(), "projected_sha256": sha(target),
                         "in_window_records": len(rows)})
    scheduler = args.artifact_root / PREFIX / "schedule/events.jsonl"
    assert sha(scheduler) == "565a1bd180d6afc366686ec12a00a3391fa42e5cdb0024baf21acdc4cb2358bc"
    events = []
    for line in scheduler.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        at = datetime.fromisoformat(row["at"].replace("Z", "+00:00")).timestamp()
        if start <= at < end:
            event = {key: row[key] for key in ("at", "event", "kind", "status", "seconds", "mode") if key in row}
            if "run_id" in row: event["run_id"] = "run-1"
            if "incident_id" in row: event["incident_id"] = "incident-1"
            events.append(event)
    assert len(events) == 2
    projected_scheduler = args.output / "inputs/events.jsonl"
    projected_scheduler.write_text("".join(json.dumps(row)+"\n" for row in events), encoding="utf-8")
    bindings.append({"source_artifact_relative": PREFIX+"/schedule/events.jsonl", "raw_sha256": sha(scheduler),
                     "projected_path": "inputs/events.jsonl", "projected_sha256": sha(projected_scheduler), "in_window_records": len(events)})
    incident_path = args.artifact_root / PREFIX / "workbench/incidents/inc-7de0b95cdfb64b67.json"
    assert sha(incident_path) == "b8fe01f846e0655d887ef6882a1da6a784bde388699d39d1248eeb8e21540bf4"
    incident = json.loads(incident_path.read_text(encoding="utf-8"))
    projected = {key: incident[key] for key in ("started_at", "status", "elapsed_seconds")}
    projected.update(id="incident-1", tasks=[{"logical_task_id": f"task-{i+1}", **{
        key: row[key] for key in ("kind", "status", "started_at", "elapsed_ms") if key in row}}
        for i, row in enumerate(incident["tasks"])])
    projected_incident = args.output / "inputs/incident.json"
    write_json(projected_incident, projected)
    bindings.append({"source_artifact_relative": PREFIX+"/workbench/incidents/inc-7de0b95cdfb64b67.json",
                     "raw_sha256": sha(incident_path), "projected_path": "inputs/incident.json", "projected_sha256": sha(projected_incident)})
    bundle = summarize_bundle(args.output / "inputs/amp", window_start=START, window_end=END,
                              expected_aics=list(aliases.values()), scheduler_files=[projected_scheduler], coordinator_files=[projected_incident])
    assert bundle["amp"]["expected_aic_sampling_window"] == original["expected_aic_sampling_window"]
    assert bundle["scheduler"]["counts"] == {"completed": 1}
    assert bundle["coordinator"]["measured_count"] == 6
    assert bundle["amp"]["median_access_ms"] is None
    write_bundle(bundle, args.output / "report")
    write_json(args.output / "source-bindings.json", {"window_start": START, "window_end": END, "duration_seconds": 1800,
        "raw_heartbeat_report_sha256": sha(original_report_path), "raw_source_files": bindings,
        "projection": "Explicit field whitelist; in-window heartbeat/scheduler selection; stable identifier aliases; exact timestamps/status/durations retained. Raw inputs untouched. Task args/products/facts and heartbeat body omitted.",
        "expected_identity_basis": "Explicit seven-identity set from hash-frozen original stability-report.json, replaced one-to-one by aliases; not inferred from present heartbeat samples.",
        "scope": "One existing 30-minute heartbeat window and one inspection with six measured tasks. No drill, AMP access latency, new runtime, platform ingestion or 24-hour acceptance is claimed."})
    print(json.dumps({"raw_source_files": len(bindings), "window_seconds": 1800, "heartbeat_slots": bundle["amp"]["expected_aic_sampling_window"],
                      "scheduler_jobs": 1, "measured_tasks": 6, "median_task_elapsed_ms": bundle["coordinator"]["median_ms"]}))


if __name__ == "__main__":
    main()
