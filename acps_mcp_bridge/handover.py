"""Shared wire fields for semantic history producers and the bridge validator."""

HISTORY_BODY_FIELDS = {"request": "payload", "product": "product"}
HISTORY_COMMON_FIELDS = frozenset({"direction", "aip_task_id"})
HISTORY_OPTIONAL_FIELDS = frozenset({"aip_session_id"})


def history_entry(direction, session_id, task_id, value):
    return {"direction": direction, "aip_session_id": session_id,
            "aip_task_id": task_id, HISTORY_BODY_FIELDS[direction]: value}
