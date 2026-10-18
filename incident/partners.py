"""Application and verification partners. Their resources remain domain-local."""
from __future__ import annotations

import os
import time
from urllib.parse import quote, urlparse
import httpx

from incident.contracts import TaskPayload, utc_now
from acps_sdk.aip.resumable import Fence


class ApplicationPartner:
    def __init__(self, aic, ledger, *, base_url=None, token=None, allowed_callers=(), client=None,
                 allowed_hosts=()):
        self.aic, self.ledger = aic, ledger
        self.base_url = base_url or os.environ.get("APP_BASE_URL", "http://127.0.0.1:8082")
        self.token = token or os.environ.get("APP_ADMIN_TOKEN", "")
        self.allowed_callers, self.client = set(allowed_callers), client
        # Only trusted domain configuration may opt into fixed Compose names.
        # No task argument supplies an endpoint or extends this allowlist.
        if isinstance(allowed_hosts, str) or not set(allowed_hosts) <= {"app-v1", "app-v2"}:
            raise ValueError("only registered application container hosts may be allowed")
        endpoint = urlparse(self.base_url)
        if (endpoint.scheme not in {"http", "https"} or endpoint.username or endpoint.password
                or endpoint.query or endpoint.fragment or endpoint.path not in {"", "/"}
                or endpoint.hostname not in {"127.0.0.1", "localhost", *allowed_hosts}):
            raise ValueError("application management endpoint must be in the local domain")
        self.base_url = self.base_url.rstrip("/")

    async def request(self, method, path, **kwargs):
        headers = {"Authorization": "Bearer " + self.token}
        if self.client:
            return await self.client.request(method, self.base_url + path, headers=headers, **kwargs)
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            return await client.request(method, self.base_url + path, headers=headers, **kwargs)

    async def execute(self, payload, caller_aic):
        task = TaskPayload.model_validate(payload)
        result = {"schema_version": "ifc/1.0", "incident_id": task.incident_id,
                  "logical_task_id": task.logical_task_id, "executor_aic": self.aic,
                  "status": "ok", "facts": [], "local_hypotheses": []}
        if caller_aic not in self.allowed_callers:
            return {**result, "status": "rejected"}
        if task.kind == "describe":
            return {**result, "description": {"resources": ["orders"],
                "tools": ["application.status", "application.pool_rebuild", "application.config_rollback"]}}
        try:
            def fact(key, value):
                return {"key": key, "value": value, "source": task.tool, "observed_at": utc_now()}
            if task.kind == "observe" and task.tool == "application.status":
                try:
                    response = await self.request("GET", "/admin/status")
                    response.raise_for_status()
                    value = response.json()
                    result["facts"] = [fact("application_reachable", True),
                        fact("application_pool_revision", value["config_revision"]),
                        fact("application_read_only", value.get("read_only")),
                        fact("application_error_codes", [e["code"] for e in value.get("errors", [])])]
                    if value.get("read_only"):
                        result["local_hypotheses"] = [{"cause": "db_read_only", "confidence": "high",
                                                       "because": ["application_read_only"]}]
                except httpx.TransportError:
                    result["facts"] = [fact("application_reachable", False)]
            elif task.kind == "act" and task.tool in {"application.pool_rebuild", "application.config_rollback"}:
                revision = task.args.get("expected_revision")
                if type(revision) is not int or revision < 0:
                    return {**result, "status": "rejected", "reason": "expected_revision_required"}
                path = "/admin/pool/rebuild" if task.tool.endswith("pool_rebuild") else "/admin/config/rollback"
                async def inspect():
                    response = await self.request("GET", "/admin/status")
                    response.raise_for_status()
                    return {"revision": response.json()["config_revision"]}
                async def action():
                    response = await self.request("POST", path, json={"expected_revision": revision})
                    response.raise_for_status()
                    return [fact("application_pool_revision", response.json()["config_revision"])]
                outcome = await self.ledger.execute(task.operation_id,
                    {"tool": task.tool, "args": task.args}, Fence(**task.fence.model_dump()), action,
                    inspect=inspect, expected_before={"revision": revision}, expected_after={"revision": revision+1})
                result["operation"] = {"operation_id": task.operation_id, "state": outcome.status}
                if outcome.status.startswith("rejected"):
                    result["status"] = "rejected"
                elif outcome.status in {"unknown", "reconciliation_required"}:
                    result["status"] = "unknown"
                else:
                    result["facts"] = outcome.result if isinstance(outcome.result, list) else []
            else:
                result.update(status="rejected", reason="unsupported_application_task")
        except Exception as exc:
            result.update(status="unknown" if task.kind == "act" else "tool_error", reason=type(exc).__name__)
        return result


class VerificationPartner:
    def __init__(self, aic, *, base_url="http://127.0.0.1:8088", allowed_callers=(), duration=30):
        self.aic, self.base_url, self.allowed_callers = aic, base_url, set(allowed_callers)
        self.duration = duration

    async def execute(self, payload, caller_aic):
        from business.load import OrderObserver, VersionedClient
        task = TaskPayload.model_validate(payload)
        result = {"schema_version": "ifc/1.0", "incident_id": task.incident_id,
                  "logical_task_id": task.logical_task_id, "executor_aic": self.aic,
                  "status": "ok", "facts": [], "local_hypotheses": []}
        if caller_aic not in self.allowed_callers:
            return {**result, "status": "rejected"}
        if task.kind == "describe":
            return {**result, "description": {"resources": ["orders"], "tools": ["incident.verification"]}}
        if task.kind != "verify" or task.tool != "incident.verification":
            return {**result, "status": "rejected"}
        original_unknown = task.args.get("original_request_unknown", False)
        original_key = task.args.get("original_request_key")
        if type(original_unknown) is not bool or (original_key is not None and not isinstance(original_key, str)):
            return {**result, "status": "rejected", "reason": "invalid_original_request_input"}
        original_key = original_key or None
        needs_original = original_unknown or original_key is not None
        original_resolved = not needs_original
        resolution = "not_required" if original_resolved else "unknown_missing_key"
        if original_key is not None:
            try:
                async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                    response = await VersionedClient(client).request("GET", self.base_url + "/receipts/" + quote(original_key, safe=""))
                original_resolved = response.status_code == 200
                resolution = ("resolved_receipt" if original_resolved else
                              "unknown_receipt_missing" if response.status_code == 404 else "unknown_receipt_unavailable")
            except (httpx.TransportError, ValueError):
                resolution = "unknown_receipt_unavailable"
        # A repeated verification must exercise fresh writes, not replay receipts
        # from a previous healthy window under the same incident identifier.
        observation_id = f"{task.incident_id}-{task.logical_task_id}"
        summary = await OrderObserver(self.base_url, run_id=observation_id, expected_api_version="v2").observe(
            duration=self.duration, min_complete=max(1, int(self.duration // 3)))
        service_recovered = summary["passed"] is True
        result["facts"] = [{"key": key, "value": value, "source": "order-workflows", "observed_at": utc_now()}
            for key, value in {"business_recovered": service_recovered and original_resolved,
                "service_recovered": service_recovered, "original_request_resolved": original_resolved,
                "original_request_resolution": resolution, "manual_required": not original_resolved,
                "order_observation": summary}.items()]
        return result
