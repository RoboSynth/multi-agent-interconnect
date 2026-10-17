"""Check official ADP/ACS metadata without contacting a target endpoint."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse
import httpx

from acps_sdk.aic import validate_aic_format
from acps_sdk.adp import DiscoveryFilter, DiscoveryRequest, DiscoveryResponse, FilterCondition
from incident.contracts import TaskPayload, utc_now
from integration.validate_acs import validate_document


class OnboardingPartner:
    def __init__(self, aic, *, discovery_url, allowed_callers, discover=None):
        self.aic, self.discovery_url = aic, discovery_url
        self.allowed_callers = frozenset(allowed_callers)
        self.discover = discover or self._discover

    async def _discover(self, aic):
        request = DiscoveryRequest(type="filtered", limit=10, filter=DiscoveryFilter(conditions=[
            FilterCondition(field="aic", op="eq", value=aic)])).to_dict()
        request["extFilter"] = {"logic": "and", "conditions": [
            {"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}]}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(self.discovery_url, json=request)
        response.raise_for_status()
        parsed = DiscoveryResponse.from_dict(response.json())
        if parsed.is_error() or parsed.result is None:
            raise RuntimeError("official discovery returned an error")
        return parsed.result.acs_map.get(aic)

    async def execute(self, payload, caller_aic):
        task = TaskPayload.model_validate(payload)
        result = {"schema_version": "ifc/1.0", "incident_id": task.incident_id,
                  "logical_task_id": task.logical_task_id, "executor_aic": self.aic,
                  "status": "ok", "facts": [], "local_hypotheses": []}
        if caller_aic not in self.allowed_callers:
            return {**result, "status": "rejected", "reason": "caller_not_allowed"}
        if task.kind == "describe":
            return {**result, "description": {"resources": ["public-acs"], "tools": ["aip.onboarding.check"],
                "active_target_probe": False}}
        target = task.args.get("target_aic")
        if (task.kind != "observe" or task.tool != "aip.onboarding.check"
                or set(task.args)-{"target_aic", "deep"} or not isinstance(target, str)
                or not validate_aic_format(target)[0] or task.args.get("deep", False) is not False):
            return {**result, "status": "rejected", "reason": "read_only_metadata_check_required"}
        try:
            document = await self.discover(target)
            report = {"target_aic": target, "found": bool(document), "active_target_probe": False,
                      "passed": False, "suggestions": []}
            if not document or document.get("aic") != target:
                report["suggestions"].append("Confirm the approved identity is published to official Discovery.")
            else:
                validation = validate_document(document)
                endpoints = document.get("endPoints", [])
                inbox = "inbox_"+target
                endpoint_ok = any(endpoint.get("transport") == "AMQP"
                    and urlparse(endpoint.get("url", "")).scheme == "amqps"
                    and parse_qs(urlparse(endpoint["url"]).query).get("inbox") == [inbox]
                    for endpoint in endpoints if isinstance(endpoint, dict))
                skills = document.get("skills", [])
                skill_ok = bool(skills) and all(isinstance(skill, dict)
                    and all(isinstance(skill.get(key), str) and skill[key].strip()
                            for key in ("id", "name", "description")) for skill in skills)
                report.update(official_registry_schema_valid=validation["official_registry_schema_valid"],
                    sdk_schema_valid=validation["sdk_schema_valid"],
                    protocol_version_valid=document.get("protocolVersion") == "02.02",
                    inbox_endpoint_valid=endpoint_ok, skills_complete=skill_ok,
                    runtime_blockers=validation.get("runtime_blockers", []))
                checks = (report["official_registry_schema_valid"] is True, report["sdk_schema_valid"],
                    report["protocol_version_valid"], endpoint_ok, skill_ok,
                    validation["official_endpoint_checks_valid"])
                report["passed"] = all(checks)
                if not checks[0]:
                    report["suggestions"].append("Validate against the pinned official Registry JSON Schema.")
                if not report["protocol_version_valid"]:
                    report["suggestions"].append("Publish protocolVersion 02.02 for this runtime.")
                if not endpoint_ok:
                    report["suggestions"].append("Publish an AMQPS endpoint with inbox=inbox_{actual AIC}.")
                if not skill_ok:
                    report["suggestions"].append("Give every advertised skill an id, name and concrete description.")
            result["facts"] = [{"key": "onboarding_report", "value": report,
                                "source": task.tool, "observed_at": utc_now()}]
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError, TypeError):
            result.update(status="tool_error", reason="official_metadata_check_failed")
        return result
