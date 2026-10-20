"""Review packaging/startup contracts; no Docker mutations in these tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review", ROOT / "deploy/review.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewEntryTests(unittest.TestCase):
    def test_fresh_install_generates_secrets_and_preserves_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(review, "ROOT", root), patch.object(review, "STATE", root / "runtime/review"):
                first = review.prepare()
                route = review.STATE / "route/route.conf"
                route.write_text("set $order_upstream app-v1:8000;\n")
                approval = (review.STATE / "approval.env").read_bytes()
                second = review.prepare()
                self.assertEqual(first, second)
                self.assertEqual(approval, (review.STATE / "approval.env").read_bytes())
                self.assertIn("app-v1", route.read_text())
                self.assertEqual(len({first[key] for key in review.SECRET_NAMES}), 4)
                self.assertTrue(all(len(first[key]) >= 32 for key in review.SECRET_NAMES))

    def test_invalid_ports_scope_and_secrets_fail_before_docker(self):
        for setting in ("WORKBENCH_PORT=18088", "COMPOSE_PROJECT_NAME=../../other",
                        "ORDER_BIND=0.0.0.0", "APP_ADMIN_TOKEN=example"):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".env").write_text(setting + "\n")
                with patch.object(review, "ROOT", root), patch.object(review, "STATE", root / "runtime/review"):
                    with self.assertRaises(ValueError):
                        review.prepare()

    def test_only_workbench_receives_docker_socket_and_ports_are_loopback(self):
        import yaml
        doc = yaml.safe_load((ROOT / "deploy/review.yml").read_text())
        self.assertEqual(doc["services"]["workbench"]["ports"], ["127.0.0.1:${WORKBENCH_PORT:-18766}:8765"])
        self.assertEqual(doc["services"]["review-ui"]["network_mode"], "service:workbench")
        self.assertNotIn("ports", doc["services"]["review-ui"])
        for role, service in doc["services"].items():
            if role != "workbench":
                self.assertFalse(any("docker.sock" in mount for mount in service.get("volumes", [])))

    def test_existing_active_incident_blocks_fault_injection(self):
        with patch.object(review, "wait_ready", return_value=("http://127.0.0.1", {"incident": {"status": "running"}})), \
                patch.object(review, "private_write") as write:
            with self.assertRaisesRegex(RuntimeError, "active"):
                review.demo({})
            write.assert_not_called()

    def test_powershell_and_shell_default_to_same_driver(self):
        for script in ("up.sh", "up.ps1"):
            self.assertIn("review.py", (ROOT / "deploy" / script).read_text())


if __name__ == "__main__":
    unittest.main()
