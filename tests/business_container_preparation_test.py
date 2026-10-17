"""Offline generated mounts and unknown-intent boundaries; no resource mutation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("container_prepare", ROOT / "deploy/prepare_agents.py")
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)
from eval.unknown_receipt_experiment import resolve_unknown


class ContainerPreparationTests(unittest.TestCase):
    def test_each_mount_contains_only_its_own_resource_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "output"
            source.mkdir()
            for name in ("cert.pem", "key.pem", "trust.pem"):
                (source / name).write_text("fixture path copy only; not a certificate", encoding="utf-8")
            for role in ("application", "verification", "database", "database-backup", "ops"):
                config = {"aic": "fixture-" + role, "endpoint": "amqps://fixture.invalid:5671",
                    "allowed_leaders": ["fixture-leader"], "cert": str(source / "cert.pem"),
                    "key": str(source / "key.pem"), "trust_bundle": str(source / "trust.pem")}
                if role == "database-backup":
                    config["aic"] = None
                (source / (role + ".json")).write_text(json.dumps(config), encoding="utf-8")
            business = root / "business.env"
            business.write_text("POSTGRES_PASSWORD=" + "admin-only-" * 4 + "\nORDERS_DB_PASSWORD=" + "orders-only-" * 4
                                + "\nAPP_ADMIN_TOKEN=" + "app-only-" * 4 + "\n", encoding="utf-8")
            approval = root / "approval.env"
            approval.write_text("INCIDENT_APPROVAL_SECRET=" + "approval-" * 5 + "\n", encoding="utf-8")
            result = preparation.prepare(source, output, business, approval, "fixture-container")
            self.assertEqual(result["pending_identities"], ["database-backup"])
            self.assertFalse((output / "database-backup").exists())
            self.assertEqual((output / "application/domain.env").read_text(), "APP_ADMIN_TOKEN=" + "app-only-" * 4 + "\n")
            db = (output / "database/domain.env").read_text()
            ops = (output / "ops/domain.env").read_text()
            self.assertIn("@postgres:5432/orders", db)
            for domain_text in (db, ops):
                self.assertNotIn("admin-only-", domain_text)
                self.assertNotIn("orders-only-", domain_text)
                self.assertNotIn("app-only-", domain_text)
            self.assertNotIn("DATABASE_URI", ops)
            self.assertFalse((output / "verification/domain.env").exists())
            with self.assertRaises(ValueError):
                preparation.prepare(source, output, business, approval, "fixture-container")

    def test_opt_in_six_domains_and_host_leader_keep_credentials_and_scope_separate(self):
        # Files are copy fixtures, not issued certificates or live identities.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "output"
            source.mkdir()
            identities = {}
            for role in ("application", "verification", "database", "database-backup", "ops", "onboarding", "coordinator"):
                material = source / role
                material.mkdir()
                for name in ("cert.pem", "key.pem", "trust.pem"):
                    (material / name).write_text(role + " fixture " + name, encoding="utf-8")
                identities[role] = {"aic": "fixture-" + role,
                    "endpoint": "amqps://fixture.invalid:5671/acps?inbox=inbox_fixture-" + role,
                    "cert": str(material / "cert.pem"), "key": str(material / "key.pem"),
                    "trust_bundle": str(material / "trust.pem")}
            identities["database-backup"]["aic"] = "aaa-backup-sorts-before-main"
            for role in ("application", "verification", "database", "database-backup", "ops", "onboarding"):
                config = {**identities[role], "allowed_leaders": [identities["coordinator"]["aic"]],
                    "mq_auth_url": "https://acl.invalid", "discovery_url": "https://discovery.invalid/query"}
                if role == "onboarding":
                    config["env_file"] = "do-not-copy-resource-env"
                    config["servers"] = {"do-not-copy": {}}
                (source / (role + ".json")).write_text(json.dumps(config), encoding="utf-8")
            coordinator = {"leader": identities["coordinator"],
                "trust_bundle": identities["coordinator"]["trust_bundle"],
                "discovery_url": "https://discovery.invalid/query", "mq_auth_url": "https://acl.invalid",
                "skills": {"application": "incident.application", "database": "db.observe", "ops": "ops.observe",
                    "verification": "incident.verification", "onboarding": "aip.onboarding.check"},
                "servers": {"resource-config-must-not-leak": {}}}
            (source / "coordinator.json").write_text(json.dumps(coordinator), encoding="utf-8")
            business, approval = root / "business.env", root / "approval.env"
            business.write_text("POSTGRES_PASSWORD=" + "admin-only-" * 4 + "\nORDERS_DB_PASSWORD=" + "orders-only-" * 4
                + "\nAPP_ADMIN_TOKEN=" + "app-only-" * 4 + "\nBRIDGE_DB_PASSWORD=" + "bridge-only-" * 4 + "\n", encoding="utf-8")
            approval.write_text("INCIDENT_APPROVAL_SECRET=" + "approval-only-" * 4 + "\n", encoding="utf-8")
            report = preparation.prepare(source, output, business, approval, "new-isolated-profile",
                include_onboarding=True, include_coordinator=True, ops_service="app-v2")
            self.assertEqual(len(report["prepared"]), 6)
            self.assertFalse(report["network_attempted"])
            self.assertFalse(report["certificate_validation_performed"])
            self.assertFalse(report["ready_for_live_start"])
            onboard = json.loads((output / "onboarding/config.json").read_text())
            self.assertEqual(onboard["role"], "onboarding")
            self.assertNotIn("env_file", onboard)
            self.assertNotIn("servers", onboard)
            self.assertFalse((output / "onboarding/domain.env").exists())
            host = json.loads((output / "coordinator/config.json").read_text())
            self.assertNotIn("servers", host)
            self.assertEqual(host["initial_participant_aics"], {"database": "fixture-database"})
            self.assertEqual(set(host["trusted_participant_aics"]["database"]),
                             {"fixture-database", "aaa-backup-sorts-before-main"})
            self.assertEqual(host["term_namespace"], "new-isolated-profile/orders")
            self.assertTrue(Path(host["term_journal_path"]).is_relative_to(output / "coordinator"))
            self.assertEqual((output / "coordinator/key.pem").read_text(), "coordinator fixture key.pem")
            for role in report["prepared"]:
                self.assertEqual((output / role / "key.pem").read_text(), role + " fixture key.pem")
            policy = yaml.safe_load((output / "ops/policy.yaml").read_text(encoding="utf-8"))
            self.assertEqual(policy["resources"]["compose_project"], "new-isolated-profile")
            self.assertEqual(policy["resources"]["compose_service"], "app-v2")
            self.assertEqual(policy["resources"]["container_name"], "new-isolated-profile-app-v2-1")
            self.assertEqual(policy["tools"]["ops.restart"]["input_schema"]["properties"], {})
            self.assertEqual(policy["tools"]["ops.restart"]["fixed_arguments"]["container_id"],
                             "new-isolated-profile-app-v2-1")
            self.assertIn("com.docker.compose.project=new-isolated-profile",
                          policy["tools"]["ops.containers"]["fixed_arguments"]["filters"]["label"])
            for role in ("database", "database-backup"):
                bridge = json.loads((output / role / "bridge.json").read_text())
                self.assertEqual(bridge["ledger_path"], "/state/operations.sqlite")
                self.assertEqual(bridge["ledger_domain"], "database")
            host_text = (output / "coordinator/config.json").read_text()
            for secret in ("admin-only-", "orders-only-", "app-only-", "bridge-only-"):
                self.assertNotIn(secret, host_text)

    def test_direct_domain_configs_reject_reused_aics_before_private_reads(self):
        for duplicate_role in ("verification", "onboarding"):
            with self.subTest(duplicate_role=duplicate_role), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "source"
                source.mkdir()
                roles = ["application", "verification", "database", "database-backup", "ops"]
                if duplicate_role == "onboarding":
                    roles.append("onboarding")
                for role in roles:
                    config = {"aic": "fixture-application" if role == duplicate_role else "fixture-" + role,
                              "endpoint": "amqps://fixture.invalid:5671"}
                    (source / (role + ".json")).write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "distinct AICs"):
                    preparation.prepare(source, root / "output", root / "missing-business.env",
                        root / "missing-approval.env", "new-profile", include_onboarding=duplicate_role == "onboarding")
                self.assertFalse((root / "output").exists())

    def test_direct_host_leader_cannot_reuse_a_domain_aic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for role in ("application", "verification", "database", "database-backup", "ops"):
                (source / (role + ".json")).write_text(json.dumps({"aic": "fixture-" + role,
                    "endpoint": "amqps://fixture.invalid:5671"}), encoding="utf-8")
            (source / "coordinator.json").write_text(json.dumps({"leader": {"aic": "fixture-database"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Coordinator.*distinct AICs"):
                preparation.prepare(source, root / "output", root / "missing-business.env",
                    root / "missing-approval.env", "new-profile", include_coordinator=True)
            self.assertFalse((root / "output").exists())

    def test_invalid_managed_service_fails_before_reading_private_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                preparation.prepare(root / "missing-source", root / "output", root / "missing.env",
                    root / "missing-approval.env", "new-profile", ops_service="../other-project")
            self.assertFalse((root / "output").exists())


class UnknownReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_abstains_without_a_new_request(self):
        client = AsyncMock()
        result = await resolve_unknown(client, "http://fixture.invalid", None)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["manual_required"])
        self.assertFalse(result["new_request_created"])
        client.get.assert_not_awaited()
        client.post.assert_not_awaited()

    async def test_missing_receipt_stays_unknown(self):
        client = AsyncMock()
        client.get.return_value.status_code = 404
        result = await resolve_unknown(client, "http://fixture.invalid", "original-key")
        self.assertEqual(result["status"], "unknown")
        client.post.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
