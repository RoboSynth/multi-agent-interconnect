"""One reviewed read-only collector run; only its held container can be stopped."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ART = Path(__file__).resolve().parent
ROOT = ART.parents[1]
OUT = ART / "execution-first"
PRIVATE = OUT / "private"
PREFIX = ["docker", "--host", "unix:///var/run/docker.sock"]
PLAN = json.loads((ART / "collector/plan.json").read_text())
READY = json.loads((ART / "source-ready.json").read_text())
EXPECTED = json.loads((PRIVATE / "expected-aic.json").read_text())
commands = []
result = {"passed": False, "started_utc": datetime.now(timezone.utc).isoformat(), "commands": commands,
          "business_MCP_model_tasks_sent": 0, "source_logs_frozen_by_hash": False, "observation_seconds": 75,
          "collector_up_invoked": False}
held = None
logs = None
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
write = lambda path, value: path.write_text(json.dumps(value, indent=2) + "\n")


def run(name, args, *, timeout=45, allow_failure=False):
    completed = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    (PRIVATE / (name + ".stdout.bin")).write_bytes(completed.stdout)
    (PRIVATE / (name + ".stderr.bin")).write_bytes(completed.stderr)
    commands.append({"name": name, "actual_exit_code": completed.returncode,
                     "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest()})
    write(OUT / "progress.json", result)
    if completed.returncode and not allow_failure:
        raise RuntimeError(name + " exited " + str(completed.returncode))
    return completed


def parsed(name, args):
    return json.loads(run(name, args).stdout)


FMT = '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"status":{{json .State.Status}},"started_at":{{json .State.StartedAt}},"restart_count":{{json .RestartCount}},"project":{{json (index .Config.Labels "com.docker.compose.project")}}}'


def original_snapshot(name):
    listing = run(name + "-ids", PREFIX + ["ps", "-a", "--no-trunc", "--format", '{{json .ID}}'])
    ids = [json.loads(line) for line in listing.stdout.splitlines()]
    metadata = run(name + "-metadata", PREFIX + ["container", "inspect", "--format", FMT, *ids])
    return {row["id"]: row for row in (json.loads(line) for line in metadata.stdout.splitlines())}


def collector_metadata(name):
    fmt = '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"labels":{{json .Config.Labels}},"state":{{json .State}},"network_mode":{{json .HostConfig.NetworkMode}},"readonly_rootfs":{{json .HostConfig.ReadonlyRootfs}},"mounts":{{json .HostConfig.Mounts}}}'
    return parsed(name, PREFIX + ["container", "inspect", "--format", fmt, PLAN["container_name"]])


def require_owned(meta):
    if meta["name"] != "/" + PLAN["container_name"] or meta["image"] != READY["expected_local_image_id"]:
        raise RuntimeError("Collector name/image mismatch")
    if any(meta["labels"].get(key) != value for key, value in PLAN["state_volume_labels"].items()):
        raise RuntimeError("Collector source ownership label mismatch")
    if held is not None and meta["id"] != held:
        raise RuntimeError("Held collector identity changed")


def source_stats(directories):
    return {role: {path.name: {"bytes": path.stat().st_size, "inode": path.stat().st_ino}
                  for kind in module.KINDS for path in directory.glob("amp_" + kind + "_*.jsonl") if path.is_file()}
            for role, directory in directories.items()}


try:
    for item in READY["source_files"]:
        if item["kind"] == "source" and sha(ROOT / item["source"]) != item["sha256"]:
            raise RuntimeError("Reviewed preparation source changed")
    if sha(ROOT / "deploy/fluent-bit/render.py") != READY["dependencies"]["renderer_sha256"]:
        raise RuntimeError("Reviewed renderer changed")
    for name, digest in PLAN["file_sha256"].items():
        if sha(ART / "collector" / name) != digest:
            raise RuntimeError("Prepared collector input changed")
    keeper = run("linux-keeper", ["ps", "-p", "2980", "-o", "pid=,ppid=,comm=,lstart="])
    if b"2980" not in keeper.stdout:
        raise RuntimeError("Existing Linux keeper not found")
    other = run("other-fluent-bit-processes", ["ps", "-C", "fluent-bit", "-o", "pid=,comm="], allow_failure=True)
    if other.returncode not in {0, 1} or other.stdout.strip():
        raise RuntimeError("Another Linux Fluent Bit process exists or cannot be excluded")
    old_inventory = json.loads((ART / "private/linux-inventory.json").read_text())
    old = {row["id"]: row for row in (json.loads(command["stdout"]) for command in old_inventory["commands"] if command["name"].startswith("container_"))}
    before = original_snapshot("before")
    if len(old) != 29 or set(before) != set(old):
        raise RuntimeError("Original 29-container identity set changed")
    for identity, meta in before.items():
        if any(meta[key] != old[identity][key] for key in ("name", "image", "status", "started_at", "restart_count")):
            raise RuntimeError("An original container changed before this run")
        if meta["name"] == "/" + PLAN["container_name"] or meta["project"] == PLAN["project"] or "fluent" in meta["name"].lower():
            raise RuntimeError("Collector name/project ownership is not exclusive")
    write(PRIVATE / "original29-before.json", before)
    image = parsed("selected-image", PREFIX + ["image", "inspect", "--format", '{"id":{{json .Id}},"os":{{json .Os}},"arch":{{json .Architecture}}}', PLAN["image"]])
    if image != {"id": READY["expected_local_image_id"], "os": "linux", "arch": "amd64"}:
        raise RuntimeError("Selected Linux image changed")
    spec = importlib.util.spec_from_file_location("collector_preparation", ROOT / "deploy/fluent-bit/prepare_linux_collector.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    existing = run("existing-offset-volume", PREFIX + ["volume", "ls", "--format", '{{json .Name}}'])
    volume_names = {json.loads(line) for line in existing.stdout.splitlines()}
    state = parsed("state-volume-metadata", PREFIX + ["volume", "inspect", "--format", '{"Name":{{json .Name}},"Labels":{{json .Labels}}}', PLAN["state_volume_name"]]) if PLAN["state_volume_name"] in volume_names else None
    module.validate_existing_state(state, PLAN["source_collection_sha256"], "stdout")
    result["state_volume_preexisting"] = state is not None
    directories = {}
    for source in PLAN["source_collection"]:
        if source["type"] == "bind":
            directory = Path(source["source"])
        else:
            volume = parsed("source-volume-" + source["role"], PREFIX + ["volume", "inspect", "--format", '{"name":{{json .Name}},"mountpoint":{{json .Mountpoint}}}', source["source"]])
            if volume["name"] != source["source"]:
                raise RuntimeError("Source volume identity mismatch")
            directory = Path(volume["mountpoint"]) / source["subpath"]
        if not directory.is_dir():
            raise RuntimeError("AMP subdirectory is not accessible: " + source["role"])
        directories[source["role"]] = directory
    initial_stats = source_stats(directories)
    write(PRIVATE / "source-stats-before.json", initial_stats)
    result["preconditions_passed"] = True
    result["collector_up_invoked"] = True
    run("collector-up", PREFIX + ["compose", "-p", PLAN["project"], "-f", str(ART / "collector/compose.json"), "up", "-d", "--no-deps", "--no-build", "collector"], timeout=90)
    meta = collector_metadata("collector-after-start")
    require_owned(meta)
    held = meta["id"]
    result["held_collector_id"] = held
    if meta["network_mode"] != "none" or not meta["readonly_rootfs"] or not meta["state"]["Running"]:
        raise RuntimeError("Collector isolation/running state mismatch")
    mounted = {mount["Target"]: mount for mount in meta["mounts"]}
    for source in PLAN["source_collection"]:
        mount = mounted[source["target"]]
        if not mount.get("ReadOnly") or mount["Source"] != source["source"]:
            raise RuntimeError("Source mount is not the reviewed read-only source")
        if source["type"] == "volume" and mount.get("VolumeOptions", {}).get("Subpath") != source["subpath"]:
            raise RuntimeError("AMP subpath isolation mismatch")
    result["seven_readonly_source_mounts_verified"] = True
    result["network_none_verified"] = True
    stdout = (PRIVATE / "collector.stdout.jsonl").open("wb")
    stderr = (PRIVATE / "collector.stderr.log").open("wb")
    logs = subprocess.Popen(PREFIX + ["logs", "--follow", held], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
    started = time.monotonic()
    while time.monotonic() - started < 75:
        if logs.poll() is not None:
            raise RuntimeError("Collector log stream exited before the observation window")
        time.sleep(max(0, min(5, 75 - (time.monotonic() - started))))
    result["actual_observation_seconds"] = round(time.monotonic() - started, 3)
    final_stats = source_stats(directories)
    write(PRIVATE / "source-stats-after.json", final_stats)
    result["natural_growth_by_role"] = {role: sum(max(0, meta["bytes"] - initial_stats[role].get(name, {}).get("bytes", 0))
        for name, meta in records.items()) for role, records in final_stats.items()}
except Exception as error:
    result.update(error_class=type(error).__name__, error=str(error))
finally:
    if held is not None:
        try:
            meta = collector_metadata("collector-before-stop")
            require_owned(meta)
            run("collector-stop", PREFIX + ["stop", "--time", "15", held], timeout=35)
            after = collector_metadata("collector-after-stop")
            require_owned(after)
            result["collector_exit_code"] = after["state"]["ExitCode"]
            result["collector_running_after_stop"] = after["state"]["Running"]
            result["collector_oom_killed"] = after["state"]["OOMKilled"]
            if after["state"]["ExitCode"] != 0 or after["state"]["Running"] or after["state"]["OOMKilled"]:
                raise RuntimeError("Collector did not stop normally with actual exit 0")
            state = parsed("offset-volume-after-stop", PREFIX + ["volume", "inspect", "--format", '{"Name":{{json .Name}},"Labels":{{json .Labels}},"Mountpoint":{{json .Mountpoint}}}', PLAN["state_volume_name"]])
            module.validate_existing_state(state, PLAN["source_collection_sha256"], "stdout")
            result["offset_databases"] = len(list(Path(state["Mountpoint"]).glob("amp-*.db")))
            result["offset_volume_retained"] = True
        except Exception as error:
            result.update(stop_error_class=type(error).__name__, stop_error=str(error))
    if logs is not None:
        try:
            result["logs_actual_exit_code"] = logs.wait(timeout=15)
        except subprocess.TimeoutExpired:
            logs.terminate()
            result["logs_actual_exit_code"] = logs.wait(timeout=5)
            result["forced_log_cli_cleanup"] = True
        stdout.close()
        stderr.close()
    try:
        after = original_snapshot("after")
        after_original = {identity: after[identity] for identity in before if identity in after}
        result["original29_preserved"] = after_original == before and set(after) - set(before) == ({held} if held else set())
        write(PRIVATE / "original29-after.json", after_original)
        if not result["original29_preserved"]:
            raise RuntimeError("Original container set/metadata changed")
    except Exception as error:
        result.update(preservation_error_class=type(error).__name__, preservation_error=str(error))
    if held is not None and (PRIVATE / "collector.stdout.jsonl").exists():
        raw = (PRIVATE / "collector.stdout.jsonl").read_bytes()
        aic_roles = {aic: role for role, aic in EXPECTED.items()}
        roles, kinds, role_kinds, ids = Counter(), Counter(), Counter(), Counter()
        bad_json, bad_amp, unknown = 0, 0, 0
        for line in raw.splitlines():
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                bad_json += 1
                continue
            if not isinstance(row, dict) or row.get("log_type") not in module.KINDS or not isinstance(row.get("aic"), str):
                bad_amp += 1
                continue
            role = aic_roles.get(row["aic"])
            if role is None:
                unknown += 1
            else:
                roles[role] += 1
                role_kinds[role + "/" + row["log_type"]] += 1
            kinds[row["log_type"]] += 1
            if row.get("log_id"):
                ids[row["log_id"]] += 1
        result["records"] = {"raw_lines": len(raw.splitlines()), "invalid_json": bad_json, "invalid_amp": bad_amp,
            "unknown_aic": unknown, "by_role": dict(roles), "by_kind": dict(kinds), "by_role_kind": dict(role_kinds),
            "unique_log_ids": len(ids), "repeated_log_id_occurrences": sum(count - 1 for count in ids.values() if count > 1),
            "stdout_sha256": hashlib.sha256(raw).hexdigest()}
        result["passed"] = ("error" not in result and "stop_error" not in result and result.get("original29_preserved")
            and result.get("collector_exit_code") == 0 and result.get("logs_actual_exit_code") == 0
            and result.get("offset_databases") == 42
            and not bad_json and not bad_amp and not unknown and set(roles) == set(EXPECTED)
            and set(kinds) == set(module.KINDS) and sum(result.get("natural_growth_by_role", {}).values()) > 0)
    result["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write(OUT / "results.json", result)
print(json.dumps({"passed": result["passed"], "preconditions_passed": result.get("preconditions_passed", False),
    "collector_up_invoked": result["collector_up_invoked"], "held_collector_identified": held is not None,
    "original29_preserved": result.get("original29_preserved"),
    "collector_exit_code": result.get("collector_exit_code"), "error_class": result.get("error_class")}))
raise SystemExit(0 if result["passed"] else 1)
