"""Persistent 30-minute checks and optional, preauthorized F01 lab drills.

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
        command = [sys.executable, str(ROOT / "eval/inject.py"), "F01", action, "--backend", backend,
                   "--record", str(self.directory / "private/injections.jsonl")]
        if backend == "native":
            command.extend(["--runtime", str(project_path(self.config["native_runtime"]))])
        process = await asyncio.create_subprocess_exec(*command, cwd=ROOT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, _ = await process.communicate()
        if process.returncode:
            raise RuntimeError(f"lab F01 {action} exited {process.returncode}")

    async def run_job(self, kind):
        if kind not in {"inspect", "drill"}:
            raise ValueError("unknown schedule job")
        if kind == "drill" and not self.enable_fault_drills:
            self.record("drill_disabled", reason="start with --enable-fault-drills for this lab")
            return
        view = await self.request("GET", "/api/state")
        if not view["connected"] or view.get("resource_credential_count") != 0:
            raise RuntimeError("coordinator must be connected and contain no resource credentials")
        if not self.allow_local and view["mode"] != "wutong-amqps":
            raise ValueError("scheduled platform operation requires wutong-amqps")
        active = self.state.get("active")
        fresh = active is None
        if fresh:
            if (view.get("incident") or {}).get("status") in {"running", "awaiting_approval"}:
                self.record("job_skipped_busy", kind=kind)
                return
            active = {"id": "schedule-"+uuid.uuid4().hex, "kind": kind}
            active["symptom"] = f"定时{'巡检' if kind == 'inspect' else '演练'} {active['id']}：检查订单业务，通过资源域确认并处理异常。"
            self.state["active"] = active
            self.save()
        try:
            await self._run_active(view, active, fresh)
        finally:
            if active["kind"] == "drill":
                await self.inject("restore")

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
                                    and approval["tool"] == "ops.restart" and approval["args"] == {})
                        if not approved:
                            self.record("operator_required", incident_id=incident_id, approval_id=approval["id"], tool=approval["tool"])
                            return
                        await self.request("POST", "/api/approvals/"+approval["id"], json={"approved": True})
                        self.record("lab_restart_approved", incident_id=incident_id, approval_id=approval["id"])
                if state["status"] not in {"running", "awaiting_approval"}:
                    self.record("job_finished", run_id=active["id"], incident_id=incident_id, status=state["status"],
                                seconds=state.get("elapsed_seconds"))
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
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        try:
            while True:
                for kind, interval in intervals.items():
                    if time.time() >= self.state["next_due"][kind]:
                        try:
                            await self.run_job(kind)
                        except (OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
                            self.record("job_failed", kind=kind, error_class=type(exc).__name__)
                        self.state["next_due"][kind] = time.time()+interval
                        self.save()
                await asyncio.sleep(5)
        finally:
            if keep_awake:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", choices=["inspect", "drill"])
    parser.add_argument("--enable-fault-drills", action="store_true")
    parser.add_argument("--allow-local", action="store_true", help="Development only; recorded as local-aip-stdio")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    scheduler = Scheduler(config, enable_fault_drills=args.enable_fault_drills, allow_local=args.allow_local)
    if args.check:
        print(json.dumps({"valid": True, "network_attempted": False, "fault_drills_enabled": args.enable_fault_drills}))
    else:
        try:
            asyncio.run(scheduler.run_job(args.once) if args.once else scheduler.run())
        except KeyboardInterrupt:
            pass
