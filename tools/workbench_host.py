"""Local workbench host with an owned, idle-only stop file; default is validation.

This entry starts no scheduler or incident. Existing workbench lifespan owns the
five local stdio participants. Configuration and persisted incidents are reused.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "artifacts/workbench-host-8766"
CONFIG = ROOT / "runtime/local-coordinator.json"
OUTPUT = ROOT / "artifacts/high-score-workbench"
PORT = 8766
SOURCE_PATHS = ("tools/workbench_host.py", "workbench_server.py", "incident/workbench_access.py",
                "incident/local_transport.py", "demo-ui/workbench.html", "demo-ui/workbench.css",
                "demo-ui/workbench.js", "demo-ui/workbench-access.js")
ALLOWED_ENV = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA",
               "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "SYSTEMDRIVE", "HOMEDRIVE",
               "HOMEPATH", "USERNAME", "OS", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PYTHONUTF8",
               "PYTHONIOENCODING", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
               "INCIDENT_LLM_BASE_URL", "INCIDENT_LLM_MODEL", "INCIDENT_LLM_API_KEY"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def clean_environment(environment):
    result = {key: value for key, value in environment.items() if key.upper() in ALLOWED_ENV}
    result.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return result


def valid_stop(value, pid, nonce):
    return (isinstance(value, dict) and value.get("action") == "stop_when_idle"
            and type(value.get("pid")) is int and value["pid"] == pid
            and value.get("session_nonce") == nonce)


def incident_hashes(output=OUTPUT):
    return {path.name: sha(path) for path in (output / "incidents").glob("inc-*.json")}


def validation():
    config = load(CONFIG)
    if config.get("mode") != "local-aip-stdio" or len(config.get("workers", [])) != 5:
        raise ValueError("This host requires the existing five-participant local stdio configuration")
    if not (ROOT / ".venv/Scripts/python.exe").is_file():
        raise FileNotFoundError("Prepare the project Python environment first")
    for path in (OUTPUT / "incidents").glob("inc-*.json"):
        run = load(path)
        if run.get("status") in {"running", "awaiting_approval"} or any(a.get("status") == "pending" for a in run.get("approvals", [])):
            raise ValueError("Resolve the active incident or pending approval before launching this host")
    return {"status": "LOCAL_HOST_CONFIGURATION_VALIDATED_NO_RUNTIME_ACTION", "port": PORT,
            "config_sha256": sha(CONFIG), "source_sha256": {name: sha(ROOT / name) for name in SOURCE_PATHS},
            "incident_sha256": incident_hashes(), "mode": config["mode"],
            "llm_enabled": config.get("llm_enabled", False), "scheduler_enabled": False}


def idle_status(app):
    active = getattr(app.state, "active", None)
    runs = list(app.state.engine.runs.values())
    transport = app.state.transport
    pending = sum(a.get("status") == "pending" for run in runs for a in run.get("approvals", []))
    inflight = len(transport.journal.list_tasks(in_flight_only=True)) if transport else None
    checks = {"workbench_active_done": active is None or active.done(), "pending_approvals_zero": pending == 0,
              "incident_states_terminal": all(run.get("status") not in {"running", "awaiting_approval"} for run in runs),
              "journal_effective_in_flight_zero": inflight == 0}
    return {"idle": all(checks.values()), "checks": checks, "pending_approvals": pending,
            "journal_effective_in_flight": inflight,
            "incident_statuses": dict(Counter(run.get("status", "unspecified") for run in runs))}


def validate_readiness(state, ready, expected):
    if state.get("pid") != ready["runtime_pid"] or state.get("connected") is not True:
        raise RuntimeError("Owned runtime has not connected")
    if state.get("mode") != "local-aip-stdio" or state.get("config_sha256") != expected["config_sha256"]:
        raise RuntimeError("Loaded configuration differs from the selected configuration")
    if len(state.get("participants", [])) != 5 or state.get("connection_error"):
        raise RuntimeError("Five local participants are not ready")
    if state.get("model_config", {}).get("enabled") is not expected["llm_enabled"]:
        raise RuntimeError("Model enable setting changed")
    if state.get("incident") is not None and "access_reconciliation" not in state["incident"]:
        raise RuntimeError("Updated access reconciliation API is missing")
    if state.get("resource_credential_count") != 0:
        raise RuntimeError("Resource credentials reached the coordinator environment")


@contextmanager
def host_lock():
    path = ROOT / "runtime/workbench-host-8766.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            yield
        finally:
            if locked:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)


async def run_session(directory, nonce):
    launch = load(directory / "launch.json")
    expected = launch["validation"]
    current = validation()
    if any(current[key] != expected[key] for key in ("config_sha256", "source_sha256", "incident_sha256")):
        raise RuntimeError("Launch inputs changed")
    sys.path.insert(0, str(ROOT))
    import uvicorn
    from fastapi.responses import JSONResponse
    from workbench_server import create_app

    app = create_app(CONFIG, OUTPUT)
    draining = False

    @app.middleware("http")
    async def drain_new_incidents(request, call_next):
        if draining and request.method == "POST" and request.url.path == "/api/incidents":
            return JSONResponse({"detail": "正在等待空闲后正常停止，暂停新事故"}, status_code=409)
        return await call_next(request)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="info"))
    report = {"status": "STARTING", "runtime_pid": os.getpid(), "parent_pid": os.getppid(), "session_nonce": nonce,
              "port": PORT, "config_sha256": expected["config_sha256"], "source_sha256": expected["source_sha256"],
              "started_at_utc": now(), "scheduler_enabled": False, "new_incidents_started_by_host": 0,
              "llm_enabled": expected["llm_enabled"]}
    task = asyncio.create_task(server.serve())
    normal = False
    transport = None
    try:
        deadline = time.monotonic() + 120
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("Server ended before readiness")
            if time.monotonic() >= deadline:
                raise TimeoutError("Server readiness timed out")
            await asyncio.sleep(0.1)
        transport = app.state.transport
        if transport is None or transport.mode != "local-aip-stdio" or len(transport.participants) != 5:
            raise RuntimeError("Local transport did not connect five participants")
        if sha(CONFIG) != expected["config_sha256"] or incident_hashes() != expected["incident_sha256"]:
            raise RuntimeError("Configuration or persisted incidents changed at startup")
        report.update(status="LOCAL_CONTROLLED_WORKBENCH_RUNNING", coordinator_term=int(transport.term),
                      local_worker_pids=[worker.process.pid for worker in transport.workers.values()])
        save(directory / "started.json", report)
        last = None
        while not task.done():
            stop = directory / "stop-request.json"
            if stop.exists():
                try:
                    request = load(stop)
                except (ValueError, OSError):
                    request = None
                if valid_stop(request, os.getpid(), nonce):
                    draining = True
                    try:
                        idle = idle_status(app)
                    except Exception as error:
                        idle = {"idle": False, "error_class": type(error).__name__}
                    if idle != last:
                        save(directory / "stop-observation.json", {"runtime_pid": os.getpid(), "session_nonce": nonce, **idle})
                        last = idle
                    if idle["idle"]:
                        report["idle_stop_checks"] = idle
                        server.should_exit = True
                        normal = True
                        break
            await asyncio.sleep(0.25)
        await task
        if not normal:
            raise RuntimeError("Server ended without an owned idle-stop request")
        exits = {name: worker.process.returncode for name, worker in transport.workers.items()}
        report.update(worker_exit_codes=exits, normal_idle_stop_requested=True)
        if not all(value == 0 for value in exits.values()) or transport.started:
            raise RuntimeError("Local participant close did not finish normally")
        report["status"] = "LOCAL_CONTROLLED_WORKBENCH_NORMAL_CLOSE"
    except BaseException as error:
        report.update(status="LOCAL_CONTROLLED_WORKBENCH_FAILED_PRESERVED", error_class=type(error).__name__)
    finally:
        try:
            if not task.done():
                server.should_exit = True
                await task
        except BaseException as error:
            report.update(status="LOCAL_CONTROLLED_WORKBENCH_FAILED_PRESERVED", cleanup_error_class=type(error).__name__)
        report.update(finished_at_utc=now(), config_unchanged=sha(CONFIG) == expected["config_sha256"],
                      source_unchanged=all(sha(ROOT / name) == digest for name, digest in expected["source_sha256"].items()))
        save(directory / "finished.json", report)
    return 0 if report["status"] == "LOCAL_CONTROLLED_WORKBENCH_NORMAL_CLOSE" else 1


def launch():
    expected = validation()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    nonce = uuid.uuid4().hex
    directory = CONTROL / nonce
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "launch.json", {"validation": expected, "session_nonce": nonce, "created_at_utc": now()})
    command = [str(ROOT / ".venv/Scripts/python.exe"), "-X", "utf8", "-B", str(Path(__file__).resolve()), "--run-session", nonce]
    with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=clean_environment(os.environ), stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 135
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned host exited before validated readiness; inspect its preserved logs")
        if (directory / "started.json").exists():
            ready = load(directory / "started.json")
            if ready["session_nonce"] != nonce or ready["config_sha256"] != expected["config_sha256"]:
                raise RuntimeError("Owned host readiness identity changed")
            try:
                with opener.open("http://127.0.0.1:8766/api/state", timeout=5) as response:
                    state = json.load(response)
            except OSError:
                time.sleep(0.2)
                continue
            validate_readiness(state, ready, expected)
            metadata = {"launcher_pid": process.pid, "runtime_pid": ready["runtime_pid"], "port": PORT,
                        "config": str(CONFIG), "config_sha256": expected["config_sha256"],
                        "launch_environment": "system-and-model-allowlist", "stdout": str(directory / "stdout.log"),
                        "stderr": str(directory / "stderr.log"), "session_nonce": nonce, "control_directory": str(directory),
                        "host_source_sha256": sha(__file__)}
            save(ROOT / "runtime/workbench-server.json", metadata)
            result = {"status": "LOCAL_CONTROLLED_WORKBENCH_READY", **metadata,
                      "participant_count": 5, "access_reconciliation_field_present": state.get("incident") is not None,
                      "persisted_incidents_unchanged": incident_hashes() == expected["incident_sha256"]}
            save(directory / "launch-result.json", result)
            return result
        time.sleep(0.2)
    raise TimeoutError("Readiness was not confirmed; owned host and logs were retained, not reported as success")


def request_stop(pid, nonce):
    if not nonce or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("A valid owned session nonce is required")
    directory = CONTROL / nonce
    ready = load(directory / "started.json")
    if ready["runtime_pid"] != pid or ready["session_nonce"] != nonce or (directory / "finished.json").exists():
        raise ValueError("Stop request does not identify the current owned host")
    with (directory / "stop-request.json").open("x", encoding="utf-8") as stream:
        json.dump({"action": "stop_when_idle", "pid": pid, "session_nonce": nonce, "requested_at_utc": now()}, stream)
        stream.write("\n")
    return {"status": "OWNED_IDLE_STOP_REQUESTED_NOT_YET_CLOSED", "runtime_pid": pid, "session_nonce": nonce}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--launch", action="store_true")
    actions.add_argument("--run-session")
    actions.add_argument("--stop", action="store_true")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--nonce")
    args = parser.parse_args(argv)
    if args.run_session:
        if len(args.run_session) != 32 or any(c not in "0123456789abcdef" for c in args.run_session):
            raise ValueError("Invalid session nonce")
        with host_lock():
            return asyncio.run(run_session(CONTROL / args.run_session, args.run_session))
    if args.stop:
        result = request_stop(args.pid, args.nonce)
    elif args.launch:
        result = launch()
    else:
        result = validation()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
