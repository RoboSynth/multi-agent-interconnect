"""AIP group command adapter with policy, ledger and MCP transports."""
from __future__ import annotations

import asyncio
import ast
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import re
import time

from .policy import PolicyRejected


class ToolExecutionError(RuntimeError):
    pass


def mcp_value(result: dict):
    if result.get("isError"):
        raise ToolExecutionError("MCP tool returned isError")
    if result.get("structuredContent") is not None:
        value = result["structuredContent"]
        value = value.get("result", value) if isinstance(value, dict) else value
        # FastMCP v1 wraps upstream list[TextContent] in structuredContent.result.
        if isinstance(value, list) and value and all(isinstance(v, dict) and v.get("type") == "text" for v in value):
            return mcp_value({"content": value})
        return value
    blocks = [part["text"] for part in result.get("content", []) if part.get("type") == "text"]
    if len(blocks) == 1:
        if blocks[0].startswith("Error:"):
            # postgres-mcp reports errors as text without setting MCP isError.
            raise ToolExecutionError("MCP server reported a textual tool error")
        try:
            return json.loads(blocks[0])
        except (ValueError, TypeError):
            if len(blocks[0]) <= 262144:
                try:
                    return ast.literal_eval(blocks[0])
                except (ValueError, SyntaxError, MemoryError, RecursionError):
                    pass
            return blocks[0]
    return blocks


def sanitize(value, secret_values=()):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(r"password|secret|token|authorization|database_uri|dsn|env$", k, re.I)
                    else sanitize(v, secret_values)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, secret_values) for v in value]
    if isinstance(value, str):
        for secret in secret_values:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)(postgres(?:ql)?|https?|amqps?)://[^\s/@]+:[^\s/@]+@", r"\1://[REDACTED]@", value)
        value = re.sub(r"(?i)(password|token|secret|authorization)(\s*[=:]\s*)([^\s,;]+)", r"\1\2[REDACTED]", value)
    return value


