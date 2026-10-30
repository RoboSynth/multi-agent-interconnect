"""Actual local PostgreSQL/Nginx fault acceptance; never substitutes test doubles."""
import argparse
import asyncio
import importlib.util
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from business.load import OrderObserver

spec = importlib.util.spec_from_file_location("business_fault_injector", ROOT / "eval/inject.py")
inject_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inject_module)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="+", default=["F01", "F02", "F06", "F07", "F10", "F12"])
    parser.add_argument("--observation-seconds", type=float, default=30)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parser.add_argument("--output", type=Path, default=ROOT / f"eval/results/local/business-native-acceptance-{stamp}.json")
    args = parser.parse_args()
    injector = inject_module.Injector(backend="native")
    base = f"http://127.0.0.1:{injector.runtime['order_port']}"
    results = {"environment": "actual local Windows PostgreSQL16 + Nginx + FastAPI", "started_at": datetime.now(timezone.utc).isoformat(),
               "scenarios": [], "unsupported": inject_module.UNSUPPORTED}
    async with httpx.AsyncClient(timeout=7, trust_env=False, headers={"Connection": "close"}) as client:
        async def create(key):
            return await client.post(base + "/orders", json={"request_key": key, "item": "native-acceptance", "quantity": 1})

        for scenario in args.scenarios:
            prefix = "accept-" + uuid.uuid4().hex
            seed = await create(prefix + "-seed")
            seed.raise_for_status()
            seed_id = seed.json()["order_id"]
            row = {"scenario": scenario, "checks": [], "started_at": datetime.now(timezone.utc).isoformat()}
            started = time.monotonic()
            def check(name, passed, **evidence):
                row["checks"].append({"name": name, "passed": bool(passed), **evidence})
                if not passed:
                    raise AssertionError(name)
            try:
                await asyncio.to_thread(injector.apply, scenario)
                key = prefix + "-write"
                if scenario == "F01":
                    response = await create(key)
                    check("stopped app produces actual gateway 502", response.status_code == 502, http_status=response.status_code)
                elif scenario == "F02":
                    response = await create(key)
                    check("v1 route misses v2 response field", response.status_code == 200 and "order_api_version" not in response.json(),
                          http_status=response.status_code, response=response.json())
                elif scenario in {"F06", "F07", "F10"}:
                    response = await client.get(base + "/orders/" + seed_id)
                    check("reads remain available", response.status_code == 200, http_status=response.status_code)
                    response = await create(key)
                    check("actual database write rejects or times out", response.status_code == 503, http_status=response.status_code, response=response.json())
                    if scenario == "F06":
                        check("lock wait uses PostgreSQL cancellation code", response.json().get("code") in {"57014", "TimeoutError"}, code=response.json().get("code"))
                    else:
                        check("PostgreSQL reports real read-only SQLSTATE", response.json().get("code") == "25006", code=response.json().get("code"))
                    if scenario == "F10":
                        await asyncio.to_thread(injector.route, "v2")
                        response = await create(key)
                        check("route repair alone leaves read-only write failure", response.status_code == 503 and response.json().get("code") == "25006",
                              http_status=response.status_code)
                elif scenario == "F12":
                    try:
                        await client.post(base + "/orders", json={"request_key": key, "item": "native-acceptance", "quantity": 1}, timeout=1.5)
                    except httpx.ReadTimeout:
                        check("client times out after backend commit", True)
                    else:
                        check("client times out after backend commit", False)
                    receipt = await client.get(base + "/receipts/" + key)
                    check("original receipt resolves unknown result", receipt.status_code == 200 and receipt.json().get("outcome") == "committed",
                          http_status=receipt.status_code, response=receipt.json())
                    row["original_order_id"] = receipt.json()["order_id"]
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                try:
                    await asyncio.to_thread(injector.restore, scenario)
                    row["restored"] = True
                except Exception as exc:
                    row.update(restored=False, restoration_error=f"{type(exc).__name__}: {exc}")
            if row.get("restored"):
                try:
                    if scenario == "F12" and "original_order_id" in row:
                        retry = await create(prefix + "-write")
                        check("same-key retry returns the committed order", retry.status_code == 200 and retry.json()["order_id"] == row["original_order_id"],
                              http_status=retry.status_code, response=retry.json())
                    observer = OrderObserver(base, run_id=prefix)
                    observation = await observer.observe(duration=args.observation_seconds)
                    row["healthy_observation"] = {k: v for k, v in observation.items() if k not in {"events", "state"}}
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
            row["duration_seconds"] = round(time.monotonic() - started, 3)
            row["passed"] = (not row.get("error") and row.get("restored") and all(c["passed"] for c in row["checks"])
                             and row.get("healthy_observation", {}).get("passed", False))
            results["scenarios"].append(row)
            results["passed"] = all(s["passed"] for s in results["scenarios"])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"scenario": scenario, "passed": row["passed"], "restored": row.get("restored"),
                              "error": row.get("error"), "healthy_observation": row.get("healthy_observation")}), flush=True)
            if not row.get("restored"):
                break
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
