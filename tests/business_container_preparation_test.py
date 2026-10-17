"""Offline generated mounts and unknown-intent boundaries; no resource mutation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

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
