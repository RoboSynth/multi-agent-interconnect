"""Exchange AIP tasks through the official Wutong AMQPS Inboxes.

Both identities receive invitations, return messages, and coordinate task states.
--run performs A-to-B and B-to-A tasks; --serve runs both message receivers.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import ssl
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
import uuid

import aio_pika
from aio_pika import ExchangeType

PILOT_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = PILOT_ROOT / "vendor" / "ACPs-community" / "acps-sdk"
if not SDK_ROOT.is_dir():
    raise RuntimeError(f"Pinned official SDK checkout missing: {SDK_ROOT}")
sys.path.insert(0, str(SDK_ROOT))

from acps_sdk.aic import validate_aic_format
from acps_sdk.aip.aip_base_model import (Product, TaskCommand, TaskCommandType,
                                        TaskResult, TaskState, TextDataItem)
from acps_sdk.aip.aip_group_leader import GroupLeader
from acps_sdk.aip.aip_group_model import (ACSObject, GroupInvitationError,
                                        GroupInvitationErrorData,
                                        InboxGroupInvitation, InboxGroupInvitationError)
from acps_sdk.aip.aip_group_partner import GroupPartnerMqClient
from acps_sdk.aip.aip_group_identity import (assert_incoming_group_message_identity,
                                           extract_amqp_user_id)
from acps_sdk.aip.aip_group_runtime import (INBOX_EXCHANGE_NAME, INBOX_MESSAGE_TTL_MS,
                                          INBOX_QUEUE_EXPIRES_MS, build_group_exchange_name,
                                          build_inbox_queue_name, invitation_is_expired,
                                          parse_amqp_endpoint_url)

REQUIRED = ("leader_aic", "partner_aic", "leader_amqp_endpoint", "partner_amqp_endpoint", "mq_auth_url",
            "leader_cert", "leader_key", "partner_cert", "partner_key", "trust_bundle")
PATH_FIELDS = ("leader_cert", "leader_key", "partner_cert", "partner_key", "trust_bundle")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sdk_contract_check():
    """Inspect the exact locally vendored methods without constructing clients."""
    contracts = {
        GroupLeader: ("leader_aic", "rabbitmq_config", "ssl_context", "identity_binding_enabled"),
        GroupLeader.create_group_session: ("session_id", "initial_partners"),
        GroupLeader.invite_partner: ("session_id", "partner_acs", "partner_acs_data"),
        GroupLeader.start_task: ("session_id", "task_content", "task_id", "target_partners"),
        GroupLeader.complete_task: ("session_id", "task_id", "target_partner"),
        GroupPartnerMqClient: ("partner_aic", "rabbitmq_host", "rabbitmq_port", "rabbitmq_vhost",
                              "rabbitmq_user", "rabbitmq_password", "ssl_context", "identity_binding_enabled"),
        GroupPartnerMqClient.start_inbox_consuming: ("handler",),
        GroupPartnerMqClient.join_group_from_invitation: ("invitation",),
        GroupPartnerMqClient.set_command_handler: ("handler",),
        GroupPartnerMqClient.accept_task: ("task_id", "session_id"),
        GroupPartnerMqClient.start_working: ("task_id", "session_id"),
        GroupPartnerMqClient.submit_for_completion: ("task_id", "session_id", "products"),
        GroupPartnerMqClient.complete_task: ("task_id", "session_id"),
        GroupPartnerMqClient.send_task_result: ("task_id", "session_id", "state", "products"),
    }
    rows = []
    for method, names in contracts.items():
        signature = inspect.signature(method)
        missing = set(names).difference(signature.parameters)
        if missing:
            raise RuntimeError(f"SDK contract mismatch: {method.__qualname__}: {sorted(missing)}")
        source = Path(inspect.getfile(method)).resolve()
        if not source.is_relative_to(SDK_ROOT.resolve()):
            raise RuntimeError(f"SDK imported from unpinned location: {source}")
        rows.append({"method": method.__qualname__, "signature": str(signature),
                     "file": str(source.relative_to(SDK_ROOT)),
                     "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    return {"mode": "offline-sdk-contract", "passed": True, "network_attempted": False,
            "platform_run_success": False, "sdk_root": str(SDK_ROOT), "contracts": rows}


def read_config(args):
    config = {}
    if args.config:
        source = Path(args.config).resolve()
        config = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict):
            raise ValueError("Config must be one JSON object")
        for key in PATH_FIELDS:
            if config.get(key):
                path = Path(config[key])
                config[key] = str(path if path.is_absolute() else source.parent / path)
    for key in (*REQUIRED, "leader_key_password_env", "partner_key_password_env"):
        if getattr(args, key, None) is not None:
            config[key] = getattr(args, key)
    return config


def load_password(config, role):
    env_name = config.get(f"{role}_key_password_env")
    if not env_name:
        return None
    value = os.environ.get(env_name)
    if value is None:
        raise ValueError(f"{role} key password environment variable is not set")
    return value


def read_pem_certificates(path):
    from cryptography import x509
    data = Path(path).read_bytes()
    blocks = re.findall(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", data, re.S)
    if not blocks:
        raise ValueError("No PEM certificates found")
    return [x509.load_pem_x509_certificate(block) for block in blocks]


def validate_certificates(config, role, trust):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    chain = read_pem_certificates(config[f"{role}_cert"])
    leaf = chain[0]
    try:
        if leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("A CA certificate cannot be used as the client leaf identity")
    except x509.ExtensionNotFound:
        pass
    password = load_password(config, role)
    key = serialization.load_pem_private_key(Path(config[f"{role}_key"]).read_bytes(),
                                             password=password.encode() if password else None)
    pub = lambda obj: obj.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if pub(leaf) != pub(key):
        raise ValueError("Certificate/private key mismatch")
    now = datetime.now(timezone.utc)
    if not leaf.not_valid_before_utc <= now <= leaf.not_valid_after_utc:
        raise ValueError("Client certificate is not valid at the current UTC time")
    cn = leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(cn) != 1 or cn[0].value.strip().upper() != config[f"{role}_aic"].upper():
        raise ValueError("Client certificate CN does not match configured AIC")
    try:
        eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound as exc:
        raise ValueError("Client certificate lacks explicit clientAuth EKU") from exc
    if ExtendedKeyUsageOID.CLIENT_AUTH not in eku:
        raise ValueError("Client certificate is not authorized for clientAuth")
    try:
        uris = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.UniformResourceIdentifier)
        aics = {uri[7:].strip().upper() for uri in uris if uri.lower().startswith("acps://")}
        if aics and aics != {config[f"{role}_aic"].upper()}:
            raise ValueError("Certificate ACPs URI SAN and configured AIC disagree")
    except x509.ExtensionNotFound:
        pass
    trust_cas = []
    for cert in trust:
        try:
            if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                trust_cas.append(cert)
        except x509.ExtensionNotFound:
            continue
    if not trust_cas:
        raise ValueError("Trust bundle has no CA certificates")
    fingerprints = {cert.fingerprint(hashes.SHA256()) for cert in trust_cas}
    candidates = chain[1:] + trust
    current = leaf
    visited = set()
    for _ in range(12):
        fingerprint = current.fingerprint(hashes.SHA256())
        if fingerprint in fingerprints:
            break
        if fingerprint in visited:
            raise ValueError("Certificate chain contains a loop")
        visited.add(fingerprint)
        issuers = [issuer for issuer in candidates if issuer.subject == current.issuer]
        valid_issuer = None
        for issuer in issuers:
            try:
                if not issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                    continue
                if not issuer.not_valid_before_utc <= now <= issuer.not_valid_after_utc:
                    continue
                current.verify_directly_issued_by(issuer)
                valid_issuer = issuer
                break
            except Exception:
                continue
        if valid_issuer is None:
            raise ValueError("Cannot build a signed, currently valid chain to supplied trust bundle")
        current = valid_issuer
    else:
        raise ValueError("Certificate chain is too deep")
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=config["trust_bundle"])
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_cert_chain(config[f"{role}_cert"], config[f"{role}_key"], password=password)
    return context, {"aic_matches_cn": True, "client_auth_eku": True, "key_matches_certificate": True,
                     "offline_signature_chain": True, "expires_utc": leaf.not_valid_after_utc.isoformat(),
                     "leaf_sha256": leaf.fingerprint(hashes.SHA256()).hex()}


def validate_config(config):
    errors = []
    contexts = {}
    details = {}
    for field in REQUIRED:
        if not isinstance(config.get(field), str) or not config[field].strip():
            errors.append(f"Missing real platform parameter: {field}")
    if errors:
        return {"mode": "offline-config", "ready": False, "network_attempted": False,
                "platform_run_success": False, "errors": errors}, contexts
    config = {**config}
    for role in ("leader", "partner"):
        config[f"{role}_aic"] = config[f"{role}_aic"].strip().upper()
        valid, reason = validate_aic_format(config[f"{role}_aic"])
        if not valid:
            errors.append(f"{role}_aic: {reason}")
    if config["leader_aic"] == config["partner_aic"]:
        errors.append("Leader and Partner must have distinct real platform AIC identities")
    for field in PATH_FIELDS:
        path = Path(config[field])
        if not path.is_file():
            errors.append(f"{field}: file does not exist")
        elif path.stat().st_size == 0:
            errors.append(f"{field}: file is empty")
    endpoints = {}
    for role in ("leader", "partner"):
        try:
            value = config[f"{role}_amqp_endpoint"]
            url = urlparse(value)
            if url.scheme != "amqps" or not url.hostname or not url.port:
                raise ValueError("A real AMQPS endpoint with explicit port is required")
            if url.username or url.password or url.fragment:
                raise ValueError("User/password/fragment in broker endpoint are not accepted")
            if "{" in value or "<" in value:
                raise ValueError("Unresolved endpoint placeholders are not accepted")
            endpoint = parse_amqp_endpoint_url(value, aic=config[f"{role}_aic"])
            if endpoint.inbox != build_inbox_queue_name(config[f"{role}_aic"]):
                raise ValueError(f"{role} ACS endpoint inbox does not match its AIC")
            endpoints[role] = endpoint
        except Exception as exc:
            errors.append(f"{role}_amqp_endpoint: {exc}")
    if len(endpoints) == 2:
        broker = lambda endpoint: (endpoint.host, endpoint.port, endpoint.vhost)
        if broker(endpoints["leader"]) != broker(endpoints["partner"]):
            errors.append("Both published Inbox endpoints must use the same official broker/vhost")
        endpoint = endpoints["leader"]
        details["broker"] = {"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                             "both_inboxes_match_aic": True}
    auth = urlparse(config["mq_auth_url"])
    if auth.scheme != "https" or not auth.hostname or auth.username or auth.password or auth.query or auth.fragment:
        errors.append("mq_auth_url must be the actual HTTPS MQ ACL service base URL, without credentials/query/fragment")
    if auth.hostname in {"localhost", "127.0.0.1", "::1"}:
        errors.append("mq_auth_url is a localhost placeholder, not a confirmed public platform ACL service")
    if not errors:
        try:
            trust = read_pem_certificates(config["trust_bundle"])
        except Exception as exc:
            errors.append(f"trust_bundle: {type(exc).__name__}: {exc}")
        else:
            for role in ("leader", "partner"):
                try:
                    contexts[role], details[role] = validate_certificates(config, role, trust)
                except Exception as exc:
                    errors.append(f"{role} certificate materials: {type(exc).__name__}: {exc}")
    report = {"mode": "offline-config", "ready": not errors, "network_attempted": False,
              "platform_run_success": False, "checks": details, "errors": errors,
              "limitations": ["Does not verify platform registration or review status",
                              "Does not verify that the supplied CA is an official platform CA",
                              "No revocation, broker, ACL permission, discovery, or live TLS checks were performed"]}
    return report, contexts


class ReadOnlyProbe:
    """Fixed operation; never executes model output, shell commands, or repairs."""
    def __init__(self, partner, leader_aic, session_id, task_id, nonce, record):
        self.partner = partner
        self.leader_aic = leader_aic
        self.session_id = session_id
        self.task_id = task_id
        self.nonce = nonce
        self.record = record
        self.state = None
        self.products = None

    async def command(self, command: TaskCommand, is_mentioned: bool):
        if not is_mentioned or command.senderRole != "leader" or command.senderId != self.leader_aic:
            return
        if command.groupId != self.partner.group_id or command.sessionId != self.session_id or command.taskId != self.task_id:
            self.record("command_ignored", reason="group/session/task mismatch")
            return
        self.record("partner_command", command=command.model_dump(mode="json"))
        if command.command == TaskCommandType.Start:
            if self.state is not None:
                await self.partner.send_task_result(self.task_id, self.session_id, self.state, products=self.products)
                return
            try:
                texts = [item.text for item in (command.dataItems or []) if isinstance(item, TextDataItem)]
                payload = json.loads("\n".join(texts))
                if payload != {"operation": "read-only-probe", "nonce": self.nonce}:
                    raise ValueError("Unsupported probe operation or nonce")
            except (ValueError, TypeError):
                self.state = TaskState.Rejected
                await self.partner.reject_task(self.task_id, self.session_id, "Only the configured read-only probe is permitted")
                return
            self.state = TaskState.Accepted
            await self.partner.accept_task(self.task_id, self.session_id)
            self.state = TaskState.Working
            await self.partner.start_working(self.task_id, self.session_id)
            product = {"operation": "read-only-probe", "nonce": self.nonce,
                       "partner_aic": self.partner.partner_aic, "observed_utc": utc_now(),
                       "result": "probe-received", "business_mutations": 0}
            self.products = [Product(id=f"probe-{self.task_id}", name="Read-only interoperability probe",
                                     dataItems=[TextDataItem(text=json.dumps(product, ensure_ascii=False))])]
            self.state = TaskState.AwaitingCompletion
            await self.partner.submit_for_completion(self.task_id, self.session_id, self.products)
        elif command.command == TaskCommandType.Complete:
            if self.state not in (TaskState.AwaitingCompletion, TaskState.Completed):
                self.record("complete_ignored", reason="probe has no validated product yet")
                return
            self.state = TaskState.Completed
            await self.partner.complete_task(self.task_id, self.session_id)
        elif command.command == TaskCommandType.Get and self.state is not None:
            await self.partner.send_task_result(self.task_id, self.session_id, self.state, products=self.products)
        elif command.command == TaskCommandType.Cancel:
            if self.state != TaskState.Completed:
                self.state = TaskState.Canceled
                await self.partner.cancel_task(self.task_id, self.session_id)
        else:
            self.record("command_ignored", reason="unsupported command")


class ManagedProbePartner(GroupPartnerMqClient):
    """Finish group shutdown outside the AMQP consumer being shut down.

    SDK v2.2.0 awaits leave cleanup from its consumer callback. aiormq owns
    that callback task and cancels it while closing the same channel, leaving
    a half-closed client. Defer cleanup so the callback can return first.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lifecycle_close_task = None

    async def _handle_leave_request(self):
        if self._lifecycle_close_task is None:
            self._lifecycle_close_task = asyncio.create_task(
                super()._handle_leave_request(), name=f"probe-partner-leave-{self.partner_aic}")

    async def close(self):
        if self._lifecycle_close_task is None:
            self._lifecycle_close_task = asyncio.create_task(
                super().close(), name=f"probe-partner-close-{self.partner_aic}")
        await self._lifecycle_close_task


