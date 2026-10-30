"""HTTP contract tests and opt-in tests against the actual PostgreSQL target.

Set BUSINESS_TEST_DATABASE=1 plus the application-domain PG* environment to run
transaction tests. Contract test doubles never count as PostgreSQL acceptance.
"""
import asyncio
import os
import unittest
import uuid
from unittest.mock import patch

import httpx

from business.order_app.main import make_app
from business.order_app.store import Conflict, NotFound, OrderStore, PoolManager


class UnavailableStore:
    async def execute(self, *args):
        raise ConnectionError("deliberately unavailable")

    async def receipt(self, key):
        raise NotFound("receipt_not_found")


class BusinessHTTPContract(unittest.IsolatedAsyncioTestCase):
    """ASGI-only boundary checks; no simulated PostgreSQL success."""

    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {"APP_ADMIN_TOKEN": "contract-test-only"})
        self.env.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app(store=UnavailableStore()), raise_app_exceptions=False),
                                        base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.env.stop()

    async def test_admin_requires_domain_token(self):
        response = await self.client.get("/admin/status")
        self.assertEqual(response.status_code, 401)

    async def test_database_failure_is_unknown(self):
        response = await self.client.post("/orders", json={"request_key": "original-key", "item": "book", "quantity": 1})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["outcome"], "unknown")
        self.assertNotIn("deliberately", response.text)

    async def test_receipt_missing_does_not_mean_not_committed(self):
        response = await self.client.get("/receipts/original-key")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["outcome"], "unknown")

    async def test_validation_rejects_invalid_quantity_before_execution(self):
        response = await self.client.post("/orders", json={"request_key": "k", "item": "book", "quantity": 0})
        self.assertEqual(response.status_code, 422)


@unittest.skipUnless(os.environ.get("BUSINESS_TEST_DATABASE") == "1", "actual PostgreSQL not enabled")
class BusinessPostgresTransactions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = PoolManager()
        await self.pool.start()
        self.store = OrderStore(self.pool)
        self.key = "test-" + uuid.uuid4().hex

    async def asyncTearDown(self):
        await self.pool.close()

    async def test_same_key_concurrent_retries_return_one_order(self):
        results = await asyncio.gather(*(self.store.execute("create", self.key, {"item": "book", "quantity": 1}) for _ in range(12)))
        self.assertTrue(all(result == results[0] for result in results))
        async with self.pool.connection() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM orders WHERE request_key=$1", self.key), 1)
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM operation_receipts WHERE operation_key=$1", self.key), 1)

    async def test_same_key_different_content_conflicts(self):
        await self.store.execute("create", self.key, {"item": "book", "quantity": 1})
        with self.assertRaises(Conflict):
            await self.store.execute("create", self.key, {"item": "book", "quantity": 2})

    async def test_cancel_replays_original_receipt(self):
        created = await self.store.execute("create", self.key, {"item": "book", "quantity": 1})
        payload = {"order_id": created["order_id"]}
        first = await self.store.execute("cancel", self.key + "-cancel", payload)
        second = await self.store.execute("cancel", self.key + "-cancel", payload)
        self.assertEqual(first, second)
        self.assertEqual(first["order"]["status"], "CANCELLED")
        self.assertEqual(await self.store.receipt(self.key + "-cancel"), first)

    async def test_key_cannot_change_operation_kind(self):
        created = await self.store.execute("create", self.key, {"item": "book", "quantity": 1})
        with self.assertRaises(Conflict):
            await self.store.execute("cancel", self.key, {"order_id": created["order_id"]})
        self.assertEqual((await self.store.order(created["order_id"]))["status"], "CREATED")

    async def test_missing_order_has_no_cancel_receipt(self):
        with self.assertRaises(NotFound):
            await self.store.execute("cancel", self.key, {"order_id": str(uuid.uuid4())})
        with self.assertRaises(NotFound):
            await self.store.receipt(self.key)


if __name__ == "__main__":
    unittest.main()
