"""F12: real committed writes with lost replies, original-key recovery, and missing-key abstention."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.load import OrderObserver


async def resolve_unknown(client, base_url, original_key):
    if not original_key:
        # Payload similarity is not an idempotency key. Do not create a new one.
        return {"status": "unknown", "manual_required": True, "reason": "original_request_key_missing",
                "new_request_created": False}
    response = await client.get(base_url + "/receipts/" + original_key)
    if response.status_code != 200 or response.json().get("outcome") != "committed":
        return {"status": "unknown", "manual_required": True, "reason": "receipt_not_confirmed",
                "new_request_created": False}
    return {"status": "committed", "manual_required": False, "receipt": response.json()}


def wsl_path(path):
    value = str(Path(path).resolve())
    if len(value) < 3 or value[1] != ":":
        return value
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")


async def run(args):
    prefix = ["wsl.exe", "-d", args.wsl, "--exec"] if args.wsl else []
    docker = prefix + ["docker"]
    convert = wsl_path if args.wsl else str
    compose = prefix + ["env", "REPLY_DROP_PORT=" + str(args.proxy_port), "docker"] if args.wsl else ["docker"]
    compose += ["compose", "-p", args.project, "--env-file", convert(args.env_file),
                "-f", convert(ROOT / "deploy/compose.yml"), "--profile", "faults"]
    def command(argv, *, data=None):
        result = subprocess.run(argv, input=data, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "REPLY_DROP_PORT": str(args.proxy_port)}, check=False)
        if result.returncode:
            raise RuntimeError("Docker command failed: " + result.stderr[-800:])
        return result.stdout.strip()
    def count(key):
        # Keys originate from uuid.hex here, never from task-supplied SQL text.
        query = "SELECT count(*), count(DISTINCT id) FROM orders WHERE request_key='" + key + "';"
        return command(docker + ["exec", "-i", args.project + "-postgres-1", "psql", "-U", "postgres", "-d", "orders", "-At", "-c", query])
    output = args.output or ROOT / ("eval/results/local/F12-container-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    if output.exists():
        raise ValueError("Choose a new output path to preserve prior evidence")
    report = {"scenario": "F12", "environment": "actual isolated Docker PostgreSQL/Nginx/FastAPI/reply-suppression proxy",
              "platform_group_tested": False, "passed": False, "checks": []}
    started = False
    def check(name, passed, **evidence):
        report["checks"].append({"name": name, "passed": bool(passed), **evidence})
        if not passed:
            raise AssertionError(name)
    try:
        command(compose + ["up", "-d", "--build", "--no-deps", "reply-drop"])
        started = True
        proxy = "http://127.0.0.1:" + str(args.proxy_port)
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            for attempt in range(30):
                try:
                    response = await client.get(proxy + "/health")
                    response.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 29:
                        raise
                    await asyncio.sleep(0.2)
            for missing in (False, True):
                key = "f12-docker-" + uuid.uuid4().hex
                payload = {"request_key": key, "item": "isolated-unknown-receipt", "quantity": 1}
                try:
                    await client.post(proxy + "/orders", json=payload, timeout=1.5)
                except httpx.ReadTimeout:
                    check("reply is lost after actual backend write", True, key_available_to_resolver=not missing)
                else:
                    check("reply is lost after actual backend write", False)
                check("PostgreSQL contains exactly one committed order", count(key) == "1|1")
                result = await resolve_unknown(client, args.url, None if missing else key)
                if missing:
                    check("missing original key remains unknown and requires manual resolution",
                          result["status"] == "unknown" and result["manual_required"] and not result["new_request_created"], result=result)
                    check("missing-key path creates no replacement order", count(key) == "1|1")
                else:
                    check("original key confirms the existing receipt", result["status"] == "committed", result=result)
                    retry = await client.post(args.url + "/orders", json=payload)
                    retry.raise_for_status()
                    check("original-key retry returns the existing order",
                          retry.json()["order_id"] == result["receipt"]["order_id"], response=retry.json())
                    check("same-key retry still leaves one database order", count(key) == "1|1")
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if started:
            try:
                command(compose + ["stop", "reply-drop"])
                report["proxy_stopped"] = True
            except Exception as exc:
                report["restore_error"] = type(exc).__name__
    if not report.get("error") and report.get("proxy_stopped"):
        healthy = await OrderObserver(args.url, run_id="f12-restored-" + uuid.uuid4().hex).observe(duration=30)
        report["healthy_observation"] = {k: v for k, v in healthy.items() if k not in {"events", "state"}}
        report["passed"] = healthy["passed"] and all(c["passed"] for c in report["checks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenario": "F12", "passed": report["passed"], "output": str(output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project", default="incident-pilot-container")
    parser.add_argument("--url", default="http://127.0.0.1:18088")
    parser.add_argument("--proxy-port", type=int, default=18090)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in args.project):
        raise ValueError("Invalid Compose project name")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
