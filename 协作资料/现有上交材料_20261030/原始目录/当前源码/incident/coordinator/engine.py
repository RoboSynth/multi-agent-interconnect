"""Credential-free coordination. Transport owns AIP, domains own resources."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import time
import uuid

from incident.contracts import Fact, TaskPayload, TaskProduct, utc_now
from .hypothesis import HypothesisEngine
from .planner import EvidencePlanner, PROBES, observation_cost


class IncidentCoordinator:
    def __init__(self, transport, directory, *, hypothesis=None, approval_issuer=None,
                 term=1, task_budget=40, on_update=None, planner_factory=EvidencePlanner,
                 eager_actions=True, probe_selector=None, generate_hypotheses=True, entry_first=True,
                 step_selector=None, skip_deterministic_model_calls=False, incident_hypotheses=False):
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
        self.step_selector = step_selector
        self.skip_deterministic_model_calls = skip_deterministic_model_calls
        self.incident_hypotheses = incident_hypotheses
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

    async def _call(self, state, tool, *, kind="observe", args=None, node=None, feedback=False):
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
            if feedback and (product.operation or {}).get("state") in {
                    "unknown", "executing", "reconciliation_required", "stale_fence", "rejected_stale_fence"}:
                raise RuntimeError(f"{tool} has an uncertain operation or stale fence; requires operator review")
            if product.status != "ok":
                if feedback and (product.status == "rejected" or (kind != "act" and product.status == "tool_error")):
                    return result
                raise RuntimeError(f"{tool} returned {product.status}; review participant evidence")
            return result
        except Exception as exc:
            if row["status"] not in {"rejected", "tool_error", "unknown"}:
                row["status"] = "not_dispatched" if row["status"] == "awaiting_approval" else (
                                "unknown" if kind == "act" else "failed")
            row["error"] = type(exc).__name__
            row["elapsed_ms"] = round((time.monotonic()-started)*1000, 3)
            if kind == "observe" and isinstance(exc, (TimeoutError, ConnectionError, OSError)):
                await self._participant_health(state, payload, row, exc)
            self.save(state)
            raise

    async def _participant_health(self, state, payload, row, error):
        diagnose = getattr(self.transport, "participant_health", None)
        if diagnose is None:
            return
        try:
            assessment = await diagnose(payload, error=error)
            if (not isinstance(assessment, dict) or type(assessment.get("confirmed")) is not bool
                    or assessment.get("participant_state") not in {"reachable", "unreachable", "unknown"}
                    or not isinstance(assessment.get("aic"), str) or not assessment["aic"]):
                raise ValueError("invalid participant health assessment")
            facts = [Fact.model_validate(fact).model_dump() for fact in assessment.get("facts", [])]
        except Exception as exc:
            self.event(state, "participant_health_check_failed", tool=payload["tool"],
                       error_class=type(exc).__name__, reason="参与者状态证据暂不可用，请人工核对。")
            return
        assessment = {**assessment, "facts": facts}
        row["participant_health"] = assessment
        state.setdefault("participant_health", []).append(assessment)
        state["facts"].extend(facts)
        confirmed = assessment["confirmed"] and assessment["participant_state"] == "unreachable"
        if confirmed:
            state["diagnosed_causes"] = sorted(set(state.get("diagnosed_causes", [])) | {"participant_unavailable"})
        self.event(state, "participant_unreachable" if confirmed else "participant_health_unconfirmed",
                   tool=payload["tool"], aic=assessment["aic"], reason=(
                       "参与者任务中断，管理请求无回复且心跳已过期，需要人工处理。" if confirmed
                       else "参与者任务中断，当前证据不足以确认失联，需要人工核对。"))

    async def _verify_after_participant_failure(self, state):
        # Business traffic is checked independently; healthy orders cannot close
        # an incident whose participant still needs an operator.
        assessment = state["participant_health"][-1]
        confirmed = assessment["confirmed"] and assessment["participant_state"] == "unreachable"
        unresolved = {"participant_failure_confirmed": confirmed, "participant_recovered": False,
                      "participant_manual_required": True, "manual_required": True, "incident_resolved": False}
        state["result"] = {**(state["result"] or {}), **unresolved}
        if "incident.verification" in getattr(self.transport, "tools", []):
            try:
                await self._verify(state)
            except asyncio.CancelledError:
                state.update(status="interrupted", error="独立业务验证中断；参与者仍需人工处理。")
                raise
            except Exception as exc:
                self.event(state, "independent_verification_failed", tool="incident.verification",
                           error_class=type(exc).__name__, reason="独立业务验证未完成，请人工核对。")
        state["result"] = {**(state["result"] or {}), **unresolved}
        state.update(status="needs_attention", error=(
            "参与者已失联，请人工恢复或安排可信接管；业务验证结果单独列示。" if confirmed
            else "参与者任务中断，失联证据尚不充分，请人工核对；业务验证结果单独列示。"))

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

    async def _verify(self, state, *, feedback=False):
        verified = await self._call(state, "incident.verification", kind="verify",
            args={"original_request_key": state["original_request_key"],
                  "original_request_unknown": state.get("original_request_unknown", False)}, feedback=feedback)
        if verified["status"] != "ok":
            state["result"] = None
            return None
        facts = {f["key"]: f["value"] for f in verified["facts"]}
        needs_original = state.get("original_request_unknown", False) or bool(state["original_request_key"])
        if needs_original and (not state["original_request_key"] or facts.get("original_request_resolved") is not True):
            # A healthy fresh workflow never proves a lost original intent.
            # Also protect callers using an older verifier.
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
        return facts

    async def _free_step(self, state, planner, available, local_hypotheses, tokens_before):
        if len(state["tasks"]) >= self.task_budget:
            raise RuntimeError("task budget exhausted; requires operator review")
        planner.symptom, planner.local_hypotheses = state["symptom"], local_hypotheses
        state["planning_history"] = planner.history
        history_before = len(planner.history)
        step = await self.step_selector(state, planner, available)
        if (step.kind not in {"observe", "act", "verify"} or step.tool not in available
                or not isinstance(step.args, dict)
                or (step.kind == "verify" and (step.tool != "incident.verification" or step.args))
                or (step.kind == "observe" and step.tool not in (
                    {probe.tool for probe in PROBES} | set(getattr(self.step_selector, "observation_tools", ()))))):
            raise ValueError("selector returned an invalid or unavailable tool step")
        if len(planner.history) == history_before:
            planner.history.append({"reason": "自由选择下一次工具调用", "tool": step.tool,
                                    "kind": step.kind, "args": dict(step.args)})
        state["model_source"], state["tokens"] = self.hypothesis.last_source, self.hypothesis.tokens - tokens_before
        self.event(state, "tool_selected", tool=step.tool, kind=step.kind, args=step.args, reason=planner.history[-1])
        if step.kind == "verify":
            facts = await self._verify(state, feedback=True)
            planner.history.append({"reason": "接收业务验证结果", "tool": step.tool,
                                    "result": facts, "status": state["tasks"][-1]["status"]})
            if facts is not None and facts.get("business_recovered") is True:
                state["status"] = "completed"
                return True
            if (facts is not None and facts.get("service_recovered") is True
                    and (facts.get("manual_required") is True or facts.get("original_request_resolved") is False)):
                state["status"] = "needs_attention"
                return True
            if getattr(self.step_selector, "method", None) == "MR":
                state["status"] = "needs_attention"
                return True
        else:
            node = step.action_node() if step.kind == "act" else None
            if node is not None:
                if node.tool != step.tool or node.kind != "act" or node.args != step.args:
                    raise ValueError("action node differs from the selected step")
                state["plan"] = [asdict(node)]
            result = await self._call(state, step.tool, kind=step.kind, args=step.args, node=node, feedback=True)
            if result["status"] == "ok":
                if node is not None:
                    planner.action_completed(node)
                else:
                    planner.update(step.tool, result["facts"])
                local_hypotheses.extend(result.get("local_hypotheses", []))
                state["facts"] = list(planner.facts.values())
                self.save(state)
                return False
            planner.history.append({"reason": "参与者拒绝或只读工具错误，反馈给下一次选择", "tool": step.tool,
                                    "kind": step.kind, "status": result["status"]})
        self.event(state, "tool_feedback", tool=step.tool, kind=step.kind, status=state["tasks"][-1]["status"],
                   result=state["result"] if step.kind == "verify" else None)
        return False

    async def _observe_batch(self, state, planner, tools, local_hypotheses):
        """At most three domains concurrently; each partner receives one task."""
        locks = {}
        semaphore = asyncio.Semaphore(3)
        async def observe(tool):
            domain = tool.split(".")[0]
            async with locks.setdefault(domain, asyncio.Lock()), semaphore:
                self.event(state, "probe_selected", tool=tool, reason=planner.history[-1] if planner.history else {})
                product = await self._call(state, tool)
                planner.update(tool, product["facts"])
                local_hypotheses.extend(product.get("local_hypotheses", []))
                state["facts"] = list(planner.facts.values())
                self.save(state)
                return product
        # Settle every dispatched observation before returning or modifying a
        # resource. gather's default early exception would leave tasks running.
        results = await asyncio.gather(*(observe(tool) for tool in tools), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results

    async def _quick_symptoms(self, state, planner, available, local_hypotheses):
        if "incident.symptom_check" not in available:
            # An old deployment must not silently substitute a full verify or
            # claim that the new three-request check happened.
            raise RuntimeError("M2v2 requires incident.symptom_check on the verification partner")
        # Only the public entry is re-checked. Resource partners are contacted again
        # only when the planner needs a fact, never as a side effect of the check.
        symptom, = await self._observe_batch(state, planner, ["incident.symptom_check"], local_hypotheses)
        facts = {fact["key"]: fact["value"] for fact in symptom["facts"]}
        passed = facts.get("symptom_check_passed") is True
        self.event(state, "quick_symptom_check", passed=passed,
                   summary=facts.get("symptom_observation"), final_verification=False)
        return passed

    async def _run_incident_planning(self, state, planner, available, local_hypotheses):
        """Once initially, one bounded regeneration only after contradiction."""
        hypotheses, generations = [], 0
        generation_evidence = None
        async def generate(reason):
            nonlocal hypotheses, generations, generation_evidence
            generation_evidence = json.dumps(list(planner.facts.values()), sort_keys=True)
            generations += 1
            state["hypothesis_generations"] = generations
            self.event(state, "hypothesis_generation", reason=reason, generation=generations)
            hypotheses = await self.hypothesis.generate(state["symptom"], list(planner.facts.values()),
                sorted(available), list(local_hypotheses), max_attempts=1,
                probe_costs={probe.tool: probe.cost for probe in planner.probes}) if self.generate_hypotheses else []
        # Initial context is captured before entry observations. Their ordering
        # remains fixed, and the same ops partner is never called concurrently.
        # The model is off the critical path: entry faults are repaired from facts
        # while it runs, and it is awaited only when a ranking decision needs it.
        model = asyncio.create_task(generate("incident_start"))
        entry = [tool for tool in ("ops.containers", "ops.route_status") if tool in available]
        try:
            await self._planning_loop(state, planner, available, local_hypotheses, model,
                                      lambda: hypotheses, generate, lambda: (generations, generation_evidence),
                                      entry)
            # Usage must be complete even when no ranking was needed.
            await model
        finally:
            if not model.done():
                model.cancel()
                await asyncio.gather(model, return_exceptions=True)
        state["hypothesis_generations"] = generations

    async def _planning_loop(self, state, planner, available, local_hypotheses, model, current, generate,
                             generation_state, entry):
        await self._observe_batch(state, planner, entry, local_hypotheses)
        quick_passed = False
        while True:
            diagnosed = set(state.get("diagnosed_causes", []))
            for key, expected, cause in (("container_state", "exited", "application_unavailable"),
                    ("route_version", "v1", "stale_route"), ("read_only", True, "database_read_only")):
                if key in planner.facts and planner.value(key) == expected:
                    diagnosed.add(cause)
            if planner.value("blocking_sessions", []):
                diagnosed.add("database_blocked")
            state["diagnosed_causes"] = sorted(diagnosed)
            actions = planner.actions()
            if actions:
                state["plan"] = [asdict(node) for node in actions]
                for node in actions:
                    self.event(state, "plan_adjusted", reason=node.reason, node=asdict(node))
                    await self._call(state, node.tool, kind="act", args=node.args, node=node)
                    planner.action_completed(node)
                state["facts"] = list(planner.facts.values())
                quick_passed = await self._quick_symptoms(state, planner, available, local_hypotheses)
                continue
            required = planner.required_probe(available)
            if quick_passed and required is None:
                selected = []
            else:
                if not required and not model.done():
                    self.event(state, "hypothesis_wait", reason="ranking_needs_hypotheses")
                    await model
                hypotheses = current()
                generations, generation_evidence = generation_state()
                current_evidence = json.dumps(list(planner.facts.values()), sort_keys=True)
                if (hypotheses and not planner.candidates(hypotheses) and generations < 2
                        and current_evidence != generation_evidence):
                    await generate("all_candidates_contradicted_by_new_evidence")
                    hypotheses = current()
                selected = [required] if required else planner.next_probes(hypotheses, available, maximum=3)
            hypotheses = current()
            state["hypotheses"] = [hypothesis.model_dump() for hypothesis in planner.candidates(hypotheses)]
            state["planning_history"] = planner.history
            if not selected:
                facts = await self._verify(state)
                state["status"] = "completed" if facts.get("business_recovered") is True else "needs_attention"
                break
            await self._observe_batch(state, planner, selected, local_hypotheses)

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
            if self.incident_hypotheses:
                await self._run_incident_planning(state, planner, available, local_hypotheses)
                return state
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
                if self.step_selector is not None:
                    if await self._free_step(state, planner, available, local_hypotheses, model_tokens_before):
                        break
                    continue
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
                # The public entry is a prerequisite for downstream business
                # recovery. Rank its probes with the same score, then open the
                # remaining graph after the entry has been observed/repaired.
                entry_probes = {"ops.containers", "ops.route_status"} & available
                eligible = entry_probes if self.entry_first and self.eager_actions and entry_probes - planner.observed else available
                planner.symptom, planner.local_hypotheses = state["symptom"], local_hypotheses
                required = None
                deterministic = False
                if self.skip_deterministic_model_calls and self.probe_selector is None:
                    required = planner.required_probe(eligible)
                    choices = [p for p in PROBES if p.tool in eligible and p.tool not in planner.observed]
                    deterministic = required is not None or len(choices) <= 1
                if deterministic:
                    # A required observation, a single available observation, or
                    # verification has no model ranking decision to make. This
                    # opt-in method keeps every resource/approval/verify guard.
                    tool = required if required is not None else planner.next_probe([], eligible)
                    reason = "required_probe" if required is not None else "single_probe" if tool else "verification"
                    state.setdefault("model_skip_events", []).append({"reason": reason, "tool": tool})
                else:
                    hypotheses = await self.hypothesis.generate(state["symptom"], list(planner.facts.values()),
                        sorted(available), local_hypotheses) if self.generate_hypotheses else []
                    state["hypotheses"] = [h.model_dump() for h in planner.candidates(hypotheses)]
                    tool = await self.probe_selector(planner, hypotheses, eligible) if self.probe_selector else planner.next_probe(hypotheses, eligible)
                state["model_source"] = self.hypothesis.last_source
                state["tokens"] = self.hypothesis.tokens - model_tokens_before
                state["planning_history"] = planner.history
                if tool is None:
                    facts = await self._verify(state)
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
            if state.get("participant_health"):
                await self._verify_after_participant_failure(state)
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
            state["observation_cost"] = observation_cost(state["tasks"])
            state.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic()-started, 3))
            self.save(state)
        return state
