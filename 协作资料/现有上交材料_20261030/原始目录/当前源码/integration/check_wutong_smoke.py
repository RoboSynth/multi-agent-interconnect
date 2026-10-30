"""Small offline contract check. Uses non-AIC object labels; never a platform run."""
import asyncio
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
import io
import socket
from unittest.mock import patch

import wutong_smoke as smoke


async def check_probe():
    # These deliberately invalid, non-AIC labels are local model fixtures only.
    # No certificate, broker, registry, or platform identity is synthesized.
    partner = smoke.GroupPartnerMqClient(partner_aic="offline-contract-partner",
                                         rabbitmq_user=None, rabbitmq_password=None)
    partner._group_id = "offline-contract-group"
    messages = []
    async def capture(message):
        messages.append(message)
    partner._publish_message = capture  # Replace the transport boundary only.
    handler = smoke.ReadOnlyProbe(partner, "offline-contract-leader", "local-session",
                                  "local-task", "local-nonce", lambda *a, **k: None)
    def command(kind, *, text=None, session="local-session"):
        return smoke.TaskCommand(id="local-command", sentAt=datetime.now(timezone.utc).isoformat(),
                                 senderRole="leader", senderId="offline-contract-leader",
                                 groupId=partner.group_id, sessionId=session, taskId="local-task",
                                 command=kind, mentions=[partner.partner_aic],
                                 dataItems=[smoke.TextDataItem(text=text)] if text else None)
    await handler.command(command(smoke.TaskCommandType.Complete), True)
    assert not messages, "Completion before a validated product must be ignored"
    payload = json.dumps({"operation": "read-only-probe", "nonce": "local-nonce"})
    await handler.command(command(smoke.TaskCommandType.Start, text=payload, session="wrong-session"), True)
    assert not messages, "Wrong session must not start a probe"
    await handler.command(command(smoke.TaskCommandType.Start, text=payload), False)
    assert not messages, "A command that does not target this Partner must be ignored"
    await handler.command(command(smoke.TaskCommandType.Start, text=payload), True)
    assert [m.status.state for m in messages] == [smoke.TaskState.Accepted, smoke.TaskState.Working,
                                                smoke.TaskState.AwaitingCompletion]
    product = json.loads(messages[-1].products[0].dataItems[0].text)
    assert product["nonce"] == "local-nonce" and product["business_mutations"] == 0
    await handler.command(command(smoke.TaskCommandType.Complete), True)
    assert messages[-1].status.state == smoke.TaskState.Completed
    assert all(m.senderId == partner.partner_aic and m.sessionId == "local-session" for m in messages)
    messages.clear()
    other = smoke.ReadOnlyProbe(partner, "offline-contract-leader", "local-session", "local-task",
                                "local-nonce", lambda *a, **k: None)
    await other.command(command(smoke.TaskCommandType.Start, text='{"operation":"repair-everything"}'), True)
    assert [m.status.state for m in messages] == [smoke.TaskState.Rejected]
    return ["completion_before_product_blocked", "wrong_session_ignored", "untargeted_command_ignored",
            "actual_sdk_accepted_working_awaiting_completion_completed_models",
            "nonce_and_zero_business_mutations", "unsupported_operation_rejected"]


def main():
    def no_network(*args, **kwargs):
        raise AssertionError("Offline contract check attempted network access")
    # Windows creates a loopback self-pipe while initializing the event loop.
    # Initialize that OS mechanism before blocking every transport connection.
    with asyncio.Runner() as runner:
        runner.get_loop()
        with patch.object(socket, "getaddrinfo", no_network), patch.object(socket.socket, "connect", no_network), patch.object(socket.socket, "connect_ex", no_network):
            contract = smoke.sdk_contract_check()
            missing, contexts = smoke.validate_config({})
            assert not missing["ready"] and len(missing["errors"]) == len(smoke.REQUIRED) and not contexts
            with redirect_stdout(io.StringIO()):
                assert smoke.main(["--run"]) == 2, "Explicit --run must still block missing real configuration"
            checks = runner.run(check_probe())
    print(json.dumps({"mode": "offline-sdk-contract", "passed": True, "network_attempted": False,
                      "platform_run_success": False, "inspected_sdk_contracts": len(contract["contracts"]),
                      "checks": ["missing_real_config_blocks_execution", *checks],
                      "limitation": "Only local SDK models and callback logic; no transport, TLS, ACL, discovery, registration or platform execution was tested"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
