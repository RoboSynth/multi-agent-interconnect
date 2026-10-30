"""Stop the registered local stack in dependency order, retaining all receipts.

Only workbench nonce shutdown, authenticated supervisor shutdown and the existing
native stop entry are used. No process is forcibly terminated by this helper.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business import native_process as native


def load(path):
    with path.open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Expected an object in the project registration")
    return value


def normalized(path):
    return os.path.normcase(str(Path(path).resolve()))


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def unchanged(path, expected):
    if fingerprint(path) != expected:
        raise RuntimeError("A registration changed during shutdown; restart the shutdown check")


class OwnedFamily:
    """Hold exact-identity handles from preflight through actual exit checks."""

    def __init__(self, pid, script, arguments, python):
        if type(pid) is not int or pid <= 0:
            raise ValueError("Expected a registered positive PID")
        self.kernel, self.ntdll = native._libraries()
        self.records = []
        launcher, images = native._python_images(python)

        def opened(candidate):
            handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, candidate)
            if not handle:
                if ctypes.get_last_error() == 87:
                    return None
                raise OSError(ctypes.get_last_error(), "Cannot open the registered local process")
            try:
                state = self.kernel.WaitForSingleObject(handle, 0)
                if state == 0:
                    self.kernel.CloseHandle(handle)
                    return None
                if state != 0x102:
                    raise OSError("Cannot query registered process liveness")
                argv = native._argv(native._command_line(self.ntdll, handle))
                expected = [str(script), *arguments]
                # The workbench adds fixed interpreter flags; argv[0] is checked
                # via its real image, never a substring in another command.
                offset = 4 if arguments and arguments[0] == "--run-session" else 1
                if (len(argv) != offset + len(expected)
                        or (offset == 4 and argv[1:4] != ["-X", "utf8", "-B"])
                        or not Path(argv[offset]).is_absolute()
                        or normalized(argv[offset]) != normalized(script)
                        or argv[offset + 1:] != arguments):
                    raise ValueError("Registered PID is not the exact local project command")
                image = native._image_path(self.kernel, handle)
                if image not in images:
                    raise ValueError("Registered PID is not the configured project Python")
                record = {"pid": candidate, "handle": handle,
                          "launcher": image == launcher,
                          "created": native._creation_time(self.kernel, handle),
                          "parent_pid": native._parent_pid(self.ntdll, handle)}
                self.records.append(record)
                return record
            except BaseException:
                self.kernel.CloseHandle(handle)
                raise

        try:
            parent = opened(pid)
            for child_pid, parent_pid in native._process_snapshot(self.kernel):
                if parent_pid != pid:
                    continue
                try:
                    child = opened(child_pid)
                except ValueError:
                    continue  # Unrelated children are outside this shutdown.
                if child and (not parent or not parent["launcher"] or child["launcher"]
                              or child["parent_pid"] != pid or child["created"] < parent["created"]):
                    raise ValueError("Registered local process family is not intact")
            if parent and parent["launcher"] and len(self.records) != 2:
                raise ValueError("Registered Python launcher lacks one verified runtime child")
        except BaseException:
            self.close()
            raise

    def wait(self, deadline):
        from ctypes import wintypes
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        for record in reversed(self.records):
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if self.kernel.WaitForSingleObject(record["handle"], remaining) != 0:
                raise TimeoutError("Shutdown requested but a registered process has not exited")
            code = wintypes.DWORD()
            if not self.kernel.GetExitCodeProcess(record["handle"], ctypes.byref(code)):
                raise OSError("Cannot confirm the registered process exit code")
            record["exit_code"] = code.value
            if code.value != 0:
                raise RuntimeError("Registered process exited abnormally after shutdown")
        return [{key: value for key, value in record.items() if key != "handle"}
                for record in self.records]

    def close(self):
        for record in self.records:
            self.kernel.CloseHandle(record["handle"])
        self.records.clear()


def workbench_stop(path, digest, timeout):
    unchanged(path, digest)
    if digest is None:
        return {"status": "NO_REGISTRATION"}
    meta = load(path)
    nonce, pid = meta.get("session_nonce"), meta.get("runtime_pid")
    if (not isinstance(nonce, str) or len(nonce) != 32
            or any(char not in "0123456789abcdef" for char in nonce)):
        raise ValueError("Invalid registered workbench nonce")
    directory = ROOT / "artifacts/workbench-host-8766" / nonce
    if normalized(meta.get("control_directory", "")) != normalized(directory):
        raise ValueError("Workbench control directory belongs to another checkout")
    ready = load(directory / "started.json")
    if ready.get("runtime_pid") != pid or ready.get("session_nonce") != nonce:
        raise ValueError("Workbench registration and session disagree")
    finished = directory / "finished.json"

    def closed_report():
        report = load(finished)
        if (report.get("runtime_pid") != pid or report.get("session_nonce") != nonce
                or report.get("status") != "LOCAL_CONTROLLED_WORKBENCH_NORMAL_CLOSE"
                or report.get("normal_idle_stop_requested") is not True
                or not report.get("idle_stop_checks", {}).get("idle")
                or not report.get("worker_exit_codes")
                or any(code != 0 for code in report["worker_exit_codes"].values())):
            raise RuntimeError("Workbench session has no confirmed normal close")
        return report

    finished_at_entry = finished.exists()
    if finished_at_entry:
        closed_report()
    family = OwnedFamily(meta.get("launcher_pid"), ROOT / "tools/workbench_host.py", ["--run-session", nonce],
                         ROOT / ".venv/Scripts/python.exe")
    try:
        if finished_at_entry:
            # The host writes its receipt before returning from main. An
            # existing receipt alone must not release the next dependency.
            exits = family.wait(time.monotonic() + timeout)
            closed_report()
            return {"status": "NORMAL_CLOSED" if exits else "ALREADY_NORMAL_CLOSED",
                    "processes": exits, "session_nonce": nonce}
        if pid not in [record["pid"] for record in family.records]:
            raise RuntimeError("Workbench exited without a confirmed close receipt")
        unchanged(path, digest)
        sys.path.insert(0, str(ROOT / "tools"))
        import workbench_host
        request = directory / "stop-request.json"
        if request.exists():
            if not workbench_host.valid_stop(load(request), pid, nonce):
                raise ValueError("Existing stop request does not match the registered session")
        else:
            workbench_host.request_stop(pid, nonce)
        deadline = time.monotonic() + timeout
        exits = family.wait(deadline)
        if not finished.exists():
            raise RuntimeError("Workbench exited without its final normal-close receipt")
        closed_report()
        return {"status": "NORMAL_CLOSED", "processes": exits, "session_nonce": nonce}
    finally:
        family.close()


def supervisor_stop(path, digest, timeout, url="http://127.0.0.1:8093"):
    unchanged(path, digest)
    if digest is None:
        return {"status": "NO_REGISTRATION"}
    pid = int(path.read_text(encoding="ascii").strip())
    family = OwnedFamily(pid, ROOT / "domains/ops/native_supervisor.py", [],
                         ROOT / ".venv/Scripts/python.exe")
    try:
        if not family.records:
            return {"status": "REGISTERED_PROCESS_ALREADY_EXITED", "pid": pid}
        from domains.ops.native_supervisor import read_token
        token = read_token()
        opener = build_opener(ProxyHandler({}))

        def call(endpoint, data=None):
            request = Request(url + endpoint, data=data,
                              headers={"Authorization": "Bearer " + token,
                                       "Content-Type": "application/json"})
            with opener.open(request, timeout=min(timeout, 10)) as response:
                return json.load(response)

        health = call("/health")
        if (health.get("ok") is not True or health.get("service") != "incident-pilot-native-ops"
                or normalized(health.get("project_root", "")) != normalized(ROOT)
                or health.get("pid") not in [record["pid"] for record in family.records]):
            raise ValueError("Authenticated supervisor does not match the registered family")
        unchanged(path, digest)
        response = call("/shutdown", b"{}")
        if (response.get("status") != "SHUTDOWN_REQUESTED"
                or response.get("pid") != health["pid"]
                or normalized(response.get("project_root", "")) != normalized(ROOT)):
            raise ValueError("Supervisor shutdown response did not match its ownership")
        exits = family.wait(time.monotonic() + timeout)
        return {"status": "NORMAL_CLOSED", "processes": exits}
    finally:
        family.close()


def validate_native(path):
    if not path.exists():
        return
    config = load(path)
    if config.get("backend") != "native" or normalized(config.get("project_root", "")) != normalized(ROOT):
        raise ValueError("Native runtime belongs to another checkout or backend")
    drive = config.get("native_drive")
    for key in ("pgdata", "postgres_bin", "nginx_prefix", "nginx_bin"):
        value = config.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("Native runtime paths must be explicitly registered and absolute")
        selected = Path(value)
        if drive and selected.drive.lower() == drive.lower():
            selected = ROOT.joinpath(*selected.parts[1:])
        resolved = selected.resolve()
        if resolved == ROOT.resolve() or not resolved.is_relative_to(ROOT.resolve()):
            raise ValueError("Native service path is outside the registered checkout")


def shutdown(timeout, pwsh):
    paths = {"workbench": ROOT / "runtime/workbench-server.json",
             "supervisor": ROOT / "runtime/ops-supervisor.pid",
             "native": ROOT / "deploy/native-runtime.json"}
    report = {"status": "INCOMPLETE", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "registration_sha256": {key: fingerprint(path) for key, path in paths.items()},
              "stages": {}, "registration_files_retained": True}
    stage = "preflight"
    try:
        validate_native(paths["native"])
        for stage, operation in (("workbench", workbench_stop), ("supervisor", supervisor_stop)):
            report["stages"][stage] = operation(paths[stage], report["registration_sha256"][stage], timeout)
            unchanged(paths[stage], report["registration_sha256"][stage])
        stage = "native"
        unchanged(paths[stage], report["registration_sha256"][stage])
        if report["registration_sha256"][stage] is None:
            report["stages"][stage] = {"status": "NO_REGISTRATION"}
        else:
            result = subprocess.run([str(pwsh), "-NoProfile", "-File", str(ROOT / "deploy/native.ps1"),
                                     "stop", "-RuntimeFile", str(paths[stage])], cwd=ROOT, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"Native stop did not complete (exit {result.returncode})")
            report["stages"][stage] = {"status": "NATIVE_STOP_EXIT_ZERO", "exit_code": 0}
        report["status"] = "REGISTERED_LOCAL_SHUTDOWN_COMPLETED"
    except Exception as error:
        report.update(failed_stage=stage, error_class=type(error).__name__, error=str(error))
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    directory = ROOT / "runtime/local-down"
    directory.mkdir(parents=True, exist_ok=True)
    receipt = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex + ".json")
    receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "receipt": str(receipt),
                      "failed_stage": report.get("failed_stage")}, ensure_ascii=False))
    return 0 if report["status"] == "REGISTERED_LOCAL_SHUTDOWN_COMPLETED" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--pwsh", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 3600 or not args.pwsh.is_absolute():
        parser.error("Use a 1..3600 second timeout and an absolute PowerShell executable")
    return shutdown(args.timeout_seconds, args.pwsh)


if __name__ == "__main__":
    sys.exit(main())
