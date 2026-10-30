"""Verify the public v2 order contract for 30 seconds after deployment."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.load import OrderObserver
from deploy.prepare_deployment import load_deployment
from eval.targets import DockerTarget


def order_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTP(S) order origin without credentials, path or query")
    # Accessing port also rejects malformed and out-of-range port values.
    parsed.port
    return value.rstrip("/")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def healthy_window(observed):
    return (observed["passed"] is True and observed["duration_seconds"] >= 30
            and observed["requests"] == 30 and observed["success"] == 30
            and observed["completed_workflows"] == 10 and observed["failed"] == 0
            and observed["unknown"] == 0 and observed["unresolved_intents"] == 0
            and observed["state"]["pending"] == [])


async def verify(url, output, *, client=None, run_id=None):
    """Write one new run; retain failures and original intent keys on disk."""
    url = order_origin(url)
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    result = {"schema_version": "deployment-h00/1", "status": "running", "order_url": url,
              "started_at": datetime.now(timezone.utc).isoformat(), "expected_api_version": "v2",
              "duration_seconds_requested": 30, "requests_per_second": 1, "seed": 17,
              "run_id": run_id or ("deploy-" + uuid.uuid4().hex),
              "scope": "Public business H00; does not verify AIP, takeover, cold start or platform ingestion"}
    save(output / "result.json", result)
    owned = client is None
    client = client or httpx.AsyncClient(timeout=4, trust_env=False)
    readiness = []
    observer = None

    async def ready(phase):
        entry = {"phase": phase}
        readiness.append(entry)
        try:
            response = await client.get(url + "/ready")
            entry["status_code"] = response.status_code
            body = response.json()
            if isinstance(body, dict):
                entry.update(ok=body.get("ok") is True, api_version=body.get("api_version"))
            if not (response.status_code == 200 and entry.get("ok") is True
                    and entry.get("api_version") == "v2"):
                raise ValueError("public_ready_is_not_healthy_v2")
        except Exception as error:
            entry["error_class"] = type(error).__name__
            raise
        finally:
            save(output / "readiness.json", readiness)

    try:
        await ready("before")
        observer = OrderObserver(url, seed=17, run_id=result["run_id"], client=client,
                                 expected_api_version="v2")
        observed = await observer.observe(duration=30, requests_per_second=1, min_complete=10)
        save(output / "h00.json", observed)
        result["business"] = {key: value for key, value in observed.items() if key not in {"events", "state"}}
        await ready("after")
        result["status"] = "passed" if healthy_window(observed) else "failed"
    except Exception as error:
        result.update(status="failed", error_class=type(error).__name__)
    finally:
        if observer is not None:
            save(output / "state.json", observer.state)
        if owned:
            await client.aclose()
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        save(output / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="Explicit public order origin, for example http://127.0.0.1:48088")
    target.add_argument("--target-config", type=Path, help="Use the exact order port from a prepared Docker target")
    target.add_argument("--deployment-file", type=Path, help="Use the same prepared manifest as deploy/up.ps1 or up.sh")
    parser.add_argument("--output", required=True, type=Path, help="New evidence directory; existing paths are refused")
    args = parser.parse_args()
    try:
        if args.deployment_file:
            manifest = load_deployment(args.deployment_file)
            url = "http://127.0.0.1:" + str(manifest["ports"]["order"])
        else:
            url = args.url if args.url else DockerTarget.from_file(args.target_config).order_url
        result = asyncio.run(verify(url, args.output))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
