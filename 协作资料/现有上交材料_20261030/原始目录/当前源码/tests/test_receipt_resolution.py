"""Real observer/partner with mock HTTP and a virtual clock; no resource or timing proof."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import httpx
import business.load as load
import incident.partners as partners

REAL_CLIENT = httpx.AsyncClient
REAL_SLEEP = asyncio.sleep
ORDER_ID = "9918f18c-01dd-4c32-aa67-868f37d63098"
OTHER_ID = "2512bbcd-9704-4a2d-ac25-036404332889"
CREATE_KEY = "receipt-resolution-original"
CANCEL_KEY = CREATE_KEY + "-cancel"


class Clock:
    def __init__(self):
        self.at = 1000.0

    def monotonic(self):
        return self.at

    async def sleep(self, duration):
        self.at += max(0, duration)
        await REAL_SLEEP(0)


def receipt(key=CREATE_KEY, *, kind="create", order_id=ORDER_ID, request_key=CREATE_KEY, changed=True):
    return {"order_api_version": "v2", "operation_key": key, "operation_kind": kind,
        "outcome": "committed", "order_id": order_id, "changed": changed,
        "order": {"id": order_id, "request_key": request_key, "item": "book", "quantity": 1,
                  "status": "CREATED" if kind == "create" else "CANCELLED"}}


def intent_state(phase="create"):
    intent = {"request_key": CREATE_KEY, "operation_key": CANCEL_KEY, "item": "book", "quantity": 1,
              "phase": phase, "was_unknown": False}
    if phase == "cancel":
        intent["order_id"] = ORDER_ID
    return {"pending": [intent], "completed": [], "next_index": 1}


class ReceiptResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def observe(self, handler, state, duration):
        self.assertTrue(Path(load.__file__).resolve().is_relative_to(ROOT))
        clock = Clock()
        async with REAL_CLIENT(transport=httpx.MockTransport(handler)) as client:
            observer = load.OrderObserver("http://mock-order", client=client, state=state,
                run_id="receipt-resolution", expected_api_version="v2")
            with patch.object(load, "time", SimpleNamespace(monotonic=clock.monotonic)), \
                    patch.object(load, "asyncio", SimpleNamespace(sleep=clock.sleep)):
                return await observer.observe(duration=duration, min_complete=1)

    async def test_unknown_create_rejects_wrong_receipts_then_resolves_the_same_original_key(self):
        invalid = {}
        invalid["wrong_key"] = {**receipt(), "operation_key": "some-other-operation"}
        invalid["uncommitted"] = {**receipt(), "outcome": "unknown"}
        invalid["malformed_id"] = {**receipt(), "order_id": "not-an-order-uuid"}
        invalid["different_nested_id"] = {**receipt(), "order": {**receipt()["order"], "id": OTHER_ID}}
        invalid["wrong_kind"] = receipt(kind="cancel", changed=False)
        for name, bad in invalid.items():
            with self.subTest(case=name):
                state, calls, lookups = intent_state(), [], []

                def handler(request):
                    calls.append((request.method, request.url.path,
                                  json.loads(request.content) if request.content else None))
                    if request.method == "POST" and request.url.path == "/orders":
                        raise httpx.ReadTimeout("mock response lost after commit", request=request)
                    if request.url.path.startswith("/receipts/"):
                        lookups.append(request.url.path)
                        self.assertEqual(state["pending"][0]["phase"], "resolve")
                        self.assertEqual(state["pending"][0]["request_key"], CREATE_KEY)
                        self.assertNotIn("order_id", state["pending"][0])
                        self.assertEqual(state["completed"], [])
                        return httpx.Response(200, json=bad if len(lookups) == 1 else receipt())
                    if request.method == "GET" and request.url.path == "/orders/" + ORDER_ID:
                        return httpx.Response(200, json={"order_api_version": "v2", "order": receipt()["order"]})
                    if request.url.path == "/orders/" + ORDER_ID + "/cancel":
                        return httpx.Response(200, json=receipt(CANCEL_KEY, kind="cancel"))
                    raise AssertionError("Unexpected request: " + request.url.path)

                result = await self.observe(handler, state, 5)
                self.assertEqual([row["outcome"] for row in result["events"]],
                                 ["unknown", "failed", "success", "success", "success"])
                self.assertEqual(lookups, ["/receipts/" + CREATE_KEY] * 2)
                creates = [row for row in calls if row[:2] == ("POST", "/orders")]
                self.assertEqual(creates, [("POST", "/orders", {"request_key": CREATE_KEY, "item": "book", "quantity": 1})])
                self.assertEqual((result["completed_workflows"], result["unresolved_intents"]), (1, 0))
                self.assertEqual(state["next_index"], 1)
                self.assertEqual(state["completed"][0]["order_id"], ORDER_ID)
                self.assertEqual(state["completed"][0]["request_key"], CREATE_KEY)

    async def test_unknown_cancel_rejects_other_order_then_accepts_same_key_unchanged_cancel(self):
        state, calls = intent_state("cancel"), []
        lookups = []

        def handler(request):
            calls.append((request.method, request.url.path))
            if request.method == "POST":
                self.assertEqual(request.url.path, "/orders/" + ORDER_ID + "/cancel")
                self.assertEqual(json.loads(request.content), {"operation_key": CANCEL_KEY})
                raise httpx.ReadTimeout("mock cancel response lost", request=request)
            lookups.append(request.url.path)
            self.assertEqual(request.url.path, "/receipts/" + CANCEL_KEY)
            self.assertEqual(state["completed"], [])
            self.assertEqual(state["pending"][0]["phase"], "resolve")
            self.assertEqual(state["pending"][0]["order_id"], ORDER_ID)
            return httpx.Response(200, json=receipt(CANCEL_KEY, kind="cancel",
                order_id=OTHER_ID if len(lookups) == 1 else ORDER_ID, changed=False))

        result = await self.observe(handler, state, 3)
        self.assertEqual([row["outcome"] for row in result["events"]], ["unknown", "failed", "success"])
        self.assertEqual(lookups, ["/receipts/" + CANCEL_KEY] * 2)
        self.assertEqual(len([row for row in calls if row[0] == "POST"]), 1)
        self.assertEqual((result["completed_workflows"], result["unresolved_intents"]), (1, 0))
        self.assertEqual(state["completed"][0]["order_id"], ORDER_ID)
        self.assertNotEqual(CREATE_KEY, CANCEL_KEY)

    async def test_valid_cancel_receipt_accepts_distinct_creation_key_and_changed_false(self):
        state = intent_state("cancel")
        state["pending"][0].update(phase="resolve", resume_phase="cancel", unknown_key=CANCEL_KEY, was_unknown=True)
        calls = []

        def handler(request):
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json=receipt(CANCEL_KEY, kind="cancel", changed=False))

        result = await self.observe(handler, state, 1)
        self.assertEqual(calls, [("GET", "/receipts/" + CANCEL_KEY)])
        self.assertEqual((result["success"], result["failed"], result["completed_workflows"]), (1, 0, 1))
        self.assertEqual(state["completed"][0]["request_key"], CREATE_KEY)

    async def test_real_partner_and_coordinator_keep_invalid_original_receipt_unresolved(self):
        from incident.coordinator.engine import IncidentCoordinator
        self.assertTrue(Path(partners.__file__).resolve().is_relative_to(ROOT))
        orders, original_calls, requests = {}, [], []

        def handler(request):
            requests.append((request.method, request.url.path))
            if request.url.path == "/receipts/" + CREATE_KEY:
                original_calls.append(request.url.path)
                return httpx.Response(200, json={**receipt(), "operation_key": "wrong-original-key"})
            if request.method == "POST" and request.url.path == "/orders":
                payload = json.loads(request.content)
                order_id = str(uuid.uuid5(uuid.NAMESPACE_URL, payload["request_key"]))
                orders[order_id] = payload["request_key"]
                return httpx.Response(200, json=receipt(payload["request_key"], order_id=order_id, request_key=payload["request_key"]))
            order_id = request.url.path.split("/")[2]
            self.assertIn(order_id, orders)
            if request.method == "GET":
                return httpx.Response(200, json={"order_api_version": "v2", "order":
                    receipt(orders[order_id], order_id=order_id, request_key=orders[order_id])["order"]})
            payload = json.loads(request.content)
            return httpx.Response(200, json=receipt(payload["operation_key"], kind="cancel", order_id=order_id,
                                                  request_key=orders[order_id]))

        partner = partners.VerificationPartner("verifier", base_url="http://mock-order", allowed_callers=["coordinator"])

        class Transport:
            async def call(self, payload):
                return await partner.execute(payload, "coordinator")

        clock = Clock()
        factory = lambda *args, **kwargs: REAL_CLIENT(transport=httpx.MockTransport(handler))
        with tempfile.TemporaryDirectory() as temporary, patch.object(partners.httpx, "AsyncClient", side_effect=factory), \
                patch.object(load, "time", SimpleNamespace(monotonic=clock.monotonic)), \
                patch.object(load, "asyncio", SimpleNamespace(sleep=clock.sleep)):
            coordinator = IncidentCoordinator(Transport(), temporary)
            state = coordinator.new("original order response lost", original_request_key=CREATE_KEY)
            facts = await coordinator._verify(state)
        self.assertTrue(facts["service_recovered"])
        self.assertFalse(facts["business_recovered"])
        self.assertFalse(facts["original_request_resolved"])
        self.assertTrue(facts["manual_required"])
        self.assertEqual(facts["original_request_resolution"], "unknown_receipt_unavailable")
        self.assertEqual(original_calls, ["/receipts/" + CREATE_KEY])
        self.assertEqual((facts["order_observation"]["success"], facts["order_observation"]["completed_workflows"]), (30, 10))
        self.assertEqual(len(requests), 31)


if __name__ == "__main__":
    unittest.main()
