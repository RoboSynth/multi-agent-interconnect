"""Versioned business data carried inside official AIP data items."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def handover_evidence(facts, ttl_seconds=60):
    """Keep the original observation time; handover never renews evidence."""
    ttl = min(max(float(ttl_seconds), 0), 300)
    references = []
    for fact in facts:
        try:
            observed = datetime.fromisoformat(fact["observed_at"].replace("Z", "+00:00"))
            expires = observed.timestamp()+ttl if observed.tzinfo else 0
        except (KeyError, TypeError, ValueError, AttributeError):
            expires = 0
        references.append({"fact": fact, "expires_at": expires})
    return references


class FenceData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    coordinator_term: int = Field(ge=1)
    takeover_version: int = Field(ge=0)


class TaskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["ifc/1.0"] = "ifc/1.0"
    incident_id: str = Field(min_length=1, max_length=128)
    logical_task_id: str = Field(min_length=1, max_length=128)
    kind: Literal["observe", "act", "describe", "verify", "resume"]
    tool: str = Field(min_length=1, max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)
    operation_id: str | None = None
    fence: FenceData | None = None
    approval: dict[str, Any] | None = None
    budget: dict[str, int] = Field(default_factory=lambda: {"deadline_ms": 15000})

    @model_validator(mode="after")
    def validate_action(self):
        if self.kind == "act" and (not self.operation_id or self.fence is None):
            raise ValueError("act requires operation_id and fence")
        deadline = self.budget.get("deadline_ms", 0)
        if not 0 < deadline <= 120000:
            raise ValueError("deadline_ms must be 1..120000")
        return self


class Fact(BaseModel):
    key: str
    value: Any
    source: str
    observed_at: str = Field(default_factory=utc_now)


class TaskProduct(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["ifc/1.0"] = "ifc/1.0"
    incident_id: str
    logical_task_id: str
    executor_aic: str
    status: Literal["ok", "tool_error", "rejected", "unknown"]
    facts: list[Fact] = Field(default_factory=list)
    local_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    operation: dict[str, Any] | None = None
    evidence_ref: str | None = None
