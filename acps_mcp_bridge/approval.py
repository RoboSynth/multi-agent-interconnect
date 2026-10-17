"""Approval proofs bind the exact action and caller, rather than trusting JSON claims."""
from __future__ import annotations

import hashlib
import hmac
import json
import time


def action_binding(payload: dict, caller_aic: str) -> dict:
    return {"incident_id": payload.get("incident_id"), "operation_id": payload.get("operation_id"),
            "tool": payload.get("tool"), "args": payload.get("args", {}), "caller_aic": caller_aic}


class ApprovalAuthority:
    def __init__(self, secret: str | bytes):
        self.secret = secret.encode() if isinstance(secret, str) else secret
        if len(self.secret) < 32:
            raise ValueError("Approval secret must contain at least 32 bytes")

    def _proof(self, document: dict) -> str:
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hmac.new(self.secret, encoded, hashlib.sha256).hexdigest()

    def issue(self, payload: dict, caller_aic: str, *, approved_by: str, ttl_seconds: int = 300) -> dict:
        if not approved_by or not 1 <= ttl_seconds <= 3600:
            raise ValueError("Approval needs an actor and a TTL between 1 and 3600 seconds")
        record = {**action_binding(payload, caller_aic), "approved_by": approved_by,
                  "approved_at": int(time.time()), "expires_at": int(time.time()) + ttl_seconds}
        return {**record, "proof": self._proof(record)}

    def verify(self, payload: dict, caller_aic: str) -> bool:
        approval = payload.get("approval")
        if not isinstance(approval, dict):
            return False
        record = {k: v for k, v in approval.items() if k != "proof"}
        now = time.time()
        return (all(record.get(k) == v for k, v in action_binding(payload, caller_aic).items())
                and bool(record.get("approved_by")) and type(record.get("expires_at")) is int
                and type(record.get("approved_at")) is int
                and record["approved_at"] <= now <= record["expires_at"]
                and record["expires_at"] - record["approved_at"] <= 3600
                and hmac.compare_digest(str(approval.get("proof", "")), self._proof(record)))
