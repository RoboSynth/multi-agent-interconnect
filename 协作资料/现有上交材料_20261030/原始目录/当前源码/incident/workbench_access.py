"""Read-only, incident-scoped captured Start/access reconciliation for the UI."""
from collections import Counter, defaultdict
import json
from pathlib import Path


REQUIRED_STATES = {"accepted", "working", "awaiting-completion", "completed"}
SCOPE = "仅核对此事故已捕获Start与对应双方AMP access，不代表全部平台流量、业务成功或Monitor入库。"


def _sources(transport, output):
    base = getattr(transport, "directory", None) or getattr(transport, "output", None)
    base = Path(base) if base else Path(output) / "transport"
    messages = Path(getattr(transport, "messages_path", None) or base / "messages.jsonl")
    amp = Path(getattr(transport, "amp_directory", None) or base / "amp")
    access = set(amp.rglob("amp_access_*.jsonl")) if amp.is_dir() else set()
    # These are explicit transport-owned local evidence mappings, never API paths.
    for paths in getattr(transport, "config", {}).get("participant_amp_paths", {}).values():
        for value in [paths] if isinstance(paths, str) else paths:
            path = Path(value)
            if path.name.startswith("amp_access_") and path.suffix == ".jsonl" and path.is_file():
                access.add(path)
    return messages, sorted({path.resolve() for path in access})


def _read(path, kind, invalid, partial, errors):
    try:
        raw = path.read_bytes()
    except OSError:
        errors[kind] += 1
        return []
    rows = []
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            continue
        if not line.endswith(b"\n"):
            partial[kind] += 1
        try:
            row = json.loads(line.decode("utf-8-sig"))
            if not isinstance(row, dict):
                raise ValueError("Log record must be an object")
        except (ValueError, UnicodeError):
            invalid[kind] += 1
        else:
            rows.append(row)
    return rows


def _belongs(message, incident_id):
    items = message.get("dataItems")
    if items is None:
        items = []
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        return None
    payload_ids = set()
    for item in items:
        value = item.get("data")
        if not isinstance(value, dict) and isinstance(item.get("text"), str):
            try:
                value = json.loads(item["text"])
            except ValueError:
                continue
        if isinstance(value, dict) and isinstance(value.get("incident_id"), str):
            payload_ids.add(value["incident_id"])
    # Formal AMQPS groups reuse their session across incidents. The captured
    # Start payload binds the run; a local session may itself be the incident.
    return payload_ids == {incident_id} if payload_ids else message.get("sessionId") == incident_id


def reconcile_incident_access(run, transport, output):
    """Return counts only; never mutate a run or expose messages, identities or paths."""
    invalid = dict(messages=0, access=0)
    partial = dict(messages=0, access=0)
    errors = dict(messages=0, access=0)
    message_path, access_paths = _sources(transport, output)
    captured = _read(message_path, "messages", invalid, partial, errors) if message_path.is_file() else []
    starts, states = {}, defaultdict(set)
    for row in captured:
        message = row.get("message")
        if not isinstance(message, dict):
            invalid["messages"] += 1
            continue
        if row.get("direction") != "send" or message.get("type") != "task-command" or message.get("command") != "start":
            continue
        belongs = _belongs(message, run["id"])
        if belongs is None:
            invalid["messages"] += 1
            continue
        if not belongs:
            continue
        values = (message.get("sessionId"), message.get("taskId"), message.get("senderId"), row.get("worker_aic"))
        if any(not isinstance(value, str) or not value for value in values):
            invalid["messages"] += 1
            continue
        key, actors = values[:2], values[2:]
        if key in starts and starts[key] != actors:
            invalid["messages"] += 1
        else:
            starts[key] = actors
    for row in captured:
        message = row.get("message", {})
        if not isinstance(message, dict):
            continue
        key = message.get("sessionId"), message.get("taskId")
        if any(not isinstance(value, str) for value in key):
            if row.get("direction") == "receive" and message.get("type") == "task-result":
                invalid["messages"] += 1
            continue
        if key in starts and row.get("direction") == "receive" and message.get("type") == "task-result" and message.get("senderId") == starts[key][1]:
            status = message.get("status", {})
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                states[key].add(status["state"])
            else:
                invalid["messages"] += 1
    expected = Counter((actor, *key) for key, actors in starts.items() for actor in actors)
    actual, unrelated = Counter(), 0
    for path in access_paths:
        for row in _read(path, "access", invalid, partial, errors):
            key = row.get("trace_id"), row.get("correlation_id")
            if any(not isinstance(value, str) or not value for value in key):
                invalid["access"] += 1
                continue
            if key not in starts:
                unrelated += 1
                continue
            if not isinstance(row.get("aic"), str) or not row["aic"]:
                invalid["access"] += 1
                continue
            actual[(row["aic"], *key)] += 1
    missing, extra = expected-actual, actual-expected
    incomplete = sum(not REQUIRED_STATES <= states[key] for key in starts)
    reasons = []
    if any(invalid.values()):
        reasons.append("invalid_log_records")
    if any(errors.values()):
        reasons.append("unreadable_log_sources")
    if any(partial.values()):
        reasons.append("unterminated_log_records")
    if missing:
        reasons.append("missing_endpoint_access")
    if extra:
        reasons.append("extra_endpoint_access")
    if incomplete:
        reasons.append("incomplete_task_lifecycles")
    status = "invalid" if any(invalid.values()) or any(errors.values()) else (
        "not_collected" if not starts else "incomplete" if reasons else "complete")
    if not starts:
        reasons.append("no_captured_starts_for_incident")
    return dict(incident_id=run["id"], status=status, passed=status == "complete" if starts else None,
        captured_start_tasks=len(starts), expected_access_records=sum(expected.values()) if starts else None,
        actual_access_records=sum(actual.values()) if starts else None,
        matched_access_records=sum((expected & actual).values()) if starts else None,
        missing_records=sum(missing.values()) if starts else None, extra_records=sum(extra.values()) if starts else None,
        incomplete_task_lifecycles=incomplete if starts else None,
        invalid_records=invalid, partial_records=partial, read_errors=errors,
        sources=dict(message_files=int(message_path.is_file()), access_files=len(access_paths)),
        unrelated_access_records_excluded=unrelated, reasons=reasons, scope=SCOPE,
        parse_scope="解析计数覆盖所读源文件全部行；无法定位事故的坏行不被丢弃或视作完整。")
