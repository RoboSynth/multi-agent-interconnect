"""Verification boundary regression; does not connect to or modify the target."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.partners import VerificationPartner


class VerificationFreshWorkflows(unittest.IsolatedAsyncioTestCase):
    async def verify_original(self, args, *, receipt_status=None, receipt_error=False):
        calls = []
        def receipt(request):
            calls.append((request.method, request.url.path))
            if receipt_error:
                raise httpx.ConnectError("mock unavailable", request=request)
            return httpx.Response(receipt_status, json={"order_id": "existing-order", "order_api_version": "v2"})
        client = httpx.AsyncClient(transport=httpx.MockTransport(receipt)) if receipt_status is not None else None
        with patch("business.load.OrderObserver") as observer:
            observer.return_value.observe = AsyncMock(return_value={"passed": True, "completed_workflows": 10})
            with patch("incident.partners.httpx.AsyncClient", **(
                    {"return_value": client} if client else {"side_effect": AssertionError("unexpected receipt request")})):
                result = await VerificationPartner("verifier", allowed_callers=["coordinator"]).execute({
                    "incident_id": "inc-original", "logical_task_id": "verify-original", "kind": "verify",
                    "tool": "incident.verification", "args": args}, "coordinator")
            if result["status"] == "ok":
                observer.assert_called_once_with("http://127.0.0.1:8088", run_id="inc-original-verify-original", expected_api_version="v2")
                observer.return_value.observe.assert_awaited_once_with(duration=30, min_complete=10)
            else:
                observer.assert_not_called()
        return result, calls

    async def test_default_has_no_original_intent_to_resolve(self):
        result, calls = await self.verify_original({})
        facts = {fact["key"]: fact["value"] for fact in result["facts"]}
        self.assertTrue(facts["business_recovered"])
        self.assertTrue(facts["service_recovered"])
        self.assertTrue(facts["original_request_resolved"])
        self.assertFalse(facts["manual_required"])
        self.assertEqual(facts["original_request_resolution"], "not_required")
        self.assertEqual(calls, [])

    async def test_unknown_without_key_keeps_manual_but_still_verifies_fresh_service(self):
        for key in (None, ""):
            with self.subTest(key=key):
                result, calls = await self.verify_original({"original_request_unknown": True, "original_request_key": key})
                facts = {fact["key"]: fact["value"] for fact in result["facts"]}
                self.assertFalse(facts["business_recovered"])
                self.assertTrue(facts["service_recovered"])
                self.assertFalse(facts["original_request_resolved"])
                self.assertTrue(facts["manual_required"])
                self.assertEqual(facts["original_request_resolution"], "unknown_missing_key")
                self.assertEqual(calls, [])

    async def test_existing_key_automatically_queries_receipt_without_rebuilding_request(self):
        for status, resolution in ((200, "resolved_receipt"), (404, "unknown_receipt_missing"),
                                   (503, "unknown_receipt_unavailable")):
            with self.subTest(status=status):
                result, calls = await self.verify_original({"original_request_key": "request-one"}, receipt_status=status)
                facts = {fact["key"]: fact["value"] for fact in result["facts"]}
                self.assertEqual(calls, [("GET", "/receipts/request-one")])
                self.assertEqual(facts["original_request_resolution"], resolution)
                self.assertIs(facts["business_recovered"], status == 200)
                self.assertIs(facts["original_request_resolved"], status == 200)
                self.assertIs(facts["manual_required"], status != 200)
                self.assertTrue(facts["service_recovered"])

    async def test_unavailable_receipt_remains_unknown_without_skipping_service_observation(self):
        result, calls = await self.verify_original({"original_request_unknown": True,
            "original_request_key": "request-one"}, receipt_status=200, receipt_error=True)
        facts = {fact["key"]: fact["value"] for fact in result["facts"]}
        self.assertFalse(facts["business_recovered"])
        self.assertTrue(facts["service_recovered"])
        self.assertEqual(facts["original_request_resolution"], "unknown_receipt_unavailable")
        self.assertEqual(calls, [("GET", "/receipts/request-one")])

    async def test_unknown_flag_is_strict_boolean_at_the_verifier_boundary(self):
        for value in ("false", 0, 1, None):
            with self.subTest(value=value):
                result, calls = await self.verify_original({"original_request_unknown": value})
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(calls, [])

    async def test_two_verification_tasks_use_disjoint_order_namespaces(self):
        summary = {"passed": True, "completed_workflows": 10, "duration_seconds": 30}
        with patch("business.load.OrderObserver") as observer:
            observer.return_value.observe = AsyncMock(return_value=summary)
            partner = VerificationPartner("verifier", allowed_callers=["coordinator"])
            for logical_task_id in ("verify-first", "verify-after-second-repair"):
                result = await partner.execute({"schema_version": "ifc/1.0", "incident_id": "inc-repeat",
                    "logical_task_id": logical_task_id, "kind": "verify", "tool": "incident.verification", "args": {}}, "coordinator")
                recovered = next(f["value"] for f in result["facts"] if f["key"] == "business_recovered")
                self.assertTrue(recovered)
            namespaces = [call.kwargs["run_id"] for call in observer.call_args_list]
            first_keys = {f"load-{namespaces[0]}-{i:06d}" for i in range(10)}
            second_keys = {f"load-{namespaces[1]}-{i:06d}" for i in range(10)}
            self.assertTrue(first_keys.isdisjoint(second_keys))
            for call in observer.return_value.observe.call_args_list:
                self.assertEqual(call.kwargs, {"duration": 30, "min_complete": 10})


if __name__ == "__main__":
    unittest.main()
