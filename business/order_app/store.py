"""Order changes and their receipts commit in the same PostgreSQL transaction."""
import asyncio
import hashlib
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def request_hash(kind, payload):
    canonical = json.dumps({"kind": kind, **payload}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def order_dict(row):
    return {key: value.isoformat() if isinstance(value, datetime) else str(value)
            if isinstance(value, uuid.UUID) else value for key, value in dict(row).items()}


class PoolManager:
    def __init__(self):
        self.pool = None
        self.revision = 0
        self.config_version = "stable"
        self.pressure_connection = None
        self.lock = asyncio.Lock()

    async def _create(self, version):
        import asyncpg
        dsn = (os.environ.get("DATABASE_URL_STABLE") or os.environ.get("DATABASE_URL")) if version in {"stable", "candidate"} else os.environ.get("DATABASE_URL")
        kwargs = {} if dsn else {
            "host": os.environ.get("PGHOST", "postgres"),
            "port": int(os.environ.get("PGPORT", "5432")),
            "database": os.environ.get("PGDATABASE", "orders"),
            "user": os.environ.get("PGUSER", "orders_app"),
            "password": os.environ["PGPASSWORD"],
        }
        return await asyncpg.create_pool(
            dsn=dsn, min_size=1, max_size=1 if version == "candidate" else int(os.environ.get("DB_POOL_MAX", "8")),
            command_timeout=float(os.environ.get("DB_COMMAND_TIMEOUT", "3")),
            timeout=float(os.environ.get("DB_CONNECT_TIMEOUT", "3")),
            server_settings={"application_name": "incident-pilot-orders-" + os.environ.get("APP_VERSION", "v2")},
            **kwargs)

    async def start(self):
        self.pool = await self._create(self.config_version)

    async def close(self):
        if self.pool:
            if self.pressure_connection is not None:
                await self.pool.release(self.pressure_connection)
                self.pressure_connection = None
            await self._close(self.pool)

    @staticmethod
    async def _close(pool):
        try:
            await asyncio.wait_for(pool.close(), timeout=5)
        except TimeoutError:
            pool.terminate()

    @asynccontextmanager
    async def connection(self):
        # Serialize acquisition with replacement so no caller grabs a closing pool.
        async with self.lock:
            if self.pool is None:
                raise ConnectionError("pool_unavailable")
            pool = self.pool
            conn = await pool.acquire(timeout=4)
        try:
            yield conn
        finally:
            await pool.release(conn)

    async def replace(self, expected_revision=None, version=None):
        async with self.lock:
            if expected_revision is not None and expected_revision != self.revision:
                raise Conflict("stale_config_revision")
            selected = version or self.config_version
            replacement = await self._create(selected)
            pressure = None
            try:
                if selected == "candidate":
                    # The opt-in F04 fixture occupies the sole application
                    # connection without any database lock or query. Rebuilding
                    # this bad configuration must not silently roll it back.
                    pressure = await replacement.acquire(timeout=4)
            except BaseException:
                await self._close(replacement)
                raise
            previous_pressure = self.pressure_connection
            previous, self.pool = self.pool, replacement
            self.pressure_connection = pressure
            self.config_version = selected
            self.revision += 1
        if previous:
            if previous_pressure is not None:
                await previous.release(previous_pressure)
            await self._close(previous)
        return {"config_revision": self.revision, "config_version": self.config_version}

    def status(self):
        return {"config_revision": self.revision, "config_version": self.config_version,
                "pool": {"size": self.pool.get_size() if self.pool else 0,
                         "idle": self.pool.get_idle_size() if self.pool else 0,
                         "max_size": self.pool.get_max_size() if self.pool else 0},
                "pool_exhausted": bool(self.pool and self.pool.get_size() >= self.pool.get_max_size()
                                       and self.pool.get_idle_size() == 0)}


class OrderStore:
    def __init__(self, pools):
        self.pools = pools

    async def receipt(self, key):
        async with self.pools.connection() as conn:
            row = await conn.fetchrow("SELECT response FROM operation_receipts WHERE operation_key=$1", key)
        if not row:
            raise NotFound("receipt_not_found")
        value = row["response"]
        return json.loads(value) if isinstance(value, str) else dict(value)

    async def order(self, order_id):
        async with self.pools.connection() as conn:
            row = await conn.fetchrow("SELECT * FROM orders WHERE id=$1", uuid.UUID(str(order_id)))
        if not row:
            raise NotFound("order_not_found")
        return order_dict(row)

    async def execute(self, kind, key, payload):
        digest = request_hash(kind, payload)
        async with self.pools.connection() as conn:
            async with conn.transaction():
                # Equal keys serialize before any mutation; a crash releases this transaction lock.
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", key)
                prior = await conn.fetchrow(
                    "SELECT request_hash,response FROM operation_receipts WHERE operation_key=$1", key)
                if prior:
                    if prior["request_hash"] != digest:
                        raise Conflict("operation_key_content_conflict")
                    value = prior["response"]
                    return json.loads(value) if isinstance(value, str) else dict(value)
                if kind == "create":
                    row = await conn.fetchrow(
                        "INSERT INTO orders(id,request_key,item,quantity,status) VALUES($1,$2,$3,$4,'CREATED') RETURNING *",
                        uuid.uuid4(), key, payload["item"], payload["quantity"])
                    changed = True
                elif kind == "cancel":
                    order_id = uuid.UUID(payload["order_id"])
                    row = await conn.fetchrow("SELECT * FROM orders WHERE id=$1 FOR UPDATE", order_id)
                    if not row:
                        raise NotFound("order_not_found")
                    changed = row["status"] != "CANCELLED"
                    if changed:
                        row = await conn.fetchrow(
                            "UPDATE orders SET status='CANCELLED',updated_at=now() WHERE id=$1 RETURNING *", order_id)
                else:
                    raise ValueError("unsupported_operation")
                order = order_dict(row)
                result = {"operation_key": key, "operation_kind": kind, "outcome": "committed",
                          "order_id": order["id"], "order": order, "changed": changed}
                await conn.execute(
                    "INSERT INTO operation_receipts(operation_key,operation_kind,request_hash,order_id,response) VALUES($1,$2,$3,$4,$5::jsonb)",
                    key, kind, digest, row["id"], json.dumps(result))
                return result
