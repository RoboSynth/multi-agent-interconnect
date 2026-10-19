"""Actual ADP discovery, describe confirmation and mTLS AIP group transport.

The configuration contains the coordinator's own certificate and public skill
queries only. Domain processes run independently; this transport never launches
tools with database/application credentials.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
import inspect
import json
import math
from pathlib import Path
import ssl
import time
import uuid

from integration import wutong_smoke as native
from acps_sdk.aip import StructuredDataItem, TextDataItem, TaskCommand
from acps_sdk.aip.aip_group_model import GroupMgmtResult
from acps_sdk.aip.resumable import TaskJournal, CoordinatorTerm, ResumableGroupLeader, Fence, ResumePackage
from incident.amp_setup import AmpRuntime
from incident.contracts import TaskPayload, TaskProduct, handover_evidence
from incident.selection import discover_candidates, select_participant
from incident.coordinator.amp_facts import AmpFactStore, TaskEvidence, ManagementStatusEvidence


class WutongTransport:
    mode = "wutong-amqps"

    def __init__(self, config, output, *, resume_payload_factory=None):
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
        self.resume_payload_factory = resume_payload_factory
        self.takeover_history_cutoffs = {}
        self._participant_failures = {}
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

    async def _select_participant(self, role, candidates, tool, *, initial=False):
        if initial:
            configured = self.config.get("initial_participant_aics", {})
            if not isinstance(configured, dict):
                raise ValueError("initial_participant_aics must map roles to AIC strings")
            if role in configured:
                aic = configured[role]
                if not isinstance(aic, str) or not aic.strip() or aic != aic.strip():
                    raise ValueError("initial participant AIC must be a nonempty exact string")
                candidates = [candidate for candidate in candidates if candidate["aic"] == aic]
        trusted = self.config.get("trusted_participant_aics", {}).get(role)
        resource = "public-acs" if role == "onboarding" else "orders"
        return await select_participant(candidates, resource=resource, tool=tool,
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
            self.session = await asyncio.wait_for(self.runtime.create_group_session(session_id, []), 60)
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
                    "ops": "ops.route_status", "verification": "incident.verification",
                    "onboarding": "aip.onboarding.check"}
        for role, skill in queries.items():
            candidates = await self._discover_candidates(role, skill)
            acs, description = await self._select_participant(role, candidates, required[role], initial=True)
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
        deadline = time.time() + timeout
        try:
            await asyncio.wait_for(self.runtime.start_task(session_id,
                task_content=json.dumps(payload, ensure_ascii=False), task_id=task_id,
                logical_task_id=payload["logical_task_id"], target_partners=[target]), timeout)
            deadline = time.time() + timeout
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
            deadline = None
            await self.runtime.complete_task(session_id, task_id, target_partner=target,
                                             logical_task_id=payload["logical_task_id"])
            deadline = time.time() + timeout
            await native.wait_for_state(self.session, task_id, target, native.TaskState.Completed, timeout)
        except (TimeoutError, ConnectionError, OSError) as error:
            self._remember_participant_failure(payload, target, error, deadline=deadline)
            raise
        # Completed is already confirmed. Local evidence storage cannot turn
        # that successful communication into a participant/channel failure.
        self.messages = [m.model_dump(mode="json") for m in self.session.message_history]
        try:
            (self.output / "messages.json").write_text(json.dumps(self.messages, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            raise RuntimeError("local AIP evidence persistence failed") from error
        return product.model_dump()

    async def call(self, payload):
        prefix = payload["tool"].split(".")[0]
        role = {"db": "database", "ops": "ops", "application": "application", "incident": "verification",
                "aip": "onboarding"}.get(prefix)
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
            try:
                result = await self._takeover(role, target, value, type(exc).__name__)
            except Exception as takeover_error:
                details = {"initial_error_class": type(exc).__name__,
                           "takeover_error_class": type(takeover_error).__name__,
                           "takeover_reason": str(takeover_error),
                           "takeover_rejection": getattr(takeover_error, "takeover_rejection", None)}
                for key, item in details.items():
                    setattr(exc, key, item)
                self.record("takeover_unavailable", failed_aic=target,
                            error_class=type(takeover_error).__name__, **details)
                raise exc from takeover_error
            result = {**result, "initial_error_class": type(exc).__name__, "takeover_error_class": None}
        self.evidence.setdefault(value["incident_id"], []).extend(result.get("facts", []))
        return result

    def _remember_participant_failure(self, payload, aic, error, *, deadline=None):
        observed = time.time()
        status = ("deadline_expired" if isinstance(error, TimeoutError) and deadline is not None
                  and observed >= deadline else "unknown" if isinstance(error, TimeoutError) else "channel_lost")
        key = (payload["incident_id"], payload["logical_task_id"])
        self._participant_failures[key] = {"aic": aic, "error": error,
            "task": TaskEvidence(aic, status, observed, deadline)}
        if len(self._participant_failures) > 128:
            self._participant_failures.pop(next(iter(self._participant_failures)))

    def _participant_reply_since(self, aic, start):
        return any(isinstance(message, GroupMgmtResult) and message.senderId == aic
            and message.senderRole == "partner" and message.sessionId == self.session.session_id
            and message.groupId == self.session.group_id for message in self.session.message_history[start:])

    async def _participant_management(self, aic, *, timeout):
        requested = time.time()
        start = len(self.session.message_history)
        phase, outcome = "publish", "unknown"
        try:
            await asyncio.wait_for(self.runtime.check_partner_status(aic, session_id=self.session.session_id), timeout)
            phase = "reply"
            until = time.monotonic() + timeout
            while not self._participant_reply_since(aic, start):
                if time.monotonic() >= until:
                    raise TimeoutError("management reply deadline expired")
                await asyncio.sleep(min(.02, max(0, until - time.monotonic())))
            outcome = "reply"
        except TimeoutError:
            outcome = "timeout" if phase == "reply" else "no_reply"
        except (ConnectionError, OSError):
            outcome = "no_reply"
        except Exception:
            outcome = "unknown"
        return ManagementStatusEvidence(aic, outcome, requested, time.time()), phase, start

    async def participant_health(self, payload, *, error):
        """Assess selected-participant evidence; configured AMP paths only."""
        aic = None
        try:
            saved = self._participant_failures.get((payload["incident_id"], payload["logical_task_id"]))
            if saved is None or saved["error"] is not error:
                raise ValueError("no bound task failure")
            aic, task = saved["aic"], saved["task"]
            timeout = self.config.get("participant_health_timeout_seconds", 2)
            wait = self.config.get("participant_health_wait_seconds", 0)
            if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30
                    or type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 60):
                raise ValueError("participant health bounds are invalid")
            configured = self.config.get("participant_amp_paths", {})
            if not isinstance(configured, dict) or not isinstance(configured.get(aic, []), list):
                raise ValueError("participant AMP sources must be an explicit per-AIC list")
            paths = [Path(value).resolve() for value in configured.get(aic, [])]
            if any(path.suffix != ".jsonl" or not path.name.startswith(("amp_heartbeat_", "amp_access_")) for path in paths):
                raise ValueError("participant AMP source is not a heartbeat/access log")
            management, phase, start = await self._participant_management(aic, timeout=timeout)
            store = AmpFactStore(heartbeat_ttl_seconds=self.config.get("participant_heartbeat_ttl_seconds", 45),
                access_ttl_seconds=self.config.get("participant_access_ttl_seconds", 60),
                evidence_ttl_seconds=self.config.get("participant_evidence_ttl_seconds", 60))
            store.load_jsonl(paths)
            result = store.assess(aic, task=task, management=management)
            proof = result["evidence"]
            expiry = proof.get("heartbeat_expires_at")
            if (wait and proof["task_valid"] and proof["management_outcome"] in {"no_reply", "timeout"}
                    and proof["heartbeat_state"] == "fresh" and result["participant_state"] == "unknown"
                    and type(expiry) in (int, float)):
                await asyncio.sleep(min(wait, max(.01, expiry - time.time() + .01)))
                store.load_jsonl(paths)
                if self._participant_reply_since(aic, start):
                    management = ManagementStatusEvidence(aic, "reply", management.requested_at, time.time())
                result = store.assess(aic, task=task, management=management)
            result.update(transport=self.mode, manual_required=True)
            result["evidence"].update(management_probe_phase=phase,
                management_requested_at=management.requested_at,
                management_observed_at=management.observed_at,
                management_probe_session=self.session.session_id, management_history_start=start)
            return result
        except Exception as exc:
            return {"schema_version": "participant-health/1.0", "aic": aic, "confirmed": False,
                "participant_state": "unknown", "task_status": "unknown", "manual_required": True,
                "reason": "participant_health_evidence_unavailable", "facts": [], "business_state": "unknown",
                "diagnostics": {"adapter_error": type(exc).__name__}}

    async def _takeover(self, role, failed, original, reason):
        """Confirm a fresh ADP candidate and its shared-resource fence before replay."""
        async with self.takeover_locks.setdefault(role, asyncio.Lock()):
            started = time.monotonic()
            incident, logical_id = original["incident_id"], original["logical_task_id"]
            messages_path = self.output / "messages.jsonl"
            history_bytes = messages_path.stat().st_size if messages_path.exists() else 0
            self.takeover_history_cutoffs[(incident, logical_id)] = history_bytes
            self.record("takeover_started", incident_id=incident, logical_task_id=logical_id,
                        failed_aic=failed, reason=reason, discovery="official-adp",
                        history_bytes_before_takeover=history_bytes)
            self.journal.record_takeover(incident, failed, reason)
            skill = self.config.get("skills", {}).get(role, {"database": "db.observe", "ops": "ops.observe",
                "application": "incident.application", "verification": "incident.verification",
                "onboarding": "aip.onboarding.check"}[role])
            candidates = await self._discover_candidates(role, skill)
            # Match the complete resource scope of the failed participant, not only a skill label.
            previous_scope = self.descriptions[role].get("resource_scope", self.descriptions[role].get("resources"))
            candidate_error = None
            rejections = []
            for candidate in sorted(candidates, key=lambda item: item["aic"]):
                if candidate["aic"] == failed:
                    continue
                try:
                    acs, description = await self._select_participant(role, [candidate], original["tool"])
                    if description.get("resource_scope", description.get("resources")) != previous_scope:
                        continue
                    original_fence = original.get("fence", {"coordinator_term": self.term, "takeover_version": 0})
                    previous = self.active_fences.get(role, Fence(**original_fence))
                    proposed = Fence(max(self.term, previous.coordinator_term), previous.takeover_version+1)
                    operation_id = original.get("operation_id") or incident+":observe:"+logical_id
                    package = ResumePackage(logical_id, "Continue the interrupted incident task",
                        evidence_refs=self._handover_evidence(incident),
                        remaining_tasks=[{"tool": original["tool"], "kind": original["kind"], "args": original.get("args", {})}],
                        operations=[{"operation_id": operation_id, "status": "delivery_unknown"}] if original.get("operation_id") else [],
                        fence=proposed)
                    resume = {**original, "kind": "resume", "operation_id": operation_id,
                        "fence": proposed.to_dict(), "args": {"advance_fence": True, "resume_package": package.to_dict()}}
                    resume = await self._resume_payload(resume, package, original_fence=original_fence)
                    control = await self._send(resume, acs["aic"])
                    if control.get("status") in {"rejected", "tool_error"}:
                        detail = control.get("reason")
                        if not isinstance(detail, str) or not detail:
                            detail = "replacement returned " + control["status"]
                        self.record("takeover_control_rejected", incident_id=incident, logical_task_id=logical_id,
                                    candidate_aic=acs["aic"], status=control["status"], reason=detail)
                        error = RuntimeError("replacement did not accept the resume: " + detail)
                        error.takeover_rejection = {"candidate_aic": acs["aic"],
                                                    "status": control["status"], "reason": detail}
                        raise error
                    operation = control.get("operation")
                    operation = operation if isinstance(operation, dict) else {}
                    confirmed = control.get("active_fence") or operation.get("active_fence")
                    if not isinstance(confirmed, dict) or Fence(**confirmed) < proposed:
                        raise RuntimeError("replacement did not activate the shared-resource fence")
                    fence = Fence(**confirmed)
                    self.active_fences[role] = fence
                    self.selected[role] = acs["aic"]
                    self.descriptions[role] = description
                    self.journal.record_takeover(incident, failed, reason, replacement=acs["aic"], fence=confirmed, state="fenced")
                    await self.runtime.force_remove_partner(failed, session_id=self.session.session_id)
                    state = operation.get("state", "unknown")
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
                    candidate_error = exc
                    rejection = getattr(exc, "takeover_rejection", None)
                    if rejection:
                        rejections.append(rejection)
                    self.record("takeover_candidate_failed", candidate_aic=candidate["aic"],
                        error_class=type(exc).__name__, reason=str(exc),
                        rejection=rejection)
                    self.journal.record_takeover(incident, failed, reason, replacement=candidate["aic"],
                                                state="candidate_failed:"+type(exc).__name__)
            error = RuntimeError("no confirmed ADP replacement completed the takeover")
            error.takeover_rejection = rejections[-1] if rejections else None
            if error.takeover_rejection:
                error.args = (str(error) + ": " + error.takeover_rejection["reason"],)
            raise error from candidate_error

    async def _resume_payload(self, default: dict, package: ResumePackage, *, original_fence=None) -> dict:
        """Match the local factory contract: replace information, never authority."""
        if self.resume_payload_factory is None:
            return default
        expected = deepcopy(default)
        value = self.resume_payload_factory(deepcopy(default), deepcopy(package))
        if inspect.isawaitable(value):
            value = await value
        TaskPayload.model_validate(value)
        if ({k: v for k, v in value.items() if k != "args"} !=
                {k: v for k, v in expected.items() if k != "args"}):
            raise ValueError("handover factory cannot change operation, fence, identity, approval or budget")
        if value.get("args", {}).get("advance_fence") is not True:
            raise ValueError("handover factory must retain args.advance_fence=true")
        handover = value["args"].get("handover")
        if handover is not None:
            control = handover.get("control", {}) if isinstance(handover, dict) else {}
            if (control.get("operation_id") != expected["operation_id"] or
                    control.get("replacement_fence") != expected["fence"] or
                    control.get("original_fence") != original_fence):
                raise ValueError("handover information cannot change the original operation or fences")
        supplied = value["args"].get("resume_package")
        if supplied is not None:
            if not isinstance(supplied, dict) or any(supplied.get(key) != package.to_dict().get(key)
                    for key in ("logical_task_id", "operations", "fence")):
                raise ValueError("handover package cannot change operation identity or fence")
        return value

    def _handover_evidence(self, incident):
        return handover_evidence(self.evidence.get(incident, []), self.config.get("evidence_ttl_seconds", 60))

    async def close(self):
        self.closing = True
        try:
            if self.session and self.runtime:
                self.record("group_session_close_started", session_id=self.session.session_id,
                            group_id=self.session.group_id)
                await asyncio.wait_for(self.runtime.dissolve_group_session(self.session.session_id), 60)
                self.record("group_session_close_completed", session_id=self.session.session_id,
                            group_id=self.session.group_id)
        finally:
            try:
                if self.runtime:
                    await native.close_runtime(self.runtime, 15, self.record)
            finally:
                await self.amp.close()
