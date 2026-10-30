"""Illustrative publisher patch for the platform maintainer, not deployed.

local_aic must come from the publisher's configured certificate/connection
identity, never a browser-supplied field. Broker verification remains required.
"""
import json

from aio_pika import DeliveryMode, Message
from acps_sdk.aip.aip_group_identity import build_outgoing_amqp_user_id


def bound_message(payload, *, local_aic, headers=None):
    user_id = build_outgoing_amqp_user_id(
        payload, local_aic=local_aic, identity_binding_enabled=True)
    return Message(
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        delivery_mode=DeliveryMode.PERSISTENT,
        headers=headers,
        user_id=user_id,
    )