class InboundProbeLeader(GroupLeader):
    """One AIC, one Inbox consumer, both outbound and inbound AIP group roles.

    The pinned SDK's GroupLeader and GroupPartnerMqClient otherwise compete for
    inbox_<AIC> and acknowledge each other's message types without handling them.
    This project adapter retains the SDK queue/identity contracts and dispatches
    both types in one consumer. Per-group Partner clients never consume an Inbox.
    """
    def __init__(self, *, allowed_peer_aic, record, **kwargs):
        super().__init__(**kwargs)
        self.allowed_peer_aic = allowed_peer_aic
        self.record = record
        self._inbound_groups = {}
        self._inbound_probes = {}
        self._inbound_lock = asyncio.Lock()
        self._inbox_consumer_tag = None
        self._inbound_closing = False

    async def _ensure_inbox(self):
        # Adapted from SDK v2.2.0 GroupLeader._ensure_inbox. Only this consumer
        # owns acknowledgement and routes invitation versus invitation-error.
        if self._inbox_queue and not getattr(self._inbox_queue, "is_closed", False):
            return
        if not self._connection:
            raise RuntimeError("Connection is not ready")
        self._inbox_channel = await self._connection.channel()
        self._inbox_queue = await self._inbox_channel.declare_queue(
            build_inbox_queue_name(self.leader_aic), durable=True, exclusive=False,
            auto_delete=False, arguments={"x-expires": INBOX_QUEUE_EXPIRES_MS,
                                          "x-message-ttl": INBOX_MESSAGE_TTL_MS})
        exchange = await self._inbox_channel.declare_exchange(
            INBOX_EXCHANGE_NAME, type=ExchangeType.TOPIC, durable=True, auto_delete=False)
        await self._inbox_queue.bind(exchange, routing_key=build_inbox_queue_name(self.leader_aic))
        self._inbox_consumer_tag = await self._inbox_queue.consume(self._dispatch_inbox)
        self.record("unified_inbox_listening", aic=self.leader_aic,
                    inbox=build_inbox_queue_name(self.leader_aic))

    async def start_inbound(self):
        """Start the real declared Inbox, without creating an outbound group."""
        await self._ensure_connection()

    async def _dispatch_inbox(self, message):
        async with message.process():
            try:
                body = json.loads(message.body.decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("Inbox body must be an object")
                kind = body.get("type")
                if kind == "group-invitation":
                    parsed = InboxGroupInvitation.model_validate(body)
                elif kind == "group-invitation-error":
                    parsed = InboxGroupInvitationError.model_validate(body)
                else:
                    self.record("inbox_type_ignored", aic=self.leader_aic, message_type=kind)
                    return
                assert_incoming_group_message_identity(
                    parsed, amqp_user_id=extract_amqp_user_id(message),
                    expected_group_id=parsed.groupId)
            except Exception as exc:
                self.record("inbox_invalid_message", aic=self.leader_aic,
                            error=f"{type(exc).__name__}: {exc}")
                return
            if isinstance(parsed, InboxGroupInvitationError):
                self.record("inbox_invitation_error_received", aic=self.leader_aic,
                            group_id=parsed.groupId, peer_aic=parsed.senderId)
                await self._handle_invitation_error(parsed)
            else:
                await self._accept_probe_invitation(parsed)

    def _partner_client(self):
        return ManagedProbePartner(
            partner_aic=self.leader_aic, rabbitmq_host=self.rabbitmq_host,
            rabbitmq_port=self.rabbitmq_port, rabbitmq_vhost=self.rabbitmq_vhost,
            rabbitmq_user=None, rabbitmq_password=None, ssl_context=self.ssl_context,
            identity_binding_enabled=True)

    async def _reject_invitation(self, invitation, reason):
        client = self._partner_client()
        try:
            await client.send_invitation_error(invitation, GroupInvitationError(
                code=-32020, message="Read-only probe invitation rejected",
                data=GroupInvitationErrorData(errorType="INVITATION_REJECTED", details=reason)))
        finally:
            await client.close()
        self.record("inbound_invitation_rejected", aic=self.leader_aic,
                    group_id=invitation.groupId, reason=reason)

    def _invitation_policy(self, invitation):
        if self._inbound_closing:
            return "Runtime is closing"
        if invitation.group.leader.aic != self.allowed_peer_aic:
            return "Only the configured test peer may initiate a probe"
        if invitation.group.leader.aic == self.leader_aic:
            return "Self invitations are not supported"
        if not any(member.aic == self.leader_aic for member in invitation.group.partners):
            return "Invitation does not include this identity"
        if invitation_is_expired(invitation.expiresAt):
            return "Invitation expired"
        expected = build_group_exchange_name(invitation.group.leader.aic, invitation.groupId)
        if invitation.amqp.exchange != expected:
            return "Invitation exchange does not match its Leader/group identity"
        return None

    async def _accept_probe_invitation(self, invitation):
        async with self._inbound_lock:
            reason = self._invitation_policy(invitation)
            if reason:
                await self._reject_invitation(invitation, reason)
                return
            existing = self._inbound_groups.get(invitation.groupId)
            if existing and existing.is_joined:
                # Re-announce joined status; never install a second group consumer.
                await existing.send_status_result(connected=True, muted=False)
                self.record("inbound_invitation_repeated", aic=self.leader_aic,
                            group_id=invitation.groupId)
                return
            if any(client.is_joined for client in self._inbound_groups.values()):
                await self._reject_invitation(invitation, "One inbound group is already active")
                return
            if existing:
                await existing.close()
                self._inbound_groups.pop(invitation.groupId, None)
            client = self._partner_client()
            async def command_handler(command, is_mentioned):
                await self._probe_command(client, command, is_mentioned)
            def disconnected(disconnected_client, group_id):
                if self._inbound_groups.get(group_id) is disconnected_client:
                    self._inbound_groups.pop(group_id, None)
                self._inbound_probes.pop(group_id, None)
            client.set_command_handler(command_handler)
            client.set_disconnect_handler(disconnected)
            try:
                joined = await client.join_group_from_invitation(invitation)
                if joined:
                    self._inbound_groups[invitation.groupId] = client
                else:
                    await client.close()
                self.record("inbound_group_joined", aic=self.leader_aic,
                            group_id=invitation.groupId, joined=joined)
            except BaseException:
                await client.close()
                raise

    async def _probe_command(self, client, command, is_mentioned):
        if (not is_mentioned or command.senderRole != "leader"
                or command.senderId != self.allowed_peer_aic
                or command.groupId != client.group_id
                or not command.taskId or not command.sessionId):
            self.record("inbound_command_ignored", aic=self.leader_aic, reason="identity/context mismatch")
            return
        tasks = self._inbound_probes.setdefault(client.group_id, {})
        context = tasks.get(command.taskId)
        if context and context.session_id != command.sessionId:
            self.record("inbound_command_ignored", aic=self.leader_aic, reason="task/session collision")
            return
        if context is None:
            if command.command != TaskCommandType.Start:
                self.record("inbound_command_ignored", aic=self.leader_aic, reason="task not started")
                return
            try:
                payload = json.loads("\n".join(item.text for item in (command.dataItems or [])
                                               if isinstance(item, TextDataItem)))
                if (not isinstance(payload, dict) or set(payload) != {"operation", "nonce"}
                        or payload["operation"] != "read-only-probe"
                        or not isinstance(payload["nonce"], str)
                        or not 1 <= len(payload["nonce"]) <= 1024):
                    raise ValueError("Invalid read-only probe")
            except (ValueError, TypeError):
                await client.reject_task(command.taskId, command.sessionId,
                                         "Only read-only-probe with a nonempty nonce string of at most 1024 characters is supported")
                return
            if len(tasks) >= 16:
                await client.reject_task(command.taskId, command.sessionId, "Probe task capacity reached")
                return
            context = ReadOnlyProbe(client, self.allowed_peer_aic, command.sessionId,
                                    command.taskId, payload["nonce"], self.record)
            tasks[command.taskId] = context
        await context.command(command, is_mentioned)

    async def close(self):
        self._inbound_closing = True
        errors = []
        def phase(name):
            self._close_phase = name
            self.record("client_close_phase", aic=self.leader_aic, phase=name)
        # Cancel the sole consumer before closing per-group clients. Its queue is
        # durable and remains the advertised identity address across restarts.
        if self._inbox_queue and self._inbox_consumer_tag:
            try:
                phase("cancel-inbox-consumer")
                await self._inbox_queue.cancel(self._inbox_consumer_tag)
            except Exception as exc:
                errors.append(f"Inbox cancel: {type(exc).__name__}: {exc}")
            self._inbox_consumer_tag = None
        phase("wait-inbound-lock")
        async with self._inbound_lock:
            for client in list(self._inbound_groups.values()):
                try:
                    phase(f"close-inbound-group:{client.group_id}")
                    await client.close()
                except Exception as exc:
                    errors.append(f"Inbound group close: {type(exc).__name__}: {exc}")
            self._inbound_groups.clear()
            self._inbound_probes.clear()
        try:
            phase("sdk-leader-close")
            await super().close()
        except Exception as exc:
            errors.append(f"Leader close: {type(exc).__name__}: {exc}")
            # A group cleanup failure must not leave the long-lived connection
            # or HTTP pool running. Preserve the failure while closing owners.
            for resource, method in ((self._inbox_channel, "close"),
                                     (self._connection, "close"),
                                     (self._group_acl_client, "aclose")):
                if resource is not None:
                    try:
                        await getattr(resource, method)()
                    except Exception as close_exc:
                        errors.append(f"Owner close: {type(close_exc).__name__}: {close_exc}")
        if errors:
            raise RuntimeError("; ".join(errors))
        phase("closed")


async def wait_for_state(session, task_id, partner_aic, target, timeout):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        snapshot = session.get_partner_task_snapshot(task_id, partner_aic)
        if snapshot:
            if snapshot["state"] == target:
                return snapshot
            if snapshot["state"] in (TaskState.Failed, TaskState.Rejected, TaskState.Canceled):
                raise RuntimeError(f"Partner returned terminal state: {snapshot['state']}")
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for actual Partner state {target.value}")


async def close_runtime(runtime, timeout, record):
    """Keep the blocked await location if a real transport cannot shut down."""
    task = asyncio.create_task(runtime.close())
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if done:
        return task.result()
    chain = []
    awaited = task.get_coro()
    for _ in range(32):
        if awaited is None:
            break
        code = getattr(awaited, "cr_code", getattr(awaited, "gi_code", None))
        frame = getattr(awaited, "cr_frame", getattr(awaited, "gi_frame", None))
        if code:
            chain.append({"file": Path(code.co_filename).name, "method": code.co_name,
                          "line": frame.f_lineno if frame else None})
        awaited = getattr(awaited, "cr_await", getattr(awaited, "gi_yieldfrom", None))
    record("client_close_timeout", aic=runtime.leader_aic,
           phase=getattr(runtime, "_close_phase", "unknown"), await_chain=chain)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    raise TimeoutError("Client close did not finish; blocked await chain recorded")


async def run_probe_round(initiator, target_aic, target_endpoint, timeout, record, *, nonce=None):
    session_id = f"smoke-{uuid.uuid4().hex}"
    task_id = f"probe-{uuid.uuid4().hex}"
    nonce = uuid.uuid4().hex if nonce is None else nonce
    result = {"initiator_aic": initiator.leader_aic, "target_aic": target_aic,
              "session_id": session_id, "task_id": task_id, "success": False}
    try:
        session = await asyncio.wait_for(initiator.create_group_session(session_id, []), timeout)
        result["group_id"] = session.group_id
        record("official_group_created", **result)
        target_acs = {"endPoints": [{"transport": "AMQP", "url": target_endpoint}]}
        await asyncio.wait_for(initiator.invite_partner(
            session_id, ACSObject(aic=target_aic), partner_acs_data=target_acs), timeout + 2)
        if session.invitation_routes.get(target_aic) != "inbox":
            raise RuntimeError("SDK did not select the required official Inbox route")
        record("partner_invited", route="inbox", initiator_aic=initiator.leader_aic,
               target_aic=target_aic, session_id=session_id)
        await asyncio.wait_for(initiator.start_task(
            session_id, task_content=json.dumps({"operation": "read-only-probe", "nonce": nonce}),
            task_id=task_id, target_partners=[target_aic]), timeout)
        snapshot = await wait_for_state(session, task_id, target_aic, TaskState.AwaitingCompletion, timeout)
        product = json.loads(snapshot.get("product_text") or "null")
        if (not isinstance(product, dict) or product.get("nonce") != nonce
                or product.get("partner_aic") != target_aic
                or product.get("business_mutations") != 0
                or product.get("result") != "probe-received"):
            raise RuntimeError("Actual returned product failed identity/nonce/read-only validation")
        record("leader_product_validated", initiator_aic=initiator.leader_aic, product=product)
        await asyncio.wait_for(initiator.complete_task(session_id, task_id, target_partner=target_aic), timeout)
        await wait_for_state(session, task_id, target_aic, TaskState.Completed, timeout)
        result["messages"] = [message.model_dump(mode="json") for message in session.message_history]
        result["states_seen"] = [message.status.state.value for message in session.message_history
                                  if isinstance(message, TaskResult) and message.taskId == task_id
                                  and message.senderId == target_aic]
        if not {"accepted", "working", "awaiting-completion", "completed"}.issubset(result["states_seen"]):
            raise RuntimeError("Required lifecycle states absent from actual received messages")
        result["product"] = product
        result["success"] = True
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        if session_id in initiator.group_sessions:
            try:
                await asyncio.wait_for(initiator.dissolve_group_session(session_id), timeout)
                result["group_close_returned"] = True
            except Exception as exc:
                result["group_close_returned"] = False
                result["cleanup_error"] = f"{type(exc).__name__}: {exc}"


async def run_smoke(config, contexts, timeout, *, serve_seconds=0):
    endpoint = parse_amqp_endpoint_url(config["partner_amqp_endpoint"], aic=config["partner_aic"])
    events = []
    report = {"mode": "official-amqps-inbox-bidirectional", "started_utc": utc_now(),
              "network_attempted": True, "platform_run_success": False,
              "business_mutations": 0, "events": events, "rounds": [],
              "cleanup_scope": "SDK close return only; inspect logs/platform for swallowed cleanup failures",
              "deployment": "one process, two real identities, one unified Inbox consumer per identity"}
    def record(event, **values):
        events.append({"at": utc_now(), "event": event, **values})
    runtimes = {}
    try:
        for role, other in (("leader", "partner"), ("partner", "leader")):
            runtime = InboundProbeLeader(
                leader_aic=config[f"{role}_aic"], allowed_peer_aic=config[f"{other}_aic"],
                record=record, rabbitmq_config={"host": endpoint.host, "port": endpoint.port,
                    "vhost": endpoint.vhost, "user": None, "password": None,
                    "auth_service_url": config["mq_auth_url"]},
                ssl_context=contexts[role], invitation_timeout_seconds=timeout,
                identity_binding_enabled=True)
            runtimes[role] = runtime
            await asyncio.wait_for(runtime.start_inbound(), timeout)
        if serve_seconds:
            record("both_inboxes_serving", seconds=serve_seconds)
            print(json.dumps({"event": "both_inboxes_serving", "seconds": serve_seconds,
                              "aics": [config["leader_aic"], config["partner_aic"]]}), flush=True)
            await asyncio.sleep(serve_seconds)
            report["inbox_service_completed"] = True
        else:
            for role, other in (("leader", "partner"), ("partner", "leader")):
                result = await run_probe_round(runtimes[role], config[f"{other}_aic"],
                                               config[f"{other}_amqp_endpoint"], timeout, record)
                report["rounds"].append(result)
                if not result["success"]:
                    raise RuntimeError(f"{role} to {other} round: {result.get('error')}")
            report["platform_run_success"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        record("run_failed", error=report["error"])
    finally:
        report["cleanup_errors"] = [row["cleanup_error"] for row in report["rounds"]
                                    if row.get("cleanup_error")]
        for name, runtime in reversed(list(runtimes.items())):
            try:
                await close_runtime(runtime, timeout, record)
                record("client_closed", role=name)
            except Exception as exc:
                report["cleanup_errors"].append(f"{name}: {type(exc).__name__}: {exc}; phase={getattr(runtime, '_close_phase', 'unknown')}")
        report["finished_utc"] = utc_now()
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    modes = result.add_mutually_exclusive_group()
    modes.add_argument("--check-sdk", action="store_true", help="Inspect real pinned SDK signatures; no network")
    modes.add_argument("--check-config", action="store_true", help="Check real files/AIC/EKU/key/chain offline; no network (default)")
    modes.add_argument("--run", action="store_true", help="Execute A-to-B and B-to-A read-only tasks over official AMQPS/ACL")
    modes.add_argument("--serve", action="store_true", help="Serve both declared read-only Inboxes without initiating tasks")
    result.add_argument("--config", help="JSON config; certificate paths may be relative to this file")
    for key in REQUIRED:
        result.add_argument("--" + key.replace("_", "-"))
    result.add_argument("--leader-key-password-env", help="Name of an existing env var, never the password itself")
    result.add_argument("--partner-key-password-env", help="Name of an existing env var, never the password itself")
    result.add_argument("--timeout", type=int, default=30)
    result.add_argument("--serve-seconds", type=int, default=600, help="Bounded --serve lifetime (5..3600 seconds)")
    result.add_argument("--output", help="New JSON evidence file; an existing file is never overwritten")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    network_attempted = False
    try:
        if not 5 <= args.timeout <= 120:
            raise ValueError("--timeout must be between 5 and 120 seconds")
        if not 5 <= args.serve_seconds <= 3600:
            raise ValueError("--serve-seconds must be between 5 and 3600 seconds")
        if args.output and Path(args.output).exists():
            raise ValueError("Evidence output already exists; choose a new file")
        contract = sdk_contract_check()
        if args.check_sdk:
            report = contract
            exit_code = 0
        else:
            config = read_config(args)
            config_report, contexts = validate_config(config)
            if not config_report["ready"] or not (args.run or args.serve):
                report = config_report
                exit_code = 0 if config_report["ready"] else 2
            else:
                config = {**config, "leader_aic": config["leader_aic"].strip().upper(), "partner_aic": config["partner_aic"].strip().upper()}
                network_attempted = True
                report = asyncio.run(run_smoke(config, contexts, args.timeout,
                                               serve_seconds=args.serve_seconds if args.serve else 0))
                report["offline_config_checks"] = config_report
                completed = report.get("inbox_service_completed", False) if args.serve else report["platform_run_success"]
                exit_code = 0 if completed and not report["cleanup_errors"] else 1
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "network_attempted": network_attempted,
                          "platform_run_success": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
