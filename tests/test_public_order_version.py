"""Mock HTTP contract regressions; no real resources, model, or elapsed window proof."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

import httpx
import business.load as load
from business.load import OrderObserver, VersionedClient
from incident.partners import VerificationPartner
import incident.partners as partners

REAL_SLEEP = asyncio.sleep
REAL_CLIENT = httpx.AsyncClient


class Clock:
    def __init__(self):
        self.at = 1000.0

    def monotonic(self):
        return self.at

    async def sleep(self, seconds):
        self.at += max(0, seconds)
        await REAL_SLEEP(0)


def body_for(phase):
    if phase in {"create", "resolve"}:
        return {"order_id": "order-a"}
    return {"order": {"id": "order-a", "status": "CANCELLED" if phase == "cancel" else "CREATED"}}


class PublicOrderVersionTests(unittest.IsolatedAsyncioTestCase):
    async def observe(self, handler, *, duration=1, state=None, expected="v2"):
        clock = Clock()
        async with REAL_CLIENT(transport=httpx.MockTransport(handler)) as client:
            observer = OrderObserver("http://mock-order", run_id="same-intent", client=client,
                state=state, expected_api_version=expected)
            with patch.object(load, "time", SimpleNamespace(monotonic=clock.monotonic)), patch.object(load, "asyncio", SimpleNamespace(sleep=clock.sleep)):
                return await observer.observe(duration=duration, min_complete=10)

    async def test_wrong_missing_or_malformed_success_never_advances_any_phase(self):
        for phase in ("create", "query", "cancel", "resolve"):
            for shape in ("v1", "missing", "array", "invalid_json"):
                with self.subTest(phase=phase, shape=shape):
                    intent = {"request_key": "original-key", "operation_key": "original-key-cancel", "item": "pen",
                        "quantity": 1, "phase": phase, "was_unknown": phase == "resolve"}
                    if phase in {"query", "cancel"}:
                        intent["order_id"] = "order-a"
                    if phase == "resolve":
                        intent.update(unknown_key="original-key", resume_phase="create")
                    state = {"pending": [intent], "completed": [], "next_index": 1}
                    original = deepcopy(state)
                    def handler(request):
                        body = body_for(phase)
                        if shape == "v1":
                            body["order_api_version"] = "v1"
                        if shape == "array":
                            body = [body]
                        return httpx.Response(200, content=b"not-json") if shape == "invalid_json" else httpx.Response(200, json=body)
                    summary = await self.observe(handler, state=state)
                    self.assertEqual(summary["failed"], 1)
                    self.assertEqual(summary["state"], original)

    async def test_v2_ten_complete_workflows_pass(self):
        def handler(request):
            phase = "create" if request.method == "POST" and request.url.path == "/orders" else "cancel" if request.url.path.endswith("/cancel") else "query"
            return httpx.Response(200, json={**body_for(phase), "order_api_version": "v2"})
        summary = await self.observe(handler, duration=30)
        self.assertTrue(summary["passed"])
        self.assertEqual((summary["success"], summary["completed_workflows"], summary["unresolved_intents"]), (30, 10, 0))

    async def test_unknown_create_and_wrong_receipt_keep_the_same_original_key(self):
        calls, receipts = [], 0
        def handler(request):
            nonlocal receipts
            calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
            if request.method == "POST" and request.url.path == "/orders":
                raise httpx.ReadTimeout("mock lost response", request=request)
            if request.url.path.startswith("/receipts/"):
                receipts += 1
                return httpx.Response(200, json={**body_for("resolve"), "order_api_version": "v1" if receipts == 1 else "v2"})
            phase = "cancel" if request.url.path.endswith("/cancel") else "query"
            return httpx.Response(200, json={**body_for(phase), "order_api_version": "v2"})
        summary = await self.observe(handler, duration=5)
        self.assertEqual([e["outcome"] for e in summary["events"]], ["unknown", "failed", "success", "success", "success"])
        original_key = calls[0][2]["request_key"]
        self.assertEqual(calls[1][1], "/receipts/" + original_key)
        self.assertEqual(calls[2][1], "/receipts/" + original_key)
        self.assertEqual(summary["state"]["next_index"], 1)
        self.assertEqual(summary["state"]["completed"][0]["request_key"], original_key)
        self.assertEqual(summary["resolved_unknown_intents"], 1)
        self.assertEqual(summary["unresolved_intents"], 0)

    async def test_503_without_version_preserves_unknown_semantics(self):
        summary = await self.observe(lambda request: httpx.Response(503, json={"outcome": "unknown"}))
        self.assertEqual((summary["unknown"], summary["failed"]), (1, 0))
        self.assertEqual(summary["state"]["pending"][0]["phase"], "resolve")
        self.assertEqual(summary["state"]["next_index"], 1)

    async def test_legacy_generic_observer_can_explicitly_remain_unversioned(self):
        def handler(request):
            phase = "create" if request.url.path == "/orders" else "cancel" if request.url.path.endswith("/cancel") else "query"
            return httpx.Response(200, json=body_for(phase))
        summary = await self.observe(handler, duration=3, expected=None)
        self.assertEqual((summary["success"], summary["completed_workflows"]), (3, 1))

    async def test_product_verifier_rejects_v1_and_missing_public_contract(self):
        for version in ("v1", None):
            with self.subTest(version=version):
                def handler(request):
                    body = body_for("create")
                    if version is not None:
                        body["order_api_version"] = version
                    return httpx.Response(200, json=body)
                clock = Clock()
                factory = lambda *a, **k: REAL_CLIENT(transport=httpx.MockTransport(handler))
                with patch.object(partners.httpx, "AsyncClient", side_effect=factory), patch.object(load, "time", SimpleNamespace(monotonic=clock.monotonic)), patch.object(load, "asyncio", SimpleNamespace(sleep=clock.sleep)):
                    result = await VerificationPartner("verifier", base_url="http://mock-order", allowed_callers=["coordinator"]).execute({
                        "incident_id": "version-check", "logical_task_id": "verify", "kind": "verify", "tool": "incident.verification"}, "coordinator")
                facts = {f["key"]: f["value"] for f in result["facts"]}
                self.assertFalse(facts["business_recovered"])
                self.assertEqual((facts["order_observation"]["failed"], facts["order_observation"]["completed_workflows"]), (30, 0))

    async def test_original_receipt_with_wrong_version_stays_unresolved(self):
        factory = lambda *a, **k: REAL_CLIENT(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={"order_id": "order-a", "order_api_version": "v1"})))
        with patch.object(partners.httpx, "AsyncClient", side_effect=factory), patch.object(load, "OrderObserver") as observer:
            observer.return_value.observe = AsyncMock(return_value={"passed": True, "completed_workflows": 10})
            result = await VerificationPartner("verifier", base_url="http://mock-order", allowed_callers=["coordinator"]).execute({
                "incident_id": "version-check", "logical_task_id": "verify", "kind": "verify", "tool": "incident.verification",
                "args": {"original_request_key": "same-original-key", "original_request_unknown": True}}, "coordinator")
            observer.assert_called_once_with("http://mock-order", run_id="version-check-verify", expected_api_version="v2")
        facts = {f["key"]: f["value"] for f in result["facts"]}
        self.assertTrue(facts["service_recovered"])
        self.assertFalse(facts["business_recovered"])
        self.assertFalse(facts["original_request_resolved"])
        self.assertTrue(facts["manual_required"])

    async def test_existing_evaluator_import_uses_the_same_shared_client(self):
        from eval.observation import VersionedClient as EvaluatorClient
        self.assertIs(EvaluatorClient, VersionedClient)


if __name__ == "__main__":
    unittest.main()
