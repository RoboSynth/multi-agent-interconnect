"""Prepare a new local manifest and images; never start services or consumers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from deploy.prepare_deployment import GENERATED_ENV_KEYS, compose_command, load_deployment, prepare

HERE = Path(__file__).resolve().parent
OUTPUT = ROOT / "runtime/private/tonight-new7-20261019"
SOURCE = Path(r"D:\AI + 开源\incident-pilot\runtime\private\new7-container-20261018\source.json")
PROJECT = "incident-pilot-new7-tech-20261019"
PORTS = [38081, 38082, 38088, 38090]


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decode(value):
    return value.decode("utf-16le" if value.count(b"\x00") > len(value) // 4 else "utf-8", errors="replace")


def main():
    if OUTPUT.exists():
        raise RuntimeError("Deployment output already exists; preserving it")
    if (HERE / "summary.json").exists():
        raise RuntimeError("A previous preparation receipt already exists; preserving it")
    # Filter this child process only. Domain private files are not loaded into it.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("COMPOSE_")
        and key.upper() not in GENERATED_ENV_KEYS
        and key.upper() not in {"DOCKER_HOST", "DOCKER_CONTEXT"}
        and not any(marker in key.upper() for marker in ("PASSWORD", "TOKEN", "SECRET", "DATABASE_URL", "DATABASE_URI", "DSN"))
    }
    windows = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$p=@(38081,38082,38088,38090); @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $p } | Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Compress"],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30)
    windows_text = decode(windows.stdout).strip()
    if windows.returncode:
        raise RuntimeError("Windows listener inventory failed")
    windows_listeners = json.loads(windows_text) if windows_text else []
    if not isinstance(windows_listeners, list):
        windows_listeners = [windows_listeners]
    linux = subprocess.run(["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "/usr/bin/ss", "-H", "-ltn"],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30)
    if linux.returncode:
        raise RuntimeError("WSL listener inventory failed")
    linux_listeners = [line for line in decode(linux.stdout).splitlines()
                       if any(field.rsplit(":", 1)[-1] in {str(port) for port in PORTS}
                              for field in line.split()[3:4])]
    save("preflight.json", {"checked_at": datetime.now(timezone.utc).isoformat(), "ports": PORTS,
        "windows_listeners": windows_listeners, "wsl_listeners": linux_listeners, "output_existed": False})
    if windows_listeners or linux_listeners:
        raise RuntimeError("A selected port already has a listener; no preparation attempted")
    summary = prepare(OUTPUT, PROJECT, {"app_v1": PORTS[0], "app_v2": PORTS[1], "order": PORTS[2]},
        reply_port=PORTS[3], mode="seven", identity_file=SOURCE, wsl="Ubuntu-22.04", root=ROOT,
        public_onboarding=False)
    save("preparation.json", summary)
    manifest = load_deployment(OUTPUT / "deployment.json", root=ROOT)
    onboarding = json.loads((OUTPUT / "domains/onboarding/config.json").read_text(encoding="utf-8"))
    public_enabled = onboarding.get("public_metadata_service", False)
    if public_enabled is not False:
        raise RuntimeError("Public onboarding must remain disabled in this preparation")
    # Keep the same explicitly selected daemon used by the read-only preflight.
    command = compose_command(manifest, root=ROOT, sanitized=True)
    docker_index = command.index("docker")
    command[docker_index:docker_index] = ["-u", "DOCKER_HOST", "-u", "DOCKER_CONTEXT",
        "-u", "INCIDENT_APPROVAL_SECRET", "-u", "PGPASSWORD", "-u", "DATABASE_URL", "-u", "DATABASE_URI", "-u", "DSN"]
    docker_index = command.index("docker")
    command[docker_index + 1:docker_index + 1] = ["--host", "unix:///var/run/docker.sock"]
    actions = [["config", "--quiet"], ["build", "app-v1", "app-v2"], ["build", "application-agent"]]
    receipts = []
    for number, action in enumerate(actions, 1):
        log = HERE / (f"{number:02d}-" + "-".join(action).replace("--", "") + ".txt")
        with log.open("xb") as stream:
            process = subprocess.run(command + action, cwd=ROOT, env=environment,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, check=False)
        receipts.append({"argv": command + action, "exit_code": process.returncode,
                         "combined_output": log.name})
        save("actions.json", receipts)
        if process.returncode:
            save("summary.json", {"status": "FAILED_PRESERVED", "failed_action": action,
                "preparation": summary, "actions": receipts, "services_started": False,
                "identity_consumers_started": False, "platform_logs_sent": False})
            print(json.dumps({"status": "FAILED_PRESERVED", "failed_action": action,
                              "exit_code": process.returncode, "evidence": str(HERE)}, ensure_ascii=False))
            return process.returncode
    tags = [PROJECT + "-app-v1:latest", PROJECT + "-app-v2:local", PROJECT + "-agent:local"]
    inspect_command = ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "/usr/bin/docker", "--host",
        "unix:///var/run/docker.sock", "image", "inspect", *tags,
        "--format", '{{json .Id}} {{json .RepoTags}} {{json .Created}}']
    inspected = subprocess.run(inspect_command, env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=30)
    save("images.json", {"argv": inspect_command, "exit_code": inspected.returncode,
        "stdout": decode(inspected.stdout), "stderr": decode(inspected.stderr)})
    source_files = ["deploy/Dockerfile.agent", "business/order_app/Dockerfile", "requirements-lock.txt",
        "requirements-high-score.txt", "incident/partners.py", "business/load.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_leader.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_partner.py"]
    source_sha256 = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files}
    result = {"status": "IMAGES_PREPARED_NOT_STARTED" if inspected.returncode == 0 else "IMAGE_INSPECT_FAILED",
        "prepared_at": datetime.now(timezone.utc).isoformat(), "preparation": summary,
        "manifest_validated": True, "onboarding_allow_public": public_enabled, "actions": receipts,
        "image_inspect_exit_code": inspected.returncode, "source_sha256": source_sha256,
        "services_started": False, "identity_consumers_started": False, "platform_logs_sent": False,
        "task_registration_attempted": False, "runtime_acceptance": "not_run"}
    save("summary.json", result)
    print(json.dumps({"status": result["status"], "deployment_file": summary["deployment_file"],
                      "actions_exit_codes": [row["exit_code"] for row in receipts],
                      "image_inspect_exit_code": inspected.returncode, "evidence": str(HERE)}, ensure_ascii=False))
    return inspected.returncode


if __name__ == "__main__":
    raise SystemExit(main())
