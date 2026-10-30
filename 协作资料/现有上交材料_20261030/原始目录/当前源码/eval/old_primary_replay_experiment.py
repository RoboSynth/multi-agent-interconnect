"""E1-c supplement: suspend and revive the SAME old primary PID, then replay its stale fence.

This uses actual local AIP stdio workers and real PostgreSQL via the upstream MCP.
Fence rejection happens atomically in the shared resource-domain operation ledger;
PostgreSQL itself does not validate the fence. It is not a platform ADP experiment.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.load import OrderObserver
from business.native_process import _libraries, _command_line
from incident.local_transport import LocalAipStdioTransport


class SuspendedPrimary:
    def __init__(self, process, aic):
        if os.name != "nt":
            raise RuntimeError("This exact-PID revival experiment requires Windows")
        self.process, self.aic, self.handle, self.active = process, aic, None, False
        self.kernel, self.ntdll = _libraries()
        for name in ("NtSuspendProcess", "NtResumeProcess"):
            function = getattr(self.ntdll, name)
            function.argtypes, function.restype = [wintypes.HANDLE], wintypes.LONG

    def suspend(self):
        if self.process.returncode is not None:
            raise RuntimeError("Primary exited before suspension")
        self.handle = self.kernel.OpenProcess(0x1000 | 0x0800, False, self.process.pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "Cannot open this experiment primary")
        try:
            command = _command_line(self.ntdll, self.handle).replace("\\", "/")
            if str(ROOT / "incident/local_worker.py").replace("\\", "/") not in command or "--aic " + self.aic not in command:
                raise ValueError("PID is not this experiment's old primary")
            status = self.ntdll.NtSuspendProcess(self.handle)
            if status:
                raise OSError("NtSuspendProcess failed: " + str(status))
            self.active = True
        except BaseException:
            self.close()
            raise
        return {"pid": self.process.pid, "suspend_ntstatus": 0, "identity_checked": True}

    def resume(self):
        if self.active:
            status = self.ntdll.NtResumeProcess(self.handle)
            if status:
                raise OSError("NtResumeProcess failed: " + str(status))
            self.active = False
        return {"pid": self.process.pid, "resume_ntstatus": 0,
                "same_process_alive": self.process.returncode is None}

    def close(self):
        try:
            self.resume()
        finally:
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None


async def run(args):
    if not args.project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in args.project):
        raise ValueError("Invalid Compose project name")
    output = args.output or ROOT / ("eval/results/local/E1c-container-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private"
    private.mkdir()
    caller, primary_aic, backup_aic = "local-container-coordinator", "local-container-db-primary", "local-container-db-backup"
    env_path = args.domain_env.resolve()
    mcp_env = "/mnt/" + str(env_path)[0].lower() + str(env_path)[2:].replace("\\", "/")
    server = {"command": "wsl.exe", "args": ["-d", args.wsl, "--exec", "docker", "run", "--rm", "-i",
        "--network", args.project + "_default", "--label", "incident-pilot=true", "--env-file", mcp_env,
        "incident-pilot-agent:local", "/opt/postgres-mcp/bin/postgres-mcp", "--access-mode=unrestricted"],
        "env_names": ["DATABASE_URI"], "timeout_seconds": 30}
    workers = []
    for role, aic in (("primary", primary_aic), ("backup", backup_aic)):
        path = private / (role + ".json")
        path.write_text(json.dumps({"executor_aic": aic, "allowed_callers": [caller],
            "policy": str(ROOT / "domains/database/policy.yaml"), "ledger_path": str(output / "resource-operations.sqlite"),
            "ledger_domain": "container-e1c", "env_files": [str(env_path)], "approval_secret_env": "INCIDENT_APPROVAL_SECRET",
            "servers": {"postgres": server}}, indent=2), encoding="utf-8")
        workers.append({"name": "e1c-" + role, "role": "database", "aic": aic, "bridge_config": str(path), "standby": role == "backup"})
    config = {"coordinator_aic": caller, "group_id": "local-e1c-container", "workers": workers,
        "directory": str(output / "transport"), "journal_path": str(output / "tasks.sqlite"),
        "term_journal_path": str(output / "coordinator-authority.sqlite"), "amp_directory": str(output / "amp"),
        "approval_env_file": str(args.approval_env.resolve()), "startup_timeout_seconds": 90}
    (output / "coordinator.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    transport = LocalAipStdioTransport(config)
    report = {"mode": "local-aip-stdio", "experiment": "E1-c exact old primary PID revival", "platform_adp_verified": False,
              "fence_enforcement": "shared resource-domain SQLite OperationLedger; PostgreSQL is the protected resource",
              "passed": False}
    suspended = None
    modified = False
    async def control(action):
        process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "eval/container_control.py"), action,
            "--wsl", args.wsl, "--project", args.project, "--env-file", str(args.business_env.resolve()),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        if process.returncode:
            raise RuntimeError("Separate container evaluator control failed: " + action)
        return json.loads(stdout)
    incident, operation = "inc-e1c-" + uuid.uuid4().hex, "op-e1c-" + uuid.uuid4().hex
    base = {"schema_version": "ifc/1.0", "incident_id": incident, "logical_task_id": "lt-e1c-restore",
            "tool": "db.restore_writes", "operation_id": operation, "budget": {"deadline_ms": 30000}}
    old_fence = {"coordinator_term": transport.term, "takeover_version": 0}
    new_fence = {**old_fence, "takeover_version": 1}
    stale = {**base, "kind": "act", "args": {}, "fence": old_fence}
    try:
        await transport.start()
        await control("readonly-on")
        modified = True
        await control("rebuild-pools")
        report["before"] = await control("status")
        initial = await transport.call_on_worker(primary_aic, {**base, "kind": "resume", "args": {"advance_fence": True}, "fence": old_fence})
        if initial.get("active_fence") != old_fence:
            raise AssertionError("Primary did not confirm its initial fence")
        stale["approval"] = transport.issue_approval(stale)
        primary = transport.workers["e1c-primary"]
        suspended = SuspendedPrimary(primary.process, primary_aic)
        report["old_primary_suspended"] = suspended.suspend()
        adopted = await transport.call_on_worker(backup_aic, {**base, "kind": "resume", "args": {"advance_fence": True}, "fence": new_fence})
        if adopted.get("active_fence") != new_fence:
            raise AssertionError("Backup failed to adopt the higher resource fence")
        action = {**base, "kind": "act", "args": {}, "fence": new_fence}
        action["approval"] = transport.issue_approval(action)
        report["backup_action"] = await transport.call_on_worker(backup_aic, action)
        if report["backup_action"].get("operation", {}).get("state") != "applied":
            raise AssertionError("Backup did not restore writes")
        report["after_backup"] = await control("status")
        # Queue the already-authorized old command to the suspended primary.
        pending = asyncio.create_task(transport.call_on_worker(primary_aic, stale))
        await asyncio.sleep(0.1)
        report["old_primary_revived"] = suspended.resume()
        report["old_primary_replay"] = await pending
        rejected = report["old_primary_replay"]
        if rejected.get("executor_aic") != primary_aic or rejected.get("status") != "rejected" or rejected.get("operation", {}).get("state") != "rejected_stale_fence":
            raise AssertionError("The revived primary failed to reject its old fence")
        events = []
        for path in (output / "amp").glob("amp_system_*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("body", {}).get("event") == "mcp_modify_invocation" and row["body"].get("operation_id") == operation:
                    events.append({"aic": row["aic"], **row["body"]})
        report["modification_invocations"] = events
        report["mcp_modifying_calls"] = len(events)
        report["revived_primary_mcp_modifying_calls"] = sum(row["aic"] == primary_aic for row in events)
        if len(events) != 1 or events[0]["aic"] != backup_aic or report["after_backup"]["read_only"]:
            raise AssertionError("Post-takeover resource modification evidence was inconsistent")
        report["checks_passed"] = True
    except Exception as exc:
        report["error_class"] = type(exc).__name__
        report["error"] = str(exc)
    finally:
        if suspended:
            suspended.close()
        if modified:
            try:
                await control("readonly-off")
                await control("rebuild-pools")
                report["cleanup"] = "restored"
            except Exception as exc:
                report["cleanup"] = "failed"
                report["cleanup_error_class"] = type(exc).__name__
        await transport.close()
    if report.get("checks_passed") and report.get("cleanup") == "restored":
        healthy = await OrderObserver(args.url, run_id="e1c-restored-" + uuid.uuid4().hex).observe(duration=30)
        report["healthy_observation"] = {key: value for key, value in healthy.items() if key not in {"events", "state"}}
        report["passed"] = healthy["passed"]
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "error": report.get("error_class")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl", default="Ubuntu-22.04")
    parser.add_argument("--project", default="incident-pilot-container")
    parser.add_argument("--domain-env", type=Path, default=ROOT / "runtime/container-domains/database/domain.env")
    parser.add_argument("--business-env", type=Path, default=ROOT / "runtime/private/container.env")
    parser.add_argument("--approval-env", type=Path, default=ROOT / "runtime/private/approval.env")
    parser.add_argument("--url", default="http://127.0.0.1:18088")
    parser.add_argument("--output", type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
