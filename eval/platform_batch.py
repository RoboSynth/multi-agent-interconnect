"""Receipt-preserving orchestration for newly authorized platform batches.

This module has no execution CLI. Callbacks must bind their own frozen plan,
authorization and ownership checks; old consumed launchers are never modified.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


CLOSE_CHECKS = {"no_group_sessions", "no_inbound_groups", "inbox_cancelled", "connection_closed",
                "owned_group_disconnected", "no_cleanup_warnings"}
REMOTE_CHECKS = {"ownership_verified", "acl_removed", "queues_removed", "exchange_removed", "consumers_closed"}


def save(path, value):
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def resource_ready(result):
    from eval.platform_resume_experiment import healthy
    return (result.get("resource_and_worker_restore") == "completed"
            and healthy(result.get("independent_final_H00", {}))
            and not any(key in result for key in ("restore_error_class", "H00_error_class",
                "restore_or_H00_error_class", "access_recovery_error_class")))


def close_ready(result):
    checks = result.get("close_checks", {})
    return (set(checks) == CLOSE_CHECKS and all(value is True for value in checks.values())
            and not result.get("cleanup_warning_events") and not result.get("close_error_class"))


async def run_batch(cases, output, *, run_case, cleanup_owned=None, quarantine=None):
    """Always retain the failing receipt; continue only with confirmed cleanup.

    cleanup_owned may make one bounded idempotent attempt on explicitly owned
    resources. A healthy order app alone never proves remote group cleanup.
    quarantine is a local callback that should isolate the affected identities.
    """
    keys = [case["key"] for case in cases]
    if len(set(keys)) != len(keys) or any(not isinstance(key, str) or not key for key in keys):
        raise ValueError("Cases need unique nonempty keys")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "cases": [], "unattempted": list(keys), "quarantined_cases": []}
    save(output / "summary.json", report)
    for case in cases:
        receipt = {"key": case["key"], "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
        result = {}
        fatal = None
        try:
            result = await run_case(case)
            if not isinstance(result, dict):
                raise TypeError("A case callback must return its result receipt")
            receipt.update(result=result, status="completed" if result.get("status") == "completed" else "failed")
        except BaseException as error:
            receipt.update(status="failed", launcher_error_class=type(error).__name__)
            if not isinstance(result, dict):
                result = {}
            if not isinstance(error, Exception):
                fatal = error
        finally:
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            report["cases"].append(receipt)
            report["unattempted"].remove(case["key"])
            # Persist before cleanup, continuation checks, or an interrupt can throw.
            save(output / "summary.json", report)
        ready = bool(result) and resource_ready(result) and close_ready(result)
        if not ready and result and resource_ready(result) and cleanup_owned is not None and fatal is None:
            try:
                cleanup = await cleanup_owned(case, result)
                receipt["cleanup_retry"] = cleanup
                ready = (isinstance(cleanup, dict) and set(cleanup) >= REMOTE_CHECKS
                         and all(cleanup[key] is True for key in REMOTE_CHECKS))
            except Exception as error:
                receipt["cleanup_retry_error_class"] = type(error).__name__
        receipt["safe_to_continue"] = ready
        if not ready:
            report["quarantined_cases"].append(case["key"])
            report["status"] = "blocked_cleanup_or_restore"
            save(output / "summary.json", report)
            if quarantine is not None:
                try:
                    quarantine(case, receipt)
                except Exception as error:
                    receipt["quarantine_error_class"] = type(error).__name__
            save(output / "summary.json", report)
            if fatal is not None:
                raise fatal
            break
        save(output / "summary.json", report)
    else:
        report["status"] = "completed" if all(row["status"] == "completed" for row in report["cases"]) else "finished_with_failures"
        save(output / "summary.json", report)
    return report
