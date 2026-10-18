"""Isolated Linux collector preparation contracts; no Docker or network calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy/fluent-bit/prepare_linux_collector.py"
spec = importlib.util.spec_from_file_location("linux_collector_preparation", SOURCE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
IMAGE = "cr.fluentbit.io/fluent/fluent-bit@sha256:" + "a" * 64


class LinuxCollectorPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "artifacts")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        coordinator = self.directory / "coordinator-amp"
        coordinator.mkdir()
        self.plan = json.loads((SOURCE.parent / "collection-plan.example.json").read_text(encoding="utf-8"))
        self.plan["sources"][0]["host_project_relative_directory"] = coordinator.relative_to(ROOT).as_posix()
        self.sources = collector.sources_from_plan(self.plan)

    def test_stdout_sources_are_readonly_subpaths_with_separate_labeled_offsets(self):
        result = collector.compose_spec(self.sources, IMAGE, "/config/collector.conf", "/config/parsers.conf")
        service = result["services"]["collector"]
        self.assertEqual(service["network_mode"], "none")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["pull_policy"], "never")
        self.assertNotIn("environment", service)
        mounts = [mount for mount in service["volumes"] if mount["target"].startswith("/sources/")]
        self.assertEqual(len(mounts), 7)
        self.assertTrue(all(mount["read_only"] for mount in mounts))
        domains = [mount for mount in mounts if mount["type"] == "volume"]
        self.assertEqual(len(domains), 6)
        self.assertTrue(all(mount["volume"]["subpath"] == "amp-" + mount["target"].split("/")[-1]
                            and mount["volume"]["nocopy"] for mount in domains))
        self.assertEqual(sum(value.get("external", False) for value in result["volumes"].values()), 5)
        self.assertEqual(result["volumes"]["offsets"]["labels"][collector.SOURCE_LABEL], collector.digest(self.sources))
        self.assertEqual(service["stop_signal"], "SIGTERM")
        self.assertEqual(service["stop_grace_period"], "15s")

    def test_source_plan_rejects_whole_volume_missing_role_and_wrong_target(self):
        for mutation in (lambda rows: rows[1].update(volume_subpath=""),
                         lambda rows: rows.pop(),
                         lambda rows: rows[1].update(collector_mount="/state")):
            plan = copy.deepcopy(self.plan)
            mutation(plan["sources"])
            with self.assertRaises(ValueError):
                collector.sources_from_plan(plan)

    def test_offset_reuse_rejects_changed_source_collection_mode_and_missing_labels(self):
        binding = collector.digest(self.sources)
        metadata = {"Name": collector.STATE_VOLUME, "Labels": collector.state_labels(binding)}
        collector.validate_existing_state(None, binding)
        collector.validate_existing_state(metadata, binding)
        for value, expected, mode in ((metadata, "b" * 64, "stdout"),
                                      (metadata, binding, "kafka"),
                                      ({"Name": collector.STATE_VOLUME, "Labels": None}, binding, "stdout")):
            with self.assertRaises(ValueError):
                collector.validate_existing_state(value, expected, mode)

    def test_render_uses_42_flat_databases_and_stable_body_globs(self):
        config = collector.render_config(self.sources)
        databases = [line.strip()[3:] for line in config.splitlines() if line.strip().startswith("DB ")]
        self.assertEqual(len(set(databases)), 42)
        self.assertTrue(all(value.startswith("/collector-state/amp-") and value.count("/") == 2 for value in databases))
        self.assertEqual(config.count("    Read_From_Head True"), 42)
        self.assertEqual(config.count("    Format json_lines"), 6)
        self.assertNotIn(".jsonl.1", config)

    def test_kafka_transport_keeps_secrets_as_environment_references_and_mounts_only_tls_files(self):
        files = {}
        for key, name in (("ssl.ca.location", "ca"), ("ssl.certificate.location", "cert"), ("ssl.key.location", "key")):
            path = self.directory / name
            path.write_text("synthetic-file", encoding="utf-8")
            files[key] = str(path)
        profile = {"brokers": "fixture.invalid:19092", "rdkafka": {"security.protocol": "sasl_ssl",
            "sasl.mechanism": "PLAIN", "sasl.username": "fixture-user", "sasl.password": "${T06_COLLECTOR_TEST_PASSWORD}", **files}}
        original = copy.deepcopy(profile)
        with patch.dict("os.environ", {"T06_COLLECTOR_TEST_PASSWORD": "synthetic-secret"}):
            mapped, mounts, environment = collector.kafka_transport(profile)
            config = collector.render_config(self.sources, mode="kafka", kafka=mapped)
        self.assertEqual(profile, original)
        self.assertEqual(len(mounts), 3)
        self.assertTrue(all(mount["read_only"] and mount["target"].startswith("/collector-transport/") for mount in mounts))
        self.assertEqual(environment, {"T06_COLLECTOR_TEST_PASSWORD"})
        self.assertIn("${T06_COLLECTOR_TEST_PASSWORD}", config)
        self.assertNotIn("synthetic-secret", config)
        self.assertEqual(config.count("    Name kafka"), 6)
        result = collector.compose_spec(self.sources, IMAGE, "/config/collector.conf", "/config/parsers.conf",
            mode="kafka", transport_mounts=mounts, environment=environment)
        self.assertEqual(result["services"]["collector"]["network_mode"], "bridge")
        self.assertEqual(result["services"]["collector"]["environment"], ["T06_COLLECTOR_TEST_PASSWORD"])
        self.assertNotEqual(result["volumes"]["offsets"]["name"], collector.STATE_VOLUME)

    def test_prepare_writes_only_four_new_files_without_running_processes(self):
        plan_path = self.directory / "sources.json"
        plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        output = self.directory / "prepared"
        with patch("subprocess.run", side_effect=AssertionError("No process may run during preparation")):
            plan = collector.prepare(output, IMAGE, plan_path)
        self.assertEqual({path.name for path in output.iterdir()}, {"compose.json", "collector.conf", "parsers.conf", "plan.json"})
        self.assertEqual(plan["actual_container_starts"], 0)
        self.assertTrue(plan["read_from_head"])
        self.assertFalse(plan["network"])
        with self.assertRaises(FileExistsError):
            collector.prepare(output, IMAGE, plan_path)

    def test_requires_explicit_pinned_image_and_kafka_mode(self):
        for image in ("fluent/fluent-bit:latest", "cr.fluentbit.io/fluent/fluent-bit:5.1.3", "sha256:" + "a" * 64):
            with self.assertRaises(ValueError):
                collector.compose_spec(self.sources, image, "/config/collector.conf", "/config/parsers.conf")
        with self.assertRaisesRegex(ValueError, "Explicit Kafka settings"):
            collector.prepare(self.directory / "kafka", IMAGE, mode="kafka")


if __name__ == "__main__":
    unittest.main()
