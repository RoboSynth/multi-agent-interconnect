"""Isolated deployment preparation and command scope; no Docker processes are started."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("deployment_preparation", ROOT / "deploy/prepare_deployment.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


def identity_source(source):
    source.mkdir()
    for role in (*deployment.ROLES, "coordinator"):
        material = source / role
        material.mkdir()
        for name in ("cert.pem", "key.pem", "trust.pem"):
            (material / name).write_text(role + " copy fixture; not an issued certificate", encoding="utf-8")
        identity = {"aic": "fixture-" + role, "endpoint": "amqps://fixture.invalid/inbox_" + role,
            "cert": str(material / "cert.pem"), "key": str(material / "key.pem"),
            "trust_bundle": str(material / "trust.pem")}
        config = {**identity, "allowed_leaders": ["fixture-coordinator"],
                  "mq_auth_url": "https://fixture.invalid/auth", "discovery_url": "https://fixture.invalid/adp"}
        if role == "coordinator":
            config = {"leader": identity, "trust_bundle": identity["trust_bundle"],
                "mq_auth_url": "https://fixture.invalid/auth", "discovery_url": "https://fixture.invalid/adp",
                "skills": {"application": "incident.application", "database": "db.observe", "ops": "ops.observe",
                           "verification": "incident.verification", "onboarding": "aip.onboarding.check"}}
        (source / (role + ".json")).write_text(json.dumps(config), encoding="utf-8")
    return source


class DeploymentPreparationTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "artifacts/deployment-gap-audit-20261018/fixtures"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="隔离 中文 ", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "output"
        self.ports = {"app_v1": 49081, "app_v2": 49082, "order": 49088}

    def prepare(self, mode="business", **kwargs):
        source = identity_source(Path(self.temporary.name) / "source") if mode == "seven" else None
        deployment.prepare(self.output, "isolated-fixture", self.ports, reply_port=49090,
                           mode=mode, source=source, **kwargs)
        return self.output / "deployment.json"

    def test_business_preparation_is_offline_private_and_has_no_injector_target(self):
        with patch.object(deployment.subprocess, "run", side_effect=AssertionError("Preparation must not run processes")):
            path = self.prepare()
        manifest = deployment.load_deployment(path)
        self.assertIsNone(manifest["target_config"])
        self.assertFalse((self.output / "target.json").exists())
        self.assertEqual(manifest["ports"], self.ports)
        env = dict(line.split("=", 1) for line in (self.output / "compose.env").read_text(encoding="utf-8").splitlines())
        secrets = [env[name] for name in ("POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "APP_ADMIN_TOKEN", "BRIDGE_DB_PASSWORD")]
        self.assertEqual(len(set(secrets)), 4)
        self.assertTrue(all(len(value) >= 36 for value in secrets))
        self.assertTrue(all(value not in path.read_text(encoding="utf-8") for value in secrets))
        self.assertEqual(env["ORDER_BIND"], "127.0.0.1")
        self.assertEqual((self.output / "nginx-runtime/route.conf").read_bytes(),
                         (ROOT / "deploy/nginx/route.default.conf").read_bytes())
        self.assertEqual(set(json.loads((self.output / "deployment.overlay.yml").read_text(encoding="utf-8"))["services"]), {"nginx"})

    def test_seven_manifest_target_and_domain_scopes_share_exact_sources(self):
        path = self.prepare("seven")
        manifest = deployment.load_deployment(path)
        target = json.loads((self.output / "target.json").read_text(encoding="utf-8"))
        for key in ("project", "wsl_distro", "compose_files", "env_file", "route_file"):
            self.assertEqual(target[key], manifest[key])
        self.assertEqual(target["ports"], {**manifest["ports"], "reply_drop": manifest["reply_drop_port"]})
        from eval.targets import DockerTarget
        self.assertEqual(DockerTarget.from_file(self.output / "target.json").reply_drop_url, "http://127.0.0.1:49090")
        overlay = json.loads((self.output / "deployment.overlay.yml").read_text(encoding="utf-8"))["services"]
        self.assertEqual(set(overlay), {"nginx", *(role + "-agent" for role in deployment.ROLES)})
        self.assertEqual({overlay[role + "-agent"]["image"] for role in deployment.ROLES}, {"isolated-fixture-agent:local"})
        for role in deployment.ROLES:
            mount = overlay[role + "-agent"]["volumes"][0]
            self.assertEqual(mount["source"], (self.output / "domains" / role).as_posix())
            self.assertTrue(mount["read_only"])
        self.assertEqual(overlay["ops-agent"]["volumes"][1]["source"], overlay["nginx"]["volumes"][0]["source"])
        host = json.loads((self.output / "domains/coordinator/config.json").read_text(encoding="utf-8"))
        self.assertEqual(host["term_namespace"], "isolated-fixture/orders")
        self.assertEqual(host["initial_participant_aics"]["database"], "fixture-database")
        self.assertNotIn("env_files", host)
        policy = (self.output / "domains/ops/policy.yaml").read_text(encoding="utf-8")
        self.assertIn("isolated-fixture-app-v2-1", policy)

    def test_legacy_three_port_target_remains_valid_and_wrong_fourth_port_is_rejected(self):
        path = self.prepare("seven")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        target_path = self.output / "target.json"
        target = json.loads(target_path.read_text(encoding="utf-8"))
        target["ports"].pop("reply_drop")
        deployment.save(target_path, target)
        name = deployment.relative(target_path, ROOT)
        manifest["input_sha256"][name] = deployment.digest(target_path)
        deployment.save(path, manifest)
        deployment.load_deployment(path)
        target["ports"]["reply_drop"] = 49091
        deployment.save(target_path, target)
        manifest["input_sha256"][name] = deployment.digest(target_path)
        deployment.save(path, manifest)
        with self.assertRaisesRegex(ValueError, "target differs"):
            deployment.load_deployment(path)

    def test_bad_options_and_incomplete_identity_fail_before_creating_output(self):
        for options in ({"project": "Bad Project"}, {"reply_port": self.ports["order"]},
                        {"wsl": "../../wrong"}, {"mode": "seven"}):
            values = {"output": self.output, "project": "isolated-fixture", "ports": self.ports, "reply_port": 49090, **options}
            with self.subTest(options=options), self.assertRaises(ValueError):
                deployment.prepare(**values)
            self.assertFalse(self.output.exists())
        source = identity_source(Path(self.temporary.name) / "source")
        config = json.loads((source / "onboarding.json").read_text(encoding="utf-8"))
        config["aic"] = "fixture-application"
        deployment.save(source / "onboarding.json", config)
        with self.assertRaisesRegex(ValueError, "distinct"):
            deployment.prepare(self.output, "isolated-fixture", self.ports, reply_port=49090, mode="seven", source=source)
        self.assertFalse(self.output.exists())
        config["aic"] = "fixture-onboarding"
        deployment.save(source / "onboarding.json", config)
        coordinator = json.loads((source / "coordinator.json").read_text(encoding="utf-8"))
        coordinator["leader"]["key"] = "coordinator/key.pem"
        deployment.save(source / "coordinator.json", coordinator)
        with self.assertRaisesRegex(ValueError, "must be absolute"):
            deployment.prepare(self.output, "isolated-fixture", self.ports, reply_port=49090, mode="seven", source=source)
        self.assertFalse(self.output.exists())

    def test_nonempty_output_refused_and_modified_route_is_preserved_by_validation(self):
        path = self.prepare()
        route = self.output / "nginx-runtime/route.conf"
        route.write_text("set $order_upstream app-v1:8000;\n", encoding="ascii")
        deployment.load_deployment(path)
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            deployment.prepare(self.output, "isolated-fixture", self.ports)
        self.assertIn("app-v1", route.read_text(encoding="utf-8"))

    def test_changed_private_input_or_target_is_rejected_before_subprocess(self):
        path = self.prepare("seven")
        for name in ("compose.env", "target.json", "domains/application/config.json"):
            file = self.output / name
            original = file.read_bytes()
            file.write_bytes(original + b"\n")
            with self.subTest(name=name), patch.object(deployment.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    deployment.launch(path, validate_only=True)
                run.assert_not_called()
            file.write_bytes(original)

    def test_manifest_rejects_cross_checkout_path_or_mismatched_profile(self):
        path = self.prepare()
        original = json.loads(path.read_text(encoding="utf-8"))
        for change in ({"env_file": "../outside.env"}, {"profiles": ["faults"]},
                       {"compose_files": ["deploy/new7.yml"]}, {"ports": {**self.ports, "order": self.ports["app_v1"]}},
                       {"ports": {**self.ports, "order": 49089}}, {"reply_drop_port": 49091}):
            deployment.save(path, {**original, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                deployment.load_deployment(path)
        deployment.save(path, original)

    def test_validate_only_runs_only_quiet_config_with_no_environment_scope_leak(self):
        path = self.prepare()
        before = {file: file.read_bytes() for file in self.output.rglob("*") if file.is_file()}
        polluted = {name: "polluted-shell-value" for name in deployment.GENERATED_ENV_KEYS}
        with patch.dict(os.environ, {**polluted, "COMPOSE_PROFILES": "faults,agents", "COMPOSE_FILE": "outside.yml",
                                    "HTTPS_PROXY": "fixture-proxy", "NO_PROXY": "localhost,fixture.invalid"}), \
                patch.object(deployment.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(deployment.launch(path, validate_only=True), 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-2:], ["config", "--quiet"])
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("COMPOSE_PROFILES", environment)
        self.assertNotIn("COMPOSE_FILE", environment)
        self.assertTrue(all(name not in environment for name in polluted))
        self.assertEqual(environment["HTTPS_PROXY"], "fixture-proxy")
        self.assertEqual(environment["NO_PROXY"], "localhost,fixture.invalid")
        self.assertEqual(before, {file: file.read_bytes() for file in self.output.rglob("*") if file.is_file()})

    def test_seven_launcher_builds_one_shared_agent_image_then_uses_no_build(self):
        path = self.prepare("seven")
        with patch.object(deployment.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(deployment.launch(path), 0)
        calls = [call.args[0] for call in run.call_args_list]
        base = deployment.compose_command(deployment.load_deployment(path), sanitized=True)
        self.assertEqual(calls, [base + action for action in
            (["config", "--quiet"], ["build", "app-v1", "app-v2"], ["build", "application-agent"],
             ["up", "-d", "--no-build", "--wait"])])
        self.assertNotIn("faults", base)

    def test_first_compose_failure_is_returned_without_retry_or_followup(self):
        path = self.prepare("seven")
        with patch.object(deployment.subprocess, "run", return_value=Mock(returncode=17)) as run:
            self.assertEqual(deployment.launch(path), 17)
        self.assertEqual(run.call_count, 1)

    @unittest.skipUnless(os.name == "nt", "Windows local-drive WSL paths")
    def test_wsl_target_and_launcher_use_identical_unicode_spaced_paths_and_distro(self):
        path = self.prepare("seven", wsl="Ubuntu-22.04")
        manifest = deployment.load_deployment(path)
        from eval.targets import DockerTarget
        target = DockerTarget.from_file(manifest["target_config"])
        command = deployment.compose_command(manifest)
        self.assertEqual(command, target.compose + ["--profile", "isolated"])
        self.assertEqual(command[:5], ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "docker"])
        self.assertIn("/mnt/d/", " ".join(command))
        self.assertNotIn(chr(92), " ".join(command))
        sanitized = deployment.compose_command(manifest, sanitized=True)
        for name in deployment.GENERATED_ENV_KEYS:
            self.assertIn(name, sanitized)
            self.assertEqual(sanitized[sanitized.index(name) - 1], "-u")
        self.assertEqual(sanitized[:5], ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "env"])

    def test_raw_identity_file_skips_native_setup_and_keeps_each_identity_separate(self):
        source = identity_source(Path(self.temporary.name) / "source")
        configurations = {role: json.loads((source / (role + ".json")).read_text(encoding="utf-8"))
                          for role in (*deployment.ROLES, "coordinator")}
        leader = configurations["coordinator"]
        raw = {key: leader[key] for key in ("discovery_url", "mq_auth_url", "trust_bundle")}
        raw["agents"] = {("database_backup" if role == "database-backup" else role):
                         {key: configurations[role][key] for key in ("aic", "endpoint", "cert", "key")}
                         for role in deployment.ROLES}
        raw["agents"]["leader"] = leader["leader"]
        raw["unrelated_secret"] = "this-field-must-not-be-copied"
        identity_file = source / "raw-identities.json"
        deployment.save(identity_file, raw)
        with patch.object(deployment.subprocess, "run", side_effect=AssertionError("No native setup or network")):
            deployment.prepare(self.output, "isolated-fixture", self.ports, reply_port=49090,
                               mode="seven", identity_file=identity_file)
        deployment.load_deployment(self.output / "deployment.json")
        for file in (self.output / "platform-source").glob("*.json"):
            config = json.loads(file.read_text(encoding="utf-8"))
            self.assertNotIn("agents", config)
            self.assertNotIn("unrelated_secret", config)
        for role in (*deployment.ROLES, "coordinator"):
            self.assertEqual((self.output / "domains" / role / "key.pem").read_bytes(),
                             (source / role / "key.pem").read_bytes())
        host = (self.output / "domains/coordinator/config.json").read_text(encoding="utf-8")
        self.assertNotIn(str(source / "database/key.pem"), host)

    def test_posix_permissions_keep_host_parent_private_and_bind_roots_readable_by_image_uid(self):
        self.prepare("seven")
        with patch.object(Path, "chmod", autospec=True) as chmod:
            deployment.protect_output(self.output)
        modes = {call.args[0]: call.args[1] for call in chmod.call_args_list}
        self.assertEqual(modes[self.output], 0o700)
        self.assertEqual(modes[self.output / "domains"], 0o700)
        self.assertEqual(modes[self.output / "compose.env"], 0o600)
        self.assertEqual(modes[self.output / "domains/coordinator"], 0o700)
        self.assertEqual(modes[self.output / "domains/coordinator/key.pem"], 0o600)
        for role in deployment.ROLES:
            directory = self.output / "domains" / role
            self.assertEqual(modes[directory], 0o755)
            self.assertEqual(modes[directory / "key.pem"], 0o644)
            # UID 65534 needs read/traverse at the mounted /domain root; host parents remain private.
            self.assertEqual(modes[directory] & 0o005, 0o005)
            self.assertEqual(modes[directory / "key.pem"] & 0o004, 0o004)


if __name__ == "__main__":
    unittest.main()
