"""Local high-score workbench; launch on 127.0.0.1:8766 beside the baseline."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
import ipaddress
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool
import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine
from incident.workbench_access import reconcile_incident_access
from tools.configure_local_coordinator import local_model_settings
from acps_sdk.aip.resumable import TaskJournal, CoordinatorTerm


class IncidentRequest(BaseModel):
    symptom: str = Field(min_length=1, max_length=2000)
    original_request_key: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    original_request_unknown: StrictBool = False


class ApprovalRequest(BaseModel):
    approved: StrictBool


def create_app(config_path=None, output=None, transport=None):
    config_path = Path(config_path or ROOT / "runtime/local-coordinator.json")
    output = Path(output or ROOT / "artifacts/high-score-workbench")
    output.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        active_transport = transport
        config = {}
        app.state.connection_error = None
        config_bytes = config_path.read_bytes() if config_path.exists() else None
        if config_bytes is not None:
            config = json.loads(config_bytes.decode("utf-8-sig"))
        app.state.config_sha256 = hashlib.sha256(config_bytes).hexdigest() if config_bytes is not None else None
        if config.get("mode", "local-aip-stdio") == "local-aip-stdio":
            hypothesis = HypothesisEngine(**local_model_settings(config), api_key="")
        else:
            # Remote deployments retain their existing enabled/environment behavior.
            hypothesis = HypothesisEngine(enabled=config.get("llm_enabled", False))
        if active_transport is None and config_path.exists():
            try:
                if config.get("mode", "local-aip-stdio") == "local-aip-stdio":
                    from incident.local_transport import LocalAipStdioTransport
                    active_transport = LocalAipStdioTransport(config_path)
                else:
                    from incident.wutong_transport import WutongTransport
                    active_transport = WutongTransport(config, output / "transport")
                await active_transport.start()
            except Exception as exc:
                app.state.connection_error = f"{type(exc).__name__}: {exc}"
                if active_transport:
                    with suppress(Exception):
                        await active_transport.close()
                active_transport = None
        journal = TaskJournal(output / "coordinator.sqlite")
        term = getattr(active_transport, "term", None) or int(CoordinatorTerm(journal))
        issuer = getattr(active_transport, "issue_approval", None)
        engine = IncidentCoordinator(active_transport, output / "incidents", term=int(term),
                                    approval_issuer=issuer, hypothesis=hypothesis)
        if active_transport is not None and hasattr(active_transport, "on_event"):
            def on_transport_event(event):
                incident_id = event.get("incident_id")
                if incident_id in engine.runs and event.get("event", "").startswith("takeover_"):
                    data = {k: v for k, v in event.items() if k not in {"event", "incident_id"}}
                    engine.event(engine.runs[incident_id], event["event"], **data)
            active_transport.on_event = on_transport_event
        for path in (output / "incidents").glob("inc-*.json"):
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") in {"running", "awaiting_approval"}:
                saved.update(status="interrupted", error="进程重启；请先核验在途操作账本")
            engine.runs[saved["id"]] = saved
        app.state.engine, app.state.transport = engine, active_transport
        app.state.active = None
        try:
            yield
        finally:
            if app.state.active and not app.state.active.done():
                app.state.active.cancel()
                with suppress(asyncio.CancelledError):
                    await app.state.active
            if active_transport:
                await active_transport.close()

    app = FastAPI(title="跨域故障协同工作台", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        try:
            local = request.client and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = request.client and request.client.host == "testclient"
        if not local or host not in {"127.0.0.1", "localhost", "::1", "testserver"} or (
                origin and urlsplit(origin).hostname not in {"127.0.0.1", "localhost", "::1"}):
            return JSONResponse({"detail": "工作台只接受本机请求"}, status_code=403)
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return JSONResponse({"detail": "需要 application/json"}, status_code=415)
            if len(await request.body()) > 8192:
                return JSONResponse({"detail": "请求过大"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
        return response

    async def incident_view(run):
        if run is None:
            return None
        summary = await asyncio.to_thread(reconcile_incident_access, run, app.state.transport, output)
        return {**run, "access_reconciliation": summary}

    @app.get("/api/state")
    async def state():
        active_transport = app.state.transport
        engine = app.state.engine
        runs = sorted(engine.runs.values(), key=lambda run: (run.get("started_at") or "", run["id"]))
        current = await incident_view(runs[-1] if runs else None)
        credential_names = {"PGPASSWORD", "PGADMINPASSWORD", "DATABASE_URL", "DATABASE_URI",
                            "APP_ADMIN_TOKEN", "ORDERS_DB_PASSWORD", "POSTGRES_PASSWORD", "OPS_SUPERVISOR_TOKEN"}
        model_endpoint = engine.hypothesis.base_url
        try:
            parsed_endpoint = urlsplit(model_endpoint)
            if (parsed_endpoint.username is not None or parsed_endpoint.password is not None
                    or parsed_endpoint.query or parsed_endpoint.fragment):
                model_endpoint = "[REDACTED]"
        except ValueError:
            model_endpoint = "[REDACTED]"
        return {"connected": active_transport is not None and getattr(active_transport, "connection_ready", True), "mode": getattr(active_transport, "mode", "unconfigured"),
                "pid": os.getpid(),
                "resource_credential_count": sum(bool(os.environ.get(name)) for name in credential_names),
                "connection_error": app.state.connection_error,
                "participants": getattr(active_transport, "participants", []), "incident": current,
                "incidents": [{"id": r["id"], "symptom": r["symptom"], "status": r["status"]} for r in runs],
                "model": "rules" if not engine.hypothesis.enabled else engine.hypothesis.model,
                "config_sha256": app.state.config_sha256,
                "model_config": {"enabled": engine.hypothesis.enabled, "base_url": model_endpoint,
                    "model": engine.hypothesis.model, "max_output_tokens": engine.hypothesis.sampling["max_tokens"],
                    "max_calls": engine.hypothesis.max_calls, "token_budget": engine.hypothesis.token_budget,
                    "timeout_seconds": engine.hypothesis.timeout_seconds},
                "artifacts": str(output)}

    @app.post("/api/incidents", status_code=202)
    async def incident(body: IncidentRequest):
        if app.state.transport is None:
            raise HTTPException(503, "参与者尚未连接。先按部署文档启动本地业务和智能体。")
        if not getattr(app.state.transport, "connection_ready", True):
            raise HTTPException(503, "智能体通信通道不可用，需要恢复连接后再巡检。")
        if app.state.active and not app.state.active.done():
            raise HTTPException(409, "当前事故仍在处理")
        engine = app.state.engine
        run = engine.new(body.symptom, original_request_key=body.original_request_key,
                         original_request_unknown=body.original_request_unknown)
        app.state.active = asyncio.create_task(engine.run(run))
        return {"id": run["id"], "status": run["status"]}

    @app.get("/api/incidents/{incident_id}")
    async def read_incident(incident_id: str):
        if incident_id not in app.state.engine.runs:
            raise HTTPException(404, "事故不存在")
        return await incident_view(app.state.engine.runs[incident_id])

    @app.post("/api/approvals/{approval_id}")
    async def approve(approval_id: str, body: ApprovalRequest):
        try:
            app.state.engine.decide(approval_id, body.approved)
        except KeyError:
            raise HTTPException(404, "审批不存在或已结束")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"id": approval_id, "status": "approved" if body.approved else "declined"}

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "demo-ui/workbench.html")

    app.mount("/assets", StaticFiles(directory=ROOT / "demo-ui"), name="assets")
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    uvicorn.run(create_app(args.config, args.output), host="127.0.0.1", port=args.port, log_level="info")
