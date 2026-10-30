"""Exercise the deployment verifier with the real order observer and HTTP transport."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deployment_verify", ROOT / "deploy/verify.py")
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


class DeploymentVerificationTests(unittest.TestCase):
    def run_case(self, *, before="v2", after="v2", order_version="v2", unknown_once=False):
        calls, clock = [], [0.0]
        orders, dropped = {}, [False]

        def handler(request):
            calls.append((request.method, request.url.path))
            if request.url.path == "/ready":
                version = before if len(calls) == 1 else after
                return httpx.Response(200, json={"ok": True, "api_version": version})
            if unknown_once and not dropped[0]:
                dropped[0] = True
                raise httpx.ReadTimeout("fixture timeout", request=request)
            body = {"order_api_version": order_version}
            if request.method == "POST" and request.url.path == "/orders":
                key = json.loads(request.content)["request_key"]
                orders.setdefault(key, str(len(orders)))
                body["order_id"] = orders[key]
            else:
                order_id = request.url.path.split("/")[2]
                if request.url.path.endswith("/cancel"):
                    body["order"] = {"id": order_id, "status": "CANCELLED"}
                elif request.url.path.startswith("/receipts/"):
                    return httpx.Response(404, json={})
                else:
                    body["order"] = {"id": order_id}
            return httpx.Response(200, json=body)

        async def sleep(seconds):
            clock[0] += seconds

        async def execute(output):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await verification.verify("http://orders.test", output, client=client, run_id="fixture")

        base = ROOT / "artifacts/deployment-verify-development-20261018/fixtures"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            output = Path(temp) / "new-run"
            # The observer still executes all 30 HTTP requests and its intent state
            # machine; only its wall clock and one-second waits are replaced.
            with patch("business.load.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("business.load.asyncio.sleep", side_effect=sleep):
                result = asyncio.run(execute(output))
            records = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in output.iterdir()}
            return result, records, calls

    def test_valid_v2_runs_thirty_requests_and_ten_original_workflows(self):
        result, records, calls = self.run_case()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(calls), 32)
        self.assertEqual(records["h00.json"]["completed_workflows"], 10)
        self.assertEqual(records["h00.json"]["duration_seconds"], 30)
        self.assertEqual(records["state.json"]["pending"], [])

    def test_v1_ready_stops_before_any_order_is_submitted(self):
        result, records, calls = self.run_case(before="v1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(calls, [("GET", "/ready")])
        self.assertNotIn("h00.json", records)

    def test_v1_order_body_cannot_pass_healthy_ready_probes(self):
        result, records, _ = self.run_case(order_version="v1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(records["h00.json"]["failed"], 30)
        self.assertTrue(records["state.json"]["pending"])

    def test_changed_after_ready_preserves_the_successful_business_window(self):
        result, records, _ = self.run_case(after="v1")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(records["h00.json"]["passed"])
        self.assertEqual(records["readiness.json"][1]["api_version"], "v1")

    def test_timeout_keeps_original_key_and_rejects_unknown_window(self):
        result, records, _ = self.run_case(unknown_once=True)
        self.assertEqual(result["status"], "failed")
        self.assertGreater(records["h00.json"]["unknown"], 0)
        self.assertEqual({event["request_key"] for event in records["h00.json"]["events"][:3]},
                         {"load-fixture-000000"})

    def test_output_is_not_overwritten_and_origin_excludes_credentials(self):
        for value in ("http://user:password@localhost", "http://localhost/orders", "ftp://localhost",
                      "http://localhost?token=secret", "http://localhost:65536"):
            with self.assertRaises(ValueError):
                verification.order_origin(value)
        self.assertEqual(verification.order_origin("http://[::1]:48088/"), "http://[::1]:48088")
        with self.assertRaises(FileExistsError):
            asyncio.run(verification.verify("http://localhost:48088", ROOT / "deploy"))

    def test_manifest_cli_uses_its_order_port_without_starting_resources(self):
        with patch.object(verification, "load_deployment", return_value={"ports": {"order": 49088}}) as load, \
                patch.object(verification, "verify", new=Mock(return_value="fixture-awaitable")) as verify, \
                patch.object(verification.asyncio, "run", return_value={"status": "passed"}) as run, \
                patch("sys.argv", ["verify.py", "--deployment-file", "deployment.json", "--output", "new-evidence"]), \
                patch("builtins.print"):
            self.assertEqual(verification.main(), 0)
        load.assert_called_once_with(Path("deployment.json"))
        verify.assert_called_once_with("http://127.0.0.1:49088", Path("new-evidence"))
        run.assert_called_once_with("fixture-awaitable")


if __name__ == "__main__":
    unittest.main()
