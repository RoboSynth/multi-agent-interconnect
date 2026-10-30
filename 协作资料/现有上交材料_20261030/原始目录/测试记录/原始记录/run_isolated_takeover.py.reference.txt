"""Persist new local subprocess evidence without changing the project checkout."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

from run_current_validation import ROOT, OUT, RecordedResult
from test_resume_transport import LocalTakeoverTests, modification_events
from incident.local_transport import LocalAipStdioTransport

CASES = OUT / "local-process-cases"
CASES.mkdir(exist_ok=True)

async def one_case(point, label=None):
    directory = CASES / (label or point)
    directory.mkdir()
    configuration = LocalTakeoverTests().configuration(directory, point)
    transport = LocalAipStdioTransport(configuration, directory / "transport")
    result = {"crash_point": point, "started_utc": datetime.now(timezone.utc).isoformat(),
              "evidence_level": "real local AIP stdio and MCP subprocesses; isolated JSON file resource, not PostgreSQL or Wutong",
              "checks": {}}
    started = time.monotonic()
    try:
        await transport.start()
        observation = {"incident_id": "fresh-local-" + point, "logical_task_id": "logical-observation",
                       "kind": "observe", "tool": "db.read_only_status", "args": {}, "budget": {"deadline_ms": 15000}}
        observed = await transport.call(observation)
        result["checks"]["observation_succeeded"] = observed["status"] == "ok"
        action = {"incident_id": observation["incident_id"], "logical_task_id": "logical-action", "kind": "act",
                  "tool": "db.restore_writes", "args": {}, "operation_id": observation["incident_id"] + ":repair",
                  "fence": {"coordinator_term": transport.term, "takeover_version": 0}, "budget": {"deadline_ms": 15000}}
        action["approval"] = transport.issue_approval(action)
        response = await transport.call(action)
        actual = json.loads((directory / "resource.json").read_text(encoding="utf-8"))
        invocations = modification_events(transport.amp_directory)
        takeovers = [event for event in transport.events if event["event"] == "takeover_completed"]
        result["checks"].update(action_succeeded=response["status"] == "ok",
                                resource_changed_once=actual == {"read_only": False, "modifying_calls": 1},
                                modification_event_once=len(invocations) == 1,
                                takeover_completed_once=len(takeovers) == 1,
                                correct_backup=len(takeovers) == 1 and takeovers[0]["replacement_aic"] == "test-database-backup")
        replay = await transport.call_on_worker("test-database-backup", action)
        result["checks"].update(stale_fence_rejected=replay["status"] == "rejected" and replay["operation"]["state"] == "rejected_stale_fence",
                                replay_did_not_modify_again=len(modification_events(transport.amp_directory)) == 1,
                                no_in_flight_tasks=transport.journal.list_tasks(in_flight_only=True) == [])
        result.update(response=response, stale_replay_response=replay, resource_after=actual, takeovers=takeovers,
                      modifying_event_count=len(invocations), transport_event_count=len(transport.events))
        if point == "after_applied":
            result["checks"]["applied_operation_not_reexecuted"] = response["operation"]["state"] == "skipped_already_applied"
    except Exception as error:
        result["error"] = {"class": type(error).__name__, "message": str(error)}
    finally:
        await transport.close()
    result.update(passed=bool(result["checks"]) and all(result["checks"].values()) and "error" not in result,
                  duration_seconds=round(time.monotonic()-started, 3), finished_utc=datetime.now(timezone.utc).isoformat())
    (directory / "case-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

def diagnostic():
    import test_handover_wire_contract as module
    original_namespace = module.SimpleNamespace
    def namespace_with_connected_session(**kwargs):
        value = original_namespace(**kwargs)
        if "session_id" in kwargs and "message_history" in kwargs:
            value.leader_mq_client = original_namespace(_channel=original_namespace(is_closed=False), _exchange=object())
        return value
    with (OUT / "fixture-diagnostic.log").open("w", encoding="utf-8") as stream:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.ResumeControlParsingTests)
        with patch.object(module, "SimpleNamespace", namespace_with_connected_session):
            result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    data = {"started_from": "three errors in unmodified test_handover_wire_contract.ResumeControlParsingTests",
            "change": "Supplementary harness supplies a healthy leader_mq_client in the test session fixture; production code and repository tests are unchanged.",
            "count": result.testsRun, "passed": result.testsRun-len(result.failures)-len(result.errors), "errors": len(result.errors),
            "failures": len(result.failures), "records": result.records}
    (OUT / "fixture-diagnostic.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

async def main():
    os.chdir(ROOT)
    with (OUT / "local-process-cases.log").open("w", encoding="utf-8") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        records = [await one_case(point) for point in ("after_observation", "before_modification", "after_applied")]
    cases = {"count": len(records), "passed": sum(row["passed"] for row in records), "cases": records}
    (OUT / "local-process-results.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    return cases

if __name__ == "__main__":
    if "--diagnostic-only" in sys.argv:
        print(json.dumps(diagnostic(), ensure_ascii=False, indent=2))
    elif "--retry-before-modification" in sys.argv:
        print(json.dumps(asyncio.run(one_case("before_modification", "before_modification_retry1")), ensure_ascii=False, indent=2))
    else:
        cases = asyncio.run(main())
        fixture = diagnostic()
        print(json.dumps({"local_process_cases": {"count": cases["count"], "passed": cases["passed"]},
                          "fixture_diagnostic": {k: fixture[k] for k in ("count", "passed", "errors", "failures")}}, ensure_ascii=False, indent=2))
