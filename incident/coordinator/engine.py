"""Credential-free coordination. Transport owns AIP, domains own resources."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import time
import uuid

from incident.contracts import TaskPayload, TaskProduct, utc_now
from .hypothesis import HypothesisEngine
from .planner import EvidencePlanner, PROBES


class IncidentCoordinator:
    def __init__(self, transport, directory, *, hypothesis=None, approval_issuer=None,
                 term=1, task_budget=40, on_update=None, planner_factory=EvidencePlanner,
                 eager_actions=True, probe_selector=None, generate_hypotheses=True, entry_first=True):
        self.transport = transport
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hypothesis = hypothesis or HypothesisEngine()
        self.approval_issuer = approval_issuer
        self.term = term
        self.task_budget = task_budget
        self.on_update = on_update
        self.planner_factory, self.eager_actions, self.probe_selector = planner_factory, eager_actions, probe_selector
        self.generate_hypotheses, self.entry_first = generate_hypotheses, entry_first
        self.runs = {}
        self.approvals = {}

    def save(self, state):
        path = self.directory / (state["id"] + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        if self.on_update:
            self.on_update(state)

    def event(self, state, event, **data):
        state["events"].append({"at": utc_now(), "event": event, **data})
        self.save(state)

    def new(self, symptom, *, original_request_key=None, original_request_unknown=False):
        if type(original_request_unknown) is not bool:
            raise ValueError("original_request_unknown must be a boolean")
        incident_id = "inc-" + uuid.uuid4().hex[:16]
        state = {"id": incident_id, "symptom": symptom, "status": "running", "started_at": utc_now(),
                 "facts": [], "hypotheses": [], "plan": [], "events": [], "tasks": [],
                 "approvals": [], "result": None, "model_source": "rules", "tokens": 0,
                 "original_request_key": original_request_key,
                 "original_request_unknown": original_request_unknown or bool(original_request_key), "error": None,
                 "transport": getattr(self.transport, "mode", "unconfigured")}
        self.runs[incident_id] = state
        self.save(state)
        return state

    async def _call(self, state, tool, *, kind="observe", args=None, node=None):
        if len(state["tasks"]) >= self.task_budget:
            raise RuntimeError("task budget exhausted; requires operator review")
        task_id = "lt-" + uuid.uuid4().hex[:12]
        data = dict(incident_id=state["id"], logical_task_id=task_id, kind=kind, tool=tool, args=args or {})
        if kind == "act":
            # One stable operation id per logical action, independent of AIP attempts.
            data.update(operation_id=state["id"] + ":" + node.id,
                        fence={"coordinator_term": self.term, "takeover_version": 0})
        payload = TaskPayload(**data).model_dump(exclude_none=True)
        if kind == "verify":
            payload["budget"] = {"deadline_ms": 120000}
        row = {"logical_task_id": task_id, "tool": tool, "kind": kind, "args": args or {},
               "status": "pending", "started_at": utc_now()}
        state["tasks"].append(row)
        started = time.monotonic()
        try:
            if kind == "act" and node.risk == "high":
                await self._approval(state, payload, row, node.reason)
            self.event(state, "task_started", logical_task_id=task_id, tool=tool)
            product = TaskProduct.model_validate(await self.transport.call(payload))
            if product.incident_id != state["id"] or product.logical_task_id != task_id:
                raise RuntimeError("participant returned a mismatched incident or task")
            result = product.model_dump(exclude_none=True)
            # None is a valid observed value; retain the required fact.value key.
            result["facts"] = [fact.model_dump() for fact in product.facts]
            row.update(status=product.status, product=result,
                       elapsed_ms=round((time.monotonic()-started)*1000, 3))
            self.event(state, "task_returned", logical_task_id=task_id, tool=tool, status=product.status)
            if product.status != "ok":
                raise RuntimeError(f"{tool} returned {product.status}; review participant evidence")
            return result
        except Exception as exc:
            if row["status"] not in {"rejected", "tool_error", "unknown"}:
                row["status"] = "not_dispatched" if row["status"] == "awaiting_approval" else (
                                "unknown" if kind == "act" else "failed")
            row["error"] = type(exc).__name__
            self.save(state)
            raise

    async def _approval(self, state, payload, row, reason):
        approval_id = "approval-" + uuid.uuid4().hex[:12]
        future = asyncio.get_running_loop().create_future()
        entry = {"id": approval_id, "incident_id": state["id"], "operation_id": payload["operation_id"],
                 "tool": payload["tool"], "args": payload["args"], "reason": reason,
                 "status": "pending", "requested_at": utc_now()}
        state["approvals"].append(entry)
        self.approvals[approval_id] = (future, payload, entry)
        state["status"] = "awaiting_approval"
        row["status"] = "awaiting_approval"
        self.event(state, "approval_requested", approval_id=approval_id, tool=payload["tool"], reason=reason)
        try:
            approved = await asyncio.wait_for(future, timeout=900)
            if not approved:
                raise RuntimeError("operator declined high risk action")
            if self.approval_issuer is None:
                raise RuntimeError("approval signer has not been configured")
            payload["approval"] = self.approval_issuer(payload)
            state["status"] = "running"
            self.event(state, "approval_granted", approval_id=approval_id)
        except BaseException:
            if entry["status"] == "pending":
                entry.update(status="expired", decided_at=utc_now())
            raise
        finally:
            self.approvals.pop(approval_id, None)

    def decide(self, approval_id, approved):
        if type(approved) is not bool:
            raise ValueError("approval decision must be a boolean")
        future, payload, entry = self.approvals[approval_id]
        if future.done():
            raise ValueError("approval already resolved")
        entry.update(status="approved" if approved else "declined", decided_at=utc_now())
        future.set_result(approved)

    async def run(self, state):
        planner = self.planner_factory()
        self.hypothesis.begin_run()
        model_tokens_before = self.hypothesis.tokens
        model_calls_before = self.hypothesis.calls
        model_requests_before = len(self.hypothesis.requests)
        source_counts_before = dict(self.hypothesis.source_counts)
        started = time.monotonic()
        local_hypotheses = []
        try:
            available = set(getattr(self.transport, "tools", [p.tool for p in PROBES]))
            while True:
                diagnosed = set(state.get("diagnosed_causes", []))
                for key, predicate, cause in (
                    ("container_state", lambda value: value == "exited", "application_unavailable"),
                    ("route_version", lambda value: value == "v1", "stale_route"),
                    ("read_only", lambda value: value is True, "database_read_only"),
                    ("blocking_sessions", bool, "database_blocked")):
                    if key in planner.facts and predicate(planner.value(key)):
                        diagnosed.add(cause)
                state["diagnosed_causes"] = sorted(diagnosed)
                # Repair only confirmed facts. Compound faults keep other domains' evidence.
                actions = planner.actions()
                remaining_probes = [p for p in PROBES if p.tool in available and p.tool not in planner.observed]
                if actions and (self.eager_actions or not remaining_probes):
                    state["plan"] = [asdict(n) for n in actions]
                    for node in actions:
                        self.event(state, "plan_adjusted", reason=node.reason, node=asdict(node))
                        await self._call(state, node.tool, kind="act", args=node.args, node=node)
                        planner.action_completed(node)
                    state["facts"] = list(planner.facts.values())
                    continue
                hypotheses = await self.hypothesis.generate(state["symptom"], list(planner.facts.values()),
                    sorted(available), local_hypotheses) if self.generate_hypotheses else []
                state["hypotheses"] = [h.model_dump() for h in planner.candidates(hypotheses)]
                state["model_source"] = self.hypothesis.last_source
                state["tokens"] = self.hypothesis.tokens - model_tokens_before
                # The public entry is a prerequisite for downstream business
                # recovery. Rank its probes with the same score, then open the
                # remaining graph after the entry has been observed/repaired.
                entry_probes = {"ops.containers", "ops.route_status"} & available
                eligible = entry_probes if self.entry_first and self.eager_actions and entry_probes - planner.observed else available
                planner.symptom, planner.local_hypotheses = state["symptom"], local_hypotheses
                tool = await self.probe_selector(planner, hypotheses, eligible) if self.probe_selector else planner.next_probe(hypotheses, eligible)
                state["model_source"] = self.hypothesis.last_source
                state["tokens"] = self.hypothesis.tokens - model_tokens_before
                state["planning_history"] = planner.history
                if tool is None:
                    verified = await self._call(state, "incident.verification", kind="verify",
                        args={"original_request_key": state["original_request_key"],
                              "original_request_unknown": state.get("original_request_unknown", False)})
                    facts = {f["key"]: f["value"] for f in verified["facts"]}
                    needs_original = state.get("original_request_unknown", False) or bool(state["original_request_key"])
                    if needs_original and (not state["original_request_key"] or facts.get("original_request_resolved") is not True):
                        # A healthy fresh workflow never proves a lost original
                        # intent. Also protect callers using an older verifier.
                        facts.setdefault("service_recovered", facts.get("business_recovered") is True)
                        facts.update(business_recovered=False, original_request_resolved=False, manual_required=True)
                        if not state["original_request_key"]:
                            facts["original_request_resolution"] = "unknown_missing_key"
                        elif facts.get("original_request_resolution") not in {"unknown_receipt_missing", "unknown_receipt_unavailable"}:
                            facts["original_request_resolution"] = "unknown"
                        self.event(state, "original_request_unresolved", reason=(
                            "原请求键已遗失，请人工核对原订单。" if not state["original_request_key"]
                            else "原请求结果仍未查清，请人工核对。"))
                    state["result"] = facts
                    if facts.get("business_recovered") is not True:
                        state["status"] = "needs_attention"
                    else:
                        state["status"] = "completed"
                    break
                self.event(state, "probe_selected", tool=tool, reason=planner.history[-1])
                result = await self._call(state, tool)
                planner.update(tool, result["facts"])
                local_hypotheses.extend(result.get("local_hypotheses", []))
                state["facts"] = list(planner.facts.values())
                self.save(state)
        except asyncio.CancelledError:
            state.update(status="interrupted", error="协调任务中断；在途修改须查账本后接续")
            raise
        except Exception as exc:
            state.update(status="needs_attention", error=f"{type(exc).__name__}: {exc}")
        finally:
            counts = {key: count - source_counts_before.get(key, 0)
                      for key, count in self.hypothesis.source_counts.items()}
            source = "llm_failed" if counts.get("failed") else (
                "mixed" if counts.get("llm") and counts.get("rules") else
                "llm" if counts.get("llm") else "rules")
            state.update(tokens=self.hypothesis.tokens - model_tokens_before,
                         model_calls=self.hypothesis.calls - model_calls_before,
                         model_source=source, model_source_counts=counts,
                         model_error=self.hypothesis.last_error,
                         model_requests=self.hypothesis.requests[model_requests_before:])
            state["token_usage_complete"] = all("usage" in request and "total_tokens" in request["usage"]
                                               for request in state["model_requests"])
            state.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic()-started, 3))
            self.save(state)
        return state
