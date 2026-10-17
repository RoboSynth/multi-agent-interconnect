"""Application-domain HTTP API. Credentials stay in this process's environment."""
import os
import secrets
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .store import Conflict, NotFound, OrderStore, PoolManager

Key = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]


class CreateOrder(BaseModel):
    request_key: Key
    item: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Annotated[int, Field(strict=True, ge=1, le=10000)] = 1


class CancelOrder(BaseModel):
    operation_key: Key


class RebuildPool(BaseModel):
    expected_revision: int | None = None


class RollbackConfig(RebuildPool):
    target_version: str = "stable"


def make_app(store=None, pools=None):
    pools = pools or PoolManager()
    store = store or OrderStore(pools)
    recent_errors = deque(maxlen=30)
    version = os.environ.get("APP_VERSION", "v2")

    @asynccontextmanager
    async def lifespan(app):
        await pools.start()
        try:
            yield
        finally:
            await pools.close()

    app = FastAPI(title="Incident Pilot order service", lifespan=lifespan)

    def envelope(value):
        return {**value, **({"order_api_version": "v2"} if version == "v2" else {})}

    async def admin(authorization: str | None = Header(default=None)):
        expected = os.environ.get("APP_ADMIN_TOKEN", "")
        if not expected or not secrets.compare_digest(authorization or "", "Bearer " + expected):
            raise HTTPException(401, "admin_authentication_required")

    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict):
        return JSONResponse({"error": str(exc), "outcome": "rejected"}, status_code=409)

    @app.exception_handler(NotFound)
    async def missing(request: Request, exc: NotFound):
        return JSONResponse({"error": str(exc), "outcome": "unknown"}, status_code=404)

    @app.exception_handler(Exception)
    async def infrastructure_error(request: Request, exc: Exception):
        code = getattr(exc, "sqlstate", None) or type(exc).__name__
        recent_errors.append({"code": code, "path": request.url.path,
                              "observed_at": datetime.now(timezone.utc).isoformat()})
        return JSONResponse({"error": "database_operation_failed", "code": code, "outcome": "unknown"}, status_code=503)

    @app.get("/health")
    async def health():
        return {"ok": True, "api_version": version}

    @app.get("/ready")
    async def ready():
        async with pools.connection() as conn:
            await conn.fetchval("SELECT 1")
        return {"ok": True, "api_version": version}

    @app.post("/orders")
    async def create(body: CreateOrder):
        return envelope(await store.execute("create", body.request_key,
                                            {"item": body.item, "quantity": body.quantity}))

    @app.get("/orders/{order_id}")
    async def order(order_id: uuid.UUID):
        return envelope({"order": await store.order(order_id)})

    @app.post("/orders/{order_id}/cancel")
    async def cancel(order_id: uuid.UUID, body: CancelOrder):
        return envelope(await store.execute("cancel", body.operation_key, {"order_id": str(order_id)}))

    @app.get("/receipts/{operation_key}")
    async def receipt(operation_key: str):
        return envelope(await store.receipt(operation_key))

    @app.get("/admin/status", dependencies=[Depends(admin)])
    async def status():
        result = {**pools.status(), "api_version": version, "errors": list(recent_errors)}
        try:
            async with pools.connection() as conn:
                result["read_only"] = await conn.fetchval("SHOW default_transaction_read_only") == "on"
                result["database_reachable"] = True
        except Exception as exc:
            result.update(database_reachable=False, database_error=getattr(exc, "sqlstate", None) or type(exc).__name__)
        return result

    @app.post("/admin/pool/rebuild", dependencies=[Depends(admin)])
    async def rebuild(body: RebuildPool):
        return await pools.replace(body.expected_revision)

    @app.post("/admin/config/rollback", dependencies=[Depends(admin)])
    async def rollback(body: RollbackConfig):
        if body.target_version != "stable":
            raise HTTPException(400, "config_version_not_allowlisted")
        return await pools.replace(body.expected_revision, "stable")

    return app


app = make_app()
