"""systemd ExecStop: request the existing idle handoff, then stop that paused PID.

This deployment helper reads JSON configuration, not certificate/private-key
contents. It starts no identity, SDK transport, Docker command or experiment.
Linux pidfds prevent a reused PID from receiving the stop signal.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import time
import uuid


def project_path(value, root):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def lease_api(root):
    sys.path.insert(0, str(root))
    return importlib.import_module("ops.aic_lease")


def expected_aics(settings, root, api):
    # Do not call load_deployment: its hash validation reads private-key bytes.
    manifest = api.load(project_path(settings["deployment_manifest"], root))
    if manifest.get("mode") != "seven":
        raise ValueError("Expected the seven-identity deployment")
    config = api.load(project_path(manifest["coordinator_config"], root))
    trusted = config.get("trusted_participant_aics", {})
    if config.get("mode") != "wutong-amqps" or set(trusted) != {
        "application", "verification", "database", "ops", "onboarding"
    }:
        raise ValueError("Expected the exact NEW7 coordinator bindings")
    if any(not isinstance(rows, list) for rows in trusted.values()):
        raise ValueError("Expected explicit participant AIC lists")
    aics = [config["leader"]["aic"], *(aic for rows in trusted.values() for aic in rows)]
    if len(aics) != 7 or len(set(aics)) != 7 or any(not isinstance(aic, str) or not aic for aic in aics):
        raise ValueError("Expected seven distinct nonempty AICs")
    return sorted(aics)


class LinuxProcess:
    def __init__(self, pid):
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("Linux pidfd support is required")
        self.pid = pid
        self.fd = os.pidfd_open(pid)

    def snapshot(self):
        directory = Path("/proc") / str(self.pid)
        fields = (directory / "stat").read_text().rsplit(") ", 1)[1].split()
        return {
            "pid": self.pid,
            "start_ticks": fields[19],
            "argv": [part.decode("utf-8") for part in (directory / "cmdline").read_bytes().split(b"\0") if part],
        }

    def terminate(self):
        signal.pidfd_send_signal(self.fd, signal.SIGTERM)

    def wait_exited(self, timeout):
        return bool(select.select([self.fd], [], [], timeout)[0])

    def close(self):
        os.close(self.fd)


def check_command(snapshot, root, config):
    argv = snapshot["argv"]
    allowed = {
        str((root / "ops/startup.py").resolve()): ("--stage", "workbench"),
        str((root / "ops/longrun_host.py").resolve()): ("--run", None),
    }
    matches = [project_path(arg, root) for arg in argv[1:] if arg.endswith(".py")]
    if len(matches) != 1 or str(matches[0]) not in allowed:
        raise RuntimeError("PID command is not the selected managed workbench")
    if argv.count("--config") != 1:
        raise RuntimeError("PID command has no unique host configuration")
    index = argv.index("--config")
    if index + 1 >= len(argv) or project_path(argv[index + 1], root) != config:
        raise RuntimeError("PID command uses a different host configuration")
    option, value = allowed[str(matches[0])]
    if argv.count(option) != 1 or (value is not None and (
        argv.index(option) + 1 >= len(argv) or argv[argv.index(option) + 1] != value
    )):
        raise RuntimeError("PID command is not a workbench runtime")


def request_and_stop(project_root, host_config, *, timeout=840, exit_timeout=15,
                     process_factory=LinuxProcess, clock=time.monotonic, wait=time.sleep,
                     token=None):
    root, config = Path(project_root).resolve(), Path(host_config).resolve()
    if timeout <= 0 or not 0 < exit_timeout <= 60:
        raise ValueError("Stop timeouts must be positive and exit timeout at most 60 seconds")
    api = lease_api(root)
    settings = api.load(config)
    control = project_path(settings["control_directory"], root)
    aics = expected_aics(settings, root, api)
    token = token or uuid.uuid4().hex
    process = None
    with api.AicLease(["handoff:" + str(control.resolve())], purpose="systemd-graceful-stop",
                      directory=control / "controllers") as reservation:
        initial = api.load(control / "host.json")
        pid, session = initial.get("pid"), initial.get("session_id")
        if initial.get("status") != "running" or not isinstance(session, str) or not session:
            raise RuntimeError("Managed host is not running; leave existing state untouched")
        if type(pid) is not int or pid <= 1 or pid == os.getpid():
            raise RuntimeError("Managed host PID is invalid")
        if sorted(initial.get("aics", [])) != aics:
            raise RuntimeError("Managed host identity set differs from the deployment")
        process = process_factory(pid)
        try:
            identity = process.snapshot()
            if identity.get("pid") != pid:
                raise RuntimeError("Process snapshot has a different PID")
            check_command(identity, root, config)
            request = dict(action="stop_when_idle", request_id=token, host_session=session,
                           owner=reservation.owner, requested_at=api.now(), aics=aics)
            api.save(control / "handoff-request.json", request)
            deadline = clock() + timeout
            while True:
                state = api.load(control / "host.json")
                if (state.get("pid") != pid or state.get("session_id") != session
                        or sorted(state.get("aics", [])) != aics):
                    raise RuntimeError("Managed host binding changed during idle handoff")
                if process.snapshot() != identity:
                    raise RuntimeError("Managed host process identity changed during idle handoff")
                if state.get("status") == "quarantined":
                    raise RuntimeError("Managed host cleanup is quarantined")
                if state.get("status") == "paused" and state.get("request_id") == token:
                    if state.get("consumers_closed") is not True or state.get("lease_released") is not True:
                        raise RuntimeError("Pause acknowledgement lacks confirmed cleanup")
                    result_path = control / "handoff-result.json"
                    if result_path.exists() and api.load(result_path).get("request_id") == token:
                        raise RuntimeError("Another controller answered this stop request")
                    # The old Uvicorn task and six SDK consumers have closed and
                    # the host is now only waiting for a handoff result. It must
                    # not receive resume/cancel before systemd stops the process.
                    process.terminate()
                    if not process.wait_exited(exit_timeout):
                        raise TimeoutError("Paused managed process did not exit after SIGTERM")
                    return dict(status="stopped", pid=pid, host_session=session, request_id=token,
                                identities=7, consumers_closed=True, lease_released=True,
                                exact_process_exited=True, stop_signal="SIGTERM")
                if state.get("status") not in {"running", "draining", "paused"}:
                    raise RuntimeError("Unexpected managed host status during idle handoff")
                if clock() >= deadline:
                    raise TimeoutError("Idle pause was not confirmed; no stop signal was sent")
                wait(.25)
        finally:
            process.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--host-config", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=840)
    parser.add_argument("--exit-timeout", type=float, default=15)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = request_and_stop(args.project_root, args.host_config,
                                  timeout=args.timeout, exit_timeout=args.exit_timeout)
    except Exception as error:
        result = dict(status="failed", error_class=type(error).__name__, error=str(error),
                      preserve_handoff_state=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "stopped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
