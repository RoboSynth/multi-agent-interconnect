"""Offline transport-boundary simulation of the pinned SDK; never a platform run.

Only AMQP connections and the ACL HTTP request boundary are replaced. The SDK
still serializes, authenticates sender fields, joins groups, routes messages,
updates task state and tears down its resources. Real TLS/ACL are not simulated
as successful evidence. Fixture AICs are from the official SDK unit tests.
"""
import asyncio
from contextlib import asynccontextmanager
from collections import Counter
import json
import socket
import ssl
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import wutong_smoke as smoke
from acps_sdk.aip.aip_group_auth import GroupAclClient
from acps_sdk.aip.aip_group_leader import PartnerInviteError

AIC_A = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
AIC_B = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JUE"


class Received:
    def __init__(self, outgoing, routing_key):
        self.body = outgoing.body
        self.user_id = outgoing.user_id
        self.headers = outgoing.headers
        self.routing_key = routing_key
        self.redelivered = False
        self.settlements = 0

    @asynccontextmanager
    async def process(self):
        try:
            yield self
        finally:
            self.settlements += 1
            assert self.settlements == 1, "A transport message must be settled exactly once"


class MemoryBroker:
    def __init__(self):
        self.queues = {}
        self.exchanges = {}
        self.connections = []
        self.pending = set()
        self.consumer_channels = {}
        self.self_shutdown_attempts = 0
        self.failures = []
        self.deliveries = []
        self.max_consumers = Counter()
        self.published = Counter()
        self.acl_calls = []

    async def connect(self, url, *, ssl_context):
        parsed = urlparse(str(url))
        query = parse_qs(parsed.query)
        assert parsed.scheme == "amqps" and query["auth"] == ["external"]
        aic = query["name"][0].removeprefix("agent-")
        assert aic in {AIC_A, AIC_B} and isinstance(ssl_context, ssl.SSLContext)
        connection = Connection(self, aic)
        self.connections.append(connection)
        return connection

    def schedule(self, callback, message, channel):
        task = asyncio.create_task(callback(message))
        self.pending.add(task)
        self.consumer_channels[task] = channel
        def done(completed):
            self.pending.discard(completed)
            self.consumer_channels.pop(completed, None)
            if not completed.cancelled() and completed.exception():
                self.failures.append(repr(completed.exception()))
        task.add_done_callback(done)

    def flush(self, state):
        while state.backlog and state.consumers:
            tags = list(state.consumers)
            tag = tags[state.index % len(tags)]
            state.index += 1
            callback, channel = state.consumers[tag]
            message = state.backlog.pop(0)
            self.deliveries.append((state.name, json.loads(message.body)["type"]))
            self.schedule(callback, message, channel)

    async def drain(self):
        while self.pending:
            await asyncio.gather(*list(self.pending), return_exceptions=True)
        assert not self.failures, self.failures


class Connection:
    def __init__(self, broker, aic):
        self.broker, self.aic = broker, aic
        self.channels = []
        self.is_closed = False

    async def channel(self):
        result = Channel(self)
        self.channels.append(result)
        return result

    async def close(self):
        for channel in self.channels:
            await channel.close()
        self.is_closed = True


class Channel:
    def __init__(self, connection):
        self.connection = connection
        self.broker = connection.broker
        self.is_closed = False

    async def declare_exchange(self, name, **kwargs):
        state = self.broker.exchanges.setdefault(name, SimpleNamespace(name=name, bindings=set()))
        return Exchange(self, state)

    async def get_exchange(self, name, **kwargs):
        return Exchange(self, self.broker.exchanges[name])

    async def declare_queue(self, name, **kwargs):
        state = self.broker.queues.setdefault(name, SimpleNamespace(
            name=name, consumers={}, backlog=[], index=0))
        return Queue(self, state)

    async def queue_delete(self, name, **kwargs):
        self.broker.queues.pop(name, None)
        for state in self.broker.exchanges.values():
            state.bindings = {item for item in state.bindings if item[0] != name}

    async def exchange_delete(self, name, **kwargs):
        self.broker.exchanges.pop(name, None)

    async def close(self):
        if self.broker.consumer_channels.get(asyncio.current_task()) is self:
            # aiormq shutdown cancels owned consumer tasks, including a callback
            # that incorrectly tries to close its own channel.
            self.broker.self_shutdown_attempts += 1
            raise asyncio.CancelledError("Consumer attempted to close its own AMQP channel")
        for queue in self.broker.queues.values():
            queue.consumers = {tag: entry for tag, entry in queue.consumers.items()
                               if entry[1] is not self}
        self.is_closed = True


