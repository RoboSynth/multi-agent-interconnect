"""E1-only bridge hooks and durable MCP invocation traces; normal Bridge is unchanged."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import json
import os
from pathlib import Path
import re
import threading

from .bridge import Bridge
from .policy import PolicyRejected


EXIT_CODES = {"after_observation": 81, "before_modification": 82, "after_applied": 83}


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    incident_id: str
    primary_aic: str
    backup_aic: str
    worker_role: str
    armed: bool
    crash_point: str | None
    crash_tool: str

    @classmethod
    def from_document(cls, document, *, experiment_id, executor_aic):
        fields = set(cls.__dataclass_fields__)
        if not isinstance(document, dict) or set(document) != fields | {"schema_version"}:
            raise ValueError("exact e1-worker/1 experiment fields required")
        if document["schema_version"] != "e1-worker/1":
            raise ValueError("unsupported experiment schema")
        value = cls(**{name: document[name] for name in fields})
        if (not isinstance(value.experiment_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value.experiment_id)
                or value.experiment_id != experiment_id
                or any(not isinstance(item, str) or not item.strip() for item in
                       (value.incident_id, value.primary_aic, value.backup_aic, value.crash_tool))
                or value.primary_aic == value.backup_aic or not value.crash_tool.startswith("db.")
                or type(value.armed) is not bool):
            raise ValueError("invalid or mismatched experiment identity")
        if value.worker_role not in {"primary", "backup"}:
            raise ValueError("experiment role must be primary or backup")
        expected_aic = value.primary_aic if value.worker_role == "primary" else value.backup_aic
        if executor_aic != expected_aic:
            raise ValueError("actual executor differs from its experiment role")
        if value.worker_role == "backup":
            if value.armed or value.crash_point is not None:
                raise ValueError("backup must never be armed for an experiment exit")
        elif value.crash_point not in EXIT_CODES:
            raise ValueError("primary requires one exact experiment crash point")
        if value.crash_point == "after_observation" and value.crash_tool != "db.read_only_status":
            raise ValueError("observation exit is restricted to db.read_only_status")
        if value.crash_point in {"before_modification", "after_applied"} and value.crash_tool != "db.restore_writes":
            raise ValueError("modification exits are restricted to db.restore_writes")
        return value

    def matches(self, point, payload, executor_aic):
        return (self.armed and self.worker_role == "primary" and executor_aic == self.primary_aic
                and point == self.crash_point and payload.get("incident_id") == self.incident_id
                and payload.get("tool") == self.crash_tool
                and payload.get("kind") == ("observe" if point == "after_observation" else "act"))


class ExperimentExit(BaseException):
    """If an injected test callback returns, still stop before product submission."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class DurableTrace:
    def __init__(self, path, spec, executor_aic):
        self.path, self.spec, self.executor_aic = Path(path), spec, executor_aic
        self._lock = threading.RLock()

    def append(self, event):
        record = {**event, "experiment_id": self.spec.experiment_id,
                  "executor_aic": self.executor_aic, "transport": "wutong-amqps"}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record


class TracedSystemEmitter:
    """CountedMcpClient reuses its exact classification; trace before official AMP."""
    def __init__(self, emitter, trace):
        self.emitter, self.trace = emitter, trace

    async def emit(self, event):
        recorded = self.trace.append(event)
        return await self.emitter.emit(recorded)


