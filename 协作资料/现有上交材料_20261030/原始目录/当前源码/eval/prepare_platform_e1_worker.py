"""Prepare an isolated E1 worker bundle/overlay; no Docker, platform or resource calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from acps_mcp_bridge.experiment import ExperimentSpec, EXIT_CODES

SOURCES = ("eval/platform_database_worker.py", "acps_mcp_bridge/experiment.py", "incident/local_worker.py")
encode = lambda value: (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
sha = lambda data: hashlib.sha256(data).hexdigest()


def documents(*, experiment_id, incident_id, primary_aic, backup_aic, crash_point, arm_primary=False,
              suspend_primary=False):
    if suspend_primary and crash_point != "before_modification":
        raise ValueError("Primary suspension is only supported before modification")
    tool = "db.read_only_status" if crash_point == "after_observation" else "db.restore_writes"
    common = dict(schema_version="e1-worker/1", experiment_id=experiment_id, incident_id=incident_id,
                  primary_aic=primary_aic, backup_aic=backup_aic, crash_tool=tool)
    primary = dict(common, worker_role="primary", armed=arm_primary, crash_point=crash_point)
    backup = dict(common, worker_role="backup", armed=False, crash_point=None)
    if suspend_primary:
        primary.update(schema_version="e1-worker/2", interruption_mode="suspend")
        backup.update(schema_version="e1-worker/2", interruption_mode="exit")
    for value, aic in ((primary, primary_aic), (backup, backup_aic)):
        ExperimentSpec.from_document(value, experiment_id=experiment_id, executor_aic=aic)
    return {"primary.json": primary, "backup.json": backup}


def prepare(output, **options):
    import yaml
    configs = documents(**options)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("E1 output must be new; preserve prior attempts")
    payloads = {name: encode(value) for name, value in configs.items()}
    for name in SOURCES:
        payloads["source/" + name] = (ROOT / name).read_bytes()
    manifest = dict(schema_version="e1-worker-bundle/1", experiment_id=options["experiment_id"],
        source_sha256={name: sha(data) for name, data in payloads.items() if name.startswith("source/")},
        experiment_sha256={name: sha(data) for name, data in payloads.items() if name.endswith(".json")},
        image_base_source_attestation_required=True, platform_identity_and_exclusive_Inbox_attestation_required=True,
        preparation_is_execution_authorization=False)
    payloads["worker-source-manifest.json"] = encode(manifest)
    digest = sha(payloads["worker-source-manifest.json"])
    services = {}
    for role, service in (("primary", "database-agent"), ("backup", "database-backup-agent")):
        services[service] = dict(command=["python", "/experiment/source/eval/platform_database_worker.py",
            "--config", "/domain/bridge.json", "--experiment", "/experiment/" + role + ".json",
            "--experiment-id", options["experiment_id"], "--trace", "/state/experiments/" + options["experiment_id"] + "/" + role + ".jsonl",
            "--bundle-manifest", "/experiment/worker-source-manifest.json", "--bundle-sha", digest, "--serve"],
            volumes=[dict(type="bind", source="${NEW7_E1_EXPERIMENT_ROOT:?Set the frozen E1 bundle WSL absolute directory}",
                          target="/experiment", read_only=True)],
            labels={"incident-pilot.experiment": options["experiment_id"], "incident-pilot.e1-role": role})
    services["database-agent"]["restart"] = "no"
    if options.get("suspend_primary"):
        services["database-agent"]["init"] = True
    payloads["e1-worker-overlay.yml"] = yaml.safe_dump(dict(services=services), sort_keys=False, allow_unicode=True).encode()
    payloads["README.md"] = ("# E1 worker overlay preparation\n\n"
        "This bundle only prepares source/configuration. The primary is unarmed by default; backup is always unarmed. "
        "A later explicitly authorized controller must bind the exact NEW7 project, image/source IDs, existing own group, "
        "shared ledger, coordinator term and real approvals before starting or replacing any worker. "
        "Stop the owned prior domain consumer before switching entrypoints; never start a second Inbox for one AIC.\n\n"
        "Append e1-worker-overlay.yml after the existing compose/agents/new7 files. "
        "Set NEW7_E1_EXPERIMENT_ROOT to this frozen bundle's WSL absolute path. "
        "Only primary restart is disabled. Existing /domain and shared /state mounts remain; "
        "the extra /experiment mount is read-only. The normal /srv image sources remain intact; "
        "only the three declared experiment imports use the bundle. The manifest pins all three sources and both role documents.\n\n"
        "--suspend-primary selects e1-worker/2 only before db.restore_writes. Its primary has init: true, "
        "so the Linux worker can SIGSTOP its own non-init PID after durable received, then continue that same request "
        "after SIGCONT; the backup remains unarmed exit mode. Default e1-worker/1 exit behavior is unchanged. "
        "Suspended/revived/result traces bind the original request SHA and PID/start ticks before AIP product submission.\n\n"
        "The trace counts actual modifying MCP invocations/returns per operation and executor, including attempts with no return; "
        "it does not count physical side effects. Traces belong in the separate primary/backup /state paths. "
        "Source preparation is not an experiment authorization, image/import attestation, live exit, takeover, or H00 result.\n").encode()
    for name, data in payloads.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return dict(status="E1_WORKER_OVERLAY_PREPARED_NOT_EXECUTED", experiment_id=options["experiment_id"],
        primary_armed=options.get("arm_primary", False), backup_armed=False, manifest_sha256=digest,
        payloads={name: dict(sha256=sha(data), bytes=len(data)) for name, data in payloads.items()},
        network_Docker_model_resource_actions=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--primary-aic", required=True)
    parser.add_argument("--backup-aic", required=True)
    parser.add_argument("--crash-point", choices=sorted(EXIT_CODES), required=True)
    parser.add_argument("--arm-primary", action="store_true")
    parser.add_argument("--suspend-primary", action="store_true", help="E1-c only: suspend the same non-init primary before modification")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    options = {key: value for key, value in vars(args).items() if key not in {"output", "prepare"}}
    if not args.prepare:
        documents(**options)
        print(json.dumps(dict(status="E1_WORKER_PLAN_VALIDATED_NO_WRITES", resource_or_network_actions=0)))
        return 0
    print(json.dumps(prepare(args.output, **options)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