class Exchange:
    def __init__(self, channel, state):
        self.channel, self.state = channel, state
        self.name = state.name

    async def publish(self, message, routing_key="", **kwargs):
        broker = self.channel.broker
        assert message.user_id == self.channel.connection.aic, "Broker user_id identity boundary"
        body = json.loads(message.body)
        assert body["senderId"] == message.user_id
        broker.published[body["type"]] += 1
        for queue_name, binding_key in list(self.state.bindings):
            if self.name == smoke.INBOX_EXCHANGE_NAME and binding_key != routing_key:
                continue
            state = broker.queues.get(queue_name)
            if state:
                state.backlog.append(Received(message, routing_key))
                broker.flush(state)
        return True


class Queue:
    def __init__(self, channel, state):
        self.channel, self.state = channel, state
        self.name = state.name

    @property
    def is_closed(self):
        return self.channel.is_closed or self.name not in self.channel.broker.queues

    async def bind(self, exchange, routing_key=""):
        exchange.state.bindings.add((self.name, routing_key))

    async def consume(self, callback):
        tag = f"consumer-{id(callback)}"
        self.state.consumers[tag] = (callback, self.channel)
        broker = self.channel.broker
        broker.max_consumers[self.name] = max(broker.max_consumers[self.name], len(self.state.consumers))
        broker.flush(self.state)
        return tag

    async def cancel(self, tag):
        self.state.consumers.pop(tag, None)

    async def delete(self, **kwargs):
        await self.channel.queue_delete(self.name, **kwargs)


def config_and_contexts():
    endpoint = lambda aic: f"amqps://offline.invalid:5671/acps?inbox=inbox_{aic}"
    return {"leader_aic": AIC_A, "partner_aic": AIC_B,
            "leader_amqp_endpoint": endpoint(AIC_A), "partner_amqp_endpoint": endpoint(AIC_B),
            "mq_auth_url": "https://offline.invalid/acl"}, {
                "leader": ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                "partner": ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)}


def new_runtime(config, contexts, role, events):
    other = "partner" if role == "leader" else "leader"
    return smoke.InboundProbeLeader(
        leader_aic=config[f"{role}_aic"], allowed_peer_aic=config[f"{other}_aic"],
        record=lambda event, **values: events.append({"event": event, **values}),
        rabbitmq_config={"host": "offline.invalid", "port": 5671, "vhost": "acps",
                         "user": None, "password": None, "auth_service_url": config["mq_auth_url"]},
        ssl_context=contexts[role], invitation_timeout_seconds=5, identity_binding_enabled=True)


