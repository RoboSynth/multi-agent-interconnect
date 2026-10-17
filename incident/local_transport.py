"""Official AIP task models and clients over isolated local stdio processes.

This transport deliberately identifies itself as local-aip-stdio. It provides
local process/channel identity binding, not AMQPS, mTLS, or platform discovery.
Resource environment files are passed as paths to domain workers and never read
by this coordinator. Only a separate approval-key file may be read here.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_sdk.aip import StructuredDataItem, TaskResult, TaskState
from acps_sdk.aip.aip_group_leader import GroupLeaderMqClient
from acps_sdk.aip.resumable import CoordinatorTerm, Fence, ResumePackage, TaskJournal
from acps_sdk.amp import MessageBody, MessageDestination
from acps_mcp_bridge import ApprovalAuthority
from incident.amp_setup import AmpRuntime
from incident.contracts import TaskPayload, TaskProduct, handover_evidence
from incident.coordinator.planner import PROBES


def local_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def environment_file(path: str | Path, *, allowed_names: set[str] | None = None) -> dict[str, str]:
    values = {}
    for line in local_path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("invalid environment file entry")
        if allowed_names is not None and key not in allowed_names:
            raise ValueError("coordinator approval file contains a non-approval variable")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


async def emit_message(emitter, message, event_type, channel):
    body = message.model_dump(mode="json", exclude_none=True)
    await emitter.emit(MessageBody(event_type=event_type, system="local-stdio",
        destination=MessageDestination(name=channel, kind="queue"), message_id=body.get("id"),
        attributes={"transport": "local-aip-stdio", "groupId": body.get("groupId"),
                    "msgType": body.get("type"), "taskId": body.get("taskId")}),
        trace_id=body.get("sessionId"), correlation_id=body.get("taskId"))


@dataclass
class LocalWorker:
    spec: dict[str, Any]
    process: Any
    ready: asyncio.Future
    stderr_file: Any
    reader: asyncio.Task | None = None
    tools: list[str] = field(default_factory=list)
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state: str = "starting"
    resource_scope: Any = None
    failure_reason: str | None = None


class LocalAipStdioTransport:
    mode = "local-aip-stdio"

    def __init__(self, config_path: str | Path | dict, directory: str | Path | None = None, *, on_event=None,
                 resume_payload_factory=None):
        self.config_path = local_path(config_path) if not isinstance(config_path, dict) else None
        self.config = dict(config_path) if isinstance(config_path, dict) else json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        self.directory = local_path(directory or self.config.get("directory", "output/local-aip"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.coordinator_aic = self.config["coordinator_aic"]
        self.group_id = self.config.get("group_id", "local-incident-group")
        self.journal = TaskJournal(local_path(self.config.get("journal_path", self.directory / "tasks.sqlite")))
        self.term_journal = TaskJournal(local_path(self.config.get("term_journal_path", "runtime/coordinator-terms.sqlite")))
        self.term = int(CoordinatorTerm(self.term_journal, "local-coordinator"))
        self.amp_directory = local_path(self.config.get("amp_directory", self.directory / "amp"))
        self.amp = AmpRuntime(self.amp_directory, "coordinator", self.coordinator_aic)
        self.leader = GroupLeaderMqClient(self.coordinator_aic, access_emitter=self.amp.access,
                                          message_emitter=self.amp.message, message_system="local-stdio")
        self.leader._group_id = self.group_id
        self.leader.publish_message = self._publish
        self.on_event = on_event
        self.resume_payload_factory = resume_payload_factory
        self.workers: dict[str, LocalWorker] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self.tools = [p.tool for p in PROBES]
        self.started = False
        self.closing = False
        self._approval = None
        self.active_workers: dict[str, str] = {}
        self.active_fences: dict[str, Fence] = {}
        self.takeover_locks: dict[str, asyncio.Lock] = {}
        self.evidence: dict[str, list[dict[str, Any]]] = {}
        self.events: list[dict[str, Any]] = []
        self.messages_path = self.directory / "messages.jsonl"
        self._capture_lock = asyncio.Lock()
        if self.config.get("approval_env_file"):
            values = environment_file(self.config["approval_env_file"], allowed_names={"INCIDENT_APPROVAL_SECRET"})
            self._approval = ApprovalAuthority(values["INCIDENT_APPROVAL_SECRET"])

    @property
    def participants(self) -> list[dict[str, Any]]:
        return self.worker_status()

    def worker_status(self) -> list[dict[str, Any]]:
        return [{"name": name, "role": worker.spec["role"], "aic": worker.spec["aic"],
                 "pid": worker.process.pid, "status": worker.state,
                 "tools": list(worker.tools), "transport": self.mode,
                 "standby": bool(worker.spec.get("standby")), "resource_scope": worker.resource_scope,
                 "identity_binding": "local-process-channel"}
                for name, worker in self.workers.items()]

    def issue_approval(self, payload: dict) -> dict:
        if self._approval is None:
            raise RuntimeError("a separate approval_env_file has not been configured")
        return self._approval.issue(payload, self.coordinator_aic, approved_by="local-workbench-operator")

    async def _event(self, event: str, **data):
        record = {"event": event, "transport": self.mode, **data}
        self.events.append(record)
        if self.on_event:
            value = self.on_event(record)
            if inspect.isawaitable(value):
                await value

    async def _capture(self, direction, worker, message):
        record = {"direction": direction, "worker": worker.spec["name"], "worker_aic": worker.spec["aic"],
                  "transport": self.mode, "timestamp": datetime.now(timezone.utc).isoformat(),
                  "message": message.model_dump(mode="json", by_alias=True, exclude_none=True)}
        def append():
            with self.messages_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        async with self._capture_lock:
            await asyncio.to_thread(append)

    async def start(self):
        if self.started:
            return self
        if self.closing:
            raise RuntimeError("transport has been closed")
        specs = self.config.get("workers", [])
        if not specs:
            raise ValueError("at least one domain worker is required")
        await self.amp.start()
        names, aics = set(), set()
        try:
            for spec in specs:
                name, aic = spec["name"], spec["aic"]
                if not isinstance(name, str) or not name.replace("-", "").replace("_", "").isalnum() or name in names or aic in aics or aic == self.coordinator_aic:
                    raise ValueError("worker names and AICs must be distinct local identities")
                names.add(name)
                aics.add(aic)
                command = [str(local_path(self.config["python"])) if self.config.get("python") else sys.executable,
                    str(ROOT / "incident/local_worker.py"), "--name", name, "--role", spec["role"], "--aic", aic,
                    "--coordinator-aic", self.coordinator_aic, "--group-id", self.group_id,
                    "--amp-directory", str(self.amp_directory),
                    "--ledger-path", str(local_path(spec.get("ledger_path", self.directory / name / "operations.sqlite")))]
                for key in ("env_file", "bridge_config", "base_url", "verification_duration"):
                    if spec.get(key) is not None:
                        value = local_path(spec[key]) if key in ("env_file", "bridge_config") else spec[key]
                        command.extend(["--" + key.replace("_", "-"), str(value)])
                if spec.get("crash_point"):
                    if not self.config.get("experiment_id") or not self.config.get("allow_experiment_crash"):
                        raise ValueError("crash hooks require an explicit isolated experiment configuration")
                    command.extend(["--experiment-id", str(self.config["experiment_id"]),
                                    "--crash-point", spec["crash_point"],
                                    "--crash-tool", spec.get("crash_tool", "db.read_only_status" if spec["crash_point"] == "after_observation" else "db.restore_writes")])
                error_path = self.directory / name / "stderr.log"
                error_path.parent.mkdir(parents=True, exist_ok=True)
                error_file = error_path.open("ab")
                environment = {key: value for key, value in os.environ.items()
                    if not re.search(r"PASSWORD|TOKEN|SECRET|DATABASE|^PG|_KEY$|DSN", key, re.I)}
                environment["PYTHONIOENCODING"] = "utf-8"
                options = {"creationflags": 0x08000000} if os.name == "nt" else {}
                try:
                    process = await asyncio.create_subprocess_exec(*command, cwd=str(ROOT), env=environment,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=error_file,
                        limit=2**20, **options)
                except BaseException:
                    error_file.close()
                    raise
                worker = LocalWorker(dict(spec), process, asyncio.get_running_loop().create_future(), error_file)
                self.workers[name] = worker
                worker.reader = asyncio.create_task(self._read_worker(name, worker))
            await asyncio.wait_for(asyncio.gather(*(w.ready for w in self.workers.values())),
                                   timeout=float(self.config.get("startup_timeout_seconds", 90)))
            self.tools = sorted({tool for worker in self.workers.values() for tool in worker.tools})
            for worker in self.workers.values():
                if not worker.spec.get("standby"):
                    self.active_workers.setdefault(worker.spec["role"], worker.spec["aic"])
            self.started = True
            await self._event("transport_started", participants=self.worker_status(), coordinator_term=self.term)
            return self
        except BaseException:
            await self.close()
            raise

    async def _read_worker(self, name, worker):
        try:
            while True:
                line = await worker.process.stdout.readline()
                if not line:
                    break
                raw = json.loads(line)
                if raw.get("event") == "ready":
                    if raw.get("aic") != worker.spec["aic"] or raw.get("mode") != self.mode:
                        raise ValueError("worker ready identity mismatch")
                    worker.tools = list(raw["tools"])
                    worker.resource_scope = raw.get("resource_scope")
                    worker.state = "ready"
                    if not worker.ready.done():
                        worker.ready.set_result(raw)
                    continue
                if raw.get("event") == "startup_error":
                    raise RuntimeError("domain worker startup failed: " + str(raw.get("error_class", "unknown")))
                message = TaskResult.model_validate(raw)
                if (message.senderId != worker.spec["aic"] or message.senderRole != "partner"
                        or message.groupId != self.group_id):
                    raise ValueError("TaskResult differs from its bound local process channel")
                pending = self.pending.get(message.taskId)
                if pending is None:
                    raise ValueError("unsolicited TaskResult")
                if pending["worker"] is not worker or message.sessionId != pending["payload"]["incident_id"]:
                    raise ValueError("TaskResult session or worker mismatch")
                await self._capture("receive", worker, message)
                await emit_message(self.amp.message, message, "receive", name + ".stdout")
                self.journal.transition(pending["attempt_id"], message.status.state, message.model_dump(mode="json", exclude_none=True))
                await self._event("task_state", aic=message.senderId, task_id=message.taskId,
                                  logical_task_id=pending["payload"]["logical_task_id"], state=message.status.state.value)
                if message.status.state == TaskState.AwaitingCompletion:
                    products = message.products or []
                    items = products[0].dataItems if len(products) == 1 else []
                    if len(items) != 1 or not isinstance(items[0], StructuredDataItem):
                        raise ValueError("one structured task product is required")
                    product = TaskProduct.model_validate(items[0].data)
                    if (product.executor_aic != worker.spec["aic"] or product.incident_id != pending["payload"]["incident_id"]
                            or product.logical_task_id != pending["payload"]["logical_task_id"]):
                        raise ValueError("task product differs from the bound executor or request")
                    pending["product"] = product.model_dump(exclude_none=True)
                    await self.leader.complete_task(message.taskId, message.sessionId, mentions=[worker.spec["aic"]])
                elif message.status.state == TaskState.Completed:
                    if "product" not in pending:
                        raise ValueError("completed arrived without an awaiting-completion product")
                    if not pending["future"].done():
                        pending["future"].set_result(pending["product"])
                elif message.status.state in (TaskState.Failed, TaskState.Rejected, TaskState.Canceled):
                    if not pending["future"].done():
                        pending["future"].set_exception(RuntimeError("domain rejected or failed an AIP task"))
                await emit_message(self.amp.message, message, "ack", name + ".stdout")
                if message.status.state in (TaskState.Completed, TaskState.Failed, TaskState.Rejected, TaskState.Canceled):
                    self.pending.pop(message.taskId, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            worker.state = "failed"
            worker.failure_reason = "local_channel_error:" + type(exc).__name__
            await self._event("worker_failed", name=name, error_class=type(exc).__name__)
            if not worker.ready.done():
                worker.ready.set_exception(RuntimeError("domain worker failed: " + type(exc).__name__))
            for pending in self.pending.values():
                if pending["worker"] is worker and not pending["future"].done():
                    pending["future"].set_exception(RuntimeError("domain worker channel failed"))
        finally:
            if not self.closing and worker.failure_reason is None:
                worker.failure_reason = "local_process_eof"
            if worker.state != "failed":
                worker.state = "stopped"
            if not worker.ready.done():
                worker.ready.set_exception(RuntimeError("domain worker exited before ready"))
            for pending in self.pending.values():
                if pending["worker"] is worker and not pending["future"].done():
                    pending["future"].set_exception(ConnectionError("domain worker exited with task in flight"))

    async def _publish(self, command):
        mentions = command.mentions
        if not isinstance(mentions, list) or len(mentions) != 1:
            raise ValueError("local transport requires one explicit target AIC")
        worker = next((w for w in self.workers.values() if w.spec["aic"] == mentions[0]), None)
        if not worker or worker.state != "ready" or worker.process.returncode is not None:
            raise ConnectionError("target local worker is not ready")
        async with worker.write_lock:
            worker.process.stdin.write((command.model_dump_json(exclude_none=True) + "\n").encode("utf-8"))
            await worker.process.stdin.drain()
        await self._capture("send", worker, command)
        await emit_message(self.amp.message, command, "send", worker.spec["name"] + ".stdin")

    async def call(self, payload):
        if not self.started:
            await self.start()
        task = TaskPayload.model_validate(payload)
        value = task.model_dump(exclude_none=True)
        role = "database" if task.tool.startswith("db.") else "ops" if task.tool.startswith("ops.") else (
            "application" if task.tool.startswith("application.") else "verification")
        candidates = [w for w in self.workers.values() if w.spec["role"] == role and task.tool in w.tools and w.state == "ready"
                      and (w.spec["aic"] == self.active_workers.get(role) or (role not in self.active_workers and not w.spec.get("standby")))]
        if not candidates:
            raise RuntimeError("no ready domain worker advertises this tool")
        worker = candidates[0]
        if role in self.active_fences and task.kind in ("act", "resume"):
            value["fence"] = self.active_fences[role].to_dict()
        try:
            result = await self._call_worker(worker, value)
        except (ConnectionError, asyncio.TimeoutError, BrokenPipeError) as exc:
            if self.closing or not self.config.get("automatic_takeover", True):
                raise
            reason = worker.failure_reason or ("task_deadline_expired" if isinstance(exc, asyncio.TimeoutError) else "local_channel_disconnected")
            result = await self._takeover(worker, value, reason)
        if result.get("facts"):
            self.evidence.setdefault(task.incident_id, []).extend(result["facts"])
        return result

    async def call_on_worker(self, aic: str, payload: dict):
        """Explicit evaluator/control call; it never rewrites a supplied fence."""
        if not self.started:
            await self.start()
        worker = next((w for w in self.workers.values() if w.spec["aic"] == aic), None)
        if worker is None or worker.state != "ready":
            raise ConnectionError("requested local worker is unavailable")
        return await self._call_worker(worker, payload)

    async def _call_worker(self, worker: LocalWorker, payload: dict):
        task = TaskPayload.model_validate(payload)
        value = task.model_dump(exclude_none=True)
        task_id = "aip-" + uuid.uuid4().hex
        attempt = self.journal.record_attempt(task.logical_task_id, session_id=task.incident_id, task_id=task_id,
            partner_aic=worker.spec["aic"], group_id=self.group_id, coordinator_term=self.term,
            content=json.dumps(value, ensure_ascii=False))
        future = asyncio.get_running_loop().create_future()
        self.pending[task_id] = {"future": future, "worker": worker, "payload": value, "attempt_id": attempt}
        self.amp.sampler.active += 1
        started = asyncio.get_running_loop().time()
        success = False
        try:
            await self.leader.start_task(task.incident_id, json.dumps(value, ensure_ascii=False), task_id,
                                         mentions=[worker.spec["aic"]])
            result = await asyncio.wait_for(asyncio.shield(future), task.budget["deadline_ms"] / 1000)
            success = result["status"] == "ok"
            return result
        except BaseException:
            self.journal.transition(attempt, "delivery_unknown" if task.kind in ("act", "resume") else "failed")
            # Keep pending identity until the worker closes; late results still
            # need reconciliation and must not be treated as unsolicited data.
            if not future.done():
                future.cancel()
            raise
        finally:
            self.amp.sampler.active -= 1
            self.amp.sampler.record((asyncio.get_running_loop().time() - started) * 1000, success)

    async def _takeover(self, failed: LocalWorker, original: dict, reason: str):
        role = failed.spec["role"]
        lock = self.takeover_locks.setdefault(role, asyncio.Lock())
        async with lock:
            incident_id, logical_id = original["incident_id"], original["logical_task_id"]
            started = time.monotonic()
            self.journal.record_takeover(incident_id, failed.spec["aic"], reason)
            await self._event("takeover_started", incident_id=incident_id, logical_task_id=logical_id,
                              failed_aic=failed.spec["aic"], reason=reason, discovery="local process directory")
            candidates = [w for w in self.workers.values() if w is not failed and w.spec["role"] == role
                          and w.state == "ready" and original["tool"] in w.tools]
            for candidate in candidates:
                describe_payload = {"schema_version": "ifc/1.0", "incident_id": incident_id,
                    "logical_task_id": (logical_id + ":describe:" + candidate.spec["name"])[:128],
                    "kind": "describe", "tool": original["tool"], "args": {}, "budget": {"deadline_ms": 15000}}
                try:
                    described = await self._call_worker(candidate, describe_payload)
                    description = described.get("description", {})
                    tools = description.get("tools", [])
                    if not isinstance(tools, list):
                        continue
                    names = set()
                    for item in tools:
                        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
                        if isinstance(name, str):
                            names.add(name)
                    scope = description.get("resource_scope", description.get("resources"))
                    if (described.get("status") != "ok" or description.get("executor_aic") != candidate.spec["aic"]
                            or original["tool"] not in names or failed.resource_scope is None or scope != failed.resource_scope):
                        continue
                    previous = Fence(**original.get("fence", {"coordinator_term": self.term, "takeover_version": 0}))
                    active = self.active_fences.get(role, previous)
                    proposed = Fence(max(self.term, previous.coordinator_term, active.coordinator_term),
                                     max(previous.takeover_version, active.takeover_version) + 1)
                    operation_id = original.get("operation_id") or (incident_id + ":observe:" + logical_id)
                    package = ResumePackage(logical_id, "Continue the original incident task after local participant failure",
                        evidence_refs=handover_evidence(
                            self.evidence.get(incident_id, []), self.config.get("evidence_ttl_seconds", 60)),
                        remaining_tasks=[{"tool": original["tool"], "kind": original["kind"], "args": original.get("args", {})}],
                        operations=[{"operation_id": operation_id, "status": "delivery_unknown"}] if original.get("operation_id") else [],
                        fence=proposed)
                    resume = {**original, "kind": "resume", "operation_id": operation_id, "fence": proposed.to_dict(),
                              "args": {"advance_fence": True, "resume_package": package.to_dict()}}
                    resume = await self._resume_payload(resume, package, original_fence=previous.to_dict())
                    control = await self._call_worker(candidate, resume)
                    confirmed = control.get("active_fence", control.get("operation", {}).get("active_fence"))
                    if not isinstance(confirmed, dict) or Fence(**confirmed) < proposed:
                        raise RuntimeError("replacement did not confirm resource-domain fence activation")
                    fence = Fence(**confirmed)
                    self.active_workers[role] = candidate.spec["aic"]
                    self.active_fences[role] = fence
                    self.journal.record_takeover(incident_id, failed.spec["aic"], reason,
                        replacement=candidate.spec["aic"], fence=confirmed, state="fenced")
                    state = control.get("operation", {}).get("state", "unknown")
                    if original["kind"] in ("observe", "verify", "describe"):
                        # Observation replay has no modifying effect or operation identity.
                        resumed = {**original, "fence": confirmed}
                        result = await self._call_worker(candidate, resumed)
                    elif state in ("applied", "skipped_already_applied", "reconciled_applied") and control.get("status") == "ok":
                        result = control
                    elif state == "received":
                        # No action was entered. The domain still checks its
                        # original approval and resource precondition on execute.
                        result = await self._call_worker(candidate, {**original, "fence": confirmed})
                    else:
                        # executing/unknown must be reconciled by the domain;
                        # the coordinator cannot infer safe retry from a timeout.
                        result = {**control, "status": "unknown"}
                    self.journal.record_takeover(incident_id, failed.spec["aic"], reason,
                        replacement=candidate.spec["aic"], fence=confirmed, state="resumed" if result.get("status") == "ok" else "needs_reconciliation")
                    if result.get("status") == "ok":
                        for task_id, pending in list(self.pending.items()):
                            if pending["worker"] is failed and pending["payload"]["logical_task_id"] == logical_id:
                                self.journal.transition(pending["attempt_id"], "canceled",
                                    {"reason": "superseded_by_confirmed_takeover", "replacement_aic": candidate.spec["aic"]})
                                if failed.state != "ready":
                                    self.pending.pop(task_id, None)
                    await self._event("takeover_completed", incident_id=incident_id, logical_task_id=logical_id,
                        failed_aic=failed.spec["aic"], replacement_aic=candidate.spec["aic"], fence=confirmed,
                        operation_state=result.get("operation", {}).get("state"), status=result.get("status"),
                        elapsed_seconds=round(time.monotonic()-started, 3), discovery="local process directory")
                    return result
                except (ConnectionError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
                    self.journal.record_takeover(incident_id, failed.spec["aic"], reason,
                        replacement=candidate.spec["aic"], state="candidate_failed:"+type(exc).__name__)
            raise RuntimeError("no confirmed local standby completed takeover")

    async def _resume_payload(self, default: dict, package: ResumePackage, *, original_fence=None) -> dict:
        """Customize handover information while preserving the fencing handshake.

        The optional factory receives independent copies of (payload, package).
        Only args may change; advance_fence must remain true. This is useful for
        evaluator comparisons without giving a strategy new operation identity,
        authority, deadline, or a chance to replay the original act directly.
        """
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
        # A supplied package must describe this exact logical operation and new
        # fence. Omitting the package is allowed for a from-scratch comparison.
        supplied = value["args"].get("resume_package")
        if supplied is not None:
            if not isinstance(supplied, dict) or any(supplied.get(key) != package.to_dict().get(key)
                    for key in ("logical_task_id", "operations", "fence")):
                raise ValueError("handover package cannot change operation identity or fence")
        return value

    async def close(self):
        if self.closing:
            return
        self.closing = True
        for worker in self.workers.values():
            if worker.process.stdin and not worker.process.stdin.is_closing():
                worker.process.stdin.close()
        for worker in self.workers.values():
            try:
                await asyncio.wait_for(worker.process.wait(), 8)
            except asyncio.TimeoutError:
                worker.process.terminate()
                await worker.process.wait()
            if worker.reader:
                try:
                    await worker.reader
                except asyncio.CancelledError:
                    pass
            worker.stderr_file.close()
        await self.amp.close()
        self.started = False


# Compatibility with the first workbench integration draft.
LocalAipTransport = LocalAipStdioTransport
