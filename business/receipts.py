"""Validate the committed receipt for one original order operation."""
import uuid


def validate_committed_receipt(body, operation_key, *, operation_kind=None, order_id=None):
    if (not isinstance(operation_key, str) or not operation_key
            or not isinstance(body, dict) or body.get("operation_key") != operation_key
            or body.get("outcome") != "committed"
            or body.get("operation_kind") not in ("create", "cancel")):
        raise ValueError("original_operation_receipt_not_committed_or_mismatched")
    received_id = body.get("order_id")
    if not isinstance(received_id, str):
        raise ValueError("receipt_order_id_invalid")
    try:
        uuid.UUID(received_id)
    except ValueError:
        raise ValueError("receipt_order_id_invalid") from None
    order = body.get("order")
    if not isinstance(order, dict) or order.get("id") != received_id:
        raise ValueError("receipt_order_identity_mismatched")
    kind = body["operation_kind"]
    if ((operation_kind is not None and kind != operation_kind)
            or (order_id is not None and received_id != order_id)):
        raise ValueError("receipt_original_operation_mismatched")
    if (not isinstance(order.get("request_key"), str) or not order["request_key"]
            or (kind == "create" and order["request_key"] != operation_key)
            or order.get("status") != ("CREATED" if kind == "create" else "CANCELLED")):
        raise ValueError("receipt_order_snapshot_invalid")
    return body