async def main_async():
    broker = MemoryBroker()
    config, contexts = config_and_contexts()
    async def fake_acl(self, method, path):
        broker.acl_calls.append((method, path))
    with patch.object(smoke.aio_pika, "connect_robust", broker.connect), \
            patch.object(GroupAclClient, "_request", fake_acl):
        report = await smoke.run_smoke(config, contexts, 5)
        assert report["platform_run_success"], report
        assert len(report["rounds"]) == 2 and all(row["success"] for row in report["rounds"])
        assert report["rounds"][0]["initiator_aic"] == AIC_A
        assert report["rounds"][1]["initiator_aic"] == AIC_B
        for row in report["rounds"]:
            assert row["group_close_returned"] and "cleanup_error" not in row
            assert row["states_seen"] == ["accepted", "working", "awaiting-completion", "completed"]
        assert not report["cleanup_errors"]
        await broker.drain()
        assert all(name.startswith("inbox_") for name in broker.queues)
        assert set(broker.exchanges) == {smoke.INBOX_EXCHANGE_NAME}
        assert all(connection.is_closed for connection in broker.connections)
        assert all(not queue.consumers for queue in broker.queues.values())

        # Real SDK pending-invitation error route must survive while A also
        # serves its own public Inbox. B deliberately refuses an extra group.
        events = []
        a, b = new_runtime(config, contexts, "leader", events), new_runtime(config, contexts, "partner", events)
        try:
            await a.start_inbound()
            await a.start_inbound()  # Repeated start cannot install a second consumer.
            await b.start_inbound()
            simultaneous = await asyncio.gather(
                smoke.run_probe_round(a, AIC_B, config["partner_amqp_endpoint"], 5,
                                      lambda event, **values: events.append({"event": event, **values}),
                                      nonce="hello-001"),
                smoke.run_probe_round(b, AIC_A, config["leader_amqp_endpoint"], 5,
                                      lambda event, **values: events.append({"event": event, **values})))
            assert all(row["success"] and row["group_close_returned"] for row in simultaneous), simultaneous
            assert simultaneous[0]["product"]["nonce"] == "hello-001", "Published ACS example must round-trip unchanged"
            await broker.drain()
            assert not a._inbound_groups and not b._inbound_groups
            # A lost main connection can be replaced without accumulating Inbox
            # consumers. This is lifecycle simulation, not real TLS reconnection.
            await a._connection.close()
            await a.start_inbound()
            assert not a._connection.is_closed
            session = await a.create_group_session("offline-rejection", [])
            b.allowed_peer_aic = AIC_B  # Authenticated A is outside configured allowlist.
            try:
                await asyncio.wait_for(a.invite_partner(
                    session.session_id, smoke.ACSObject(aic=AIC_B),
                    partner_acs_data={"endPoints": [{"transport": "AMQP", "url": config["partner_amqp_endpoint"]}]}), 2)
                raise AssertionError("Disallowed invitation unexpectedly succeeded")
            except PartnerInviteError:
                pass
            assert any(row["event"] == "inbox_invitation_error_received" for row in events)
            assert not a._pending_invitations
            assert not b._inbound_groups
            # Bind sender identity before dispatch: a forged property must not
            # reach even the otherwise matching invitation-error handler.
            outgoing = smoke.aio_pika.Message(body=json.dumps({
                "type": "group-invitation-error", "id": "offline-forged", "sentAt": smoke.utc_now(),
                "senderRole": "partner", "senderId": AIC_B, "groupId": session.group_id,
                "invitationToken": "offline-token", "error": {"code": -1, "message": "fixture"}
            }).encode(), user_id=AIC_A)
            forged = Received(outgoing, smoke.build_inbox_queue_name(AIC_A))
            before = sum(row["event"] == "inbox_invitation_error_received" for row in events)
            await a._dispatch_inbox(forged)
            assert forged.settlements == 1
            assert sum(row["event"] == "inbox_invitation_error_received" for row in events) == before
            assert events[-1]["event"] == "inbox_invalid_message"
        finally:
            await b.close()
            await a.close()
        await broker.drain()
    assert all(broker.max_consumers[smoke.build_inbox_queue_name(aic)] == 1 for aic in (AIC_A, AIC_B))
    assert all(connection.is_closed for connection in broker.connections)
    assert all(not queue.consumers for queue in broker.queues.values())
    assert broker.self_shutdown_attempts == 0, "Cleanup must run outside its consumer callback"
    return {"mode": "offline-sdk-transport-boundary-simulation", "passed": True,
            "network_attempted": False, "platform_run_success": False,
            "sdk_lifecycle_rounds": 4, "max_consumers_per_identity_inbox": 1,
            "published_message_types": dict(broker.published),
            "checks": ["A_to_B_and_B_to_A_actual_sdk_state_machine", "single_inbox_consumer_per_AIC",
                       "simultaneous_bidirectional_rounds", "repeated_start_is_idempotent",
                       "published_hello_001_example_round_trips_unchanged",
                       "main_connection_replacement_preserves_single_inbox", "authenticated_rejection_reaches_pending_invitation",
                       "forged_sender_property_rejected_before_dispatch", "all_connections_closed",
                       "group_shutdown_runs_outside_its_consumer_callback",
                       "only_long_lived_inbox_resources_remain"],
            "limitation": "In-memory AMQP and ACL boundaries; no live TLS, certificate issuance, platform admission or broker permissions tested"}


def main():
    def no_network(*args, **kwargs):
        raise AssertionError("Offline simulation attempted network")
    with asyncio.Runner() as runner:
        runner.get_loop()  # Windows loopback self-pipe precedes transport blocking.
        with patch.object(socket, "getaddrinfo", no_network), \
                patch.object(socket.socket, "connect", no_network), \
                patch.object(socket.socket, "connect_ex", no_network):
            result = runner.run(main_async())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
