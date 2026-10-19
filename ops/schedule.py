"""Persistent 30-minute checks and optional, preauthorized rotating lab drills.

All coordination goes through the workbench; fault injection is a separate lab
evaluator process. This process never loads a domain credential file.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
from datetime import datetime, timezone
import json
import os
import random
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
import uuid
import httpx

ROOT = Path(__file__).resolve().parents[1]


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


class SchedulerAlreadyRunning(RuntimeError):
    pass


class ScheduleLock:
    """Hold one OS lock per persisted scheduler directory, without waiting."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.stream = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        stream = (self.directory / "scheduler.lock").open("a+b")
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise SchedulerAlreadyRunning("Scheduler already running for this state directory") from exc
        self.stream = stream
        return self

    def __exit__(self, *exc):
        try:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None


class Scheduler:
    def __init__(self, config, *, client=None, enable_fault_drills=False, allow_local=False):
        self.config = config
        self.base_url = config["workbench_url"].rstrip("/")
        address = urlparse(self.base_url)
        allowed = {"127.0.0.1", "localhost", "coordinator"}
        if address.scheme != "http" or address.hostname not in allowed or address.username or address.password:
            raise ValueError("workbench must be a local project service without embedded credentials")
        self.directory = project_path(config["directory"])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "schedule.json"
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"next_due": {}, "active": None}
        self.client = client
        self.enable_fault_drills, self.allow_local = enable_fault_drills, allow_local
        self.intervals = {"inspect": self.config.get("inspect_interval_seconds", 1800),
                          "drill": self.config.get("drill_interval_seconds", 7200)}
        if any(type(value) is not int or value < 60 for value in self.intervals.values()):
            raise ValueError("schedule intervals must be integer seconds >=60")
        self.drills = config.get("drill_scenarios", ["F01"])
        if (not isinstance(self.drills, list) or not self.drills or len(set(self.drills)) != len(self.drills)
                or any(item not in {"F01", "F02", "F06", "F07"} for item in self.drills)):
            raise ValueError("drill_scenarios must be distinct supported lab scenarios")
        seed = config.get("drill_seed", 0)
        if type(seed) is not int:
            raise ValueError("drill_seed must be an integer")
        self.drills = list(self.drills)
        random.Random(seed).shuffle(self.drills)
        self.auto_approvals = config.get("drill_auto_approvals", [{"tool": "ops.restart", "args": {}}])
        if (not isinstance(self.auto_approvals, list) or any(not isinstance(row, dict)
                or set(row) != {"tool", "args"} or not isinstance(row["tool"], str)
                or not isinstance(row["args"], dict) for row in self.auto_approvals)):
            raise ValueError("drill_auto_approvals must contain exact tool/args pairs")

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def record(self, event, **data):
        row = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)

    async def request(self, method, path, **kwargs):
        if self.client:
            response = await self.client.request(method, self.base_url+path, **kwargs)
        else:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.request(method, self.base_url+path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def inject(self, action):
        backend = self.config.get("fault_backend", "native")
        if backend not in {"native", "docker"}:
            raise ValueError("unsupported lab fault backend")
        active = self.state.get("active") or {}
        scenario = active.get("scenario", "F01")
        if scenario not in self.drills:
            raise ValueError("persisted drill scenario differs from this configuration")
        command = [sys.executable, str(ROOT / "eval/inject.py"), scenario, action, "--backend", backend,
                   "--record", str(self.directory / "private/injections.jsonl")]
        if backend == "native":
            command.extend(["--runtime", str(project_path(self.config["native_runtime"]))])
        elif self.config.get("target_config"):
            command.extend(["--target-config", str(project_path(self.config["target_config"]))])
        elif len(self.drills) > 1:
            raise ValueError("rotating Docker drills require an explicit target_config")
        process = await asyncio.create_subprocess_exec(*command, cwd=ROOT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, _ = await process.communicate()
        if process.returncode:
            raise RuntimeError(f"lab {scenario} {action} exited {process.returncode}")

    async def run_job(self, kind):
        if kind not in {"inspect", "drill"}:
            raise ValueError("unknown schedule job")
        if kind == "drill" and not self.enable_fault_drills:
            self.record("drill_disabled", reason="start with --enable-fault-drills for this lab")
            return
        control = self.config.get("longrun_control_directory")
        if control:
            host_path = project_path(control) / "host.json"
            host = json.loads(host_path.read_text(encoding="utf-8-sig")) if host_path.is_file() else {}
            if host.get("status") != "running":
                self.record("job_skipped_host_unavailable", kind=kind, host_status=host.get("status", "not_recorded"))
                return
        view = await self.request("GET", "/api/state")
        if not view["connected"] or view.get("resource_credential_count") != 0:
            raise RuntimeError("coordinator must be connected and contain no resource credentials")
        if not self.allow_local and view["mode"] != "wutong-amqps":
            raise ValueError("scheduled platform operation requires wutong-amqps")
        active = self.state.get("active")
        if kind == "inspect" and active is not None and active.get("kind") != "inspect":
            self.record("operator_required_pending_drill", run_id=active["id"])
            return
        fresh = active is None
        if fresh:
            if (view.get("incident") or {}).get("status") in {"running", "awaiting_approval"}:
                self.record("job_skipped_busy", kind=kind)
                return
            active = {"id": "schedule-"+uuid.uuid4().hex, "kind": kind}
            if kind == "drill":
                index = self.state.get("next_drill_index", 0)
                if type(index) is not int or index < 0:
                    raise ValueError("invalid persisted drill rotation index")
                active["scenario"] = self.drills[index % len(self.drills)]
            active["symptom"] = f"定时{'巡检' if kind == 'inspect' else '演练'} {active['id']}：检查订单业务，通过资源域确认并处理异常。"
            self.state["active"] = active
            self.save()
        try:
            await self._run_active(view, active, fresh)
        finally:
            if active["kind"] == "drill":
                try:
                    await self.inject("restore")
                except Exception as error:
                    self.record("job_failed", run_id=active["id"], kind="drill", phase="restore",
                                error_class=type(error).__name__)
                    raise
                if active.get("finished"):
                    self.record("job_finished", run_id=active["id"], kind="drill", **active["terminal_result"])
                    self.state["active"] = None
                    self.state["next_drill_index"] = self.state.get("next_drill_index", 0) + 1
                    self.save()

    async def _run_active(self, view, active, fresh):
        if not fresh:
            # A dispatch timeout/restart is reconciled by its unique symptom tag;
            # absence is kept unknown, rather than posting a duplicate incident.
            matches = [row for row in view["incidents"] if row["symptom"] == active["symptom"]]
            if not matches:
                self.record("dispatch_unknown", run_id=active["id"])
                return
            incident_id = matches[0]["id"]
        else:
            if active["kind"] == "drill":
                await self.inject("apply")
            try:
                response = await self.request("POST", "/api/incidents", json={"symptom": active["symptom"]})
                incident_id = response["id"]
            except (httpx.HTTPError, KeyError):
                self.record("dispatch_unknown", run_id=active["id"])
                return
        self.record("job_started", run_id=active["id"], kind=active["kind"], incident_id=incident_id, mode=view["mode"])
        try:
            deadline = time.monotonic()+self.config.get("job_timeout_seconds", 600)
            while time.monotonic() < deadline:
                state = await self.request("GET", "/api/incidents/"+incident_id)
                for approval in state.get("approvals", []):
                    if approval["status"] == "pending":
                        approved = (self.enable_fault_drills and active["kind"] == "drill"
                                    and {"tool": approval["tool"], "args": approval["args"]} in self.auto_approvals)
                        if not approved:
                            self.record("operator_required", incident_id=incident_id, approval_id=approval["id"], tool=approval["tool"])
                            return
                        await self.request("POST", "/api/approvals/"+approval["id"], json={"approved": True})
                        self.record("lab_restart_approved", incident_id=incident_id, approval_id=approval["id"])
                if state["status"] not in {"running", "awaiting_approval"}:
                    if active["kind"] == "drill":
                        active["finished"] = True
                        active["terminal_result"] = {"incident_id": incident_id, "status": state["status"],
                                                     "seconds": state.get("elapsed_seconds")}
                    else:
                        self.record("job_finished", run_id=active["id"], kind=active["kind"],
                                    incident_id=incident_id, status=state["status"], seconds=state.get("elapsed_seconds"))
                        self.state["active"] = None
                    self.save()
                    return
                await asyncio.sleep(self.config.get("poll_seconds", 2))
            self.record("job_timeout", incident_id=incident_id)
        finally:
            self.save()

    async def run(self):
        intervals = self.intervals
        now = time.time()
        for kind, interval in intervals.items():
            self.state["next_due"].setdefault(kind, now if kind == "inspect" else now+interval)
        self.save()
        keep_awake = sys.platform == "win32" and self.config.get("keep_awake", False)
        if keep_awake:
            previous = int(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)) & 0xffffffff
            self.record("keep_awake_request", success=previous != 0, requested_flags="0x80000001",
                        previous_execution_state=hex(previous))
        try:
            while True:
                for kind, interval in intervals.items():
                    if time.time() >= self.state["next_due"][kind]:
                        try:
                            await self.run_job(kind)
                        except (OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
                            self.record("job_failed", kind=kind, error_class=type(exc).__name__,
                                        run_id=(self.state.get("active") or {}).get("id", "schedule-failed-"+uuid.uuid4().hex))
                        self.state["next_due"][kind] = time.time()+interval
                        self.save()
                await asyncio.sleep(5)
        finally:
            if keep_awake:
                previous = int(ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)) & 0xffffffff
                self.record("keep_awake_release", success=previous != 0, requested_flags="0x80000000",
                            previous_execution_state=hex(previous))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", choices=["inspect", "drill"])
    parser.add_argument("--enable-fault-drills", action="store_true")
    parser.add_argument("--allow-local", action="store_true", help="Development only; recorded as local-aip-stdio")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.check:
        scheduler = Scheduler(config, enable_fault_drills=args.enable_fault_drills, allow_local=args.allow_local)
        print(json.dumps({"valid": True, "network_attempted": False, "fault_drills_enabled": args.enable_fault_drills}))
    else:
        try:
            with ScheduleLock(project_path(config["directory"])):
                scheduler = Scheduler(config, enable_fault_drills=args.enable_fault_drills, allow_local=args.allow_local)
                asyncio.run(scheduler.run_job(args.once) if args.once else scheduler.run())
        except SchedulerAlreadyRunning as exc:
            print(json.dumps({"status": "already_running", "error": str(exc), "resource_calls_performed": 0}), file=sys.stderr)
            raise SystemExit(2)
        except KeyboardInterrupt:
            pass
