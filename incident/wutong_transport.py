"""Actual ADP discovery, describe confirmation and mTLS AIP group transport.

The configuration contains the coordinator's own certificate and public skill
queries only. Domain processes run independently; this transport never launches
tools with database/application credentials.
"""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import ssl
import time
import uuid

from integration import wutong_smoke as native
from acps_sdk.aip import StructuredDataItem, TextDataItem, TaskCommand
from acps_sdk.aip.resumable import TaskJournal, CoordinatorTerm, ResumableGroupLeader, Fence, ResumePackage
from incident.amp_setup import AmpRuntime
from incident.contracts import TaskProduct, handover_evidence
from incident.selection import discover_candidates, select_participant


class WutongTransport:
    mode = "wutong-amqps"

    def __init__(self, config, output):
        self.config, self.output = config, Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.journal = TaskJournal(self.output / "journal.sqlite")
        self.runtime = self.session = None
        self.selected, self.participants, self.tools, self.messages = {}, [], [], []
        identity = config["leader"]
        self.aic = identity["aic"]
        # Native and platform development modes touch the same orders resource;
        # they must reserve terms from the same persistent authority.
        term_path = config.get("term_journal_path", Path(__file__).resolve().parents[1] / "runtime/coordinator-terms.sqlite")
        self.term_journal = TaskJournal(term_path)
        self.coordinator_term = CoordinatorTerm(self.term_journal, config.get("term_namespace", "local-coordinator"))
        self.term = int(self.coordinator_term)
        self.descriptions, self.active_fences, self.evidence, self.takeover_locks = {}, {}, {}, {}
        self.on_event = None
        self.closing = False
        self.amp = AmpRuntime(self.output / "amp", "coordinator", self.aic,
                              cert=identity["cert"], key=identity["key"])
        self.approval_authority = None
        if config.get("approval_env_file"):
            from acps_mcp_bridge.approval import ApprovalAuthority
            path = Path(config["approval_env_file"])
            values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                          if line and not line.startswith("#"))
            if set(values) != {"INCIDENT_APPROVAL_SECRET"}:
                raise ValueError("Coordinator approval file may contain only the approval key")
            self.approval_authority = ApprovalAuthority(values["INCIDENT_APPROVAL_SECRET"])

    def record(self, event, **data):
        record = {"event": event, **data}
        with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self.amp.system.emit_sync(record)
        if self.on_event:
            self.on_event(record)

    async def _describe(self, acs):
        phase = "invite"
        try:
            await self.runtime.invite_partner(self.session.session_id, native.ACSObject(aic=acs["aic"]), partner_acs_data=acs)
            phase = "describe-task"
            payload = {"schema_version": "ifc/1.0", "incident_id": "capability-confirmation",
                "logical_task_id": "describe-"+uuid.uuid4().hex, "kind": "describe", "tool": "describe",
                "args": {}, "budget": {"deadline_ms": 15000}}
            result = await self._send(payload, acs["aic"])
            if result["status"] != "ok":
                raise RuntimeError("participant rejected capability confirmation")
            return {**result.get("description", {}), "executor_aic": result["executor_aic"]}
        except (Exception, asyncio.CancelledError) as exc:
            self.record("capability_confirmation_failed", aic=acs["aic"], phase=phase, error_class=type(exc).__name__)
            raise

    async def _select_participant(self, role, candidates, tool):
        trusted = self.config.get("trusted_participant_aics", {}).get(role)
        return await select_participant(candidates, resource="orders", tool=tool,
            describe=self._describe, trusted_aics=trusted,
            describe_timeout_seconds=self.config.get("participant_describe_timeout_seconds", 30),
            record=lambda event, **data: self.record(event, role=role, **data))

    async def _discover_candidates(self, role, skill):
        try:
            return await discover_candidates(self.config["discovery_url"], skill, record=self.record)
        except Exception as exc:
            self.record("official_discovery_failed", role=role, phase="official-adp", error_class=type(exc).__name__)
            raise

    def _capture(self, direction, message, peer):
        row = {"direction": direction, "worker_aic": peer, "transport": self.mode,
               "message": message.model_dump(mode="json", exclude_none=True)}
        with (self.output / "messages.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")

    async def start(self):
        identity = self.config["leader"]
        context = ssl.create_default_context(cafile=self.config["trust_bundle"])
        context.load_cert_chain(identity["cert"], identity["key"])
        endpoint = native.parse_amqp_endpoint_url(identity["endpoint"], aic=self.aic)
        leader = native.InboundProbeLeader(leader_aic=self.aic, allowed_peer_aic=self.aic,
            record=self.record, ssl_context=context, identity_binding_enabled=True,
            access_emitter=self.amp.access, message_emitter=self.amp.message,
            rabbitmq_config={"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                             "user": None, "password": None, "auth_service_url": self.config["mq_auth_url"]})
        self.runtime = ResumableGroupLeader(leader, self.journal, self.coordinator_term)
        leader.add_task_listener(lambda session, message: self._capture("receive", message, message.senderId))
        self.term = int(self.runtime.term)
        await self.amp.start()
        await asyncio.wait_for(self.runtime.start_inbound(), 30)
        session_id = "incident-"+uuid.uuid4().hex
        self.record("group_session_creation_started", session_id=session_id, group_id="group-"+session_id,
                    owner_aic=self.aic)
        try:
            self.session = await asyncio.wait_for(self.runtime.create_group_session(session_id, []), 30)
        except Exception as exc:
            self.record("group_session_creation_failed", session_id=session_id, phase="group-create",
                        error_class=type(exc).__name__)
            raise
        self.record("group_session_created", session_id=session_id, group_id=self.session.group_id, owner_aic=self.aic)
        publisher = self.session.leader_mq_client.publish_message
        async def capture_published(message):
            await publisher(message)
            if isinstance(message, TaskCommand):
                for peer in message.mentions or []:
                    self._capture("send", message, peer)
        self.session.leader_mq_client.publish_message = capture_published
        queries = self.config.get("skills", {"application": "incident.application", "database": "db.observe",
                                             "ops": "ops.observe", "verification": "incident.verification"})
        required = {"application": "application.status", "database": "db.read_only_status",
                    "ops": "ops.route_status", "verification": "incident.verification"}
        for role, skill in queries.items():
            candidates = await self._discover_candidates(role, skill)
            acs, description = await self._select_participant(role, candidates, required[role])
            self.selected[role] = acs["aic"]
            self.descriptions[role] = description
            self.participants.append({"role": role, "aic": acs["aic"],
                                      "resources": description.get("resources", description.get("resource_scope", []))})
            self.tools.extend(t if isinstance(t, str) else t.get("name", t.get("id")) for t in description["tools"])
            self.record("adp_participant_confirmed", role=role, aic=acs["aic"], description=description)

    def issue_approval(self, payload):
        if self.approval_authority is None:
            raise RuntimeError("approval key has not been configured")
        return self.approval_authority.issue(payload, self.aic, approved_by="workbench")

    async def _send(self, payload, target):
        started = time.monotonic()
        self.amp.sampler.active += 1
        success = False
        try:
            result = await self._dispatch(payload, target)
            success = result.get("status") == "ok"
            self.amp.audit_event({**payload, "caller_aic": self.aic, "status": result.get("status")})
            return result
        finally:
            self.amp.sampler.active -= 1
            self.amp.sampler.record((time.monotonic()-started)*1000, success)

    async def _dispatch(self, payload, target):
        task_id = "aip-" + uuid.uuid4().hex
        session_id = self.session.session_id
        timeout = payload.get("budget", {}).get("deadline_ms", 15000)/1000 + 5
        await asyncio.wait_for(self.runtime.start_task(session_id,
            task_content=json.dumps(payload, ensure_ascii=False), task_id=task_id,
            logical_task_id=payload["logical_task_id"], target_partners=[target]), timeout)
        await native.wait_for_state(self.session, task_id, target, native.TaskState.AwaitingCompletion, timeout)
        messages = [m for m in self.session.message_history if isinstance(m, native.TaskResult)
                    and m.taskId == task_id and m.senderId == target and m.status.state == native.TaskState.AwaitingCompletion]
        if not messages:
            raise RuntimeError("missing actual AIP product")
        items = [item for product in messages[-1].products or [] for item in product.dataItems or []]
        if len(items) != 1:
            raise RuntimeError("one ifc/1.0 result item is required")
        value = items[0].data if isinstance(items[0], StructuredDataItem) else json.loads(items[0].text)
        product = TaskProduct.model_validate(value)
        if (product.executor_aic, product.incident_id, product.logical_task_id) != (
                target, payload["incident_id"], payload["logical_task_id"]):
            raise RuntimeError("AIP product identity/correlation mismatch")
        await self.runtime.complete_task(session_id, task_id, target_partner=target,
                                         logical_task_id=payload["logical_task_id"])
        await native.wait_for_state(self.session, task_id, target, native.TaskState.Completed, timeout)
        self.messages = [m.model_dump(mode="json") for m in self.session.message_history]
        (self.output / "messages.json").write_text(json.dumps(self.messages, ensure_ascii=False, indent=2), encoding="utf-8")
        return product.model_dump()

    async def call(self, payload):
        prefix = payload["tool"].split(".")[0]
        role = {"db": "database", "ops": "ops", "application": "application", "incident": "verification"}.get(prefix)
        if role not in self.selected:
            raise RuntimeError("no confirmed participant for this tool")
        value = dict(payload)
        if value.get("kind") == "act" and role in self.active_fences:
            value["fence"] = self.active_fences[role].to_dict()
        target = self.selected[role]
        try:
            result = await self._send(value, target)
        except (TimeoutError, ConnectionError, OSError) as exc:
            if self.closing or not self.config.get("automatic_takeover", True):
                raise
            result = await self._takeover(role, target, value, type(exc).__name__)
        self.evidence.setdefault(value["incident_id"], []).extend(result.get("facts", []))
        return result

    async def _takeover(self, role, failed, original, reason):
        """Confirm a fresh ADP candidate and its shared-resource fence before replay."""
        async with self.takeover_locks.setdefault(role, asyncio.Lock()):
            started = time.monotonic()
            incident, logical_id = original["incident_id"], original["logical_task_id"]
            self.record("takeover_started", incident_id=incident, logical_task_id=logical_id,
                        failed_aic=failed, reason=reason, discovery="official-adp")
            self.journal.record_takeover(incident, failed, reason)
            skill = self.config.get("skills", {}).get(role, {"database": "db.observe", "ops": "ops.observe",
                "application": "incident.application", "verification": "incident.verification"}[role])
            candidates = await self._discover_candidates(role, skill)
            # Match the complete resource scope of the failed participant, not only a skill label.
            previous_scope = self.descriptions[role].get("resource_scope", self.descriptions[role].get("resources"))
            for candidate in sorted(candidates, key=lambda item: item["aic"]):
                if candidate["aic"] == failed:
                    continue
                try:
                    acs, description = await self._select_participant(role, [candidate], original["tool"])
                    if description.get("resource_scope", description.get("resources")) != previous_scope:
                        continue
                    previous = self.active_fences.get(role, Fence(**original.get("fence", {
                        "coordinator_term": self.term, "takeover_version": 0})))
                    proposed = Fence(max(self.term, previous.coordinator_term), previous.takeover_version+1)
                    operation_id = original.get("operation_id") or incident+":observe:"+logical_id
                    package = ResumePackage(logical_id, "Continue the interrupted incident task",
                        evidence_refs=self._handover_evidence(incident),
                        remaining_tasks=[{"tool": original["tool"], "kind": original["kind"], "args": original.get("args", {})}],
                        operations=[{"operation_id": operation_id, "status": "delivery_unknown"}] if original.get("operation_id") else [],
                        fence=proposed)
                    control = await self._send({**original, "kind": "resume", "operation_id": operation_id,
                        "fence": proposed.to_dict(), "args": {"advance_fence": True, "resume_package": package.to_dict()}}, acs["aic"])
                    confirmed = control.get("active_fence") or control.get("operation", {}).get("active_fence")
                    if not isinstance(confirmed, dict) or Fence(**confirmed) < proposed:
                        raise RuntimeError("replacement did not activate the shared-resource fence")
                    fence = Fence(**confirmed)
                    self.active_fences[role] = fence
                    self.selected[role] = acs["aic"]
                    self.descriptions[role] = description
                    self.journal.record_takeover(incident, failed, reason, replacement=acs["aic"], fence=confirmed, state="fenced")
                    await self.runtime.force_remove_partner(failed, session_id=self.session.session_id)
                    state = control.get("operation", {}).get("state", "unknown")
                    if original["kind"] in {"observe", "verify", "describe"}:
                        result = await self._send(original, acs["aic"])
                    elif state in {"applied", "skipped_already_applied", "reconciled_applied"} and control.get("status") == "ok":
                        result = control
                    elif state == "received":
                        result = await self._send({**original, "fence": confirmed}, acs["aic"])
                    else:
                        result = {**control, "status": "unknown"}
                    self.journal.record_takeover(incident, failed, reason, replacement=acs["aic"], fence=confirmed,
                        state="resumed" if result.get("status") == "ok" else "needs_reconciliation")
                    self.record("takeover_completed", incident_id=incident, logical_task_id=logical_id,
                        failed_aic=failed, replacement_aic=acs["aic"], fence=confirmed, status=result["status"],
                        elapsed_seconds=round(time.monotonic()-started, 3), discovery="official-adp")
                    return result
                except (TimeoutError, ConnectionError, OSError, RuntimeError, ValueError) as exc:
                    self.journal.record_takeover(incident, failed, reason, replacement=candidate["aic"],
                                                state="candidate_failed:"+type(exc).__name__)
            raise RuntimeError("no confirmed ADP replacement completed the takeover")

    def _handover_evidence(self, incident):
        return handover_evidence(self.evidence.get(incident, []), self.config.get("evidence_ttl_seconds", 60))

    async def close(self):
        self.closing = True
        try:
            if self.session and self.runtime:
                self.record("group_session_close_started", session_id=self.session.session_id,
                            group_id=self.session.group_id)
                await asyncio.wait_for(self.runtime.dissolve_group_session(self.session.session_id), 15)
                self.record("group_session_close_completed", session_id=self.session.session_id,
                            group_id=self.session.group_id)
        finally:
            try:
                if self.runtime:
                    await native.close_runtime(self.runtime, 15, self.record)
            finally:
                await self.amp.close()
