"""One-command local review deployment; Python standard library only."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime/review"
DEFAULTS = {"COMPOSE_PROJECT_NAME": "incident-review", "WORKBENCH_PORT": "18766",
            "ORDER_PORT": "18088", "APP_V1_PORT": "18081", "APP_V2_PORT": "18082",
            "ORDER_BIND": "127.0.0.1"}
SECRET_NAMES = ("POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "APP_ADMIN_TOKEN", "BRIDGE_DB_PASSWORD")


def read_env(path):
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#") and "=" in line)


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def prepare():
    env_path = STATE / "compose.env"
    values = read_env(env_path) if env_path.exists() else {**DEFAULTS, **read_env(ROOT / ".env")}
    for key, default in DEFAULTS.items():
        values.setdefault(key, default)
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,48}", values["COMPOSE_PROJECT_NAME"]):
        raise ValueError("COMPOSE_PROJECT_NAME must use lowercase letters, digits and hyphens")
    ports = [int(values[key]) for key in ("WORKBENCH_PORT", "ORDER_PORT", "APP_V1_PORT", "APP_V2_PORT")]
    if len(set(ports)) != 4 or any(not 1024 <= port <= 65535 for port in ports):
        raise ValueError("Choose four distinct unprivileged ports")
    if values["ORDER_BIND"] != "127.0.0.1":
        raise ValueError("The review deployment must bind to loopback")
    for name in SECRET_NAMES:
        values[name] = values.get(name) or secrets.token_urlsafe(36)
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", values[name]):
            raise ValueError(name + " must be a 32-128 character URL-safe secret, or left empty")
    private_write(env_path, "".join(f"{key}={value}\n" for key, value in values.items()))
    approval = STATE / "approval.env"
    if not approval.exists():
        private_write(approval, "INCIDENT_APPROVAL_SECRET=" + secrets.token_urlsafe(48) + "\n")
    route = STATE / "route/route.conf"
    if not route.exists():
        private_write(route, "set $order_upstream app-v2:8000;\n")
    return values


def docker_command():
    if shutil.which("docker"):
        return ["docker"], False
    if os.name == "nt" and shutil.which("wsl.exe"):
        return ["wsl.exe", "-d", os.environ.get("INCIDENT_WSL_DISTRO", "Ubuntu-22.04"), "--exec", "docker"], True
    raise RuntimeError("Docker with Compose v2 and Linux containers is required")


def docker_path(path, wsl):
    path = str(path.resolve())
    if not wsl:
        return path
    if not re.match(r"^[A-Za-z]:[\\/]", path):
        raise ValueError("WSL requires a local drive path")
    return "/mnt/" + path[0].lower() + path[2:].replace("\\", "/")


def compose(values):
    command, wsl = docker_command()
    return command + ["compose", "-p", values["COMPOSE_PROJECT_NAME"],
                      "--env-file", docker_path(STATE / "compose.env", wsl),
                      "-f", docker_path(ROOT / "deploy/compose.yml", wsl),
                      "-f", docker_path(ROOT / "deploy/review.yml", wsl)]


def run(command, **kwargs):
    # Do not let unrelated shell secrets or Compose variables override this project.
    kwargs.setdefault("env", {key: value for key, value in os.environ.items()
                             if key not in {*DEFAULTS, *SECRET_NAMES} and not key.startswith("COMPOSE_")})
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def http(url, data=None):
    request = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=8) as response:
        return json.load(response)


def wait_ready(values, timeout=120):
    address = "http://127.0.0.1:" + values["WORKBENCH_PORT"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = http(address + "/api/state")
            if state.get("connected") and len(state.get("participants", [])) == 5:
                return address, state
            if state.get("connection_error"):
                raise RuntimeError("Worker startup failed: " + state["connection_error"])
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Workbench did not become ready; run deploy/review.py logs")


def demo(values):
    address, state = wait_ready(values)
    if (state.get("incident") or {}).get("status") in {"running", "awaiting_approval"}:
        raise RuntimeError("An incident is active; let it finish before injecting another fault")
    order = "http://127.0.0.1:" + values["ORDER_PORT"]
    ready = http(order + "/ready")
    if ready.get("api_version") != "v2" or ready.get("ok") is not True:
        raise RuntimeError("Demo requires a healthy v2 baseline")
    cmd = compose(values)
    # Only this review project's route file and nginx service are modified.
    private_write(STATE / "route/route.conf", "set $order_upstream app-v1:8000;\n")
    run(cmd + ["exec", "-T", "nginx", "nginx", "-t"], capture_output=True)
    run(cmd + ["exec", "-T", "nginx", "nginx", "-s", "reload"], capture_output=True)
    deadline = time.monotonic() + 10
    while http(order + "/ready").get("api_version") != "v1":
        if time.monotonic() > deadline:
            raise RuntimeError("Fault did not reach the public entry point")
        time.sleep(.2)
    print("Observed real fault: public order API is v1. Starting diagnosis and repair.", flush=True)
    created = http(address + "/api/incidents", {"symptom": "订单入口返回的字段不符合v2业务合同，请诊断并恢复。"})
    target = ROOT / "artifacts/review" / (created["id"] + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    print("Incident " + created["id"] + " — watch " + address, flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        incident = http(address + "/api/incidents/" + created["id"])
        if incident["status"] in {"completed", "needs_attention", "failed"}:
            target.write_text(json.dumps(incident, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if incident["status"] != "completed" or (incident.get("result") or {}).get("business_recovered") is not True:
                raise RuntimeError("Recovery did not pass; original result retained at " + str(target))
            print("PASS: automatic route recovery and 30-second / 10-workflow verification.")
            print("Result: " + str(target))
            return
        if incident["status"] == "awaiting_approval":
            print("A high-risk action requires approval in the workbench.", flush=True)
        time.sleep(2)
    raise RuntimeError("Demo timed out; inspect the workbench and preserve the current incident")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down", "demo", "status", "logs", "prepare"], nargs="?", default="up")
    args = parser.parse_args()
    if args.action not in {"up", "prepare"} and not (STATE / "compose.env").exists():
        parser.error("Start the review deployment first")
    values = prepare() if args.action in {"up", "prepare"} else read_env(STATE / "compose.env")
    if args.action == "prepare":
        print("Local review configuration prepared; secret values are not printed.")
        return
    cmd = compose(values)
    if args.action == "up":
        run(cmd + ["config", "--quiet"])
        run(cmd + ["up", "-d", "--build", "--wait", "--wait-timeout", "180"])
        address, state = wait_ready(values)
        print("Workbench: " + address)
        print("Order API: http://127.0.0.1:" + values["ORDER_PORT"] + "/ready")
        print("Connected local workers: " + str(len(state["participants"])))
        print("Fault and automatic repair: python deploy/review.py demo")
    elif args.action == "down":
        run(cmd + ["stop", "--timeout", "30"])
        print("Review services stopped. Data and original run records retained.")
    elif args.action == "demo":
        demo(values)
    elif args.action == "logs":
        run(cmd + ["logs", "--tail", "80"])
    else:
        run(cmd + ["ps", "--all"])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
