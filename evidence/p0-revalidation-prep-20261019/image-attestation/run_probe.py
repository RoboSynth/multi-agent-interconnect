"""Linux-side once-only supervisor for one retained, offline image container."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "checkout"
IMAGE = "sha256:f7e91b059a7b50b52294a6a3ab09dfb1d072841817480bbc2ad2b870f440f6ea"
NAME = "incident-pilot-revalidation-image-probe-20261019"
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def command(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, timeout=kwargs.pop("timeout", 30), **kwargs)


def checked(argv):
    r = command(argv)
    if r.returncode:
        raise RuntimeError("Read-only Docker preflight failed: " + str(r.returncode))
    return r.stdout


def containers():
    raw = checked(DOCKER + ["ps", "-a", "--no-trunc", "--format", "{{.ID}}|{{.Names}}"])
    return {line.split("|", 1)[0]: line.split("|", 1)[1] for line in raw.decode("utf-8").splitlines()}


def main():
    before = containers()
    assert NAME not in before.values(), "Reserved probe name already exists; never reuse it"
    baseline = json.loads((HERE.parent / "runtime-inventory/before-container-ids.json").read_text(encoding="utf-8-sig"))
    assert set(baseline) <= before.keys(), "Original container IDs missing before probe"
    assert json.loads(checked(DOCKER + ["image", "inspect", "--format", "{{json .Id}}", IMAGE])) == IMAGE
    assert json.loads(checked(DOCKER + ["image", "inspect", "--format", "{{json .Config.Volumes}}", IMAGE])) in (None, {})
    module = ast.parse((ROOT / "eval/targets.py").read_text(encoding="utf-8-sig"))
    domain = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DOMAIN_SOURCE_FILES" for t in n.targets))
    extras = ("vendor/ACPs-community/acps-sdk/acps_sdk/amp/message_emitter.py", "acps_mcp_bridge/experiment.py",
        "acps_mcp_bridge/approval.py", "acps_mcp_bridge/client.py", "acps_mcp_bridge/audit.py",
        "incident/local_worker.py", "incident/wutong_transport.py", "business/load.py", "business/receipts.py", "workbench_server.py",
        "tools/configure_local_coordinator.py", "domains/database/requirements.txt", "domains/ops/requirements.txt")
    expected = {name: digest(ROOT / name) for name in sorted(set(domain) | set(extras))}
    source_inputs = expected | {"eval/targets.py": digest(ROOT / "eval/targets.py"),
        "deploy/Dockerfile.agent": digest(ROOT / "deploy/Dockerfile.agent")}
    template = (HERE / "container_probe.py").read_text(encoding="utf-8")
    assert template.count("__EXPECTED_SOURCES__") == 1
    payload = template.replace("__EXPECTED_SOURCES__", repr(expected)).encode("utf-8")
    (HERE / "probe-input.py").write_bytes(payload)
    save("input.json", {"image_id": IMAGE, "container_name": NAME, "source_sha256": source_inputs,
        "domain_source_count": len(domain), "probe_input_sha256": hashlib.sha256(payload).hexdigest(),
        "supervisor_sha256": digest(__file__), "template_sha256": digest(HERE / "container_probe.py")})
    # A once-only reservation is never removed, even when preconditions fail.
    with (HERE / "reservation.json").open("x", encoding="utf-8") as out:
        json.dump({"container_name": NAME, "image_id": IMAGE, "recorded_at_utc": datetime.now(timezone.utc).isoformat()}, out)
    argv = DOCKER + ["run", "--name", NAME, "--init", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "128", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--interactive", IMAGE, "python", "-B", "-"]
    start = time.monotonic()
    proc = command(argv, input=payload, timeout=240)
    (HERE / "probe.stdout.json").write_bytes(proc.stdout)
    (HERE / "probe.stderr.log").write_bytes(proc.stderr)
    inspected = json.loads(checked(DOCKER + ["container", "inspect", NAME]))[0]
    after = containers()
    same_sources = {name: digest(ROOT / name) for name in source_inputs} == source_inputs
    scope = {"id": inspected["Id"], "name": inspected["Name"].lstrip("/"), "image_id": inspected["Image"],
        "status": inspected["State"]["Status"], "running": inspected["State"]["Running"],
        "exit_code": inspected["State"]["ExitCode"], "started_at": inspected["State"]["StartedAt"],
        "finished_at": inspected["State"]["FinishedAt"], "network_mode": inspected["HostConfig"]["NetworkMode"],
        "readonly_rootfs": inspected["HostConfig"]["ReadonlyRootfs"], "init": inspected["HostConfig"].get("Init"),
        "mount_count": len(inspected["Mounts"]), "user": inspected["Config"]["User"],
        "container_retained": True, "auto_remove": inspected["HostConfig"]["AutoRemove"]}
    save("container.json", scope)
    result = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "actual_docker_run_exit_code": proc.returncode,
        "duration_seconds": time.monotonic() - start, "container": scope,
        "source_inputs_unchanged": same_sources, "original_container_count": len(baseline),
        "original_container_ids_preserved": set(baseline) <= after.keys(),
        "other_preexisting_container_ids_preserved": set(before) <= after.keys(),
        "new_container_ids": sorted(after.keys() - before.keys()),
        "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
        "stderr_bytes": len(proc.stderr), "command": argv, "passed": False}
    save("results.json", result)
    assert proc.returncode == 0, "Container probe failed; preserve this attempt and never rerun implicitly"
    proof = json.loads(proc.stdout.decode("utf-8"))
    assert proof["passed"] is True and same_sources and result["original_container_ids_preserved"]
    assert result["other_preexisting_container_ids_preserved"]
    assert result["new_container_ids"] == [scope["id"]]
    assert (scope["image_id"] == IMAGE and scope["status"] == "exited" and scope["running"] is False
        and scope["exit_code"] == 0 and scope["network_mode"] == "none" and scope["readonly_rootfs"] is True
        and scope["init"] is True and scope["mount_count"] == 0 and scope["auto_remove"] is False
        and scope["user"] == "65534:65534")
    result["passed"] = True
    result["probe"] = proof
    save("results.json", result)
    print(json.dumps({"passed": True, "image_id": IMAGE, "container_status": scope["status"],
        "source_count": proof["source_count"], "installed_sdk_source_count": len(proof["installed_sdk_sources"]),
        "pip_checks": {k: v["pip_check"]["exit_code"] for k, v in proof["environments"].items()},
        "pglast_version": proof["environments"]["postgres_mcp"]["parse_sql"]["pglast_version"],
        "original_container_ids_preserved": result["original_container_ids_preserved"],
        "results_sha256": digest(HERE / "results.json")}))


if __name__ == "__main__":
    main()
