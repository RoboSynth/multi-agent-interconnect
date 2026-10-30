"""Fake readiness only, with no HTTP, source keys, SDK identities or systemd."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("wait_cloud_helper", HERE / "wait_cloud_workbench.py")
waiter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(waiter)


class WaitTests(unittest.IsolatedAsyncioTestCase):
    async def test_delegates_same_host_config_to_existing_readiness_without_launching(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host = root / "host.json"
            settings = dict(control_directory="private/control", port=8877)
            host.write_text(json.dumps(settings))
            calls = []
            async def ready(actual, *, root):
                calls.append((actual, root))
                return dict(status="running", pid=123, session_id="fake-host")
            result = await waiter.wait_ready(root, host, waiter=ready)
            self.assertEqual(calls, [(settings, root)])
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["identity_consumers_started"], 0)

    async def test_readiness_failure_remains_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host = root / "host.json"
            host.write_text("{}")
            async def failed(settings, *, root):
                raise TimeoutError("fake not ready")
            with self.assertRaises(TimeoutError):
                await waiter.wait_ready(root, host, waiter=failed)

    def test_default_cli_does_not_read_config_or_query(self):
        with patch.object(waiter, "wait_ready", side_effect=AssertionError("must not query")):
            self.assertEqual(waiter.main([]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