class ExperimentBridge(Bridge):
    def __init__(self, *args, experiment, current_payload=None, trace, exit_callback=os._exit, **kwargs):
        super().__init__(*args, **kwargs)
        self.experiment, self.trace, self.exit_callback = experiment, trace, exit_callback
        self.current_payload = current_payload or ContextVar("e1_bridge_payload", default=None)
        self._tripped = False

    async def _trip(self, point, payload):
        if self._tripped or not self.experiment.matches(point, payload, self.executor_aic):
            return
        self._tripped = True
        operation = self.ledger.get(payload["operation_id"]) if payload.get("operation_id") else None
        self.trace.append({"event": "experiment_worker_crash", "crash_point": point,
            "exit_code": EXIT_CODES[point], "incident_id": payload["incident_id"],
            "logical_task_id": payload["logical_task_id"], "operation_id": payload.get("operation_id"),
            "tool": payload["tool"], "ledger_state": operation["state"] if operation else None,
            "AIP_product_submitted": False})
        result = self.exit_callback(EXIT_CODES[point])
        if inspect.isawaitable(result):
            await result
        raise ExperimentExit(EXIT_CODES[point])

    async def execute(self, payload, caller_aic):
        token = self.current_payload.set(payload)
        try:
            if self.experiment.matches("before_modification", payload, self.executor_aic):
                # Preserve the real policy/approval and durable ledger implementations.
                # Invalid/stale requests retain Bridge's rejection response; no hook fires.
                from acps_sdk.aip.resumable import Fence
                from incident.contracts import TaskPayload
                existing = self.ledger.get(payload.get("operation_id", ""))
                if existing is None or existing["state"] == "received":
                    try:
                        TaskPayload.model_validate(payload)
                        call = self.policy.authorize(payload, caller_aic)
                        received = self.ledger.record_received(payload["operation_id"],
                            {"tool": call.alias, "args": payload.get("args", {}), "resources": self.policy.resources},
                            Fence(**payload["fence"]))
                    except (PolicyRejected, ValueError, TypeError):
                        return await super().execute(payload, caller_aic)
                    if received["state"] == "received":
                        await self._trip("before_modification", payload)
            result = await super().execute(payload, caller_aic)
            if result.get("status") == "ok":
                if payload.get("kind") == "observe":
                    await self._trip("after_observation", payload)
                elif (payload.get("kind") == "act" and result.get("operation", {}).get("state") == "applied"):
                    durable = self.ledger.get(payload["operation_id"])
                    if durable and durable["state"] == "applied":
                        await self._trip("after_applied", payload)
            return result
        finally:
            self.current_payload.reset(token)


def operation_counts(paths, *, experiment_id, incident_id):
    """Count actual upstream attempts/returns, never infer physical side effects."""
    invocations, returns = {}, {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event") not in {"mcp_modify_invocation", "mcp_modify_returned"}:
                continue
            if (event.get("experiment_id") != experiment_id or event.get("incident_id") != incident_id
                    or event.get("transport") != "wutong-amqps"
                    or any(not isinstance(event.get(key), str) or not event[key] for key in
                           ("invocation_id", "operation_id", "executor_aic", "logical_task_id"))):
                raise ValueError("MCP trace differs from its exact experiment/incident/operation scope")
            collection = invocations if event["event"] == "mcp_modify_invocation" else returns
            if event["invocation_id"] in collection:
                raise ValueError("duplicate MCP trace invocation event")
            collection[event["invocation_id"]] = event
    rows = {}
    for key, event in returns.items():
        original = invocations.get(key)
        if original is None or any(original[field] != event[field] for field in
                                   ("executor_aic", "operation_id", "logical_task_id", "server", "upstream_tool", "tool")):
            raise ValueError("MCP return has no matching invocation")
    for key, event in invocations.items():
        row = rows.setdefault((event["executor_aic"], event["operation_id"]), {
            "executor_aic": event["executor_aic"], "operation_id": event["operation_id"],
            "invocations": 0, "returned": 0, "returned_errors": 0, "without_return": 0})
        row["invocations"] += 1
        row["returned"] += key in returns
        row["returned_errors"] += key in returns and returns[key]["is_error"] is True
        row["without_return"] += key not in returns
    return {"transport": "wutong-amqps", "experiment_id": experiment_id, "incident_id": incident_id,
            "counting": "Actual modifying MCP invocation attempts and observed returns, not physical side effects.",
            "operations": [rows[key] for key in sorted(rows)]}
