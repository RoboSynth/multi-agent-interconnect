"""Offline reproduction using real SDK serialization and project dispatch.

All channel/delivery objects are fakes; no credentials, network, identities or
cloud processes are opened. This reproduces the receiver contract, not a capture
of Dingdang's private sending implementation.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import argparse
import asyncio
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aip.aip_group_leader import GroupLeaderMqClient, GroupLeaderState
from acps_sdk.aip.aip_group_model import ACSObject
from incident.platform_worker import DomainGroupRuntime
from integration.wutong_smoke import build_group_exchange_name
from domains.onboarding.text import prepare_text_request

SERVICE = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JU5"
INTERNAL = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
EXTERNAL = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"


async def outgoing(binding):
    exchange = SimpleNamespace(publish=AsyncMock())
    sender = GroupLeaderMqClient(leader_aic=EXTERNAL, identity_binding_enabled=binding)
    sender._state = GroupLeaderState.READY
    sender._group_id = "offline-interop"
    sender._exchange_name = build_group_exchange_name(EXTERNAL, sender._group_id)
    sender._channel = SimpleNamespace(declare_exchange=AsyncMock(return_value=exchange))
    await sender.invite_via_inbox(ACSObject(aic=SERVICE), partner_inbox="offline-only")
    return exchange.publish.call_args.args[0]


class Delivery:
    def __init__(self, body, user_id, headers=None):
        self.body, self.user_id, self.headers = body, user_id, headers or {}
        self.normal_context_exit = False

    @asynccontextmanager
    async def process(self):
        yield self
        self.normal_context_exit = True


async def receive(message, *, public=True):
    events, admitted = [], []
    runtime = DomainGroupRuntime(
        bridge=SimpleNamespace(), leader_aic=SERVICE, allowed_leaders=[INTERNAL],
        public_metadata_service=public,
        record=lambda event, **details: events.append({"event": event, **details}),
        rabbitmq_config={"host": "offline.invalid", "port": 5671, "vhost": "/"},
    )

    async def inspect_policy(invitation):
        admitted.append({"policy_error": runtime._invitation_policy(invitation)})

    runtime._accept_probe_invitation = inspect_policy
    await runtime._dispatch_inbox(message)
    return {"events": events, "invitation_handler_calls": len(admitted),
            "policy_results": admitted, "normal_context_exit": message.normal_context_exit}


async def run():
    enabled, disabled = await outgoing(True), await outgoing(False)
    assert enabled.user_id == EXTERNAL
    assert disabled.user_id is None
    definitions = [
        ("sdk_default_binding", Delivery(enabled.body, enabled.user_id), True, 1, None),
        ("sdk_binding_disabled", Delivery(disabled.body, disabled.user_id), True, 0, "PeerAicMissingError"),
        ("header_is_not_property", Delivery(enabled.body, None, {"user_id": EXTERNAL}), True, 0, "PeerAicMissingError"),
        ("mismatched_sender", Delivery(enabled.body, INTERNAL), True, 0, "SenderIdentityMismatchError"),
        ("private_allowlist", Delivery(enabled.body, enabled.user_id), False, 1, None),
    ]
    results = []
    for name, delivery, public, calls, error in definitions:
        result = await receive(delivery, public=public)
        assert result["invitation_handler_calls"] == calls, (name, result)
        if error:
            assert any(row.get("error", "").startswith(error + ":") for row in result["events"])
        else:
            assert not result["events"]
        if name == "sdk_default_binding":
            assert result["policy_results"] == [{"policy_error": None}]
        if name == "private_allowlist":
            assert result["policy_results"] == [{"policy_error": "Leader is not authorized for this domain"}]
        results.append({"case": name, "passed": True, **result})
    text_results = []
    for text, expected in (
        (f"请检查 {EXTERNAL} 的公开元数据", None),
        (f"请检查 {EXTERNAL} 的公开元数据。不要修改资源，不要进行主动端点探测。",
         "read_only_metadata_check_required"),
    ):
        request, refusal = prepare_text_request(text, session_id="offline", task_id="offline",
                                               executor_aic=SERVICE)
        reason = refusal.get("reason") if refusal else None
        assert reason == expected
        text_results.append({"input": text, "reason": reason, "tool": request["tool"], "passed": True})
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline real SDK serializer/dispatcher with fake channels; no live Dingdang sender inspection.",
        "network_calls": 0, "identity_cases": results, "text_cases": text_results,
        "passed": len(results) + len(text_results),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "network_calls": 0}))
