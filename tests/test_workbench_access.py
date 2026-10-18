"""Captured-log/UI API behavior using local fixture bytes; no real transport."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.reconcile_access import reconcile
from incident.workbench_access import reconcile_incident_access
from fastapi.testclient import TestClient
from workbench_server import create_app


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")


def captures(incident_id, count, *, session="shared-formal-session", prefix="task"):
    messages, access = [], []
    for index in range(count):
        task = prefix+str(index)
        peer = "worker-"+str(index % 2)
        start = dict(type="task-command", command="start", senderId="coordinator", sessionId=session,
            taskId=task, dataItems=[dict(type="text", text=json.dumps(dict(incident_id=incident_id)))])
        messages.append(dict(direction="send", worker_aic=peer, message=start))
        for state in ["accepted", "working", "awaiting-completion", "completed"]:
            messages.append(dict(direction="receive", worker_aic=peer, message=dict(type="task-result",
                senderId=peer, sessionId=session, taskId=task, status=dict(state=state))))
        access.extend(dict(aic=actor,trace_id=session,correlation_id=task) for actor in ["coordinator",peer])
    return messages, access


class WorkbenchAccessTests(unittest.TestCase):
    def fixture(self, directory, messages, access):
        base = Path(directory)/"transport"
        message_path, amp = base/"messages.jsonl", base/"amp"
        write_rows(message_path,messages)
        write_rows(amp/"amp_access_fixture.jsonl",access)
        return SimpleNamespace(mode="wutong-amqps",output=base,config={},close=AsyncMock()), message_path, amp

    def test_twelve_starts_and_twenty_four_access_match_existing_reconciler(self):
        messages, access = captures("inc-one",12)
        with tempfile.TemporaryDirectory() as directory:
            transport,path,amp = self.fixture(directory,messages,access)
            original = reconcile(path,amp,transport="wutong-amqps")
            run = dict(id="inc-one",tasks=[{"logical_task_id":"phantom"}]*20)
            before = deepcopy(run)
            summary = reconcile_incident_access(run,transport,directory)
            self.assertEqual(summary["status"],"complete")
            for key in ["captured_start_tasks","expected_access_records","actual_access_records","missing_records","extra_records"]:
                self.assertEqual(summary[key],original[key])
            self.assertEqual((summary["captured_start_tasks"],summary["actual_access_records"]),(12,24))
            self.assertEqual(run,before)
            self.assertNotIn(directory,json.dumps(summary))
            self.assertNotIn("worker-",json.dumps(summary))

    def test_coordinator_only_capture_is_missing_the_peer_endpoint(self):
        messages, access = captures("inc-one",12)
        with tempfile.TemporaryDirectory() as directory:
            transport,_,_ = self.fixture(directory,messages,[row for row in access if row["aic"]=="coordinator"])
            summary = reconcile_incident_access(dict(id="inc-one"),transport,directory)
            self.assertEqual((summary["status"],summary["expected_access_records"],summary["actual_access_records"],summary["missing_records"]),("incomplete",24,12,12))
            self.assertFalse(summary["passed"])

    def test_bad_json_and_malformed_fields_do_not_disappear_or_leak(self):
        messages, access = captures("inc-one",12)
        access.append(dict(aic="worker",trace_id=[],correlation_id={}))
        with tempfile.TemporaryDirectory() as directory:
            transport,_,amp = self.fixture(directory,messages,access)
            with (amp/"amp_access_fixture.jsonl").open("a",encoding="utf-8") as stream:
                stream.write('bad private fixture line\n')
            summary = reconcile_incident_access(dict(id="inc-one"),transport,directory)
            self.assertEqual(summary["status"],"invalid")
            self.assertEqual(summary["invalid_records"]["access"],2)
            self.assertEqual(summary["actual_access_records"],24)
            self.assertNotIn("private fixture",json.dumps(summary))

    def test_malformed_start_data_items_do_not_fail_the_whole_api(self):
        for value in [5,0,False,{},"bad",[5],[{},"bad"]]:
            with self.subTest(data_items=value), tempfile.TemporaryDirectory() as directory:
                messages, access = captures("inc-one",12)
                malformed, _ = captures("inc-one",1,session="inc-one",prefix="malformed")
                malformed[0]["message"]["dataItems"] = value
                transport,_,_ = self.fixture(directory,messages+[malformed[0]],access)
                app = create_app(Path(directory)/"absent.json",Path(directory)/"workbench",transport)
                with TestClient(app,raise_server_exceptions=False) as client:
                    app.state.engine.runs = {"inc-one":dict(id="inc-one",symptom="fixture",status="completed")}
                    for endpoint in ["/api/state","/api/incidents/inc-one"]:
                        response = client.get(endpoint)
                        self.assertEqual(response.status_code,200)
                        run = response.json()["incident"] if endpoint=="/api/state" else response.json()
                        summary = run["access_reconciliation"]
                        self.assertEqual(summary["status"],"invalid")
                        self.assertEqual(summary["invalid_records"]["messages"],1)
                        self.assertEqual((summary["captured_start_tasks"],summary["actual_access_records"]),(12,24))
                        self.assertFalse(summary["passed"])
        for mode in ["missing",None,[]]:
            with self.subTest(native_data_items=mode), tempfile.TemporaryDirectory() as directory:
                messages, access = captures("inc-native",1,session="inc-native")
                if mode=="missing":
                    del messages[0]["message"]["dataItems"]
                else:
                    messages[0]["message"]["dataItems"] = mode
                transport,_,_ = self.fixture(directory,messages,access)
                summary = reconcile_incident_access(dict(id="inc-native"),transport,directory)
                self.assertEqual((summary["status"],summary["actual_access_records"]),("complete",2))
                self.assertEqual(summary["invalid_records"]["messages"],0)

    def test_absent_capture_is_unknown_rather_than_zero_verified_access(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = reconcile_incident_access(dict(id="inc-missing"),None,directory)
            self.assertEqual(summary["status"],"not_collected")
            self.assertIsNone(summary["actual_access_records"])
            self.assertIsNone(summary["expected_access_records"])
            self.assertIsNone(summary["passed"])

    def test_session_collision_and_other_incident_are_excluded(self):
        messages, access = captures("inc-one",12)
        other_messages, other_access = captures("inc-other",1,prefix="other")
        access.append(dict(aic="coordinator",trace_id="other-session",correlation_id="task0"))
        with tempfile.TemporaryDirectory() as directory:
            transport,_,_ = self.fixture(directory,messages+other_messages,access+other_access)
            summary = reconcile_incident_access(dict(id="inc-one"),transport,directory)
            self.assertEqual(summary["status"],"complete")
            self.assertEqual(summary["actual_access_records"],24)
            self.assertEqual(summary["unrelated_access_records_excluded"],3)

    def test_duplicate_access_and_missing_lifecycle_are_reported(self):
        messages, access = captures("inc-one",12)
        messages.pop()
        access.append(access[0])
        with tempfile.TemporaryDirectory() as directory:
            transport,_,_ = self.fixture(directory,messages,access)
            summary = reconcile_incident_access(dict(id="inc-one"),transport,directory)
            self.assertEqual((summary["status"],summary["extra_records"],summary["incomplete_task_lifecycles"]),("incomplete",1,1))

    def test_unterminated_valid_tail_is_counted_but_never_complete(self):
        messages, access = captures("inc-one",12)
        with tempfile.TemporaryDirectory() as directory:
            transport,_,amp = self.fixture(directory,messages,access)
            path = amp/"amp_access_fixture.jsonl"
            path.write_bytes(path.read_bytes().rstrip(b"\n"))
            summary = reconcile_incident_access(dict(id="inc-one"),transport,directory)
            self.assertEqual(summary["status"],"incomplete")
            self.assertEqual(summary["actual_access_records"],24)
            self.assertEqual(summary["partial_records"]["access"],1)

    def test_api_history_uses_selected_run_and_never_changes_saved_runs(self):
        messages, access = captures("inc-old",12)
        other_messages, other_access = captures("inc-latest",1,prefix="latest")
        with tempfile.TemporaryDirectory() as directory:
            transport,_,_ = self.fixture(directory,messages+other_messages,access+other_access)
            app = create_app(Path(directory)/"absent.json",Path(directory)/"workbench",transport)
            with TestClient(app) as client:
                app.state.engine.runs = {key:dict(id=key,symptom=key,status="completed") for key in ["inc-old","inc-latest"]}
                before = deepcopy(app.state.engine.runs)
                latest = client.get("/api/state").json()["incident"]
                history = client.get("/api/incidents/inc-old").json()
                self.assertEqual((latest["access_reconciliation"]["captured_start_tasks"],history["access_reconciliation"]["captured_start_tasks"]),(1,12))
                self.assertEqual(history["id"],"inc-old")
                self.assertEqual(app.state.engine.runs,before)
                self.assertEqual(client.get("/api/incidents/unknown").status_code,404)


if __name__ == "__main__":
    unittest.main()
