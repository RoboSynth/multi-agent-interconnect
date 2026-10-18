"""Prepare one isolated Linux stdout collector; no Docker or network calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render as fluent
from render import COLLECTION_ROLES, KINDS

PROJECT = "incident-pilot-t06-collector-20261018"
STATE_VOLUME = PROJECT + "-offsets"
SOURCE_LABEL = "incident-pilot.collector.sources-sha256"


def project_name(mode):
    if mode not in {"stdout", "kafka"}:
        raise ValueError("mode.invalid")
    return PROJECT if mode == "stdout" else PROJECT + "-kafka"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linux_path(path):
    value = Path(path).resolve().as_posix()
    if re.match(r"^[A-Za-z]:/", value):
        return "/mnt/" + value[0].lower() + value[2:]
    if value.startswith("/"):
        return value
    raise ValueError("A Linux-visible absolute path is required")


def sources_from_plan(plan, root=ROOT):
    rows = plan.get("sources", [])
    if len(rows) != 7 or {row.get("role") for row in rows} != set(COLLECTION_ROLES):
        raise ValueError("Exactly the seven collection roles are required")
    sources = []
    for role in COLLECTION_ROLES:
        row = next(row for row in rows if row["role"] == role)
        target = "/sources/" + role
        if row.get("collector_mount") != target or row.get("collector_log_directory") != target:
            raise ValueError("Source targets must match their roles")
        if role == "coordinator":
            directory = (root / row["host_project_relative_directory"]).resolve()
            if not directory.is_relative_to(root.resolve()) or not directory.is_dir():
                raise ValueError("The coordinator AMP directory must exist inside this project")
            sources.append({"role": role, "type": "bind", "source": linux_path(directory), "target": target})
        else:
            subpath = "amp-" + role
            if row.get("volume_subpath") != subpath or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", row.get("named_volume", "")):
                raise ValueError("Only the role's AMP subdirectory may be mounted")
            sources.append({"role": role, "type": "volume", "source": row["named_volume"],
                            "subpath": subpath, "target": target})
    identities = {(row["type"], row["source"], row.get("subpath")) for row in sources}
    if len(identities) != 7 or len({row["source"] for row in sources if row["type"] == "volume"}) != 5:
        raise ValueError("Expected seven distinct source directories in five named volumes plus one bind")
    return sources


def render_config(sources, *, mode="stdout", kafka=None):
    config = fluent.render_collection_paths(
        {row["role"]: row["target"] for row in sources},
        {role: "/collector-state/amp-" + role + "-{kind}.db" for role in COLLECTION_ROLES},
        "/collector/parsers.conf", mode=mode, kafka=kafka, read_from_head=True)
    config = config.replace("    Grace 1", "    Grace 5")
    if mode == "stdout":
        config = config.replace("    Workers 0", "    Workers 0\n    Format json_lines\n    Json_Date_Key false")
    return config


def state_labels(binding, mode="stdout"):
    return {"incident-pilot.collector": "t06", "incident-pilot.collector.project": project_name(mode),
            "incident-pilot.collector.mode": mode, SOURCE_LABEL: binding}


def validate_existing_state(metadata, binding, mode="stdout"):
    """Call with selected Docker volume metadata before every start/reuse."""
    if metadata is None:
        return
    if metadata.get("Name") != project_name(mode) + "-offsets" or any((metadata.get("Labels") or {}).get(key) != value
            for key, value in state_labels(binding, mode).items()):
        raise ValueError("Existing offset volume belongs to a different source collection")


def compose_spec(sources, image, config_path, parser_path, *, mode="stdout", transport_mounts=(), environment=()):
    if not re.fullmatch(r"cr\.fluentbit\.io/fluent/fluent-bit@sha256:[0-9a-f]{64}", image):
        raise ValueError("Pin an official Fluent Bit repository digest")
    binding = digest(sources)
    project = project_name(mode)
    volumes = {"offsets": {"name": project + "-offsets", "labels": state_labels(binding, mode)}}
    mounts = [{"type": "bind", "source": str(config_path), "target": "/collector/fluent-bit.conf",
               "read_only": True, "bind": {"create_host_path": False}},
              {"type": "bind", "source": str(parser_path), "target": "/collector/parsers.conf",
               "read_only": True, "bind": {"create_host_path": False}}]
    for row in sources:
        mount = {"type": row["type"], "source": row["source"], "target": row["target"], "read_only": True}
        if row["type"] == "volume":
            key = "source-" + row["source"]
            volumes[key] = {"external": True, "name": row["source"]}
            mount.update(source=key, volume={"nocopy": True, "subpath": row["subpath"]})
        else:
            mount["bind"] = {"create_host_path": False}
        mounts.append(mount)
    mounts.extend(transport_mounts)
    mounts.append({"type": "volume", "source": "offsets", "target": "/collector-state", "volume": {"nocopy": True}})
    service = {
        "image": image, "pull_policy": "never", "container_name": project,
        "command": ["-c", "/collector/fluent-bit.conf"], "network_mode": "none" if mode == "stdout" else "bridge", "read_only": True,
        "restart": "no", "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "pids_limit": 64, "stop_signal": "SIGTERM", "stop_grace_period": "15s",
        "labels": state_labels(binding, mode), "volumes": mounts}
    if environment:
        service["environment"] = sorted(environment)
    return {"name": project, "services": {"collector": service}, "volumes": volumes}


def kafka_transport(profile):
    """Validate host paths, then map only individual TLS files into the container."""
    import os
    fluent.validate_kafka(profile)
    mapped = {"brokers": profile["brokers"], "rdkafka": dict(profile["rdkafka"])}
    mounts = []
    names = {"ssl.ca.location": "ca.pem", "ssl.certificate.location": "client.pem", "ssl.key.location": "client-key.pem"}
    for key in fluent.TLS_FILES:
        if key in profile["rdkafka"]:
            value = fluent.ENV_REFERENCE.sub(lambda match: os.environ[match[1]], profile["rdkafka"][key])
            target = "/collector-transport/" + names[key]
            mounts.append({"type": "bind", "source": linux_path(value), "target": target,
                           "read_only": True, "bind": {"create_host_path": False}})
            mapped["rdkafka"][key] = target
    environment = {name for value in mapped["rdkafka"].values() for name in fluent.ENV_REFERENCE.findall(value)}
    return mapped, mounts, environment


def prepare(output, image, plan_path=HERE / "collection-plan.example.json", *, mode="stdout", kafka_settings=None):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "artifacts") or output == ROOT / "artifacts":
        raise ValueError("Use a new dedicated project artifact directory")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8-sig"))
    sources = sources_from_plan(plan)
    mapped, transport, environment = None, [], set()
    if mode == "kafka":
        if kafka_settings is None:
            raise ValueError("Explicit Kafka settings are required")
        mapped, transport, environment = kafka_transport(json.loads(Path(kafka_settings).read_text(encoding="utf-8-sig")))
    elif kafka_settings is not None:
        raise ValueError("Kafka settings require explicit Kafka mode")
    config = render_config(sources, mode=mode, kafka=mapped)
    spec = compose_spec(sources, image, linux_path(output / "collector.conf"), linux_path(output / "parsers.conf"),
        mode=mode, transport_mounts=transport, environment=environment)
    output.mkdir(parents=True, exist_ok=False)
    (output / "collector.conf").write_text(config, encoding="utf-8")
    (output / "parsers.conf").write_bytes((HERE / "parsers.conf").read_bytes())
    (output / "compose.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    prepared = {"schema_version": "t06-linux-collector/1", "status": "prepared_not_started",
        "project": project_name(mode), "container_name": project_name(mode), "state_volume_name": project_name(mode) + "-offsets",
        "state_volume_labels": state_labels(digest(sources), mode), "source_collection": sources,
        "source_collection_sha256": digest(sources), "image": image,
        "read_from_head": True, "mode": mode, "historical_replay_scope": "Only this mode's new isolated offset volume; stdout consumption does not imply Kafka delivery",
        "tail_inputs": 42, "offset_databases": 42, "named_source_volumes": 5,
        "actual_container_starts": 0, "network": mode == "kafka", "kafka_or_monitor_verified": False,
        "preconditions": ["Verify exclusive one-collector ownership of all seven directories",
            "Inspect existing state volume and call validate_existing_state before every start; never reuse with a changed source mapping",
            "Verify all six AMP volume subpaths exist; never fall back to the entire source volume",
            "Record all 29 original container IDs/StartedAt/restart counts and verify them unchanged after stop"],
        "observation": "Parse stdout; verify seven configured AIC identities and all six kinds with natural appends only; do not reject ordinary source growth by frozen log-file hashes",
        "stop": "Verify held collector ID/name/labels, docker stop with SIGTERM and 15-second grace, require actual ExitCode 0 and no forced kill; preserve offsets and originals",
        "file_sha256": {name: sha(output / name) for name in ("collector.conf", "parsers.conf", "compose.json")},
        "input_sha256": {"collection_plan": sha(plan_path), "renderer": sha(HERE / "render.py"),
                         "preparer": sha(Path(__file__))}}
    (output / "plan.json").write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", required=True, help="Official cr.fluentbit.io repository digest")
    parser.add_argument("--mode", "--Mode", choices=["stdout", "kafka"], default="stdout")
    parser.add_argument("--kafka-settings", "--KafkaSettings", type=Path)
    args = parser.parse_args()
    plan = prepare(args.output, args.image, mode=args.mode, kafka_settings=args.kafka_settings)
    print(json.dumps({"status": plan["status"], "source_collection_sha256": plan["source_collection_sha256"],
        "tail_inputs": 42, "offset_databases": 42, "actual_container_starts": 0}))


if __name__ == "__main__":
    main()
