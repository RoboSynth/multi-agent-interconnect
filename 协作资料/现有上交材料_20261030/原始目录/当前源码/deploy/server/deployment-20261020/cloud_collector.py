"""Stage 6 NEW7 collector helper; no action occurs without --execute.

Designed for /opt/incident-pilot. All Docker/network operations are confined to
explicit actions; importing this file is offline. Canonical source is unchanged.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

PROJECT = "incident-pilot-new7-cloud-20261019"
COLLECTOR_PROJECT = PROJECT + "-collector"
IMAGE = "cr.fluentbit.io/fluent/fluent-bit@sha256:0c768b8263e8935e19cea66fbd7e1c768db7f9edc710e832e93f058bad0ef027"
DEPLOYMENT = "runtime/private/cloud-new7-20261019/deployment.json"
AMP = "artifacts/cloud-longrun-workbench/transport/amp"
WORK = "artifacts/cloud-collector-20261019"
PRIVATE = "runtime/private/cloud-collector-scan-20261019"
ROLES = ("coordinator", "application", "database", "database-backup", "ops", "verification", "onboarding")
KINDS = ("audit", "heartbeat", "metrics", "access", "message", "system")
STATE_KEY = {"database-backup": "database-agent-state", **{role: role + "-agent-state" for role in ROLES[1:] if role != "database-backup"}}
READ_LOGS = r'''
import base64,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
if not p.is_dir() or p.is_symlink(): raise RuntimeError("AMP directory missing or symlink")
rows=[]
for kind in ("audit","heartbeat","metrics","access","message","system"):
 for f in sorted(p.glob("amp_"+kind+"_*.jsonl")):
  if not f.is_file() or f.is_symlink(): raise RuntimeError("AMP log is not an ordinary file")
  data=f.read_bytes()
  if len(data)>16777216: raise RuntimeError("AMP snapshot exceeds bounded scan size")
  rows.append({"kind":kind,"name":f.name,"data":base64.b64encode(data).decode()})
print(json.dumps(rows))
'''


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=45)
    if result.returncode:
        # Never print Docker inspect environments or scanned log contents.
        raise RuntimeError(f"Command failed: {args[0]} (exit {result.returncode})")
    return result.stdout


def docker(*args):
    return run(["docker", *args])


def inspect_one(kind, identifier):
    rows = json.loads(docker(kind, "inspect", identifier) if kind == "volume" else docker("inspect", identifier))
    if len(rows) != 1:
        raise ValueError("Expected exactly one Docker object")
    return rows[0]


def container_binding(row, role):
    labels = row.get("Config", {}).get("Labels") or {}
    if (labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != role + "-agent"
            or not row.get("State", {}).get("Running")):
        raise ValueError("Domain container ownership or running state differs")
    mounts = [mount for mount in row.get("Mounts", []) if mount.get("Destination") == "/state"]
    if len(mounts) != 1 or mounts[0].get("Type") != "volume" or not mounts[0].get("Name"):
        raise ValueError("Expected exactly one named /state volume")
    return {"id": row["Id"], "role": role, "name": row["Name"], "volume": mounts[0]["Name"],
            "started_at": row["State"]["StartedAt"], "restart_count": row.get("RestartCount", 0),
            "compose_project": PROJECT, "compose_service": role + "-agent"}


def resolve_sources(root):
    manifest = load(root / DEPLOYMENT)
    if manifest.get("project") != PROJECT or manifest.get("mode") != "seven" or manifest.get("wsl_distro") is not None:
        raise ValueError("Expected this exact native Linux NEW7 deployment")
    amp = (root / AMP).resolve()
    if not amp.is_relative_to(root) or not amp.is_dir() or amp.is_symlink():
        raise ValueError("The longrun coordinator AMP directory must already exist")
    bindings, sources = {}, [{"role": "coordinator", "host_project_relative_directory": AMP,
                            "collector_mount": "/sources/coordinator", "collector_log_directory": "/sources/coordinator"}]
    for role in ROLES[1:]:
        ids = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT,
                     "--filter", "label=com.docker.compose.service=" + role + "-agent").split()
        if len(ids) != 1:
            raise ValueError("Expected exactly one owned domain container: " + role)
        row = container_binding(inspect_one("container", ids[0]), role)
        metadata = inspect_one("volume", row["volume"])
        labels = metadata.get("Labels") or {}
        if metadata.get("Name") != row["volume"] or labels.get("com.docker.compose.project") != PROJECT or labels.get("com.docker.compose.volume") != STATE_KEY[role]:
            raise ValueError("Named state volume ownership differs: " + role)
        docker("exec", row["id"], "python", "-c",
               "import pathlib,sys; p=pathlib.Path(sys.argv[1]); assert p.is_dir() and not p.is_symlink()", "/state/amp-" + role)
        bindings[role] = row
        sources.append({"role": role, "named_volume": row["volume"], "volume_subpath": "amp-" + role,
                        "collector_mount": "/sources/" + role, "collector_log_directory": "/sources/" + role})
    if len({row["volume"] for row in bindings.values()}) != 5 or bindings["database"]["volume"] != bindings["database-backup"]["volume"]:
        raise ValueError("Expected exactly five state volumes and shared primary/backup state")
    return {"sources": sources, "source_mounts_read_only": True, "scope": PROJECT}, bindings


def module(root, name, relative):
    file = root / relative
    sys.path.insert(0, str(file.parent))
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location(name, file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def preparer(root):
    value = module(root, "cloud_linux_collector", "deploy/fluent-bit/prepare_linux_collector.py")
    if value.ROOT.resolve() != root:
        raise ValueError("Collector source checkout differs from selected root")
    # Process-local selection, not a modification of the canonical SDK/script.
    value.PROJECT = COLLECTOR_PROJECT
    return value


def existing_volume(name):
    names = docker("volume", "ls", "--format", "{{.Name}}").splitlines()
    return inspect_one("volume", name) if name in names else None


def prepare(root):
    work = root / WORK
    if work.exists():
        raise FileExistsError("Collector preparation already exists; preserve and inspect it")
    plan, bindings = resolve_sources(root)
    prep = preparer(root)
    if existing_volume(prep.project_name("kafka") + "-offsets") is not None:
        raise ValueError("Initial deployment requires a brand-new offset volume; do not erase or reuse it")
    # Refuse any existing same-name collector, including an exited one.
    if docker("ps", "-aq", "--filter", "name=^/" + prep.project_name("kafka") + "$").strip():
        raise ValueError("A same-name collector already exists")
    work.mkdir(mode=0o700)
    save(work / "collection-plan.json", plan)
    save(work / "source-bindings.json", bindings)
    stages = {}
    for name, kinds in (("heartbeat-access", "heartbeat,access"), ("all-six", "all")):
        result = prep.prepare(work / name, IMAGE, plan_path=work / "collection-plan.json", mode="kafka",
                              kafka_settings=root / "deploy/fluent-bit/kafka-settings.wutong-public.example.json",
                              read_from_head=False, kinds=kinds)
        if result["read_from_head"] is not False or result["source_collection_sha256"] != prep.digest(prep.sources_from_plan(plan)):
            raise ValueError("Collector preparation does not preserve the selected source mapping")
        stages[name] = {key: result[key] for key in ("project", "container_name", "state_volume_name", "state_volume_labels", "kinds", "tail_inputs", "outputs", "read_from_head")}
    if stages["heartbeat-access"]["state_volume_name"] != stages["all-six"]["state_volume_name"]:
        raise ValueError("The phased collector must share offsets")
    save(work / "prepared.json", {"status": "prepared_not_started", "stages": stages, "image": IMAGE})
    return {"status": "prepared_not_started", "work": str(work), "stages": stages}


def stable_bindings(root):
    recorded = load(root / WORK / "source-bindings.json")
    for role, expected in recorded.items():
        actual = container_binding(inspect_one("container", expected["id"]), role)
        if actual != expected:
            raise ValueError("Original source container identity/start/restart changed: " + role)
    return recorded


def host_logs(directory):
    rows = []
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Coordinator AMP directory is unavailable")
    for kind in KINDS:
        for file in sorted(directory.glob("amp_" + kind + "_*.jsonl")):
            if not file.is_file() or file.is_symlink():
                raise ValueError("AMP log is not an ordinary file")
            data = file.read_bytes()
            if len(data) > 16777216:
                raise ValueError("AMP snapshot exceeds bounded scan size")
            rows.append({"kind": kind, "name": file.name, "data": base64.b64encode(data).decode()})
    return rows


def scan(root):
    bindings = stable_bindings(root)
    private = root / PRIVATE / stamp()
    private.mkdir(parents=True, mode=0o700)
    counts = {kind: 0 for kind in KINDS}
    paths = []
    for role in ROLES:
        rows = host_logs(root / AMP) if role == "coordinator" else json.loads(docker(
            "exec", bindings[role]["id"], "python", "-c", READ_LOGS, "/state/amp-" + role))
        destination = private / role
        destination.mkdir(mode=0o700)
        for row in rows:
            if row["kind"] not in KINDS or Path(row["name"]).name != row["name"]:
                raise ValueError("Unexpected source log metadata")
            content = base64.b64decode(row["data"], validate=True)
            file = destination / row["name"]
            file.write_bytes(content)
            file.chmod(0o600)
            paths.append(file)
            counts[row["kind"]] += sum(bool(line.strip()) for line in content.splitlines())
    secret_scan = module(root, "cloud_secret_scan", "eval/secret_scan.py")
    known = []
    for env in (root / "runtime/private/cloud-new7-20261019/compose.env", root / "runtime/private/cloud-new7-20261019/approval.env"):
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if any(term in key for term in ("PASSWORD", "TOKEN", "SECRET", "DATABASE_URL", "DATABASE_URI", "DSN")) and value:
                    known.append(value)
    report = secret_scan.scan(paths, known)
    report.update(records_by_kind=counts, captured_at_utc=datetime.now(timezone.utc).isoformat(),
                  missing_kinds=[kind for kind in KINDS if not counts[kind]],
                  nonempty_policy="Scan every existing kind. At least one JSON record overall; do not manufacture records for absent kinds.",
                  source_scope="Only this fresh cloud deployment's seven AMP directories; snapshots remain private")
    report["stage_gate_passed"] = report["machine_checks_passed"] and report["json_records"] > 0
    report_path = root / WORK / ("scan-" + stamp() + ".json")
    save(report_path, report)
    if not report["stage_gate_passed"]:
        raise RuntimeError("AMP secret/JSON/nonempty gate failed; report: " + str(report_path))
    save(root / WORK / "scan-passed.json", {"report": str(report_path), "captured_at_utc": report["captured_at_utc"]})
    return {"status": "scan_passed", "report": str(report_path), "records_by_kind": counts}


def collector_identity(row, plan, expected_id=None):
    labels = row.get("Config", {}).get("Labels") or {}
    if (row.get("Name") != "/" + plan["container_name"] or expected_id is not None and row.get("Id") != expected_id
            or any(labels.get(key) != value for key, value in plan["state_volume_labels"].items())):
        raise ValueError("Collector ID/name/source labels do not match the held ownership")
    return row


def compose(root, stage, *args):
    return docker("compose", "-p", preparer(root).project_name("kafka"), "-f", str(root / WORK / stage / "compose.json"), *args)


def start(root, stage):
    stable_bindings(root)
    work = root / WORK
    scan_gate = load(work / "scan-passed.json")
    if not load(scan_gate["report"])["stage_gate_passed"]:
        raise ValueError("No successful AMP scan")
    plan = load(work / stage / "plan.json")
    prep = preparer(root)
    metadata = existing_volume(plan["state_volume_name"])
    if stage == "heartbeat-access" and metadata is not None:
        raise ValueError("Initial collector requires fresh offsets; existing state is preserved")
    if stage == "all-six":
        if metadata is None or not load(work / "alive-seven.json")["all_online"] or not load(work / "stop-heartbeat-access.json")["normal_exit_zero"]:
            raise ValueError("Expansion requires seven aliveMap online, shared offsets, and verified normal stop")
        initial = load(work / "held-heartbeat-access.json")
        previous = collector_identity(inspect_one("container", plan["container_name"]), plan, initial["id"])
        if previous.get("State", {}).get("Running") or previous["State"].get("ExitCode") != 0:
            raise ValueError("The held initial collector must still be stopped normally before replacement")
    elif docker("ps", "-aq", "--filter", "name=^/" + plan["container_name"] + "$").strip():
        raise ValueError("An unexpected same-name collector exists before initial startup")
    prep.validate_existing_state(metadata, plan["source_collection_sha256"], "kafka")
    if any(prep.sha(work / stage / name) != expected for name, expected in plan["file_sha256"].items()):
        raise ValueError("Prepared collector configuration changed")
    docker("image", "inspect", IMAGE)
    compose(root, stage, "config", "--quiet")
    compose(root, stage, "up", "-d", "--no-deps", "collector")
    row = collector_identity(inspect_one("container", plan["container_name"]), plan)
    if not row.get("State", {}).get("Running"):
        raise RuntimeError("Collector exited during startup")
    save(work / ("held-" + stage + ".json"), {"id": row["Id"], "name": row["Name"], "labels": plan["state_volume_labels"], "started_at": row["State"]["StartedAt"], "stage": stage})
    prep.validate_existing_state(existing_volume(plan["state_volume_name"]), plan["source_collection_sha256"], "kafka")
    return {"status": "collector_started", "stage": stage, "id": row["Id"], "kinds": plan["kinds"], "read_from_head": plan["read_from_head"]}


def identities(root):
    manifest = load(root / DEPLOYMENT)
    config = load(root / manifest["coordinator_config"])
    aics = {"coordinator": config["leader"]["aic"]}
    domain_root = (root / manifest["coordinator_config"]).parent.parent
    for role in ROLES[1:]:
        bridge = role in {"database", "database-backup", "ops"}
        row = load(domain_root / role / ("bridge.json" if bridge else "config.json"))
        aics[role] = (row["platform"] if bridge else row)["aic"]
    if len(set(aics.values())) != 7 or any(not isinstance(value, str) or not value.strip() for value in aics.values()):
        raise ValueError("Expected exactly seven distinct AICs")
    endpoint = urlsplit(config["discovery_url"])
    if endpoint.scheme != "https" or endpoint.hostname != "wt.ioa.pub" or endpoint.username or endpoint.password:
        raise ValueError("Expected the configured official credential-free HTTPS Discovery endpoint")
    return aics, config["discovery_url"]


def query(root):
    import httpx
    stable_bindings(root)
    held = load(root / WORK / "held-heartbeat-access.json")
    plan = load(root / WORK / "heartbeat-access/plan.json")
    row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
    if not row["State"]["Running"]:
        raise ValueError("Initial collector is no longer running")
    started = datetime.fromisoformat(held["started_at"].replace("Z", "+00:00"))
    if (datetime.now(timezone.utc) - started).total_seconds() < 120:
        raise ValueError("Wait until two full minutes after collector start before querying")
    aics, url = identities(root)
    checker = module(root, "cloud_check_alive", "tools/check_alive.py")
    with httpx.Client(timeout=httpx.Timeout(25, connect=5), trust_env=False) as client:
        response = client.post(url, json=checker.request_for(list(aics.values())))
        response.raise_for_status()
        raw = response.json()
    result = checker.summarize(raw, list(aics.values()))
    result.update(observed_at_utc=datetime.now(timezone.utc).isoformat(), mode="discovery-read-only", endpoint=url, role_aics=aics, response=raw)
    path = root / WORK / ("alive-observation-" + stamp() + ".json")
    save(path, result)
    if not result["all_online"] or result["online_count"] != 7:
        raise RuntimeError("Seven-AIC aliveMap gate failed; stop stage 6 and inspect: " + str(path))
    save(root / WORK / "alive-seven.json", result)
    return {"status": "seven_aliveMap_online", "report": str(path), "online_count": 7,
            "access_ingestion_confirmed": None, "rank_confirmed": None}


def stop(root, stage):
    work = root / WORK
    # Stage 6 initial stop must preserve the frozen source processes. After
    # supervision is installed, normal domain restarts are legitimate; bind
    # the current owned processes before/after stop without accepting new sources.
    source_before = same_source_mapping(root) if stage == "all-six" else stable_bindings(root)
    held, plan = load(work / ("held-" + stage + ".json")), load(work / stage / "plan.json")
    row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
    if not row.get("State", {}).get("Running"):
        raise ValueError("Held collector is not running; preserve state for inspection")
    if row.get("Config", {}).get("StopSignal") != "SIGTERM":
        raise ValueError("Collector must declare SIGTERM as its normal stop signal")
    docker("stop", "--time", "15", held["id"])
    row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
    state = row["State"]
    result = {"id": row["Id"], "stage": stage, "state": {key: state.get(key) for key in ("Status", "Running", "ExitCode", "OOMKilled", "Error", "StartedAt", "FinishedAt")},
              "normal_exit_zero": state.get("Running") is False and state.get("ExitCode") == 0 and not state.get("OOMKilled") and not state.get("Error")}
    source_after = same_source_mapping(root) if stage == "all-six" else stable_bindings(root)
    if source_after != source_before:
        raise ValueError("Source processes changed during the collector stop")
    save(work / ("stop-" + stage + ".json"), result)
    if not result["normal_exit_zero"]:
        raise RuntimeError("Collector did not stop normally with ExitCode 0; preserve offsets and stop stage 6")
    return {"status": "collector_stopped_normally", "id": row["Id"], "exit_code": 0}


def same_source_mapping(root):
    """Boot re-attestation permits owned domain restarts, never a source change."""
    current, bindings = resolve_sources(root)
    expected = load(root / WORK / "collection-plan.json")
    if current != expected:
        raise ValueError("Collector source mapping changed across supervisor startup")
    return bindings


def supervise(root):
    """Adopt stage-6 all-six collector, or normally resume the same stopped ID.

    Foreground systemd process. SIGTERM/SIGINT stop exactly the held collector;
    no Docker down, force kill, volume deletion, or other-container stop occurs.
    """
    work = root / WORK
    bindings = same_source_mapping(root)
    plan, held = load(work / "all-six/plan.json"), load(work / "held-all-six.json")
    prep = preparer(root)
    prep.validate_existing_state(existing_volume(plan["state_volume_name"]), plan["source_collection_sha256"], "kafka")
    if any(prep.sha(work / "all-six" / name) != expected for name, expected in plan["file_sha256"].items()):
        raise ValueError("Prepared all-six collector configuration changed")
    row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
    if row.get("Config", {}).get("StopSignal") != "SIGTERM":
        raise ValueError("Expected SIGTERM collector stop signal")
    if not row["State"]["Running"]:
        if row["State"].get("ExitCode") != 0 or row["State"].get("OOMKilled") or row["State"].get("Error"):
            raise ValueError("Prior collector exit was not normal; preserve state for review")
        # start (not compose up) preserves immutable container ID and its offset mount.
        docker("start", held["id"])
        row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
        if not row["State"]["Running"]:
            raise RuntimeError("Held collector failed to resume")
    session = stamp()
    save(work / ("supervisor-start-" + session + ".json"), {
        "id": held["id"], "source_bindings": bindings, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "collector_started_at": row["State"]["StartedAt"], "state_volume_name": plan["state_volume_name"]})
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    prior = {number: signal.signal(number, request_stop) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        while not stopping:
            row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
            if not row["State"]["Running"]:
                save(work / ("supervisor-unexpected-exit-" + session + ".json"), {
                    "id": held["id"], "state": {key: row["State"].get(key) for key in ("Status", "Running", "ExitCode", "OOMKilled", "Error", "FinishedAt")}})
                raise RuntimeError("Collector exited outside its supervisor stop; preserve failure before restarting")
            time.sleep(2)
        # Match the same fixed container ID and all source labels immediately before stop.
        row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
        if not row["State"]["Running"]:
            raise RuntimeError("Collector stopped before normal supervised stop could be established")
        docker("stop", "--time", "15", held["id"])
        row = collector_identity(inspect_one("container", held["id"]), plan, held["id"])
        state = row["State"]
        normal = state.get("Running") is False and state.get("ExitCode") == 0 and not state.get("OOMKilled") and not state.get("Error")
        save(work / ("supervisor-stop-" + session + ".json"), {
            "id": held["id"], "normal_exit_zero": normal,
            "state": {key: state.get(key) for key in ("Status", "Running", "ExitCode", "OOMKilled", "Error", "FinishedAt")}})
        if not normal:
            raise RuntimeError("Supervised collector stop was not ExitCode 0")
        return {"status": "supervised_collector_stopped_normally", "id": held["id"], "exit_code": 0}
    finally:
        for number, handler in prior.items():
            signal.signal(number, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "scan", "start-initial", "query", "stop-initial", "start-all", "stop-all", "supervise-all"))
    parser.add_argument("--root", type=Path, default=Path("/opt/incident-pilot"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "not_executed", "action": args.action, "root": str(args.root), "image": IMAGE}))
        return 0
    if os.name != "posix" or os.geteuid() != 0:
        raise PermissionError("Execute on the cloud Linux host as root")
    root = args.root.resolve()
    if root != Path("/opt/incident-pilot"):
        raise ValueError("This deployment helper is bound to /opt/incident-pilot")
    actions = {"prepare": lambda: prepare(root), "scan": lambda: scan(root),
               "start-initial": lambda: start(root, "heartbeat-access"), "query": lambda: query(root),
               "stop-initial": lambda: stop(root, "heartbeat-access"), "start-all": lambda: start(root, "all-six"),
               "stop-all": lambda: stop(root, "all-six"), "supervise-all": lambda: supervise(root)}
    print(json.dumps(actions[args.action](), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "failed_stop", "error_type": type(error).__name__, "problem": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
