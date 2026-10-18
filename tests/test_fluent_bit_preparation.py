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


if __name__ == "__main__":
    unittest.main()