def _handover_digest(payload, args):
    """Validate optional evidence metadata; nothing in it grants execution authority."""
    from acps_sdk.aip.resumable import Fence

    handover = args["handover"]
    strategy = handover.get("strategy") if isinstance(handover, dict) else None
    fields = {"from_scratch": set(), "full_history": {"conversation"}, "resume_package": {"package"}}
    if not isinstance(strategy, str) or strategy not in fields:
        raise PolicyRejected("invalid handover strategy")
    if (set(handover) - ({"strategy", "goal", "evidence_ttl_seconds", "control"} | fields[strategy])
            or not {"control", *fields[strategy]} <= set(handover)):
        raise PolicyRejected("invalid handover representation")
    if "goal" in handover and (not isinstance(handover["goal"], str) or not handover["goal"].strip()):
        raise PolicyRejected("handover goal must be a nonempty string")
    ttl = handover.get("evidence_ttl_seconds", 60)
    if type(ttl) not in (int, float) or not math.isfinite(ttl) or ttl <= 0:
        raise PolicyRejected("invalid handover evidence TTL")

    def fence(value):
        if not isinstance(value, dict) or set(value) != {"coordinator_term", "takeover_version"}:
            raise PolicyRejected("invalid handover fence")
        try:
            return Fence(**value)
        except (TypeError, ValueError) as exc:
            raise PolicyRejected("invalid handover fence") from exc

    control = handover["control"]
    if not isinstance(control, dict) or set(control) != {"operation_id", "original_fence", "replacement_fence"}:
        raise PolicyRejected("invalid handover control")
    replacement = fence(control["replacement_fence"])
    if (control["operation_id"] != payload["operation_id"] or replacement != fence(payload.get("fence"))
            or fence(control["original_fence"]) > replacement):
        raise PolicyRejected("handover control differs from the resume operation")
    if args.get("advance_fence") is not True:
        raise PolicyRejected("handover requires advance_fence=true")

    if strategy == "full_history":
        conversation = handover["conversation"]
        if not isinstance(conversation, list):
            raise PolicyRejected("handover conversation must be a list")
        for item in conversation:
            direction = item.get("direction") if isinstance(item, dict) else None
            body = {"request": "payload", "product": "product"}.get(direction) if isinstance(direction, str) else None
            required = {"direction", "aip_task_id", body}
            if (body is None or not required <= set(item) or set(item) - required - {"aip_session_id"}
                    or not isinstance(item["aip_task_id"], str) or not item["aip_task_id"]
                    or not isinstance(item[body], dict)):
                raise PolicyRejected("invalid handover conversation entry")
            if "aip_session_id" in item and (not isinstance(item["aip_session_id"], str)
                                             or not item["aip_session_id"].strip()):
                raise PolicyRejected("invalid handover conversation session")
            request = item[body]
            if direction == "request" and request.get("operation_id") == payload["operation_id"]:
                if (request.get("tool") != payload.get("tool") or request.get("incident_id") != payload["incident_id"]
                        or fence(request.get("fence")) != fence(control["original_fence"])):
                    raise PolicyRejected("handover history differs from the original operation")
    if strategy == "resume_package":
        package = handover["package"]
        package_fields = {"schema_version", "logical_task_id", "goal", "evidence_refs", "hypotheses",
                          "remaining_tasks", "operations", "fence", "created_at"}
        if (not isinstance(package, dict) or set(package) - package_fields
                or package.get("schema_version", "1.0") != "1.0"
                or package.get("logical_task_id") != payload["logical_task_id"]
                or not isinstance(package.get("goal"), str)
                or fence(package.get("fence")) != replacement):
            raise PolicyRejected("invalid handover resume package")
        for key in ("evidence_refs", "hypotheses", "remaining_tasks", "operations"):
            if not isinstance(package.get(key, []), list) or not all(isinstance(item, dict) for item in package.get(key, [])):
                raise PolicyRejected("invalid handover resume package list")
        if (not any(item.get("operation_id") == payload["operation_id"] for item in package.get("operations", []))
                or package != args.get("resume_package")):
            raise PolicyRejected("handover package differs from the resume operation or args.resume_package")
    elif "resume_package" in args:
        raise PolicyRejected("handover strategy does not use a resume package")

    def json_data(value, depth=0):
        if depth > 64:
            return False
        if value is None or type(value) in (str, int, bool):
            return True
        if type(value) is float:
            return math.isfinite(value)
        if type(value) is list:
            return all(json_data(item, depth + 1) for item in value)
        if type(value) is dict:
            return all(type(key) is str and json_data(item, depth + 1) for key, item in value.items())
        return False

    if not json_data(handover):
        raise PolicyRejected("handover must contain only JSON data")
    encoded = json.dumps(handover, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Bridge:
    def __init__(self, policy, clients: dict, ledger, executor_aic: str, *, audit=None,
                 resource_guard=None, secret_values=(), max_output_bytes=32768):
        self.policy, self.clients, self.ledger = policy, clients, ledger
        self.executor_aic, self.audit = executor_aic, audit
        self.resource_guard, self.secret_values = resource_guard, secret_values
        self.max_output_bytes = max_output_bytes
        self.inventory = {}

    async def initialize(self):
        for name, client in self.clients.items():
            self.inventory[name] = await client.tools()
        missing = [alias for alias, spec in self.policy.tools.items()
                   if not any(t["name"] == spec["mcp_tool"] for t in self.inventory.get(spec["server"], []))]
        if missing:
            raise RuntimeError("Configured MCP tools are absent: " + ", ".join(missing))
        return self

    async def _audit(self, payload, caller_aic, result, elapsed_ms):
        if not self.audit:
            return None
        event = {"caller_aic": caller_aic, "executor_aic": self.executor_aic,
                 "incident_id": payload.get("incident_id"), "logical_task_id": payload.get("logical_task_id"),
                 "tool": payload.get("tool", payload.get("kind", "invalid")),
                 "operation_id": payload.get("operation_id"), "status": result["status"],
                 "operation_state": result.get("operation", {}).get("state"), "elapsed_ms": elapsed_ms}
        value = self.audit(event)
        return await value if inspect.isawaitable(value) else value

    async def execute(self, payload: dict, caller_aic: str) -> dict:
        started = time.monotonic()
        result = {"schema_version": "ifc/1.0", "incident_id": payload.get("incident_id"),
                  "logical_task_id": payload.get("logical_task_id"), "executor_aic": self.executor_aic,
                  "status": "ok", "facts": [], "local_hypotheses": []}
        try:
            self.policy.authorize_caller(caller_aic)
            if payload.get("schema_version") != "ifc/1.0" or not all(
                    isinstance(payload.get(k), str) and payload[k] for k in ("incident_id", "logical_task_id")):
                raise PolicyRejected("invalid ifc/1.0 task envelope")
            kind = payload.get("kind")
            if kind == "describe":
                result["description"] = self.policy.describe(self.inventory)
            elif kind == "resume":
                if not isinstance(payload.get("operation_id"), str):
                    raise PolicyRejected("resume requires operation_id")
                args = payload.get("args", {})
                if not isinstance(args, dict) or set(args) - {"advance_fence", "resume_package", "handover"}:
                    raise PolicyRejected("invalid resume arguments")
                if "handover" in args:
                    result["handover_sha256"] = _handover_digest(payload, args)
                if args.get("advance_fence"):
                    if args["advance_fence"] is not True:
                        raise PolicyRejected("advance_fence must be boolean true")
                    from acps_sdk.aip.resumable import Fence
                    try:
                        active = await self.ledger.activate_fence(Fence(**payload.get("fence", {})))
                    except (TypeError, ValueError) as exc:
                        result["operation"] = {"operation_id": payload["operation_id"], "state": "rejected_stale_fence"}
                        raise PolicyRejected("resume fence was invalid or stale") from exc
                    result["active_fence"] = active.to_dict()
                entry = self.ledger.get(payload["operation_id"])
                if entry and entry["parameters"]["tool"] != payload.get("tool"):
                    raise PolicyRejected("resume tool differs from the recorded operation")
                reconciled = None
                if entry and entry["state"] in {"executing", "unknown", "failed"}:
                    spec = self.policy.tools.get(payload.get("tool"), {})
                    reconciliation = spec.get("reconcile")
                    if reconciliation:
                        reference_alias = reconciliation["tool_alias"]
                        reference = self.policy.tools[reference_alias]
                        async def inspect_existing():
                            query = {"sql": reference["sql_template"]} if "sql_template" in reference else reference.get("fixed_arguments", {})
                            observed = mcp_value(await self.clients[reference["server"]].call(reference["mcp_tool"], query))
                            return self._facts(reference_alias, observed)[0]["value"]
                        def unavailable_effect():
                            raise RuntimeError("Resume never issues another modification")
                        from acps_sdk.aip.resumable import Fence
                        current = self.ledger.current_fence()
                        reconciled = await self.ledger.execute(payload["operation_id"], entry["parameters"], current,
                            unavailable_effect, inspect=inspect_existing, expected_after=reconciliation["expected_after"])
                        entry = self.ledger.get(payload["operation_id"])
                result["operation"] = {"operation_id": payload["operation_id"],
                                       "state": reconciled.status if reconciled and reconciled.status == "reconciled_applied"
                                       else "skipped_already_applied" if entry and entry["state"] == "applied"
                                       else entry["state"] if entry else "unknown"}
                if "active_fence" in result:
                    result["operation"]["active_fence"] = result["active_fence"]
                if entry and entry["state"] == "applied":
                    recorded_result = entry.get("result")
                    result["facts"] = recorded_result if isinstance(recorded_result, list) else self._facts(
                        entry["parameters"]["tool"], recorded_result)
                if not entry or entry["state"] not in {"applied", "received"}:
                    result["status"] = "unknown"
            else:
                call = self.policy.authorize(payload, caller_aic)
                arguments = dict(call.arguments)
                if call.specification.get("container_guard"):
                    if not self.resource_guard:
                        raise PolicyRejected("container label guard is not configured")
                    checked = self.resource_guard(arguments["container_id"], **self.policy.container_scope)
                    arguments["container_id"] = await checked if inspect.isawaitable(checked) else checked
                if call.specification.get("blocker_guard"):
                    recorded = self.ledger.get(payload["operation_id"])
                    if not recorded or recorded["state"] != "applied":
                        guard = self.policy.tools["db.blocking_sessions"]
                        blockers = mcp_value(await self.clients[guard["server"]].call(
                            guard["mcp_tool"], {"sql": guard["sql_template"]}))
                        allowed = {pid for row in blockers if isinstance(row, dict)
                                   for pid in row.get("blocking_pids", [])} if isinstance(blockers, list) else set()
                        if payload["args"]["pid"] not in allowed:
                            raise PolicyRejected("target PID is not an observed experiment blocking session")

                async def action():
                    client = self.clients[call.server]
                    if call.specification.get("restart_sequence"):
                        mcp_value(await client.call("stop_container", arguments))
                    output = mcp_value(await client.call(call.tool, arguments))
                    if call.specification.get("restart_sequence") and self.policy.container_scope:
                        # The upstream start response can contain its pre-start cached state.
                        reference = self.policy.tools["ops.containers"]
                        observed = mcp_value(await self.clients[reference["server"]].call(
                            reference["mcp_tool"], reference.get("fixed_arguments", {})))
                        facts = self._facts("ops.containers", observed)
                        for fact in facts:
                            fact["source"] = call.alias
                        return facts
                    return self._facts(call.alias, output)

                deadline = payload.get("budget", {}).get("deadline_ms", 15000)
                if type(deadline) is not int or not 1 <= deadline <= 120000:
                    raise PolicyRejected("deadline_ms must be between 1 and 120000")
                if call.risk == "read":
                    result["facts"] = await asyncio.wait_for(action(), deadline / 1000)
                else:
                    from acps_sdk.aip.resumable import Fence
                    reconciliation = call.specification.get("reconcile")
                    ledger_options = {}
                    if reconciliation:
                        reference_alias = reconciliation["tool_alias"]
                        reference = self.policy.tools[reference_alias]
                        if reference["risk"] != "read":
                            raise PolicyRejected("reconciliation tool must be read-only")
                        async def inspect_resource():
                            query = {"sql": reference["sql_template"]} if "sql_template" in reference else reference.get("fixed_arguments", {})
                            observed = mcp_value(await self.clients[reference["server"]].call(reference["mcp_tool"], query))
                            return self._facts(reference_alias, observed)[0]["value"]
                        ledger_options = {"inspect": inspect_resource, "expected_after": reconciliation["expected_after"]}
                        if "expected_before" in reconciliation:
                            ledger_options["expected_before"] = reconciliation["expected_before"]
                        argument = reconciliation.get("expected_before_argument")
                        if argument is not None and argument in payload.get("args", {}):
                            if (call.alias != "ops.route_rollback" or argument != "expected_route_version"
                                    or payload["args"][argument] != "unknown"):
                                raise PolicyRejected("Only guarded unregistered-route recovery may override the v1 precondition")
                            ledger_options["expected_before"] = payload["args"][argument]
                    # Deadline cancellation makes an in-flight action unknown in the durable ledger.
                    outcome = await asyncio.wait_for(self.ledger.execute(
                        payload["operation_id"], {"tool": call.alias, "args": payload.get("args", {}),
                                                  "resources": self.policy.resources},
                        Fence(**payload["fence"]), action, **ledger_options), deadline / 1000)
                    result["operation"] = {"operation_id": payload["operation_id"], "state": outcome.status}
                    entry = self.ledger.get(payload["operation_id"])
                    if entry:
                        result["operation"].update(before={"value": entry.get("before_state")}, after={"value": entry.get("after_state")})
                    if outcome.status.startswith("rejected"):
                        result["status"] = "rejected"
                    elif outcome.status in {"unknown", "reconciliation_required"}:
                        result["status"] = "unknown"
                    else:
                        result["facts"] = outcome.result if isinstance(outcome.result, list) else self._facts(call.alias, outcome.result)
                for fact in result["facts"]:
                    if fact["key"] == "read_only" and fact["value"] is True:
                        result["local_hypotheses"].append({"cause": "db_read_only", "confidence": "high",
                                                           "because": ["fact:read_only"]})
        except PolicyRejected as exc:
            result.update(status="rejected", reason=str(exc))
        except (TimeoutError, asyncio.TimeoutError):
            result.update(status="unknown" if payload.get("kind") == "act" else "tool_error", reason="tool deadline exceeded")
            if payload.get("operation_id"):
                result["operation"] = {"operation_id": payload["operation_id"], "state": "unknown"}
        except Exception as exc:
            # Do not send MCP stderr, SQL connection strings, or exception messages across AIP.
            result.update(status="tool_error", reason=type(exc).__name__)
        result = sanitize(result, self.secret_values)
        evidence = await self._audit(payload, caller_aic, result, int((time.monotonic() - started) * 1000))
        if evidence:
            result["evidence_ref"] = "amp:audit:" + str(evidence)
        return result

    def _facts(self, alias, output):
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except ValueError:
                pass
        extra_facts = []
        if (alias in {"ops.route_status", "ops.route_rollback"} and isinstance(output, dict)
                and isinstance(output.get("route_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", output["route_sha256"])):
            extra_facts.append(("route_sha256", output["route_sha256"]))
        key = {"db.health": "db_health", "db.read_only_status": "read_only",
               "db.blocking_sessions": "blocking_sessions", "db.restore_writes": "read_only",
               "db.terminate_blocker": "blocking_session_terminated", "ops.route_status": "route_version",
               "ops.route_rollback": "route_version", "ops.containers": "containers",
               "ops.logs": "container_logs", "ops.restart": "container_state"}.get(alias, alias)
        if (alias == "ops.containers" and not self.policy.container_scope
                and isinstance(output, dict) and output.get("backend") == "native"):
            key = "container_state"
        if isinstance(output, list) and len(output) == 1 and isinstance(output[0], dict) and key in output[0]:
            output = output[0][key]
        elif isinstance(output, dict) and key in output:
            output = output[key]
        if key == "containers" and self.policy.container_scope and not isinstance(output, list):
            raise ToolExecutionError("container observation did not return a list")
        if key == "containers" and isinstance(output, list):
            if self.policy.container_scope:
                from domains.ops.guard import container_matches_scope
                selected = [c for c in output if isinstance(c, dict)
                            and container_matches_scope(c, self.policy.container_scope)]
                if len(selected) > 1:
                    raise ToolExecutionError("configured container target is ambiguous")
                rows = []
                for container in selected:
                    state = container.get("status", container.get("state", {}))
                    if isinstance(state, dict):
                        state = state.get("Status")
                    state = state if state in {"running", "exited"} else "unknown"
                    rows.append({"id": container.get("id", container.get("Id")),
                                 "name": self.policy.container_scope["container_name"], "status": state})
                key, output = "container_state", rows[0]["status"] if rows else "unknown"
                extra_facts.append(("containers", rows))
            else:
                output = [{k: v for k, v in c.items() if k.lower() in {"id", "name", "status", "state", "labels"}}
                          for c in output if isinstance(c, dict)]
        if key == "read_only" and not isinstance(output, (bool, str)):
            raise ToolExecutionError("read_only template did not return a boolean fact")
        if key == "container_state" and isinstance(output, dict):
            output = output.get("status", output.get("State", {}).get("Status", "unknown"))
        if key == "read_only" and isinstance(output, str):
            if output.lower() not in {"on", "off", "true", "false", "1", "0"}:
                raise ToolExecutionError("read_only template returned an unknown boolean string")
            output = output.lower() in {"on", "true", "1"}
        facts = []
        for fact_key, value in [(key, output), *extra_facts]:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            if len(encoded.encode()) > self.max_output_bytes:
                value = {"truncated": True, "preview": encoded[:self.max_output_bytes // 4],
                         "original_bytes": len(encoded.encode())}
            facts.append({"key": fact_key, "value": value, "source": alias,
                          "observed_at": datetime.now(timezone.utc).isoformat()})
        return facts

    def bind_partner(self, client):
        """Bind an official GroupPartner after its AMQP identity assertion boundary.

        The SDK's _start_consuming verifies authenticated AMQP user_id with
        assert_incoming_group_message_identity before dispatching this callback.
        A senderId taken from JSON alone is never used as authenticated identity.
        """
        if not getattr(client, "_identity_binding_enabled", False):
            raise ValueError("MCP bridge requires official AMQP identity binding")
        if client.partner_aic != self.executor_aic:
            raise ValueError("Partner AIC differs from bridge executor AIC")
        from acps_sdk.aip import Product, StructuredDataItem, TextDataItem, TaskCommandType, TaskState
        states, locks = {}, {}

        async def handler(command, is_mentioned):
            if not is_mentioned:
                return
            if (command.senderRole != "leader" or command.groupId != client.group_id
                    or not command.sessionId or not command.taskId):
                await self._audit({"kind": "invalid"}, command.senderId, {"status": "rejected"}, 0)
                return
            key = (command.sessionId, command.taskId)
            async with locks.setdefault(key, asyncio.Lock()):
                saved = states.get(key)
                if command.command == TaskCommandType.Start:
                    if saved:
                        await client.send_task_result(command.taskId, command.sessionId, saved[0], products=saved[1])
                        return saved[1][0].dataItems[0].data
                    try:
                        items = command.dataItems or []
                        if len(items) != 1:
                            raise ValueError("one structured JSON item is required")
                        item = items[0]
                        payload = item.data if isinstance(item, StructuredDataItem) else json.loads(item.text)
                        if not isinstance(payload, dict):
                            raise ValueError("object required")
                    except (AttributeError, ValueError, TypeError):
                        await self._audit({"kind": "invalid"}, command.senderId, {"status": "rejected"}, 0)
                        await client.reject_task(command.taskId, command.sessionId, "invalid ifc/1.0 task data")
                        return
                    await client.accept_task(command.taskId, command.sessionId)
                    await client.start_working(command.taskId, command.sessionId)
                    output = await self.execute(payload, command.senderId)
                    products = [Product(id=f"mcp-{command.taskId}", name=payload.get("tool", payload.get("kind", "invalid")),
                                        dataItems=[StructuredDataItem(data=output)])]
                    states[key] = (TaskState.AwaitingCompletion, products)
                    await client.submit_for_completion(command.taskId, command.sessionId, products)
                    return output
                elif saved and command.command == TaskCommandType.Complete:
                    states[key] = (TaskState.Completed, saved[1])
                    await client.complete_task(command.taskId, command.sessionId)
                elif saved and command.command == TaskCommandType.Get:
                    await client.send_task_result(command.taskId, command.sessionId, saved[0], products=saved[1])
                elif saved and command.command == TaskCommandType.Cancel:
                    states[key] = (TaskState.Canceled, saved[1])
                    await client.cancel_task(command.taskId, command.sessionId)
        client.set_command_handler(handler)
        return handler
