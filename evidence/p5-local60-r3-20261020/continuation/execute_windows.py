"""Own the local batch lifecycle; never start a Wutong consumer.

Run through launch_windows.py so an interrupted tool console cannot kill the
evaluator. Helpers are the previous batch's reviewed lifecycle scripts, copied
to the new artifact directory with their provenance, never executed in place.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
ARTIFACTS = ROOT.parent / "incident-pilot/artifacts/p5-local60-r3-20261020/continuation"
PWSH = Path("C:/Users/16080/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def command(name, args, *, timeout=None):
    with (ARTIFACTS / (name + ".txt")).open("xb") as stream:
        result = subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    save(ARTIFACTS / (name + "-command.json"), {"command": args, "exit_code": result.returncode,
        "finished_at": datetime.now(timezone.utc).isoformat()})
    return result.returncode


def prepare():
    for port in (55432, 8081, 8082, 8088, 8089, 8093):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Local batch port already occupied: {port}")
    for name in ("start_model.py", "preflight.py", "cleanup_local.py", "helper-provenance.json"):
        shutil.copyfile(EVIDENCE / "lifecycle" / name, ARTIFACTS / name)
    files = ["runtime/local-coordinator.json", "runtime/database-bridge.json",
             "runtime/database-backup-bridge.json", "runtime/ops-bridge.json"]
    for name in files:
        source = ROOT / name
        backup = ARTIFACTS / "private/config-before" / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open("xb") as stream:
            stream.write(source.read_bytes())
        config = json.loads(source.read_text(encoding="utf-8-sig"))
        if name.endswith("local-coordinator.json"):
            if (config.get("mode") != "local-aip-stdio" or config.get("automatic_takeover") is not False
                or not config["coordinator_aic"].startswith("local-")
                or any(not row["aic"].startswith("local-") for row in config["workers"])):
                raise RuntimeError("Batch configuration must contain only isolated local identities")
            config["term_journal_path"] = str(ARTIFACTS / "private/coordinator-terms.sqlite")
        else:
            label = Path(name).stem
            config["audit_path"] = str(ARTIFACTS / f"private/{label}-audit.jsonl")
            config["ledger_path"] = str(ARTIFACTS / f"private/{label}-operations.sqlite")
        save(source, config)
    save(ARTIFACTS / "scope.json", {"requested_cells": 16, "full_matrix_cells": 60, "methods": ["MR", "M0", "M1", "M2v2"],
        "scenarios": ["F01", "F02", "F06", "F07", "F10"], "repeats": 3,
        "transport": "local-aip-stdio", "backend": "native", "platform_calls": 0, "paid_apis": 0,
        "instruction": "User authorized fixing the missing verification field, passing tests, executing all 60 cells, preserving original results and uploading to GitHub; preserve failed cells without changing algorithms during the run",
        "cleanup": "final 30-second health window and stop exactly registered batch processes"})


def main():
    os.environ["PYTHONUTF8"] = "1"
    os.environ["INCIDENT_LLM_API_KEY"] = ""
    result = {"status": "PREPARING", "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}
    started_resources = False
    try:
        prepare()
        started_resources = True
        # Match local-up.ps1: reuse/provision the registered cluster before
        # native.ps1 starts applications. Existing matching secrets are kept.
        if command("database-prepare", [sys.executable, str(ROOT / "tools/prepare_native_database.py")], timeout=150):
            raise RuntimeError("Native database preparation failed")
        if command("native-start", [str(PWSH), "-NoProfile", "-File", str(ROOT / "deploy/native.ps1"),
                "-Action", "start", "-RuntimeFile", str(ROOT / "deploy/native-runtime.json")], timeout=150):
            raise RuntimeError("Native business startup failed")
        if command("restore-interrupted", [sys.executable, str(ROOT / "eval/inject.py"), "F07", "restore", "--backend", "native", "--runtime", str(ROOT / "deploy/native-runtime.json"), "--record", str(ARTIFACTS / "private/restoration.jsonl")], timeout=90):
            raise RuntimeError("Interrupted F07 restoration failed")
        for stage, helper in (("model-start", "start_model.py"), ("preflight", "preflight.py")):
            if command(stage, [sys.executable, str(ARTIFACTS / helper)], timeout=150):
                raise RuntimeError(stage + " failed")
        save(ARTIFACTS / "controller-status.json", {**result, "status": "MATRIX_RUNNING"})
        # The evaluator's nonzero exit is a preserved experimental result, not
        # permission to rewrite an algorithm or to discard unsuccessful cells.
        code = command("evaluator-output", [sys.executable, str(EVIDENCE / "run.py")])
        result.update(status="EVALUATOR_RETURNED", evaluator_exit_code=code)
    except BaseException as error:
        traceback.print_exc()
        result.update(status="CONTROLLER_FAILED", error_class=type(error).__name__, error=str(error))
    finally:
        if started_resources:
            try:
                result["cleanup_exit_code"] = command("cleanup-output", [sys.executable,
                    str(ARTIFACTS / "cleanup_local.py")], timeout=420)
            except BaseException as error:
                traceback.print_exc()
                result["cleanup_error"] = {"error_class": type(error).__name__, "error": str(error)}
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(ARTIFACTS / "controller-result.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["status"] == "EVALUATOR_RETURNED" and result.get("cleanup_exit_code") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
