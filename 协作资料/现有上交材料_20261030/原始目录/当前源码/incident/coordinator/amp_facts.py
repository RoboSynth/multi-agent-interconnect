"""Convert explicitly supplied AMP logs into conservative participant facts.

These local records do not prove Monitor ingestion, process death or business
health. Failure confirmation needs a current task failure, a subsequent real
management query without a reply, and a previously observed expired heartbeat.
The SDK TakeoverManager's separate early-return signals are not a joint verdict.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Iterable


@dataclass(frozen=True)
class TaskEvidence:
    aic: str
    status: str  # ok / deadline_expired / channel_lost / unknown
    observed_at: float
    deadline: float | None = None


@dataclass(frozen=True)
class ManagementStatusEvidence:
    aic: str
    outcome: str  # reply / timeout / no_reply / unknown; publishing is not a reply
    requested_at: float
    observed_at: float


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


class AmpFactStore:
    """Bounded AMP evidence; timestamps and AICs retain their original meaning.

    ``ingest`` accepts decoded records. ``load_jsonl`` reads only explicit paths,
    counts unreadable files/invalid lines and never treats absence as a failure.
    No environment, private configuration, payload body or PID is inspected.
    All public API times are finite nonnegative epoch seconds, including ``now``.
    """

    def __init__(self, *, heartbeat_ttl_seconds=45, access_ttl_seconds=60,
                 evidence_ttl_seconds=60, capacity=8192):
        for value in (heartbeat_ttl_seconds, access_ttl_seconds, evidence_ttl_seconds):
            if not _number(value) or value == 0:
                raise ValueError("evidence TTL must be finite and positive")
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.access_ttl_seconds = access_ttl_seconds
        self.evidence_ttl_seconds = evidence_ttl_seconds
        self.capacity = capacity
        self._records = OrderedDict()
        self.diagnostics = {key: 0 for key in ("accepted", "duplicates", "invalid", "future", "unsupported", "unreadable_files")}

    @staticmethod
    def _now(now):
        value = time.time() if now is None else now
        if not _number(value):
            raise ValueError("now must be finite nonnegative epoch seconds")
        try:
            _iso(value)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("now must be a representable UTC timestamp") from exc
        return value

    def ingest(self, records: Iterable[dict], *, now=None):
        now = self._now(now)
        before = dict(self.diagnostics)
        for row in records:
            try:
                if (not isinstance(row, dict) or any(not _text(row.get(key)) for key in ("aic", "log_id", "log_type", "timestamp"))
                        or row.get("schema_version", "1.0") != "1.0" or not isinstance(row.get("body"), dict)):
                    raise ValueError("invalid AMP envelope")
                stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("timestamp needs a timezone")
                stamp = stamp.timestamp()
                if not _number(stamp):
                    raise ValueError("invalid timestamp")
                kind, body = row["log_type"], row["body"]
                if kind not in ("heartbeat", "access"):
                    self.diagnostics["unsupported"] += 1
                    continue
                if kind == "heartbeat" and body.get("uptimeSeconds") is not None and not _number(body["uptimeSeconds"]):
                    raise ValueError("invalid uptime")
                observation = {"aic": row["aic"], "log_id": row["log_id"], "kind": kind, "timestamp": stamp}
                if kind == "access":
                    duration = body.get("durationMs")
                    if duration is not None and not _number(duration):
                        raise ValueError("invalid access duration")
                    callee, response = body.get("callee"), body.get("response")
                    observation["target_response"] = False
                    if isinstance(callee, dict) and callee.get("aic") == row["aic"] and isinstance(response, dict):
                        status = response.get("statusCode")
                        if type(status) is int and 200 <= status <= 599:
                            observation.update(target_response=True, status_code=status,
                                               success=200 <= status < 300 and not body.get("error"))
                if stamp > now:
                    self.diagnostics["future"] += 1
                    continue
            except (ValueError, TypeError, OverflowError, OSError):
                self.diagnostics["invalid"] += 1
                continue
            key = (observation["aic"], kind, observation["log_id"])
            # Validate before dedup: an invalid/future row cannot consume an ID.
            if key in self._records:
                self.diagnostics["duplicates"] += 1
                continue
            self._records[key] = observation
            if len(self._records) > self.capacity:
                self._records.popitem(last=False)
            self.diagnostics["accepted"] += 1
        return {key: value - before[key] for key, value in self.diagnostics.items()}

    def load_jsonl(self, paths, *, now=None):
        now = self._now(now)
        before = dict(self.diagnostics)
        if isinstance(paths, (str, Path)):
            paths = [paths]
        for path in paths:
            try:
                with Path(path).open(encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                        except (ValueError, TypeError):
                            self.diagnostics["invalid"] += 1
                            continue
                        self.ingest([row], now=now)
            except (OSError, UnicodeError, TypeError, ValueError):
                self.diagnostics["unreadable_files"] += 1
        return {key: value - before[key] for key, value in self.diagnostics.items()}

    def assess(self, aic, *, task=None, management=None, now=None):
        now = self._now(now)
        if not _text(aic):
            raise ValueError("assessment needs one exact nonempty AIC")
        observations = [row for row in self._records.values() if row["aic"] == aic and row["timestamp"] <= now]
        latest = lambda rows: max(rows, key=lambda row: row["timestamp"], default=None)
        heartbeat = latest(row for row in observations if row["kind"] == "heartbeat")
        access = latest(row for row in observations if row["kind"] == "access" and row["target_response"])
        heartbeat_age = now - heartbeat["timestamp"] if heartbeat else None
        heartbeat_state = ("fresh" if heartbeat_age <= self.heartbeat_ttl_seconds else "expired") if heartbeat else "unknown"
        access_fresh = access is not None and now - access["timestamp"] <= self.access_ttl_seconds
        access_state = ("success" if access["success"] else "error") if access_fresh else "unknown"

        task_status = task.status if (isinstance(task, TaskEvidence) and isinstance(task.status, str)
            and task.status in {"ok", "deadline_expired", "channel_lost", "unknown"}) else "unknown"
        task_valid = (isinstance(task, TaskEvidence) and task.aic == aic and _number(task.observed_at)
                      and 0 <= now - task.observed_at <= self.evidence_ttl_seconds)
        if task_status == "deadline_expired":
            task_valid = bool(task_valid and _number(task.deadline) and task.deadline <= task.observed_at)
        task_failed = bool(task_valid and task_status in {"deadline_expired", "channel_lost"})
        management_valid = (isinstance(management, ManagementStatusEvidence) and management.aic == aic
            and isinstance(management.outcome, str)
            and management.outcome in {"reply", "timeout", "no_reply"}
            and _number(management.requested_at) and _number(management.observed_at)
            and management.requested_at <= management.observed_at <= now
            and now - management.observed_at <= self.evidence_ttl_seconds)
        if task_failed and management_valid:
            management_valid = management.requested_at >= task.observed_at
        management_outcome = management.outcome if management_valid else "unknown"
        management_failed = management_outcome in {"timeout", "no_reply"}
        heartbeat_after_failure = bool(task_failed and heartbeat and heartbeat["timestamp"] >= task.observed_at)
        access_after_failure = bool(task_failed and access and access["timestamp"] >= task.observed_at)
        # A response before a later observed failure cannot prove subsequent
        # reachability. Keep it in the facts, and still wait for the previously
        # observed heartbeat's real TTL before confirming the joint verdict.
        heartbeat_liveness = heartbeat_state == "fresh" and (not task_failed or heartbeat_after_failure)
        access_liveness = access_fresh and (not task_failed or access_after_failure)

        confirmed, state, reason = False, "unknown", "insufficient_joint_evidence"
        if ((task_valid and task_status == "ok") or management_outcome == "reply"
                or heartbeat_liveness or access_liveness):
            state = "reachable"
            reason = "recent_liveness_conflicts_with_task_failure" if task_failed else "recent_liveness_evidence"
        elif task_failed and management_failed and heartbeat_state == "expired":
            confirmed, state, reason = True, "unreachable", "task_and_management_failure_with_expired_heartbeat"
        elif task_failed and heartbeat_state == "fresh":
            reason = "awaiting_heartbeat_expiry_after_task_failure"

        def fact(key, value, source, stamp):
            return {"key": key, "value": value, "source": source, "observed_at": _iso(stamp)}

        facts = [fact("participant_reachable", {"aic": aic, "state": state}, "coordinator.amp_facts", now),
                 fact("participant_heartbeat_status", {"aic": aic, "state": heartbeat_state}, "amp.heartbeat", heartbeat["timestamp"] if heartbeat else now),
                 fact("participant_heartbeat_age_seconds", {"aic": aic, "seconds": heartbeat_age}, "amp.heartbeat", heartbeat["timestamp"] if heartbeat else now),
                 fact("participant_access_status", {"aic": aic, "state": access_state}, "amp.access", access["timestamp"] if access else now)]
        return {"schema_version": "participant-health/1.0", "aic": aic, "confirmed": confirmed,
                "participant_state": state, "task_status": task_status, "reason": reason,
                "manual_required": task_failed, "facts": facts, "observed_at": _iso(now),
                "business_state": "unknown",
                "evidence": {"task_valid": bool(task_valid), "management_outcome": management_outcome,
                    "management_valid": bool(management_valid), "heartbeat_state": heartbeat_state,
                    "heartbeat_age_seconds": heartbeat_age, "heartbeat_log_id": heartbeat["log_id"] if heartbeat else None,
                    "heartbeat_expires_at": heartbeat["timestamp"] + self.heartbeat_ttl_seconds if heartbeat else None,
                    "heartbeat_after_task_failure": heartbeat_after_failure,
                    "access_state": access_state, "access_log_id": access["log_id"] if access else None,
                    "access_age_seconds": now - access["timestamp"] if access else None,
                    "access_after_task_failure": access_after_failure},
                "diagnostics": dict(self.diagnostics)}
