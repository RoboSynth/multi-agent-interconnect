"""Application/verification domain processes on the official Wutong Inbox.

The baseline owns the one Inbox consumer and authenticates AMQP user_id before
dispatch. Per-group official Partner clients own task consumers. Resource
environment files are loaded only by this domain process, never a coordinator.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import OrderedDict
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from integration import wutong_smoke as native
from acps_mcp_bridge.bridge import sanitize
from acps_mcp_bridge.platform import BridgeGroupRuntime
from acps_sdk.aic import validate_aic_format
from acps_sdk.aip import Product, StructuredDataItem, TaskCommandType, TaskState, TextDataItem
from acps_sdk.aip.resumable import OperationLedger
from acps_sdk.amp import AuditEmitter, CertificateAuditSigner
from incident.amp_setup import AmpRuntime
from incident.contracts import TaskPayload, TaskProduct
from incident.local_transport import environment_file
from incident.partners import ApplicationPartner, VerificationPartner
from domains.onboarding.check import OnboardingPartner

PATH_FIELDS = ("cert", "key", "trust_bundle", "env_file", "ledger_path", "amp_directory", "evidence_path")


def load_config(path):
    source = Path(path).resolve()
    config = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or config.get("role") not in ("application", "verification", "onboarding"):
        raise ValueError("role must be application, verification or onboarding; MCP gateways use their existing CLI")
    for field in ("aic", "endpoint", "mq_auth_url", "cert", "key", "trust_bundle"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError("missing platform configuration field: " + field)
    config["aic"] = config["aic"].strip().upper()
    leaders = config.get("allowed_leaders")
    if not isinstance(leaders, list) or not leaders or not all(isinstance(aic, str) for aic in leaders):
        raise ValueError("allowed_leaders must be a nonempty AIC list")
    config["allowed_leaders"] = sorted({aic.strip().upper() for aic in leaders})
    for aic in [config["aic"], *config["allowed_leaders"]]:
        valid, _ = validate_aic_format(aic)
        if not valid:
            raise ValueError("invalid platform AIC")
    if config["aic"] in config["allowed_leaders"]:
        raise ValueError("a domain cannot invite itself")
    config.setdefault("name", config["role"] + "-platform")
    config.setdefault("amp_directory", "amp/" + config["name"])
    config.setdefault("evidence_path", config["name"] + "-events.jsonl")
    config.setdefault("ledger_path", config["role"] + "-operations.sqlite")
    if not config["name"].replace("-", "").replace("_", "").isalnum():
        raise ValueError("name must be a simple identifier")
    for field in PATH_FIELDS:
        if config.get(field):
            value = Path(config[field])
            config[field] = str(value if value.is_absolute() else source.parent / value)
    url = urlparse(config["endpoint"])
    if url.scheme != "amqps" or not url.hostname or not url.port or url.username or url.password or url.fragment:
        raise ValueError("a published AMQPS endpoint without embedded credentials is required")
    endpoint = native.parse_amqp_endpoint_url(config["endpoint"], aic=config["aic"])
    if endpoint.inbox != native.build_inbox_queue_name(config["aic"]):
        raise ValueError("published Inbox does not match the domain AIC")
    auth = urlparse(config["mq_auth_url"])
    if auth.scheme != "https" or not auth.hostname or auth.username or auth.password or auth.query or auth.fragment:
        raise ValueError("mq_auth_url must be the HTTPS ACL service base URL")
    return config


def domain_environment(config):
    values = environment_file(config["env_file"]) if config.get("env_file") else {}
    os.environ.update(values)
    return [value for name, value in values.items() if re.search(r"password|token|secret|dsn|database_uri", name, re.I) and value]


def tls_context(config):
    mapped = {"partner_aic": config["aic"], "partner_cert": config["cert"], "partner_key": config["key"],
              "trust_bundle": config["trust_bundle"], "partner_key_password_env": config.get("key_password_env")}
    context, checks = native.validate_certificates(mapped, "partner", native.read_pem_certificates(config["trust_bundle"]))
    return context, checks


def signed_amp(config):
    key_pem = Path(config["key"]).read_text(encoding="utf-8")
    if config.get("key_password_env"):
        # Official CertificateAuditSigner accepts unencrypted PEM. Decrypt only
        # in memory; no temporary private-key file is written.
        from cryptography.hazmat.primitives import serialization
        key = serialization.load_pem_private_key(key_pem.encode(),
            password=os.environ[config["key_password_env"]].encode())
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
    if importlib.util.find_spec("jcs") is None:
        raise RuntimeError("the official AMP signing dependency jcs is not installed")
    signer = CertificateAuditSigner(private_key_pem=key_pem, cert_pem=Path(config["cert"]).read_text(encoding="utf-8"))
    amp = AmpRuntime(config["amp_directory"], config["name"], config["aic"])
    amp.audit = AuditEmitter(Path(config["amp_directory"]) / f"amp_audit_{config['name']}.jsonl", config["aic"], signer=signer)
    amp.signed_audit = True
    return amp


class DomainExecutorAdapter:
    """Adapt any domain execute(payload, authenticated_caller) to native tasks.

    Existing MCP gateways keep their own CLI and Bridge.bind_partner. This
    adapter supplies the same contract for ApplicationPartner/VerificationPartner.
    """
    def __init__(self, executor, aic, allowed_leaders, amp, *, secret_values=(), task_capacity=4096):
        if type(task_capacity) is not int or task_capacity < 1:
            raise ValueError("task_capacity must be a positive integer")
        self.executor, self.executor_aic, self.amp = executor, aic, amp
        self.allowed_leaders = frozenset(allowed_leaders)
        self.policy = SimpleNamespace(allowed_callers=self.allowed_leaders)
        self.secret_values, self.task_capacity = tuple(secret_values), task_capacity

    def _audit(self, command, payload, status, reason=None):
        event = {"event": "domain_task", "caller_aic": command.senderId,
            "incident_id": payload.get("incident_id", command.sessionId), "logical_task_id": payload.get("logical_task_id", command.taskId),
            "tool": payload.get("tool", command.command.value), "status": status}
        if payload.get("operation_id"):
            event["operation_id"] = payload["operation_id"]
        if reason:
            event["reason"] = reason
        self.amp.audit_event(event)

    def bind_partner(self, client):
        if not getattr(client, "_identity_binding_enabled", False) or client.partner_aic != self.executor_aic:
            raise ValueError("domain tasks require the official authenticated Partner identity boundary")
        tasks, locks = OrderedDict(), {}

        async def handler(command, is_mentioned):
            if not is_mentioned:
                return None
            group = getattr(client, "_group_info", None)
            leader = getattr(getattr(group, "leader", None), "aic", None)
            if (command.senderRole != "leader" or command.senderId not in self.allowed_leaders or command.senderId != leader
                    or command.groupId != client.group_id or not command.taskId or not command.sessionId):
                self._audit(command, {}, "rejected", "identity_context_mismatch")
                return {"status": "rejected", "reason": "identity_context_mismatch"}
            task_id = command.taskId
            async with locks.setdefault(task_id, asyncio.Lock()):
                saved = tasks.get(task_id)
                if saved and saved["session_id"] != command.sessionId:
                    self._audit(command, {}, "rejected", "task_session_mismatch")
                    return {"status": "rejected", "reason": "task_session_mismatch"}
                if command.command == TaskCommandType.Start:
                    if saved:
                        tasks.move_to_end(task_id)
                        await client.send_task_result(task_id, command.sessionId, saved["state"], products=saved["products"])
                        return saved["output"]
                    while len(tasks) >= self.task_capacity:
                        removable = next((key for key, value in tasks.items() if value["state"] in
                            (TaskState.Completed, TaskState.Canceled, TaskState.Rejected, TaskState.Failed)
                            and not locks[key].locked()), None)
                        if removable is None:
                            await client.reject_task(task_id, command.sessionId, "Domain task capacity reached")
                            return {"status": "rejected", "reason": "task_capacity_reached"}
                        tasks.pop(removable)
                        locks.pop(removable, None)
                    try:
                        if len(command.dataItems or []) != 1:
                            raise ValueError("one IFC item required")
                        item = command.dataItems[0]
                        value = item.data if isinstance(item, StructuredDataItem) else json.loads(item.text)
                        payload = TaskPayload.model_validate(value).model_dump(exclude_none=True)
                    except (AttributeError, ValueError, TypeError):
                        self._audit(command, {}, "rejected", "invalid_ifc_schema")
                        await client.reject_task(task_id, command.sessionId, "Invalid ifc/1.0 task schema")
                        return {"status": "rejected", "reason": "invalid_ifc_schema"}
                    await client.accept_task(task_id, command.sessionId)
                    await client.start_working(task_id, command.sessionId)
                    try:
                        output = await asyncio.wait_for(self.executor.execute(payload, command.senderId), payload["budget"]["deadline_ms"]/1000)
                        output = TaskProduct.model_validate(output).model_dump(exclude_none=True)
                        if (output["executor_aic"], output["incident_id"], output["logical_task_id"]) != (
                                self.executor_aic, payload["incident_id"], payload["logical_task_id"]):
                            raise ValueError("domain returned mismatched IFC identity")
                        if isinstance(output.get("description"), dict):
                            output["description"]["executor_aic"] = self.executor_aic
                    except Exception as exc:
                        output = {"schema_version": "ifc/1.0", "incident_id": payload["incident_id"],
                            "logical_task_id": payload["logical_task_id"], "executor_aic": self.executor_aic,
                            "status": "unknown" if payload["kind"] in ("act", "resume") else "tool_error",
                            "facts": [], "reason": type(exc).__name__}
                    output = sanitize(output, self.secret_values)
                    products = [Product(id="domain-"+task_id, name=payload["tool"], dataItems=[StructuredDataItem(data=output)])]
                    tasks[task_id] = {"session_id": command.sessionId, "state": TaskState.AwaitingCompletion,
                                      "products": products, "output": output}
                    self._audit(command, payload, output["status"], output.get("reason"))
                    await client.submit_for_completion(task_id, command.sessionId, products)
                    return output
                if saved is None:
                    self._audit(command, {}, "rejected", "task_not_started")
                    return {"status": "rejected", "reason": "task_not_started"}
                if command.command == TaskCommandType.Complete:
                    if saved["state"] not in (TaskState.AwaitingCompletion, TaskState.Completed):
                        return {"status": "rejected", "reason": "task_not_awaiting_completion"}
                    saved["state"] = TaskState.Completed
                    await client.complete_task(task_id, command.sessionId)
                elif command.command == TaskCommandType.Get:
                    await client.send_task_result(task_id, command.sessionId, saved["state"], products=saved["products"])
                elif command.command == TaskCommandType.Cancel and saved["state"] != TaskState.Completed:
                    saved["state"] = TaskState.Canceled
                    await client.cancel_task(task_id, command.sessionId)
                else:
                    return {"status": "rejected", "reason": "unsupported_task_transition"}
                return saved["output"]
        client.set_command_handler(handler)
        return handler


class DomainGroupRuntime(BridgeGroupRuntime):
    def __init__(self, *, allowed_leaders, **kwargs):
        self.allowed_leaders = frozenset(allowed_leaders)
        if not self.allowed_leaders:
            raise ValueError("a domain Leader allowlist is required")
        super().__init__(allowed_peer_aic=sorted(self.allowed_leaders)[0], **kwargs)

    def _invitation_policy(self, invitation):
        # Retain the baseline's exchange, member, expiry and lifecycle checks,
        # extending only its single allowed-peer field to a domain allowlist.
        leader = invitation.group.leader.aic
        if self._inbound_closing:
            return "Runtime is closing"
        if leader not in self.allowed_leaders or leader == self.leader_aic:
            return "Leader is not authorized for this domain"
        if not any(member.aic == self.leader_aic for member in invitation.group.partners):
            return "Invitation does not include this identity"
        if native.invitation_is_expired(invitation.expiresAt):
            return "Invitation expired"
        if invitation.amqp.exchange != native.build_group_exchange_name(leader, invitation.groupId):
            return "Invitation exchange does not match its Leader/group identity"
        return None


class PlatformWorker:
    def __init__(self, config, *, executor=None, amp=None, ssl_context=None):
        self.config = config
        self.executor, self.amp, self.ssl_context = executor, amp, ssl_context
        self.runtime = None
        self.started = False
        self.secret_values = ()

    def record(self, event, **data):
        record = sanitize({"event": event, "aic": self.config["aic"], **data}, self.secret_values)
        path = Path(self.config["evidence_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str)+"\n")
        if self.amp:
            self.amp.system.emit_sync(record)

    def prepare(self):
        if self.runtime is not None:
            return self.runtime
        self.secret_values = domain_environment(self.config)
        if self.ssl_context is None:
            self.ssl_context, _ = tls_context(self.config)
        self.amp = self.amp or signed_amp(self.config)
        if not self.amp.signed_audit:
            raise ValueError("formal platform domain workers require certificate-signed audit")
        if self.executor is None:
            if self.config["role"] == "application":
                self.executor = ApplicationPartner(self.config["aic"], OperationLedger(self.config["ledger_path"], "application"),
                    base_url=self.config.get("base_url"), allowed_callers=self.config["allowed_leaders"],
                    allowed_hosts=self.config.get("allowed_application_hosts", ()))
            elif self.config["role"] == "verification":
                self.executor = VerificationPartner(self.config["aic"], base_url=self.config.get("base_url", "http://127.0.0.1:8088"),
                    allowed_callers=self.config["allowed_leaders"], duration=self.config.get("verification_duration", 30))
            else:
                self.executor = OnboardingPartner(self.config["aic"], discovery_url=self.config["discovery_url"],
                    allowed_callers=self.config["allowed_leaders"])
        bridge = DomainExecutorAdapter(self.executor, self.config["aic"], self.config["allowed_leaders"], self.amp,
                                       secret_values=self.secret_values, task_capacity=self.config.get("task_capacity", 4096))
        endpoint = native.parse_amqp_endpoint_url(self.config["endpoint"], aic=self.config["aic"])
        self.runtime = DomainGroupRuntime(bridge=bridge, amp=self.amp, allowed_leaders=self.config["allowed_leaders"],
            leader_aic=self.config["aic"], record=self.record, ssl_context=self.ssl_context, identity_binding_enabled=True,
            rabbitmq_config={"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                "user": None, "password": None, "auth_service_url": self.config["mq_auth_url"]})
        return self.runtime

    async def start(self):
        if self.started:
            return self
        self.prepare()
        await self.amp.start()
        try:
            await asyncio.wait_for(self.runtime.start_inbound(), self.config.get("connect_timeout_seconds", 30))
            self.started = True
            self.amp.audit_event({"event": "platform_domain_started", "incident_id": "process-start",
                                  "caller_aic": self.config["aic"], "status": "ok"})
            self.record("platform_domain_ready", role=self.config["role"], signed_audit=True)
            return self
        except BaseException:
            await self.close()
            raise

    async def close(self):
        try:
            if self.runtime:
                await native.close_runtime(self.runtime, self.config.get("close_timeout_seconds", 15), self.record)
        finally:
            if self.amp:
                await self.amp.close()
            self.started = False


async def serve(config):
    worker = PlatformWorker(config)
    try:
        await worker.start()
        print(json.dumps({"status": "ready", "mode": "wutong-amqps", "role": config["role"], "aic": config["aic"]}), flush=True)
        await asyncio.Event().wait()
    finally:
        await worker.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Validate this domain's config/certificate offline; do not connect")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.check:
            domain_environment(config)
            _, checks = tls_context(config)
            if importlib.util.find_spec("jcs") is None:
                raise RuntimeError("the official AMP signing dependency jcs is not installed")
            print(json.dumps({"mode": "offline-platform-domain-config", "ready": True, "network_attempted": False,
                              "platform_run_success": False, "role": config["role"], "certificate": checks}, ensure_ascii=False))
        else:
            asyncio.run(serve(config))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_class": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
