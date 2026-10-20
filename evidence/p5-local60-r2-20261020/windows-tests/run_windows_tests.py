from __future__ import annotations
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
import unittest

output = Path(__file__).resolve().parent
repo = output.parents[2]
os.chdir(repo)
sys.path.insert(0, str(repo))
scope = sys.argv[1]
patterns = [
    "test_p5_incident_scheduling.py", "test_carried_symptom_intents.py",
    "test_coordinator.py", "test_planner_conflicts.py", "test_model_eval.py",
] if scope == "affected" else (["test_evaluation_report_integrity.py", "test_stability_bundle.py", "test_evaluation_reports.py"] if scope == "report-revision" else ["test*.py"])
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
start = time.monotonic()
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for pattern in patterns:
    suite.addTests(loader.discover(str(repo / "tests"), pattern=pattern))
with (output / f"{scope}.log").open("w", encoding="utf-8", newline="\n") as log:
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
metadata = {
    "scope": scope, "started_at_utc": started,
    "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "elapsed_seconds": time.monotonic() - start,
    "command": [sys.executable, str(Path(__file__).resolve()), scope],
    "working_directory": str(repo), "python": sys.version,
    "platform": platform.platform(), "patterns": patterns,
    "tests_run": result.testsRun, "failures": len(result.failures),
    "errors": len(result.errors), "skipped": len(result.skipped),
    "expected_failures": len(result.expectedFailures),
    "unexpected_successes": len(result.unexpectedSuccesses),
    "failure_cases": [{"test": str(case), "traceback": tb} for case, tb in result.failures],
    "error_cases": [{"test": str(case), "traceback": tb} for case, tb in result.errors],
    "skipped_cases": [{"test": str(case), "reason": reason} for case, reason in result.skipped],
    "successful": result.wasSuccessful(), "exit_code": 0 if result.wasSuccessful() else 1,
}
(output / f"{scope}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: metadata[key] for key in ("scope", "tests_run", "failures", "errors", "skipped", "successful", "exit_code", "elapsed_seconds")}, ensure_ascii=False))
raise SystemExit(metadata["exit_code"])