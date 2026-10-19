"""Formal E1-b information binding and actual captured-send verification.

These helpers do not start a transport or contact a participant. The runner
owns execution; history comes only from the pre-takeover capture boundary.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.handover_experiment import HandoverRecorder, METHODS, fresh_facts
from eval.resume_support import formal_semantic_history, save


def bind_handover(transport, method, output):
    """Install the existing recorder with formal, strictly bounded history."""
    if transport.mode != "wutong-amqps" or method not in METHODS:
        raise ValueError("formal handover requires wutong-amqps and a known method")
    if transport.resume_payload_factory is not None:
        raise ValueError("a handover factory is already bound")

    def history_reader(incident, logical):
        key = (incident, logical)
        if key not in transport.takeover_history_cutoffs:
            raise ValueError("formal takeover history boundary was not recorded")
        return formal_semantic_history(Path(transport.output) / "messages.jsonl", incident,
            before_bytes=transport.takeover_history_cutoffs[key])

    recorder = HandoverRecorder(method, transport, Path(output), history_reader=history_reader)
    transport.resume_payload_factory = recorder
    return recorder


def verify_handover(transport, recorder, original_payload, product, *, backup_aic, now=None):
    """Validate the sole captured resume and return its reusable facts/metrics.

    Session IDs identify the formal group, not the incident. Neither a locally
    prepared payload nor an unrelated capture can prove a transmitted handover.
    """
    if transport.mode != "wutong-amqps" or recorder.metrics is None or recorder.transfer is None:
        raise ValueError("formal handover information was not recorded")
    incident, logical = original_payload["incident_id"], original_payload["logical_task_id"]
    cutoff = transport.takeover_history_cutoffs.get((incident, logical))
    if type(cutoff) is not int or cutoff < 0:
        raise ValueError("formal takeover history boundary was not recorded")
    path = Path(transport.output) / "messages.jsonl"
    raw = path.read_bytes()
    if (not raw.endswith(b"\n") or cutoff > len(raw)
            or cutoff and raw[cutoff - 1:cutoff] != b"\n"):
        raise ValueError("captured messages must have complete record boundaries")
    matches, offset = [], 0
    for line in raw.splitlines(keepends=True):
        entry = json.loads(line)
        message = entry.get("message", {})
        if entry.get("direction") == "send" and message.get("command") == "start":
            for item in message.get("dataItems") or []:
                text = item.get("text")
                if not isinstance(text, str):
                    continue
                payload = json.loads(text)
                if (isinstance(payload, dict) and payload.get("kind") == "resume"
                        and (payload.get("incident_id"), payload.get("logical_task_id")) == (incident, logical)):
                    matches.append((offset, entry, payload, text))
        offset += len(line)
    if len(matches) != 1:
        raise ValueError("exactly one actual resume IFC text must be captured")
    offset, entry, payload, text = matches[0]
    message = entry["message"]
    if (offset < cutoff or entry.get("transport") != transport.mode
            or entry.get("worker_aic") != backup_aic
            or message.get("sessionId") != transport.session.session_id
            or message.get("senderId") != transport.aic
            or not isinstance(message.get("taskId"), str) or not message["taskId"]):
        raise ValueError("actual resume session, sender or backup target mismatch")
    if payload.get("operation_id") != original_payload.get("operation_id") or not payload.get("operation_id"):
        raise ValueError("actual resume operation mismatch")
    handover = payload.get("args", {}).get("handover")
    if handover != recorder.transfer:
        raise ValueError("actual transmitted handover differs from recorded information")
    control = handover.get("control", {})
    if (control.get("operation_id") != original_payload["operation_id"]
            or control.get("original_fence") != original_payload["fence"]
            or control.get("replacement_fence") != payload.get("fence")):
        raise ValueError("actual handover changed original operation or fences")
    encoded = text.encode("utf-8")
    if len(encoded) != recorder.metrics["resume_ifc_payload_utf8_bytes"]:
        raise ValueError("handover byte count does not match actual transmitted IFC text")
    digest = hashlib.sha256(json.dumps(handover, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if (product.get("status"), product.get("incident_id"), product.get("logical_task_id"),
            product.get("executor_aic")) != ("ok", incident, logical, backup_aic):
        raise ValueError("replacement product identity or status mismatch")
    if product.get("handover_sha256") != digest:
        raise ValueError("replacement did not acknowledge this actual transmitted handover")
    reusable = fresh_facts(handover, now=now)
    metrics = {**deepcopy(recorder.metrics), "native_transmitted_ifc_text_bytes": len(encoded),
        "native_transmitted_ifc_text_sha256": hashlib.sha256(encoded).hexdigest(),
        "native_resume_aip_task_id": message["taskId"], "native_resume_session_id": message["sessionId"],
        "replacement_acknowledged_handover_sha256": digest,
        "history_bytes_before_takeover": cutoff, "transport": transport.mode}
    recorder.metrics = metrics
    save(recorder.output / "handover-metrics.json", metrics)
    return {"fresh_facts": reusable, "metrics": metrics}
