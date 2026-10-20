"""Offline fixtures only: no Docker, platform call, credential or identity read."""
from __future__ import annotations

import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
CANONICAL = HERE.parents[1]
spec = importlib.util.spec_from_file_location("cloud_collector_under_test", HERE / "deployment-20261020" / "cloud_collector.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.metadata = {}
        self.volumes = {}
        for number, role in enumerate(subject.ROLES[1:], 1):
            identifier = f"domain-{number}"
            state_key = subject.STATE_KEY[role]
            volume = subject.PROJECT + "_" + state_key
            self.metadata[identifier] = {"Id": identifier, "Name": "/fixture-" + role,
                "Config": {"Labels": {"com.docker.compose.project": subject.PROJECT, "com.docker.compose.service": role + "-agent"}},
                "State": {"Running": True, "StartedAt": "2026-10-19T01:00:00Z"}, "RestartCount": 0,
                "Mounts": [{"Type": "volume", "Name": volume, "Destination": "/state"}]}
            self.volumes[volume] = {"Name": volume, "Labels": {"com.docker.compose.project": subject.PROJECT, "com.docker.compose.volume": state_key}}

    def __call__(self, *args):
        self.calls.append(args)
        if args[:3] == ("volume", "ls", "--format"):
            return "\n".join(self.volumes)
        if args[:2] == ("volume", "inspect"):
            return json.dumps([self.volumes[args[2]]])
        if args[0] == "inspect":
            key = args[1]
            row = self.metadata.get(key) or next((row for row in self.metadata.values() if row["Name"] == "/" + key), None)
            if row is None:
                raise RuntimeError("Unknown fake Docker object")
            return json.dumps([row])
        if args[:2] == ("ps", "-aq"):
            service = next((part.split("=", 2)[2] for part in args if part.startswith("label=com.docker.compose.service=")), None)
            return "\n".join(key for key, row in self.metadata.items() if service and row["Config"]["Labels"].get("com.docker.compose.service") == service)
        if args[0] == "exec":
            if args[4] == subject.READ_LOGS:
                return json.dumps([{"kind": "heartbeat", "name": "amp_heartbeat_fixture.jsonl", "data": base64.b64encode(b'{"kind":"heartbeat","aic":"fixture"}\n').decode()}])
            return ""
        if args[0] == "image":
            return "[]"
        if args[0] == "stop":
            row = self.metadata[args[-1]]
            row["State"].update(Running=False, Status="exited", ExitCode=0, OOMKilled=False, Error="")
            return row["Id"]
        if args[0] == "start":
            self.metadata[args[1]]["State"].update(Running=True, Status="running", ExitCode=0)
            return args[1]
        raise AssertionError("Unexpected fake command: " + repr(args))


class CollectorChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cloud-collector-fixture-")
        self.root = Path(self.temp.name)
        for relative in ("deploy/fluent-bit/prepare_linux_collector.py", "deploy/fluent-bit/render.py",
                         "deploy/fluent-bit/parsers.conf", "deploy/fluent-bit/kafka-settings.wutong-public.example.json",
                         "eval/secret_scan.py", "tools/check_alive.py"):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CANONICAL / relative, destination)
        (self.root / subject.AMP).mkdir(parents=True)
        deployment = self.root / subject.DEPLOYMENT
        deployment.parent.mkdir(parents=True)
        subject.save(deployment, {"project": subject.PROJECT, "mode": "seven", "wsl_distro": None})
        (deployment.parent / "compose.env").write_text("APP_ADMIN_TOKEN=fixture-secret-token\n", encoding="utf-8")
        (deployment.parent / "approval.env").write_text("INCIDENT_APPROVAL_SECRET=fixture-approval-secret\n", encoding="utf-8")
        self.fake = FakeDocker()
        self.docker = patch.object(subject, "docker", self.fake)
        self.docker.start()

    def tearDown(self):
        self.docker.stop()
        self.temp.cleanup()

    def prepared(self):
        return subject.prepare(self.root)

    def collector(self):
        plan = subject.load(self.root / subject.WORK / "all-six/plan.json")
        row = {"Id": "held-collector", "Name": "/" + plan["container_name"],
               "Config": {"Labels": plan["state_volume_labels"], "StopSignal": "SIGTERM"},
               "State": {"Running": True, "Status": "running", "ExitCode": 0, "OOMKilled": False, "Error": "", "StartedAt": "2026-10-19T01:00:00Z"}}
        self.fake.metadata[row["Id"]] = row
        self.fake.volumes[plan["state_volume_name"]] = {"Name": plan["state_volume_name"], "Labels": plan["state_volume_labels"]}
        subject.save(self.root / subject.WORK / "held-all-six.json", {"id": row["Id"]})
        return row, plan

    def test_real_six_routes_two_phases_shared_fresh_offsets(self):
        result = self.prepared()
        a, b = result["stages"]["heartbeat-access"], result["stages"]["all-six"]
        self.assertEqual(a["tail_inputs"], 14)
        self.assertEqual(b["tail_inputs"], 42)
        self.assertEqual(set(b["kinds"]), set(subject.KINDS))
        self.assertIn("metrics", b["kinds"])
        self.assertNotIn("task", b["kinds"])
        self.assertFalse(a["read_from_head"])
        self.assertEqual(a["state_volume_name"], b["state_volume_name"])
        self.assertEqual(a["state_volume_labels"], b["state_volume_labels"])
        self.assertFalse(any(part.endswith("$ ") for args in self.fake.calls for part in args))
        self.assertFalse(any(args[0] in {"compose", "start", "stop"} for args in self.fake.calls))

    def test_exact_five_owned_volumes_and_database_shared(self):
        result, bindings = subject.resolve_sources(self.root)
        self.assertEqual(len(result["sources"]), 7)
        self.assertEqual(len({row["volume"] for row in bindings.values()}), 5)
        self.assertEqual(bindings["database"]["volume"], bindings["database-backup"]["volume"])
        self.assertTrue(all(row.get("volume_subpath", "amp-coordinator").startswith("amp-") for row in result["sources"]))

    def test_wrong_volume_project_rejected(self):
        next(iter(self.fake.volumes.values()))["Labels"]["com.docker.compose.project"] = "another-project"
        with self.assertRaisesRegex(ValueError, "volume ownership"):
            subject.resolve_sources(self.root)

    def test_container_alias_or_labels_rejected(self):
        row = deepcopy(next(iter(self.fake.metadata.values())))
        row["Config"]["Labels"]["com.docker.compose.project"] = "another-project"
        with self.assertRaisesRegex(ValueError, "ownership"):
            subject.container_binding(row, "application")

    def test_existing_offsets_rejected_before_prepare(self):
        name = subject.COLLECTOR_PROJECT + "-kafka-offsets"
        self.fake.volumes[name] = {"Name": name, "Labels": {}}
        with self.assertRaisesRegex(ValueError, "brand-new offset"):
            self.prepared()

    def test_missing_kind_is_reported_without_fabrication_or_failure(self):
        self.prepared()
        (self.root / subject.AMP / "amp_heartbeat_fixture.jsonl").write_text('{"aic":"fixture","kind":"heartbeat"}\n', encoding="utf-8")
        result = subject.scan(self.root)
        report = subject.load(result["report"])
        self.assertTrue(report["stage_gate_passed"])
        self.assertGreater(report["json_records"], 0)
        self.assertEqual(report["hits"], 0)
        self.assertEqual(report["parse_errors"], 0)
        self.assertEqual(report["read_errors"], 0)
        self.assertIn("metrics", report["missing_kinds"])

    def test_partial_json_is_not_silently_dropped(self):
        self.prepared()
        (self.root / subject.AMP / "amp_access_fixture.jsonl").write_text('{"partial":', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "gate failed"):
            subject.scan(self.root)
        reports = list((self.root / subject.WORK).glob("scan-2*.json"))
        self.assertEqual(len(reports), 1)
        self.assertGreater(subject.load(reports[0])["parse_errors"], 0)
        self.assertFalse((self.root / subject.WORK / "scan-passed.json").exists())

    def test_known_resource_secret_blocks_send(self):
        self.prepared()
        (self.root / subject.AMP / "amp_message_fixture.jsonl").write_text('{"payload":"fixture-secret-token"}\n', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "gate failed"):
            subject.scan(self.root)
        self.assertFalse((self.root / subject.WORK / "scan-passed.json").exists())

    def test_held_id_mismatch_rejected(self):
        self.prepared()
        row, plan = self.collector()
        with self.assertRaisesRegex(ValueError, "ID/name/source labels"):
            subject.collector_identity(row, plan, "different-id")

    def test_supervisor_adopts_and_normally_stops_only_held_collector(self):
        self.prepared()
        row, _ = self.collector()
        handlers = {}
        def set_signal(number, handler):
            prior = handlers.get(number)
            handlers[number] = handler
            return prior
        def request_stop(seconds):
            handlers[subject.signal.SIGTERM](subject.signal.SIGTERM, None)
        with patch.object(subject.signal, "signal", set_signal), patch.object(subject.time, "sleep", request_stop):
            result = subject.supervise(self.root)
        self.assertEqual(result["exit_code"], 0)
        stops = [args for args in self.fake.calls if args[0] == "stop"]
        self.assertEqual(stops, [("stop", "--time", "15", row["Id"])])
        self.assertFalse(any(args[0] in {"rm", "kill", "compose"} for args in self.fake.calls))

    def test_supervisor_resumes_same_normally_stopped_id(self):
        self.prepared()
        row, _ = self.collector()
        row["State"]["Running"] = False
        handlers = {}
        def set_signal(number, handler):
            prior = handlers.get(number)
            handlers[number] = handler
            return prior
        with patch.object(subject.signal, "signal", set_signal), patch.object(subject.time, "sleep", lambda seconds: handlers[subject.signal.SIGTERM](subject.signal.SIGTERM, None)):
            subject.supervise(self.root)
        self.assertIn(("start", row["Id"]), self.fake.calls)

    def test_supervisor_refuses_failed_prior_exit(self):
        self.prepared()
        row, _ = self.collector()
        row["State"].update(Running=False, ExitCode=137)
        with self.assertRaisesRegex(ValueError, "Prior collector exit"):
            subject.supervise(self.root)
        self.assertFalse(any(args[0] == "start" for args in self.fake.calls))

    def test_stop_all_allows_prior_normal_domain_restarts_and_preserves_offsets(self):
        self.prepared()
        row, plan = self.collector()
        for identifier, domain in self.fake.metadata.items():
            if identifier != row["Id"]:
                domain["State"]["StartedAt"] = "2026-10-20T01:00:00Z"
                domain["RestartCount"] = 1
        result = subject.stop(self.root, "all-six")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn(plan["state_volume_name"], self.fake.volumes)
        self.assertFalse(any(args[0] in {"rm", "kill", "compose"} for args in self.fake.calls))

    def test_full_phase6_uses_checked_configs_seven_alive_and_shared_offset(self):
        self.prepared()
        subject.save(self.root / subject.WORK / "scan-passed.json", {"report": str(self.root / subject.WORK / "fake-scan.json")})
        subject.save(self.root / subject.WORK / "fake-scan.json", {"stage_gate_passed": True})
        starts = []
        def compose_start(root, stage, *args):
            if args == ("config", "--quiet"):
                return ""
            self.assertEqual(args, ("up", "-d", "--no-deps", "collector"))
            plan = subject.load(root / subject.WORK / stage / "plan.json")
            for key in list(self.fake.metadata):
                if self.fake.metadata[key]["Name"] == "/" + plan["container_name"]:
                    del self.fake.metadata[key]
            identifier = "collector-" + stage
            self.fake.metadata[identifier] = {"Id": identifier, "Name": "/" + plan["container_name"],
                "Config": {"Labels": plan["state_volume_labels"], "StopSignal": "SIGTERM"},
                "State": {"Running": True, "Status": "running", "ExitCode": 0, "OOMKilled": False, "Error": "", "StartedAt": "2026-10-19T01:00:00Z"}}
            self.fake.volumes.setdefault(plan["state_volume_name"], {"Name": plan["state_volume_name"], "Labels": plan["state_volume_labels"]})
            starts.append(stage)
            return ""
        aics = {role: "fixture-" + role for role in subject.ROLES}
        response = {"result": {"aliveMap": {value: {"alive": True} for value in aics.values()}}}
        posted = []
        class Client:
            def __init__(self, **kwargs):
                self.options = kwargs
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def post(self, url, json):
                posted.append((url, json))
                class Response:
                    def raise_for_status(self):
                        pass
                    def json(self):
                        return response
                return Response()
        with patch.object(subject, "compose", compose_start), patch.object(subject, "identities", lambda root: (aics, "https://wt.ioa.pub/discovery/acps-adp-v2/discover")), patch("httpx.Client", Client):
            initial = subject.start(self.root, "heartbeat-access")
            observed = subject.query(self.root)
            subject.stop(self.root, "heartbeat-access")
            expanded = subject.start(self.root, "all-six")
        self.assertEqual(observed["online_count"], 7)
        self.assertNotEqual(initial["id"], expanded["id"])
        self.assertEqual(starts, ["heartbeat-access", "all-six"])
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0][1]["limit"], 50)
        self.assertEqual(set(posted[0][1]["filter"]["conditions"][0]["value"]), set(aics.values()))
        offset_names = [name for name in self.fake.volumes if name.endswith("-offsets")]
        self.assertEqual(offset_names, [subject.COLLECTOR_PROJECT + "-kafka-offsets"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
