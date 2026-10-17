"""Exercise existing registered identities over real Wutong AMQPS.

By default this checks application/verification discovery and describe only;
it neither injects faults nor claims acceptance of the full four-domain system.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from incident.wutong_transport import WutongTransport
from acps_sdk.aic import validate_aic_format


def observation_arguments(tool, target_aic=None):
    if tool == "aip.onboarding.check":
        if not isinstance(target_aic, str) or not validate_aic_format(target_aic)[0]:
            raise ValueError("onboarding observation requires a valid --observe-target-aic")
        return {"target_aic": target_aic}
    if target_aic is not None:
        raise ValueError("--observe-target-aic is only valid for aip.onboarding.check")
    return {}


async def run(args):
    tool = args.observe_tool or ("application.status" if args.observe_application else None)
    tool_args = observation_arguments(tool, getattr(args, "observe_target_aic", None))
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    roles = args.roles.split(",")
    processes = []
    transport = None
    result = {"started_at": datetime.now(timezone.utc).isoformat(),
              "mode": "wutong-amqps", "scope": roles, "full_p0_acceptance": False,
              "fault_injection": False, "status": "failed"}
    try:
        if not args.external_workers:
            for role in roles:
                if role not in {"application", "verification"}:
                    raise ValueError("bridge domains must be started independently; use --external-workers")
                config = json.loads((args.config_dir / f"{role}.json").read_text(encoding="utf-8"))
                config["amp_directory"] = str(output / "amp")
                config["evidence_path"] = str(output / f"{role}-events.jsonl")
                config_path = output / f"{role}.json"
                config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
                stdout_path = output / f"{role}-stdout.log"
                stderr_path = output / f"{role}-stderr.log"
                environment = dict(os.environ)
                environment["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")])
                environment["PYTHONIOENCODING"] = "utf-8"
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    process = subprocess.Popen([sys.executable, "-m", "incident.platform_worker",
                        "--config", str(config_path)], cwd=ROOT, env=environment,
                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
                processes.append(process)
                deadline = time.monotonic() + 45
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"{role} worker exited {process.returncode}; inspect its logs")
                    if '"status": "ready"' in stdout_path.read_text(encoding="utf-8", errors="replace"):
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{role} worker readiness timed out")
                    await asyncio.sleep(.2)
        config = json.loads((args.config_dir / "coordinator.json").read_text(encoding="utf-8"))
        config["skills"] = {role: config["skills"][role] for role in roles}
        transport = WutongTransport(config, output / "coordinator")
        await asyncio.wait_for(transport.start(), 180)
        result["participants"] = transport.participants
        result["tools"] = sorted(set(transport.tools))
        if tool:
            payload = {"schema_version": "ifc/1.0", "incident_id": "platform-smoke-"+uuid.uuid4().hex,
                       "logical_task_id": "lt-"+uuid.uuid4().hex, "kind": "observe",
                       "tool": tool, "args": tool_args,
                       "budget": {"deadline_ms": 30000 if tool == "aip.onboarding.check" else 15000}}
            result["observation"] = await transport.call(payload)
        result["status"] = "completed"
        return 0
    except Exception as exc:
        result["error_class"] = type(exc).__name__
        result["error_stack"] = [{"file": str(Path(frame.filename).relative_to(ROOT))
            if Path(frame.filename).is_relative_to(ROOT) else Path(frame.filename).name,
            "line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(exc.__traceback__)]
        if isinstance(exc, AttributeError):
            result["error_attribute"] = exc.name
        # Resource/provider exception text may contain credentials. Logs stay local.
        print(json.dumps({"status": "failed", "error_class": type(exc).__name__}), flush=True)
        return 1
    finally:
        if transport:
            try:
                await transport.close()
            except Exception as exc:
                result["close_error_class"] = type(exc).__name__
        for process in processes:
            if process.poll() is None:
                process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roles", default="application,verification")
    parser.add_argument("--external-workers", action="store_true")
    parser.add_argument("--observe-application", action="store_true")
    parser.add_argument("--observe-tool", choices=["application.status", "db.read_only_status",
                        "db.blocking_sessions", "ops.containers", "ops.route_status", "aip.onboarding.check"])
    parser.add_argument("--observe-target-aic", help="Explicit public metadata target for aip.onboarding.check")
    args = parser.parse_args()
    try:
        observation_arguments(args.observe_tool or ("application.status" if args.observe_application else None),
                              args.observe_target_aic)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(asyncio.run(run(args)))
