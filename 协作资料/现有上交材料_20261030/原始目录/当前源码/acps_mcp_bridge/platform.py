"""Reuse the baseline's tested single-Inbox AIP invitation dispatcher."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path
import ssl
import time

from integration import wutong_smoke as transport


class BridgeGroupRuntime(transport.InboundProbeLeader):
    def __init__(self, *, bridge, amp=None, max_inbound_groups=1, **kwargs):
        if type(max_inbound_groups) is not int or not 1 <= max_inbound_groups <= 4:
            raise ValueError("max_inbound_groups must be an integer from 1 to 4")
        self.max_inbound_groups = max_inbound_groups
        self.amp = amp
        if amp:
            kwargs.setdefault("message_emitter", amp.message)
            kwargs.setdefault("access_emitter", amp.access)
        super().__init__(**kwargs)
        self.bridge = bridge
        self.bridge_handlers = {}

    def _partner_client(self):
        return transport.ManagedProbePartner(
            partner_aic=self.leader_aic, rabbitmq_host=self.rabbitmq_host,
            rabbitmq_port=self.rabbitmq_port, rabbitmq_vhost=self.rabbitmq_vhost,
            rabbitmq_user=None, rabbitmq_password=None, ssl_context=self.ssl_context,
            identity_binding_enabled=True,
            message_emitter=self.amp.message if self.amp else None,
            access_emitter=self.amp.access if self.amp else None)

    def _bind_client(self, client):
        handler = self.bridge.bind_partner(client)
        seen = OrderedDict()
        async def instrumented(command, is_mentioned):
            key = (command.groupId, command.sessionId, command.taskId)
            collect = bool(self.amp and is_mentioned and command.command == transport.TaskCommandType.Start and key not in seen)
            if collect:
                seen[key] = None
                if len(seen) > 8192:
                    seen.popitem(last=False)
                self.amp.sampler.active += 1
            started, success = time.monotonic(), False
            try:
                output = await handler(command, is_mentioned)
                success = isinstance(output, dict) and output.get("status") == "ok"
                return output
            finally:
                if collect:
                    self.amp.sampler.active -= 1
                    self.amp.sampler.record((time.monotonic() - started) * 1000, success)
        client.set_command_handler(instrumented)
        if client.group_id:
            self.bridge_handlers[client.group_id] = instrumented
        return instrumented

    async def _accept_probe_invitation(self, invitation):
        # Bind the business callback before join starts its consumer. The
        # baseline probe dispatcher wraps the callback without returning its
        # value; this adapter preserves business status for AMP access metrics.
        async with self._inbound_lock:
            reason = self._invitation_policy(invitation)
            if reason:
                await self._reject_invitation(invitation, reason)
                return
            existing = self._inbound_groups.get(invitation.groupId)
            if existing and existing.is_joined:
                leader = getattr(getattr(getattr(existing, "_group_info", None), "leader", None), "aic", None)
                if leader != invitation.group.leader.aic:
                    await self._reject_invitation(invitation, "Group id belongs to another Leader")
                    return
                await existing.send_status_result(connected=True, muted=False)
                return
            if sum(client.is_joined for client in self._inbound_groups.values()) >= self.max_inbound_groups:
                await self._reject_invitation(invitation, "Inbound group capacity reached")
                return
            if existing:
                await existing.close()
                self._inbound_groups.pop(invitation.groupId, None)
            client = self._partner_client()
            bound = self._bind_client(client)
            def disconnected(disconnected_client, group_id):
                if self._inbound_groups.get(group_id) is disconnected_client:
                    self._inbound_groups.pop(group_id, None)
                self.bridge_handlers.pop(group_id, None)
            client.set_disconnect_handler(disconnected)
            try:
                joined = await client.join_group_from_invitation(invitation)
                if joined:
                    self._inbound_groups[invitation.groupId] = client
                    self.bridge_handlers[invitation.groupId] = bound
                else:
                    await client.close()
                self.record("inbound_group_joined", aic=self.leader_aic, group_id=invitation.groupId, joined=joined)
            except BaseException:
                await client.close()
                raise

    async def _probe_command(self, client, command, is_mentioned):
        if client.group_id not in self.bridge_handlers:
            # _start_consuming in the official GroupPartner validates AMQP
            # authenticated user_id before the callback reaches this method.
            self.bridge_handlers[client.group_id] = self._bind_client(client)
        return await self.bridge_handlers[client.group_id](command, is_mentioned)


async def serve_platform(bridge, config: dict, *, record=lambda *a, **k: None):
    from incident.amp_setup import AmpRuntime
    context = ssl.create_default_context(cafile=config["trust_bundle"])
    context.load_cert_chain(config["cert"], config["key"])
    endpoint = transport.parse_amqp_endpoint_url(config["endpoint"], aic=bridge.executor_aic)
    callers = list(bridge.policy.allowed_callers)
    if len(callers) != 1:
        raise ValueError("The baseline Inbox runner requires exactly one coordinator AIC")
    amp = AmpRuntime(config.get("amp_directory", Path(__file__).resolve().parents[1] / "runtime/amp-platform"),
                     config.get("name", "mcp-bridge"), bridge.executor_aic, cert=config["cert"], key=config["key"])
    bridge.audit = amp.audit_event
    runtime = BridgeGroupRuntime(bridge=bridge, amp=amp, leader_aic=bridge.executor_aic,
        allowed_peer_aic=callers[0], record=record, ssl_context=context, identity_binding_enabled=True,
        rabbitmq_config={"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                         "user": None, "password": None, "auth_service_url": config["mq_auth_url"]})
    try:
        await amp.start()
        await runtime.start_inbound()
        await asyncio.Event().wait()
    finally:
        try:
            await transport.close_runtime(runtime, 15, record)
        finally:
            await amp.close()
