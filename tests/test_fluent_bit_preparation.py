"""File-only preparation and owned-run contracts; never run Fluent Bit or Kafka."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy/fluent-bit/render.py"
spec = importlib.util.spec_from_file_location("fluent_preparation", SOURCE)
fluent = importlib.util.module_from_spec(spec); spec.loader.exec_module(fluent)


class FluentPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "artifacts")
        self.root = Path(self.temp.name)
        self.logs = self.root / "logs"; self.logs.mkdir()
        for kind in fluent.KINDS:
            (self.logs / ("amp_" + kind + "_synthetic.jsonl")).write_text('{"aic":"fixture","log_id":"unchanged"}\n', encoding="utf-8")
        self.parser = ROOT / "deploy/fluent-bit/parsers.conf"
        self.root_patch = patch.object(fluent, "ROOT", self.root); self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop(); self.temp.cleanup()

    def invoke(self, *args):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = fluent.main(["--log-directory", str(self.logs), *args])
        return code, json.loads(stream.getvalue())

    def test_check_has_no_write_alias_subprocess_or_network(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        with patch.object(fluent, "native_path", side_effect=AssertionError("alias")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             patch("subprocess.run", side_effect=AssertionError("process")), \
             patch("socket.socket", side_effect=AssertionError("network")):
            code, report = self.invoke("--check", "--state-root", str(self.root / "absent"))
        self.assertEqual(code, 0); self.assertTrue(report["passed"])
        self.assertEqual(report["log_files_by_kind"], dict.fromkeys(fluent.KINDS, 1))
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_missing_kind_and_directory_fail_without_creating_state(self):
        (self.logs / "amp_audit_synthetic.jsonl").unlink()
        code, report = self.invoke("--check")
        self.assertEqual(code, 1); self.assertIn("logs.missing_kind:audit", report["errors"])
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = fluent.main(["--log-directory", str(self.root / "missing"), "--state-root", str(self.root / "state"), "--mode", "kafka"])
        self.assertEqual(code, 1); self.assertFalse((self.root / "state").exists())
        self.assertIn("kafka.brokers_required", json.loads(stream.getvalue())["errors"])

    def tls_profile(self):
        for name in ("ca", "cert", "key"):
            (self.root / name).write_text("synthetic metadata fixture", encoding="utf-8")
        return dict(brokers="fixture.invalid:19092", rdkafka={"security.protocol": "ssl", "ssl.ca.location": str(self.root / "ca"),
            "ssl.certificate.location": str(self.root / "cert"), "ssl.key.location": str(self.root / "key")})

    def test_tls_preflight_checks_existence_without_reading_material_or_printing_values(self):
        profile = self.tls_profile()
        with patch.object(Path, "open", side_effect=AssertionError("TLS content read")):
            report = fluent.check(self.logs, self.parser, mode="kafka", kafka=profile)
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["kafka"]["tls_files_checked"]), 3)
        for private_value in (profile["brokers"], str(self.root / "key"), "synthetic metadata fixture"):
            self.assertNotIn(private_value, json.dumps(report))

    def test_tls_missing_ca_pair_or_path_is_rejected(self):
        profile = self.tls_profile()
        for change in ({"ssl.ca.location": None}, {"ssl.key.location": None}, {"ssl.key.location": str(self.root / "missing")}):
            with self.subTest(fields=list(change)):
                changed = json.loads(json.dumps(profile))
                for key, value in change.items():
                    if value is None: changed["rdkafka"].pop(key)
                    else: changed["rdkafka"][key] = value
                self.assertFalse(fluent.check(self.logs, self.parser, mode="kafka", kafka=changed)["passed"])

    def test_sasl_environment_required_and_secret_never_reported(self):
        profile = self.tls_profile()
        profile["rdkafka"].update({"security.protocol": "sasl_ssl", "sasl.mechanism": "PLAIN", "sasl.username": "${T06_FIXTURE_USER}", "sasl.password": "${T06_FIXTURE_PASSWORD}"})
        with patch.dict(os.environ, {"T06_FIXTURE_USER": "", "T06_FIXTURE_PASSWORD": ""}):
            self.assertFalse(fluent.check(self.logs, self.parser, mode="kafka", kafka=profile)["passed"])
        with patch.dict(os.environ, {"T06_FIXTURE_USER": "synthetic-user", "T06_FIXTURE_PASSWORD": "synthetic-secret"}):
            report = fluent.check(self.logs, self.parser, mode="kafka", kafka=profile)
        self.assertTrue(report["passed"]); self.assertNotIn("synthetic-secret", json.dumps(report))
        profile["rdkafka"]["sasl.password"] = "literal-forbidden"
        self.assertFalse(fluent.check(self.logs, self.parser, mode="kafka", kafka=profile)["passed"])

    def test_invalid_kafka_render_fails_before_native_alias(self):
        with patch.object(fluent, "native_path", side_effect=AssertionError("must validate first")):
            for profile in (None, {"brokers": "TODO", "rdkafka": {}}, {"brokers": "host:1\nInjected yes", "rdkafka": {"security.protocol": "plaintext"}}):
                with self.subTest(profile_present=bool(profile)), self.assertRaises(ValueError):
                    fluent.render(self.logs, self.root / "state", self.parser, mode="kafka", kafka=profile)

    def test_default_stdout_and_legacy_render_cli_still_write_without_running(self):
        state, output = self.root / "state", self.root / "stdout.conf"
        with patch.object(fluent, "native_path", side_effect=lambda path: str(Path(path).resolve())), patch("subprocess.run", side_effect=AssertionError("unexpected process")):
            code, report = self.invoke("--state-directory", str(state), "--output", str(output))
        self.assertEqual(code, 0); self.assertTrue(output.exists())
        text = output.read_text(encoding="utf-8")
        self.assertEqual(text.count("    Name stdout"), 6); self.assertNotIn("    Name kafka", text)
        self.assertIn("    Read_From_Head False", text)
        self.assertFalse(report["kafka_connection_tested"])

    def test_source_alias_identity_and_distinct_source_or_mode_state(self):
        other = self.root / "other"; other.mkdir()
        for kind in fluent.KINDS: (other / ("amp_" + kind + "_other.jsonl")).write_text("{}\n")
        self.assertEqual(fluent.source_id(self.logs), fluent.source_id(self.logs / ".." / "logs"))
        if os.name == "nt": self.assertEqual(fluent.source_id(self.logs), fluent.source_id(str(self.logs).upper()))
        self.assertNotEqual(fluent.source_id(self.logs), fluent.source_id(other))
        state_root = self.root / "states"
        with patch.object(fluent, "native_path", side_effect=lambda path: str(Path(path).resolve())):
            self.invoke("--state-root", str(state_root))
            with redirect_stdout(io.StringIO()): fluent.main(["--log-directory", str(other), "--state-root", str(state_root)])
            profile = self.root / "kafka.json"; profile.write_text(json.dumps(dict(brokers="fixture.invalid:19092", rdkafka={"security.protocol": "plaintext"})))
            self.invoke("--state-root", str(state_root), "--mode", "kafka", "--kafka-settings", str(profile))
        paths = [state_root / fluent.source_id(self.logs) / "stdout/fluent-bit-stdout.conf",
                 state_root / fluent.source_id(other) / "stdout/fluent-bit-stdout.conf",
                 state_root / fluent.source_id(self.logs) / "kafka/fluent-bit-kafka.conf"]
        self.assertTrue(all(path.is_file() for path in paths))
        db_paths = [line.strip() for path in paths for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("DB ")]
        self.assertEqual(len(set(db_paths)), 18)

    def test_actual_owner_contention_across_processes_and_release(self):
        code = "import importlib.util,sys;from pathlib import Path;s=importlib.util.spec_from_file_location('f',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.ROOT=Path(sys.argv[2]);\ntry:\n with m.source_owner(sys.argv[3]):pass\nexcept ValueError:sys.exit(2)"
        def child(directory):
            return subprocess.run([sys.executable, "-B", "-c", code, str(SOURCE), str(self.root), str(directory)], capture_output=True, timeout=15).returncode
        with fluent.source_owner(self.logs):
            self.assertEqual(child(self.logs / ".." / "logs"), 2)
            self.assertEqual(child(self.root / "different-source"), 0)
        self.assertEqual(child(self.logs), 0)

    def test_runtime_owner_cannot_be_bypassed_by_different_state_root(self):
        executable = self.root / "unused.exe"; executable.write_bytes(b"not executed")
        with fluent.source_owner(self.logs), patch("subprocess.run", side_effect=AssertionError("must not spawn")), patch.object(fluent, "native_path", side_effect=AssertionError("must not render")):
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "already_owned"):
                fluent.main(["--log-directory", str(self.logs), "--state-root", str(self.root / "different-state"), "--executable", str(executable)])
        self.assertFalse((self.root / "different-state").exists())

    def test_foreground_owner_covers_wait_and_releases_after_failure(self):
        executable = self.root / "unused.exe"; executable.write_bytes(b"not executed")
        def fake_wait(argv):
            self.assertEqual(argv[0], str(executable.resolve()))
            with self.assertRaisesRegex(ValueError, "already_owned"):
                with fluent.source_owner(self.logs): pass
            return SimpleNamespace(returncode=19)
        with patch.object(fluent, "native_path", side_effect=lambda path: str(Path(path).resolve())), patch("subprocess.run", side_effect=fake_wait):
            with redirect_stdout(io.StringIO()):
                result = fluent.main(["--log-directory", str(self.logs), "--state-root", str(self.root / "state"), "--executable", str(executable)])
        self.assertEqual(result, 19)
        with fluent.source_owner(self.logs): pass

    def test_kafka_render_keeps_audit_timestamp_and_environment_password_reference(self):
        profile = self.tls_profile()
        profile["rdkafka"].update({"sasl.password": "${T06_FIXTURE_PASSWORD}"})
        with patch.dict(os.environ, {"T06_FIXTURE_PASSWORD": "synthetic-secret"}), patch.object(fluent, "native_path", side_effect=lambda path: str(Path(path).resolve())):
            text = fluent.render(self.logs, self.root / "state", self.parser, mode="kafka", kafka=profile)
        self.assertIn("timestamp_key _fb_ts", text); self.assertNotIn("synthetic-secret", text)
        self.assertIn("${T06_FIXTURE_PASSWORD}", text)
        self.assertEqual(text.count("rdkafka.allow.auto.create.topics false"), 6)
        self.assertEqual([line.strip().split(" ")[-1] for line in text.splitlines() if line.strip().startswith("Topics ")], ["amp." + kind for kind in fluent.KINDS])

    def collection(self):
        sources = {}
        for role in fluent.COLLECTION_ROLES:
            directory = self.root / role; directory.mkdir()
            for kind in fluent.KINDS:
                (directory / ("amp_" + kind + "_fixture.jsonl")).write_text('{}\n', encoding="utf-8")
            sources[role] = directory
        return sources

    def test_collection_has_42_isolated_databases_and_excludes_archived_files(self):
        sources = self.collection()
        directory = sources["coordinator"]
        for suffix in ("1", "20", "001", "tmp", "1.tmp", "db", "-1"):
            (directory / ("amp_audit_fixture.jsonl." + suffix)).write_text('{}\n', encoding="utf-8")
        with patch.object(fluent, "native_path", side_effect=lambda value: Path(value).resolve().as_posix()):
            text = fluent.render_collection(sources, self.root / "state", self.parser)
            single = fluent.render(directory, self.root / "single", self.parser)
        text = text.replace("\\", "/")
        self.assertEqual(text.count("    Name tail\n"), 42)
        self.assertEqual(text.count("    Name stdout\n"), 6)
        self.assertNotIn("    Name kafka", text)
        databases = [line for line in text.splitlines() if line.startswith("    DB ")]
        self.assertEqual(len(set(databases)), 42)
        self.assertEqual(text.count("    Read_From_Head True"), 42)
        audit = next(line for line in text.splitlines() if line.startswith("    Path ") and "/coordinator/amp_audit_" in line)
        self.assertEqual(audit.strip().split("/coordinator/")[1], "amp_audit_*.jsonl")
        for suffix in ("1", "20", "001", "tmp", "1.tmp", "db", "-1"):
            self.assertNotIn("amp_audit_fixture.jsonl." + suffix, text)
            self.assertNotIn("amp_audit_fixture.jsonl." + suffix, single)

    def test_collection_rejects_missing_invalid_and_canonical_duplicate_sources(self):
        sources = self.collection()
        invalid = [dict(sources, invalid_role=self.logs), {key: value for key, value in sources.items() if key != "ops"},
                   dict(sources, ops=sources["coordinator"] / ".." / "coordinator")]
        for mapping in invalid:
            with self.subTest(keys=list(mapping)), self.assertRaises(ValueError):
                fluent.collection_sources(mapping)
        if os.name == "nt":
            with self.assertRaisesRegex(ValueError, "duplicate_canonical_source"):
                fluent.collection_sources(dict(sources, ops=Path(str(sources["coordinator"]).upper())))

    def test_collection_failed_lock_acquisition_releases_previously_acquired_locks(self):
        sources = self.collection()
        ordered = sorted(sources.values(), key=fluent.source_id)
        with fluent.source_owner(ordered[3]):
            with self.assertRaisesRegex(ValueError, "already_owned"):
                with fluent.collection_owner(sources): self.fail("Blocked owner unexpectedly acquired")
            for directory in ordered[:3]:
                with fluent.source_owner(directory): pass
        with fluent.collection_owner(dict(reversed(list(sources.items())))):
            with self.assertRaisesRegex(ValueError, "already_owned"):
                with fluent.source_owner(ordered[0]): pass

    def test_collection_cli_check_stays_readonly_and_render_creates_only_its_states(self):
        sources = self.collection()
        mapping = self.root / "sources.json"
        mapping.write_text(json.dumps({key: str(value) for key, value in sources.items()}), encoding="utf-8")
        stream = io.StringIO()
        with patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             patch.object(fluent, "native_path", side_effect=AssertionError("alias")), \
             patch("subprocess.run", side_effect=AssertionError("process")), redirect_stdout(stream):
            code = fluent.main(["--collection-sources", str(mapping), "--check"])
        self.assertEqual(code, 0); self.assertTrue(json.loads(stream.getvalue())["passed"])
        with patch.object(fluent, "native_path", side_effect=lambda value: Path(value).resolve().as_posix()), redirect_stdout(io.StringIO()):
            self.assertEqual(fluent.main(["--collection-sources", str(mapping), "--state-root", str(self.root / "state")]), 0)
        self.assertEqual(len(list((self.root / "state").glob("*/stdout"))), 7)
        self.assertFalse(any(self.root.glob("*.db")))
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(fluent.main(["--collection-sources", str(mapping), "--mode", "kafka", "--check"]), 1)
        self.assertFalse(json.loads(stream.getvalue())["passed"])

    def test_collection_kafka_preflight_is_readonly_and_missing_profile_rejects(self):
        sources = self.collection()
        profile = self.tls_profile()
        with patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")), \
             patch.object(Path, "open", side_effect=AssertionError("material read")), \
             patch.object(fluent, "native_path", side_effect=AssertionError("alias")), \
             patch("subprocess.run", side_effect=AssertionError("process")), \
             patch("socket.socket", side_effect=AssertionError("network")):
            report = fluent.check_collection(sources, self.parser, mode="kafka", kafka=profile)
            rejected = fluent.check_collection(sources, self.parser, mode="kafka")
        self.assertTrue(report["passed"]); self.assertFalse(rejected["passed"])
        for role in fluent.COLLECTION_ROLES:
            self.assertEqual(rejected["sources"][role]["errors"], ["kafka.brokers_required"])
        self.assertNotIn(profile["brokers"], json.dumps(report))
        self.assertNotIn(str(self.root / "key"), json.dumps(report))

    def test_collection_kafka_cli_preserves_default_and_separates_42_databases(self):
        sources = self.collection()
        mapping, profile = self.root / "sources.json", self.root / "kafka.json"
        mapping.write_text(json.dumps({key: str(value) for key, value in sources.items()}), encoding="utf-8")
        profile.write_text(json.dumps(dict(brokers="fixture.invalid:19092", rdkafka={"security.protocol": "plaintext"})), encoding="utf-8")
        state = self.root / "state"
        with patch.object(fluent, "native_path", side_effect=lambda value: Path(value).resolve().as_posix()), \
             patch("subprocess.run", side_effect=AssertionError("must not run")), redirect_stdout(io.StringIO()):
            self.assertEqual(fluent.main(["--collection-sources", str(mapping), "--state-root", str(state)]), 0)
            self.assertEqual(fluent.main(["--collection-sources", str(mapping), "--state-root", str(state),
                                         "--mode", "kafka", "--kafka-settings", str(profile)]), 0)
            with self.assertRaisesRegex(ValueError, "require_kafka_mode"):
                fluent.main(["--collection-sources", str(mapping), "--kafka-settings", str(profile), "--check"])
        stdout = (state / "collection-stdout.conf").read_text(encoding="utf-8")
        kafka = (state / "collection-kafka.conf").read_text(encoding="utf-8")
        self.assertEqual(stdout.count("    Name stdout\n"), 6)
        self.assertEqual(kafka.count("    Name tail\n"), 42)
        self.assertEqual(kafka.count("    Name kafka\n"), 6)
        self.assertEqual(kafka.count("    timestamp_key _fb_ts"), 1)
        self.assertEqual(kafka.count("rdkafka.allow.auto.create.topics false"), 6)
        databases = [line.replace("\\", "/") for text in (stdout, kafka) for line in text.splitlines() if line.startswith("    DB ")]
        self.assertEqual(len(set(databases)), 84)
        self.assertEqual(len(list(state.glob("*/kafka"))), 7)

    def linux_paths(self):
        return ({role: "/sources/" + role for role in fluent.COLLECTION_ROLES},
                {role: "/collector-state/amp-" + role + "-{kind}.db" for role in fluent.COLLECTION_ROLES})

    def test_linux_paths_share_routes_keep_flat_databases_and_never_use_host_io(self):
        sources, databases = self.linux_paths()
        profile = dict(brokers="fixture.invalid:19092", rdkafka={"security.protocol": "sasl_ssl",
            "ssl.ca.location": "/collector-transport/ca", "sasl.mechanism": "PLAIN",
            "sasl.username": "${T06_FIXTURE_USER}", "sasl.password": "${T06_FIXTURE_PASSWORD}"})
        with patch.object(Path, "open", side_effect=AssertionError("file read")), \
             patch.object(Path, "is_file", side_effect=AssertionError("host stat")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(fluent, "native_path", side_effect=AssertionError("native path")), \
             patch("socket.socket", side_effect=AssertionError("network")), \
             patch("subprocess.run", side_effect=AssertionError("process")):
            text = fluent.render_collection_paths(sources, databases, "/collector/parsers.conf", mode="kafka", kafka=profile)
            stdout = fluent.render_collection_paths(sources, databases, "/collector/parsers.conf")
        self.assertEqual(text.count("    Name tail\n"), 42)
        self.assertEqual(text.count("    Name kafka\n"), 6)
        self.assertEqual(stdout.count("    Name stdout\n"), 6)
        db_lines = [line for line in text.splitlines() if line.startswith("    DB ")]
        self.assertEqual(len(set(db_lines)), 42)
        self.assertIn("    DB /collector-state/amp-database-backup-audit.db", db_lines)
        self.assertIn("    Path /sources/database-backup/amp_audit_*.jsonl", text)
        self.assertIn("    rdkafka.sasl.password ${T06_FIXTURE_PASSWORD}", text)
        self.assertIn("    rdkafka.ssl.ca.location /collector-transport/ca", text)
        self.assertNotIn("\\", text)

    def test_linux_paths_reject_missing_roles_path_injection_and_duplicate_databases(self):
        sources, databases = self.linux_paths()
        cases = [(dict(sources, ops="/sources/../private"), databases),
                 (dict(sources, ops="/sources/ops\nInjected true"), databases),
                 (dict(sources, ops=sources["coordinator"]), databases),
                 ({role: value for role, value in sources.items() if role != "ops"}, databases),
                 (sources, dict(databases, ops=databases["coordinator"])),
                 (sources, dict(databases, ops="/collector-state/fixed.db"))]
        for source, state in cases:
            with self.subTest(index=cases.index((source, state))), self.assertRaises(ValueError):
                fluent.render_collection_paths(source, state, "/collector/parsers.conf")
        with self.assertRaisesRegex(ValueError, "brokers_required"):
            fluent.render_collection_paths(sources, databases, "/collector/parsers.conf", mode="kafka")


if __name__ == "__main__":
    unittest.main()
