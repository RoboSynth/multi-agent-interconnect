"""Third local60 batch: the same 5 scenarios x 4 methods x 3 repeats, new code.

Same arguments, seeds, model and budgets as evidence/p5-local60-20261020; the definitions are identical to r2; only
the inapplicable carried-intent fact serialization is fixed (see eval/run.py manifest).
Local identities and native resources only; no Wutong identity or paid API.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import subprocess
import traceback

ROOT = Path(__file__).resolve().parents[2]
BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from eval.run import build_parser, freeze_sources, run


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def main():
    os.environ["INCIDENT_LLM_API_KEY"] = ""
    config_path = ROOT / "runtime/local-coordinator.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if config.get("mode") != "local-aip-stdio" or not config["coordinator_aic"].startswith("local-"):
        raise RuntimeError("This batch must use local identities only")
    if any(not row["aic"].startswith("local-") for row in config["workers"]):
        raise RuntimeError("Cloud identity in local batch configuration")
    if config.get("automatic_takeover") is not False:
        raise RuntimeError("Set automatic_takeover=false in runtime/local-coordinator.json first")
    output = BATCH / "matrix"
    if output.exists():
        raise RuntimeError("Output exists; never overwrite a previous attempt")
    args = build_parser().parse_args([
        "--config", str(config_path), "--runtime", str(ROOT / "deploy/native-runtime.json"),
        "--transport", "local-aip-stdio", "--backend", "native", "--scenarios", "F01,F02,F06,F07,F10",
        "--methods", "MR,M0,M1,M2v2", "--repeats", "3", "--approve-high", "--enable-llm",
        "--model-base-url", "http://127.0.0.1:8089/v1", "--model", "Qwen3-1.7B-Q8_0", "--seed", "42",
        "--max-output-tokens", "768", "--model-call-budget", "40", "--model-token-budget", "65536",
        "--task-budget", "40", "--deadline-seconds", "600", "--instance-seeds", "101,202,303",
        "--order-url", "http://127.0.0.1:8088", "--output", str(output)])
    started = datetime.now(timezone.utc).isoformat()
    save(BATCH / "execution-intent.json", {"started_at": started, "requested_cells": 60,
        "code_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": freeze_sources(BATCH / "binding"), "same_arguments_as": "evidence/p5-local60-20261020",
        "transport": "local-aip-stdio", "platform_calls": 0, "paid_apis": 0, "arguments": vars(args)})
    try:
        code = asyncio.run(run(args))
        result = {"status": "EVALUATOR_FINISHED", "exit_code": code}
    except BaseException as error:
        traceback.print_exc()
        code, result = 1, {"status": "EVALUATOR_FAILED", "error_class": type(error).__name__, "error": str(error),
                           "exit_code": 1}
    result.update(started_at=started, finished_at=datetime.now(timezone.utc).isoformat())
    save(BATCH / "execution-result.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
