"""Run a newly authorized platform batch inside the local AIC lease handoff.

The long-running inspection host holds the seven formal identities. A batch asks
the host to stop when idle, takes the identities, runs every case through
``platform_batch.run_batch`` and hands them back. The host resumes only when
every attempted case confirmed resource restore, H00 and full own-group cleanup;
otherwise the identities stay quarantined for a human check. Like run_batch,
this module has no CLI: callers bind their own frozen plans and authorization.
"""
from __future__ import annotations

from ops.aic_lease import DEFAULT_DIRECTORY, experiment_lease
from eval.platform_batch import run_batch, save
from pathlib import Path

RESUMABLE_STATUSES = {"completed", "finished_with_failures"}


def cleanup_receipt(report):
    """Return the lease cleanup receipt, or None when any case is unconfirmed."""
    cases = report.get("cases", [])
    if (report.get("status") not in RESUMABLE_STATUSES or not cases or report.get("unattempted")
            or report.get("quarantined_cases") or any(row.get("safe_to_continue") is not True for row in cases)):
        return None
    return {"resource_restored": True, "h00_passed": True, "consumers_closed": True,
            "remote_groups_closed": True, "evidence": "platform_batch summary.json",
            "cases": [row["key"] for row in cases]}


async def run_leased_batch(cases, output, *, aics, purpose, run_case, control_directory=None,
                           lease_directory=DEFAULT_DIRECTORY, cleanup_owned=None, quarantine=None,
                           handoff_timeout=180, poll_seconds=.25):
    output = Path(output)
    lease_record = {"aics": sorted(aics), "purpose": purpose,
                    "inspection_handoff": control_directory is not None}
    async with experiment_lease(aics, purpose=purpose, control_directory=control_directory,
                                directory=lease_directory, timeout=handoff_timeout,
                                poll_seconds=poll_seconds) as ownership:
        lease_record["lease_id"] = ownership.lease.owner["lease_id"]
        report = await run_batch(cases, output, run_case=run_case,
                                 cleanup_owned=cleanup_owned, quarantine=quarantine)
        receipt = cleanup_receipt(report)
        if receipt is not None:
            ownership.mark_cleanup_verified(receipt)
        lease_record["identities_returned"] = receipt is not None
        lease_record["after_batch"] = "resume_inspection" if receipt is not None else "quarantine_for_manual_check"
        report["lease"] = lease_record
        save(output / "summary.json", report)
    return report
