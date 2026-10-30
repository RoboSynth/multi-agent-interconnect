"""Intents left by intermediate symptom checks are finished outside the scored window.

Reproduces the local60 F06/F07 shape offline: a quick check during a write
failure leaves one unknown create; after repair the final verification must
finish it with its original key and still score a fresh 30-second window.
"""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
import httpx
import business.load as load
from incident.partners import VerificationPartner
from incident.contracts import TaskProduct


class OrderApi:
    def __init__(self):
        self.writes_ok, self.orders, self.receipts, self.creates = True, {}, {}, []

    def body(self, value, status=200):
        return httpx.Response(status, json={"order_api_version": "v2", **value})

    def __call__(self, request):
        path, method = request.url.path, request.method
        if method == "POST" and path == "/orders":
            key = json.loads(request.content)["request_key"]
            if not self.writes_ok:
                return httpx.Response(503, json={"detail": "read-only"})
            if key not in self.receipts:
                order = {"id": str(uuid.uuid4()), "request_key": key, "status": "CREATED"}
                self.orders[order["id"]] = order
                self.creates.append(key)
                self.receipts[key] = {"operation_key": key, "operation_kind": "create", "outcome": "committed",
                                      "order_id": order["id"], "order": dict(order)}
            return self.body(self.receipts[key])
        if method == "GET" and path.startswith("/receipts/"):
            key = path.split("/receipts/", 1)[1]
            return self.body(self.receipts[key]) if key in self.receipts else httpx.Response(404, json={"detail": "none"})
        if method == "GET" and path.startswith("/orders/"):
            return self.body({"order": self.orders[path.split("/")[2]]})
        if method == "POST" and path.endswith("/cancel"):
            order = self.orders[path.split("/")[2]]
            order["status"] = "CANCELLED"
            return self.body({"order": dict(order), "operation_key": json.loads(request.content)["operation_key"]})
        return httpx.Response(404)


class CarriedIntentTests(unittest.IsolatedAsyncioTestCase):
    def wire_roundtrip(self, result):
        # Match the worker's serialization and the transport's receiving schema.
        sent = TaskProduct.model_validate(result).model_dump(exclude_none=True)
        received = TaskProduct.model_validate(json.loads(json.dumps(sent)))
        return {fact.key: fact.value for fact in received.facts}

    async def test_final_without_pending_symptoms_survives_worker_serialization(self):
        for symptom_state in (None, {}, {"pending": []}):
            with self.subTest(symptom_state=symptom_state):
                api = OrderApi()
                real = httpx.AsyncClient
                fake_httpx = SimpleNamespace(
                    AsyncClient=lambda **_: real(transport=httpx.MockTransport(api)),
                    TransportError=httpx.TransportError)
                partner = VerificationPartner("verifier", base_url="http://orders.test",
                                              allowed_callers=["leader"])
                if symptom_state is not None:
                    partner.symptom_states["inc"] = symptom_state
                with patch.object(load, "httpx", fake_httpx), \
                        patch.object(load.asyncio, "sleep", new=AsyncMock()):
                    # A second task on the same worker must remain usable.
                    for task_id in ("final-1", "final-2"):
                        result = await partner.execute({
                            "incident_id": "inc", "logical_task_id": task_id,
                            "kind": "verify", "tool": "incident.verification"}, "leader")
                        facts = self.wire_roundtrip(result)
                        self.assertNotIn("carried_symptom_intents", facts)
                        self.assertTrue(facts["business_recovered"])
                        observation = facts["order_observation"]
                        self.assertEqual((observation["requests"], observation["success"],
                                          observation["completed_workflows"]), (30, 30, 10))
                self.assertEqual(len(api.creates), 20)

    async def run_incident(self, *, repaired):
        api = OrderApi()
        real = httpx.AsyncClient
        fake_httpx = SimpleNamespace(AsyncClient=lambda **_: real(transport=httpx.MockTransport(api)),
                                     TransportError=httpx.TransportError)
        partner = VerificationPartner("verifier", base_url="http://orders.test", allowed_callers=["leader"])
        quick = {"incident_id": "inc", "logical_task_id": "quick", "kind": "observe", "tool": "incident.symptom_check"}
        with patch.object(load, "httpx", fake_httpx), patch.object(load.asyncio, "sleep", new=AsyncMock()):
            api.writes_ok = False
            check = await partner.execute(quick, "leader")
            api.writes_ok = repaired
            final = await partner.execute({**quick, "logical_task_id": "final", "kind": "verify",
                                           "tool": "incident.verification"}, "leader")
        return api, self.wire_roundtrip(check), self.wire_roundtrip(final)

    async def test_repaired_service_passes_and_carried_key_has_exactly_one_order(self):
        api, check, final = await self.run_incident(repaired=True)
        self.assertFalse(check["symptom_check_passed"])
        self.assertEqual(check["symptom_observation"]["unresolved_intents"], 1)
        carried = final["carried_symptom_intents"]
        self.assertEqual((carried["unresolved_intents"], carried["completed_workflows"], carried["failed"]), (0, 1, 0))
        window = final["order_observation"]
        # The scored window is fresh: no slot is spent on the earlier check's receipt.
        self.assertEqual((window["requests"], window["success"], window["unknown"], window["completed_workflows"]),
                         (30, 30, 0, 10))
        self.assertTrue(window["passed"])
        self.assertTrue(final["business_recovered"])
        carried_key = [key for key in api.creates if key.startswith("load-quick-")]
        self.assertEqual(len(carried_key), 1)  # Same original key; never a second order.

    async def test_unrecovered_service_leaves_intent_unresolved_and_fails(self):
        _, _, final = await self.run_incident(repaired=False)
        self.assertEqual(final["carried_symptom_intents"]["unresolved_intents"], 1)
        self.assertFalse(final["business_recovered"])


if __name__ == "__main__":
    unittest.main()
