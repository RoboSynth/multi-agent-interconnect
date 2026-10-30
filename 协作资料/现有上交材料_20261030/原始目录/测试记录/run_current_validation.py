"""Fresh, isolated verification for the submission prepared on 2026-10-29."""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest

import argparse

_parser = argparse.ArgumentParser(description="Reproduce the current offline validation without changing source files")
_parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent / "当前源码")
_parser.add_argument("--output", type=Path, help="New result directory; defaults to a timestamped folder beside this script")
_parser.add_argument("--check", action="store_true", help="Check paths and print configuration without running tests")
_parser.add_argument("--diagnostic-only", action="store_true", help="For run_isolated_takeover.py: supply the missing healthy-channel fixture")
_parser.add_argument("--retry-before-modification", action="store_true", help="For run_isolated_takeover.py: run a fresh before-modification case")
_args = _parser.parse_args()
ROOT = _args.repo.resolve()
OUT = (_args.output.resolve() if _args.output else Path(__file__).resolve().parent / "新运行结果" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
if not (ROOT / "incident/wutong_transport.py").is_file() or not (ROOT / "tests/test_resume_transport.py").is_file():
    raise SystemExit("Source checkout not found: provide --repo <checkout>")
if OUT == ROOT or ROOT in OUT.parents:
    raise SystemExit("Keep output outside the source checkout")
if _args.check:
    print(json.dumps({"repo_found": True, "output_outside_repo": True, "default_layout": "测试记录 beside 当前源码"}, ensure_ascii=False))
    raise SystemExit(0)
OUT.mkdir(parents=True, exist_ok=False)
SDK = ROOT / "vendor/ACPs-community/acps-sdk"
TMP = OUT / "temporary"
TMP.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True
os.environ.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", TMP=str(TMP), TEMP=str(TMP),
                  PYTHONPATH=os.pathsep.join([str(ROOT), str(SDK)]))
tempfile.tempdir = str(TMP)
sys.path[:0] = [str(ROOT / "tests"), str(ROOT), str(SDK)]

GROUPS = {
    "protocol_and_discovery": ["test_wutong_transport", "test_discovery_resilience", "test_participant_selection", "test_task_ordering"],
    "takeover_and_identity": ["test_formal_handover", "test_handover_wire_contract", "test_resume_transport", "test_takeover_error_details", "test_aic_lease"],
    "tool_policy_and_audit": ["test_bridge_gateway", "test_gateway_policy_experiment"],
    "business_receipt_resolution": ["test_receipt_reconciliation", "test_receipt_resolution"],
    "workbench_state_and_evidence": ["test_workbench", "test_workbench_access"],
    "onboarding_and_rotation": ["test_onboarding_text", "test_external_rotation"],
}

def now():
    return datetime.now(timezone.utc).isoformat()

def git(*args):
    if not (ROOT / ".git").exists():
        return "snapshot-without-git"
    return subprocess.check_output(["git", "-C", str(ROOT), "-c", "core.quotepath=false", *args],
                                   encoding="utf-8").strip()

def source_files():
    paths = [ROOT / "workbench_server.py"]
    for subdir in ("incident", "acps_mcp_bridge", "domains", "ops", "business", "vendor/ACPs-community/acps-sdk/acps_sdk"):
        paths.extend(p for p in (ROOT / subdir).rglob("*") if p.suffix in (".py", ".yaml", ".json") and "__pycache__" not in p.parts)
    paths.extend(ROOT / "tests" / (module + ".py") for names in GROUPS.values() for module in names)
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}

class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)
    def record(self, test, status, detail=None):
        self.records.append({"test": test.id(), "status": status, "duration_seconds": round(time.monotonic()-self.started, 4), "detail": detail})
    def addSuccess(self, test):
        self.record(test, "passed")
        super().addSuccess(test)
    def addError(self, test, err):
        self.record(test, "error", self._exc_info_to_string(err, test))
        super().addError(test, err)
    def addFailure(self, test, err):
        self.record(test, "failed", self._exc_info_to_string(err, test))
        super().addFailure(test, err)
    def addSkip(self, test, reason):
        self.record(test, "skipped", reason)
        super().addSkip(test, reason)
    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.record(subtest, "subtest_failed", self._exc_info_to_string(err, test))
        super().addSubTest(test, subtest, err)

def main():
    os.chdir(ROOT)
    source_before = source_files()
    metadata = {"schema": "fresh-submission-validation/1", "started_utc": now(), "python": sys.version,
                "python_executable": sys.executable, "platform": platform.platform(), "head": git("rev-parse", "HEAD"),
                "git_status_before": git("status", "--short"), "groups": GROUPS,
                "scope": "Selected offline tests; includes isolated local stdio subprocess fixtures. Mocked Wutong transport is not live platform proof.",
                "command": f'"{sys.executable}" -X utf8 -B "{Path(__file__).resolve()}"',
                "source_hashes": source_before}
    (OUT / "source-manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    all_records = []
    group_results = {}
    with (OUT / "validation.log").open("w", encoding="utf-8") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        print(json.dumps({key: value for key, value in metadata.items() if key != "source_hashes"}, ensure_ascii=False, indent=2))
        for group, modules in GROUPS.items():
            print("\nGROUP", group, flush=True)
            started = time.monotonic()
            suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
            result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
            records = [{**row, "group": group} for row in result.records]
            all_records.extend(records)
            group_results[group] = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                                    "skipped": len(result.skipped), "passed": result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                                    "duration_seconds": round(time.monotonic()-started, 3)}
            stream.flush()
    source_after = source_files()
    changed = [name for name, digest in source_before.items() if source_after.get(name) != digest]
    summary = {"schema": metadata["schema"], "started_utc": metadata["started_utc"], "finished_utc": now(), "head": metadata["head"],
               "scope": metadata["scope"], "command": metadata["command"], "group_results": group_results,
               "totals": {key: sum(group[key] for group in group_results.values()) for key in ("tests_run", "passed", "failures", "errors", "skipped")},
               "source_changed_during_run": changed, "git_status_after": git("status", "--short"), "test_records": all_records}
    (OUT / "validation-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in ("test_records", "git_status_after")}, ensure_ascii=False, indent=2))
    return int(bool(summary["totals"]["failures"] or summary["totals"]["errors"] or changed))

if __name__ == "__main__":
    raise SystemExit(main())
