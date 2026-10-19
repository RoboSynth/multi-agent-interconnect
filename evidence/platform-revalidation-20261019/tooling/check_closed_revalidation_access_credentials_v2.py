"""Once-only, post-terminal T05/T62 evidence collection; no product actions.

Default invocation describes the contract without reading private inputs or Docker.
--scan accepts frozen six-domain snapshots. --collect-docker optionally obtains
those snapshots using only exact-project inspect and docker cp, even after stop.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH / "checkout"
CANONICAL = BATCH.parents[1]
PROJECT = "incident-pilot-revalidation-20261019"
DERIVED_FROM_SHA256 = "1186826d5392a86a7673ca7ca1db31ad3d35ca555089535222439b1ddd1a353b"
REVISION_PARENT_SHA256 = "2b91078d80ce1cc7f3bf459355aa47c7818d21aef481bde29fe00e1d2c74a5e2"
sys.dont_write_bytecode = True
SERVICES = {
    "application-agent": "application", "verification-agent": "verification",
    "database-agent": "database", "database-backup-agent": "database-backup",
    "ops-agent": "ops", "onboarding-agent": "onboarding",
}
SECRET_NAMES = {"POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "APP_ADMIN_TOKEN", "BRIDGE_DB_PASSWORD", "INCIDENT_APPROVAL_SECRET"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stable(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Required regular evidence file missing or symlinked")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size:
        raise RuntimeError("Evidence changed while being read")
    return raw


def read(path):
    return json.loads(stable(path).decode("utf-8-sig"))


def windows_to_wsl(value):
    value = str(value)
    path = PureWindowsPath(value)
    if (path.root and len(path.drive) == 2 and path.drive[1] == ":"
            and path.drive[0].isascii() and path.drive[0].isalpha()):
        return Path("/").joinpath("mnt", path.drive[0].lower(), *path.parts[1:]).as_posix()
    return value


def local(value, base=ROOT):
    value = str(value)
    if os.name != "nt":
        value = windows_to_wsl(value)
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()


def within(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence path outside its reviewed root")
    return path


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def module(name, path, expected):
    if sha(stable(path)) != expected:
        raise ValueError("Reviewed reusable analysis source changed")
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def closure(args, prepared):
    raw = stable(args.terminal)
    if sha(raw) != args.terminal_sha:
        raise ValueError("Batch terminal receipt SHA mismatch")
    value = json.loads(raw)
    phases = value.get("phase_sessions")
    if (value.get("status") != "terminal" or value.get("actual_wait_observed") is not True
            or value.get("expected_plans") != 12 or not isinstance(phases, list) or not phases
            or any(not isinstance(p, dict) or p.get("terminal") is not True
                   or type(p.get("actual_os_exit_code")) is not int or "session_id" not in p for p in phases)
            or type(value.get("attempted_count")) is not int or type(value.get("unattempted_count")) is not int
            or min(value["attempted_count"], value["unattempted_count"]) < 0
            or value["attempted_count"] + value["unattempted_count"] != 12):
        raise ValueError("A truthful terminal batch receipt with observed waits/counts is required")
    if value.get("prepared_summary_sha256", sha(stable(BATCH / "plan-preparation/prepared-summary.json"))) != sha(stable(BATCH / "plan-preparation/prepared-summary.json")):
        raise ValueError("Terminal receipt describes another prepared batch")
    stop = value.get("owned_project_stop_receipt")
    if not isinstance(stop, dict) or set(stop) != {"path", "sha256"}:
        raise ValueError("Terminal receipt needs owned_project_stop_receipt {path,sha256}")
    path = within(local(stop["path"], BATCH), BATCH)
    if sha(stable(path)) != stop["sha256"]:
        raise ValueError("Owned-project stop proof SHA mismatch")
    proof = read(path)
    if proof.get("status") != "stopped" or proof.get("remaining_running_owned") != 0 or proof.get("project", PROJECT) != PROJECT:
        raise ValueError("Owned project has not been recorded stopped")
    if stop["path"] not in {"execution/stop/result.json", "execution-rest/stop/result.json"}:
        raise ValueError("Final stop must name the exact owned execution stage")
    stop_process = read(path.parent / "compose-stop.exit.json")
    keeper = value.get("owned_keeper_exit_receipt", {})
    expected_keeper = stop["path"].split("/", 1)[0] + "/keeper.exit.json"
    if keeper.get("path") != expected_keeper:
        raise ValueError("Final keeper must belong to the final stop stage")
    keeper_path = within(local(keeper["path"], BATCH), BATCH)
    if sha(stable(keeper_path)) != keeper.get("sha256"):
        raise ValueError("Final keeper exit proof SHA mismatch")
    keeper_process = read(keeper_path)
    if any(p.get("terminal") is not True or type(p.get("actual_exit_code")) is not int
           or p["actual_exit_code"] != 0 for p in (stop_process, keeper_process)):
        raise ValueError("Final stop and keeper must have actual terminal exit0")
    assert prepared["project"] == PROJECT and prepared["plan_count"] == len(prepared["plans"]) == 12
    keys = {item["key"] for item in prepared["plans"]}
    if set(value.get("plan_dispositions", {})) != keys:
        raise ValueError("Terminal receipt must classify exactly the12 prepared plans")
    for item in prepared["plans"]:
        declared = value["plan_dispositions"][item["key"]]
        case_output = within(local(item["output"]), ROOT / "eval/results/platform/revalidation-20261019")
        execution = BATCH / "execution" / item["key"]
        if declared == "not_attempted":
            if case_output.exists() or execution.exists():
                raise ValueError("Not-attempted plan already has execution evidence")
            continue
        if declared not in {"passed", "failed"}:
            raise ValueError("Unresolved case cannot enter a closed analysis")
        runner, receipt, result = read(execution / "runner.exit.json"), read(execution / "receipt.json"), read(case_output / "results.json")
        if (runner.get("terminal") is not True or type(runner.get("actual_exit_code")) is not int
                or receipt.get("actual_exit_code") != runner["actual_exit_code"]
                or not receipt.get("finished_at") or not result.get("finished_at")
                or receipt.get("plan_sha256") != item["plan_sha256"]):
            raise ValueError("Attempted case has no matching real terminal receipts")
    return value


def docker(args, output):
    # Direct WSL->Linux Python is preferred; native Windows remains explicit.
    prefix = ["docker", "--host", "unix:///var/run/docker.sock"] if os.name != "nt" else [
        "wsl.exe", "-d", "Ubuntu-22.04", "--exec", "docker", "--host", "unix:///var/run/docker.sock"]
    serial = [0]

    def invoke(*argv):
        if argv[0] not in {"inspect", "cp"}:
            raise ValueError("Only readonly inspect/cp commands are allowed")
        serial[0] += 1
        # docker runs in WSL when this collector is invoked by native Windows Python.
        if os.name == "nt" and argv[0] == "cp":
            argv = (*argv[:-1], windows_to_wsl(argv[-1]))
        r = subprocess.run(prefix + list(argv), capture_output=True, timeout=45)
        save(output / "private-command-metadata" / (str(serial[0]) + ".json"), {
            "operation": argv[0], "actual_exit_code": r.returncode,
            "stdout_bytes": len(r.stdout), "stdout_sha256": sha(r.stdout),
            "stderr_bytes": len(r.stderr), "stderr_sha256": sha(r.stderr)})
        if r.returncode:
            raise RuntimeError("Readonly Docker operation failed; retained command hash/exit proof")
        return r.stdout
    return invoke


def collect_domains(args, output, prepared):
    invoke = docker(args, output)
    names = [PROJECT + "-" + service + "-1" for service in SERVICES]
    records = json.loads(invoke("inspect", *names))
    actual = {}
    for row in records:
        labels = row["Config"].get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        role = SERVICES.get(service)
        domain_label = "database" if role == "database-backup" else "operations" if role == "ops" else role
        if (service not in SERVICES or service in actual or labels.get("com.docker.compose.project") != PROJECT
                or labels.get("incident-pilot") != "true" or labels.get("incident-pilot.domain") != domain_label
                or row["Name"].lstrip("/") != PROJECT + "-" + service + "-1"
                or row["Image"] != prepared["image_id"] or row["State"].get("Running") is not False
                or row["State"].get("Status") != "exited"):
            raise ValueError("Snapshot source is not one exact owned domain/image")
        mounts = {m["Destination"]: m for m in row.get("Mounts", [])}
        domain, state = mounts.get("/domain", {}), mounts.get("/state", {})
        expected_domain = str(ROOT / "runtime/private/revalidation-20261019/domains" / role)
        expected_domain = windows_to_wsl(expected_domain)
        state_key = "database-agent-state" if role == "database-backup" else service + "-state"
        if (domain.get("Type") != "bind" or domain.get("RW") is not False
                or domain.get("Source") != expected_domain or state.get("Type") != "volume"
                or state.get("Name") != PROJECT + "_" + state_key or state.get("RW") is not True):
            raise ValueError("Domain readonly bind or owned state volume does not match this exact role")
        volumes = json.loads(invoke("inspect", "--type", "volume", state["Name"]))
        if (len(volumes) != 1 or volumes[0].get("Name") != state["Name"]
                or (volumes[0].get("Labels") or {}).get("com.docker.compose.project") != PROJECT
                or (volumes[0].get("Labels") or {}).get("com.docker.compose.volume") != state_key):
            raise ValueError("State volume ownership labels mismatch")
        actual[service] = row
    if set(actual) != set(SERVICES):
        raise ValueError("Six owned domain containers are required for collection")
    entries = []
    for service, role in SERVICES.items():
        row = actual[service]
        directory = output / "private-domain-amp" / service
        directory.mkdir(parents=True, exist_ok=False)
        invoke("cp", row["Id"] + ":/state/amp-" + role + "/.", str(directory))
        files = []
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or not re.fullmatch(r"amp_[A-Za-z0-9_-]+\.jsonl", path.name):
                raise ValueError("Unexpected/symlinked domain AMP snapshot entry")
            raw = stable(path)
            files.append({"name": path.name, "sha256": sha(raw), "bytes": len(raw)})
        if not files:
            raise ValueError("A domain has no captured AMP files")
        entries.append({"service": service, "role": role, "container_id": row["Id"], "image_id": row["Image"],
            "started_at": row["State"]["StartedAt"], "directory": str(directory), "files": files,
            "stopped_before_copy": True, "domain_readonly_bind_verified": True,
            "domain_mount_source_sha256": sha(next(m["Source"] for m in row["Mounts"] if m["Destination"] == "/domain").encode()),
            "state_volume_name": next(m["Name"] for m in row["Mounts"] if m["Destination"] == "/state"),
            "state_volume_ownership_verified": True})
    def identity(row):
        return (row["Image"], row["Name"], row["State"]["StartedAt"], row["State"].get("FinishedAt"),
                row["State"]["Status"], row["State"]["Running"], row.get("Config", {}).get("Labels"),
                sorted(row.get("Mounts", []), key=lambda m: m["Destination"]))
    after = {row["Id"]: identity(row)
        for row in json.loads(invoke("inspect", *names))}
    before = {row["Id"]: identity(row) for row in records}
    if after != before:
        raise ValueError("Domain identity/state changed during readonly snapshot collection")
    manifest = {"schema": "acceptance-domain-amp-snapshots/1", "project": PROJECT,
        "image_id": prepared["image_id"], "domains": entries, "collection": "exact-container-id docker cp only",
        "source_container_identity_unchanged": True,
        "all_six_stopped_before_copy": True, "all_domain_readonly_mounts_verified": True,
        "all_state_volume_ownership_verified": True,
        "shared_state_volume_contract": "database and database-backup share the owned database-agent-state volume; role-specific AMP directories are copied separately"}
    save(output / "private-domain-snapshot-manifest.json", manifest)
    return manifest


def validate_snapshots(manifest, prepared):
    if (manifest.get("schema") != "acceptance-domain-amp-snapshots/1" or manifest.get("project") != PROJECT
            or manifest.get("image_id") != prepared["image_id"]):
        raise ValueError("Domain snapshots describe another project/image")
    if not all(manifest.get(k) is True for k in ("source_container_identity_unchanged", "all_six_stopped_before_copy",
               "all_domain_readonly_mounts_verified", "all_state_volume_ownership_verified")):
        raise ValueError("Snapshots lack stopped-container/mount/volume ownership verification")
    rows = manifest.get("domains", [])
    if len(rows) != 6 or {row.get("service") for row in rows} != set(SERVICES):
        raise ValueError("Snapshot manifest must cover exactly six domain roles")
    selected = []
    for row in rows:
        service = row["service"]
        directory = local(row["directory"], BATCH)
        if (row.get("role") != SERVICES[service] or row.get("image_id") != prepared["image_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", row.get("container_id", "")) or not row.get("started_at")
                or any(row.get(k) is not True for k in ("stopped_before_copy", "domain_readonly_bind_verified", "state_volume_ownership_verified"))):
            raise ValueError("Snapshot domain identity/image binding is incomplete")
        if not row.get("files"):
            raise ValueError("Domain snapshot file inventory is empty")
        expected = {}
        for file in row["files"]:
            name = file["name"]
            if not re.fullmatch(r"amp_[A-Za-z0-9_-]+\.jsonl", name) or name in expected:
                raise ValueError("Invalid/duplicate AMP snapshot name")
            path = directory / name
            raw = stable(path)
            if sha(raw) != file["sha256"] or len(raw) != file["bytes"]:
                raise ValueError("Frozen AMP snapshot bytes changed")
            expected[name] = path
        if {p.name for p in directory.iterdir()} != set(expected):
            raise ValueError("Domain snapshot inventory is not exhaustive")
        selected += [("domains/" + service + "/" + name, "amp_jsonl", path) for name, path in sorted(expected.items())]
    return selected


def rows(path):
    raw = stable(path)
    parsed, invalid, partial = [], 0, 0
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        partial += int(not line.endswith(b"\n"))
        try:
            row = json.loads(line.decode("utf-8-sig"))
            if not isinstance(row, dict):
                raise ValueError("Record must be an object")
        except (ValueError, UnicodeError):
            invalid += 1
        else:
            parsed.append(row)
    return parsed, {"invalid": invalid, "partial": partial}


def reconcile_case(key, captures, domain_access, tool, output):
    selected = [p for label, _, p in captures if p.name == "messages.jsonl"]
    if len(selected) != 1:
        return {"key": key, "status": "missing_or_ambiguous_capture", "message_file_count": len(selected),
            "endpoint_access_match_passed": False, "captured_start_tasks": None}
    messages, bad = rows(selected[0])
    starts, normalized = {}, []
    for row in messages:
        message = row.get("message")
        if not isinstance(message, dict):
            bad["invalid"] += 1
            continue
        kind = message.get("type")
        if row.get("direction") == "send" and kind == "task-command" and message.get("command") == "start":
            values = (message.get("sessionId"), message.get("taskId"), message.get("senderId"), row.get("worker_aic"))
            if any(not isinstance(v, str) or not v for v in values) or (values[1] in starts and starts[values[1]] != values):
                bad["invalid"] += 1
                continue
            starts[values[1]] = values
        if row.get("direction") == "receive" and kind == "task-result":
            status = message.get("status")
            if not isinstance(status, dict) or not isinstance(status.get("state"), str) or not isinstance(message.get("taskId"), str):
                bad["invalid"] += 1
                continue
        normalized.append(row)
    directory = output / "private-normalized-access" / key
    directory.mkdir(parents=True, exist_ok=False)
    message_path = directory / "messages.jsonl"
    message_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in normalized), encoding="utf-8")
    own_access = []
    own_bad = Counter(invalid=0, partial=0)
    for _, _, path in captures:
        if path.name.startswith("amp_access_"):
            data, errors = rows(path)
            own_access += data
            own_bad.update(errors)
    filtered = []
    malformed_access, unrelated = 0, 0
    for row in domain_access + own_access:
        values = (row.get("trace_id"), row.get("correlation_id"), row.get("aic"))
        if any(not isinstance(v, str) or not v for v in values):
            malformed_access += 1
            continue
        expected = starts.get(values[1])
        if expected is None or expected[0] != values[0]:
            unrelated += 1
            continue
        filtered.append(row)
    access_path = directory / "amp_access_normalized.jsonl"
    access_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in filtered), encoding="utf-8")
    try:
        report = tool.reconcile(message_path, directory, transport="wutong-amqps")
    except Exception as error:
        return {"key": key, "status": "reconciler_failed", "error_class": type(error).__name__,
            "invalid_messages": bad, "endpoint_access_match_passed": False}
    report["incomplete_task_lifecycles"] = len(report["incomplete_task_lifecycles"])
    report.update(key=key, invalid_messages=bad, invalid_coordinator_access=dict(own_bad),
        malformed_access_shapes_observed=malformed_access, exact_session_unrelated_access_excluded=unrelated,
        start_key_sha256=[sha(json.dumps(v[:2], separators=(",", ":")).encode()) for v in starts.values()],
        captured_session_sha256=sorted({sha(v[0].encode()) for v in starts.values()}),
        distinct_captured_sessions=len({v[0] for v in starts.values()}),
        input_capture_derived_for_reconciler=True, original_capture_unchanged=True)
    report["endpoint_access_match_passed"] = (report["captured_start_tasks"] > 0 and report["missing_records"] == 0
        and report["extra_records"] == 0 and not any(bad.values()) and not any(own_bad.values()) and not malformed_access
        and report["distinct_captured_sessions"] == 1)
    report["status"] = "access_matched" if report["endpoint_access_match_passed"] else "findings_or_incomplete"
    return report


def scan(args):
    tools = read(HERE / "revalidation-analysis-tools-v2.json")
    if sha(stable(Path(__file__))) != tools["helper_sha256"]:
        raise ValueError("Reviewed closed-analysis wrapper changed")
    prepared_path = BATCH / "plan-preparation/prepared-summary.json"
    prepared = read(prepared_path)
    if sha(stable(prepared_path)) != tools["prepared_summary_sha256"]:
        raise ValueError("Frozen prepared plan index changed")
    terminal = closure(args, prepared)
    output = within(args.output.resolve(), HERE)
    output.mkdir(parents=True, exist_ok=False)
    try:
        reusable = {name: module("acceptance_closed_" + name, local(item["path"], CANONICAL), item["sha256"])
            for name, item in tools["modules"].items()}
        if args.collect_docker:
            manifest = collect_domains(args, output, prepared)
        else:
            if not args.domain_snapshot_manifest or not args.domain_snapshot_sha:
                raise ValueError("Supply frozen six-domain snapshots and their exact manifest SHA, or --collect-docker")
            raw = stable(args.domain_snapshot_manifest)
            if sha(raw) != args.domain_snapshot_sha:
                raise ValueError("External domain snapshot manifest SHA mismatch")
            manifest = json.loads(raw)
        domain_files = validate_snapshots(manifest, prepared)
        selected = list(domain_files)
        known, _ = reusable["inventory"].inventory()
        known = set(known)
        historical_count = len(known)
        if historical_count != 63:
            raise ValueError("Historical reusable inventory no longer contains its reviewed63 values")
        capture_by_key, dispositions, missing_captures = {}, [], []
        configs, envs = set(), set()
        for item in prepared["plans"]:
            plan_path = within(local(item["plan"]), ROOT)
            if sha(stable(plan_path)) != item["plan_sha256"]:
                raise ValueError("Frozen plan changed")
            plan = read(plan_path)
            directory = within(local(item["output"]), ROOT / "eval/results/platform/revalidation-20261019")
            result_path = directory / ("result.json" if item["case"] == "F12/E5" else "results.json")
            disposition = terminal.get("plan_dispositions", {}).get(item["key"], "unclassified_no_result")
            declared = disposition
            if result_path.is_file():
                value = read(result_path)
                disposition = "terminal_result" if value.get("finished_at") or value.get("completed_at") else (
                    "running" if declared == "running" else "incomplete_result")
            dispositions.append({"key": item["key"], "result_disposition": disposition,
                "root_declared_disposition": declared,
                "result_present": result_path.is_file(), "result_sha256": sha(stable(result_path)) if result_path.is_file() else None})
            config = within(local(plan["config"]), ROOT)
            configs.add(config)
            document = read(config)
            if document.get("approval_env_file"):
                envs.add(within(local(document["approval_env_file"]), ROOT))
            target = read(within(local(plan["target_config"]), ROOT))
            envs.add(within(local(target["env_file"]), ROOT))
            chosen = []
            if directory.is_dir():
                for parent, dirs, files in os.walk(directory, followlinks=False):
                    dirs[:] = [d for d in dirs if d != "source" and not (Path(parent) / d).is_symlink()]
                    for name in sorted(files):
                        if name not in {"messages.json", "messages.jsonl", "coordinator.json"} and not re.fullmatch(r"amp_[A-Za-z0-9_-]+\.jsonl", name):
                            continue
                        path = within(Path(parent) / name, directory)
                        kind = "coordinator_configuration" if name == "coordinator.json" else "aip_json" if name == "messages.json" else "aip_jsonl" if name == "messages.jsonl" else "amp_jsonl"
                        chosen.append(("runs/" + item["key"] + "/" + path.relative_to(directory).as_posix(), kind, path))
            capture_by_key[item["key"]] = chosen
            if disposition != "not_attempted":
                for required in ("messages.jsonl", "amp_message_coordinator.jsonl"):
                    if not any(p.name == required for _, _, p in chosen):
                        missing_captures.append({"key": item["key"], "required_capture": required})
            selected.extend(chosen)
        selected += [("prepared-coordinator/" + str(i) + ".json", "coordinator_configuration", p) for i, p in enumerate(sorted(configs))]
        current_env_values = set()
        inventory_envs = envs | {local(p) for p in args.known_secret_env}
        inventory_envs |= {within(local(p, CANONICAL), CANONICAL) for p in tools.get("additional_known_secret_env", [])}
        inventory_env_sha256 = {}
        for path in sorted(inventory_envs):
            inventory_env_sha256[path.relative_to(CANONICAL).as_posix()] = sha(stable(path))
            for line in stable(path).decode("utf-8-sig").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() in SECRET_NAMES and value:
                    current_env_values.add(value)
        if len(current_env_values) < 5:
            raise ValueError("Current business/approval credential inventory is incomplete")
        known.update(current_env_values)
        file_reports = [reusable["scanner"].inspect_file(label, kind, path, known, reusable["patterns"].PATTERNS)
            for label, kind, path in selected]
        known_count = len(known)
        known.clear()
        domain_access, domain_bad = [], Counter(invalid=0, partial=0)
        for _, _, path in domain_files:
            if path.name.startswith("amp_access_"):
                data, bad = rows(path)
                domain_bad.update(bad)
                for row in data:
                    if any(not isinstance(row.get(name), str) or not row.get(name) for name in ("trace_id", "correlation_id", "aic")):
                        domain_bad["invalid_shapes"] += 1
                    else:
                        domain_access.append(row)
        reconciliations = [reconcile_case(key, captures, domain_access, reusable["reconciler"], output)
            for key, captures in capture_by_key.items()]
        report = {
            "schema": "acceptance-closed-access-credentials/1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "terminal_sha256": args.terminal_sha, "prepared_summary_sha256": sha(stable(prepared_path)),
            "planned_count": 12, "attempted_count": terminal["attempted_count"], "unattempted_count": terminal["unattempted_count"],
            "phase_actual_exits": [{k: p[k] for k in ("session_id", "actual_os_exit_code", "terminal")} for p in terminal["phase_sessions"]],
            "plan_result_dispositions": dispositions,
            "missing_required_captures": missing_captures,
            "domain_snapshot_roles": [row["service"] for row in manifest["domains"]],
            "domain_access_parse_counts": dict(domain_bad), "access_reconciliations": reconciliations,
            "credential_inventory": {"historical_distinct": historical_count, "current_env_distinct": len(current_env_values), "total_distinct": known_count},
            "credential_env_input_sha256": inventory_env_sha256,
            "reused_analysis_sources": tools["modules"],
            "credential_scan": {"files": [{k: v for k, v in row.items() if k not in {"raw_locations", "decoded_locations"}} for row in file_reports],
                "raw_hits": sum(r["raw_line_category_hits"] for r in file_reports),
                "decoded_hits": sum(r["decoded_field_category_hits"] for r in file_reports),
                "parse_or_decode_errors": sum(r["json_parse_errors"] + r["utf8_decode_errors"] for r in file_reports)},
            "scope": "All found coordinator configuration/AIP/AMP captures in these12 plan outputs plus frozen six-domain AMP files; sources exclude source snapshots. Original22 T05 remains unchanged.",
            "derived_from_helper_sha256": DERIVED_FROM_SHA256,
            "revision_parent_sha256": REVISION_PARENT_SHA256,
            "limits": ["Missing/unattempted captures never prove zero messages; unclassified dispositions remain unknown.",
                "Task lifecycle completeness is separate from exact endpoint access matching; interruption may leave intentionally incomplete tasks.",
                "Malformed rows are counted over full physical inputs; normalized derived inputs never replace raw originals.",
                "JSON/JSONL/AMP capture representations overlap and are never added as unique traffic.",
                "No broker inventory, uncaptured management-payload, Monitor ingestion, signature verification or long-term uptime claim.",
                "Domain logs are frozen prefixes/full stopped files, not a guarantee against future writes."],
            "raw_sources_modified": False, "resource_operations_AMQPS_model_business_requests": 0,
        }
        scan_value = report["credential_scan"]
        report["credential_scan_content_zero_hits_and_parse_errors"] = scan_value["raw_hits"] == scan_value["decoded_hits"] == scan_value["parse_or_decode_errors"] == 0
        attempted = [r for r in dispositions if r["result_disposition"] != "not_attempted"]
        report["capture_coverage_complete"] = (all(r["result_disposition"] in {"terminal_result", "not_attempted"} for r in dispositions)
            and sum(r["result_disposition"] == "terminal_result" for r in dispositions) == terminal["attempted_count"]
            and sum(r["result_disposition"] == "not_attempted" for r in dispositions) == terminal["unattempted_count"]
            and not missing_captures
            and all(r.get("captured_start_tasks") is not None for r in reconciliations if any(d["key"] == r["key"] for d in attempted)))
        start_counts = Counter(value for row in reconciliations for value in row.get("start_key_sha256", []))
        report["duplicate_start_keys_across_run_outputs"] = sum(count - 1 for count in start_counts.values() if count > 1)
        session_counts = Counter(session for row in reconciliations for session in row.get("captured_session_sha256", []))
        report["distinct_captured_case_sessions"] = len(session_counts)
        report["duplicate_session_across_case_outputs"] = sum(n - 1 for n in session_counts.values() if n > 1)
        report["credential_scan_passed"] = (terminal["attempted_count"] > 0 and report["capture_coverage_complete"]
            and report["credential_scan_content_zero_hits_and_parse_errors"])
        report["endpoint_access_match_passed"] = (terminal["attempted_count"] > 0 and not any(domain_bad.values())
            and report["duplicate_start_keys_across_run_outputs"] == 0 and all(r["endpoint_access_match_passed"]
            for r in reconciliations if any(d["key"] == r["key"] for d in attempted))
            and report["distinct_captured_case_sessions"] == terminal["attempted_count"]
            and report["duplicate_session_across_case_outputs"] == 0)
        report["overall_passed"] = report["credential_scan_passed"] and report["capture_coverage_complete"] and report["endpoint_access_match_passed"]
        if any(sha(stable(local(item["path"], CANONICAL))) != item["sha256"] for item in tools["modules"].values()):
            raise ValueError("Reusable analysis source changed during the read-only analysis")
        save(output / "closed-access-credentials.json", report)
        save(output / "analysis-exit.json", {"status": "passed" if report["overall_passed"] else "findings_or_incomplete",
            "analysis_exit_code": 0 if report["overall_passed"] else 1,
            "report_sha256": sha(stable(output / "closed-access-credentials.json")), "source_files_modified": False})
        print(json.dumps({"overall_passed": report["overall_passed"], "attempted_count": terminal["attempted_count"],
            "credential_scan_passed": report["credential_scan_passed"], "endpoint_access_match_passed": report["endpoint_access_match_passed"],
            "report_sha256": sha(stable(output / "closed-access-credentials.json"))}))
        return 0 if report["overall_passed"] else 1
    except Exception as error:
        save(output / "analysis-failure.json", {"status": "analysis_failed", "error_class": type(error).__name__,
            "source_files_modified": False, "resource_operations_AMQPS_model_business_requests": 0})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--terminal", type=Path)
    parser.add_argument("--terminal-sha")
    parser.add_argument("--output", type=Path, default=HERE / "closed-access-credentials-first")
    parser.add_argument("--domain-snapshot-manifest", type=Path)
    parser.add_argument("--domain-snapshot-sha")
    parser.add_argument("--collect-docker", action="store_true")
    parser.add_argument("--known-secret-env", action="append", default=[])
    args = parser.parse_args()
    if not args.scan:
        print(json.dumps({"status": "PREPARED_NOT_EXECUTED", "project": PROJECT,
            "required": "--scan --terminal <batch-terminal.json> --terminal-sha <SHA> plus --domain-snapshot-manifest/--domain-snapshot-sha or --collect-docker",
            "resource_operations_AMQPS_model_business_requests": 0}))
        return 0
    if not args.terminal or not re.fullmatch(r"[0-9a-f]{64}", args.terminal_sha or ""):
        parser.error("--scan requires the exact terminal receipt and SHA")
    if args.collect_docker and (args.domain_snapshot_manifest or args.domain_snapshot_sha):
        parser.error("Choose external frozen snapshots or readonly Docker collection")
    return scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
