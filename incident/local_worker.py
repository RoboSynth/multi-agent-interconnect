"""One resource-domain process for local native AIP stdio delivery.

Only this process loads its domain environment/configuration. The stdin pipe is
bound at launch to one coordinator AIC; this is a local IPC boundary, not mTLS.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from contextvars import ContextVar
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from acps_sdk.aip import Product, StructuredDataItem, TaskCommand, TaskCommandType, TaskState, TextDataItem
from acps_sdk.aip.aip_group_partner import GroupPartnerMqClient, PartnerGroupState
from acps_sdk.aip.resumable import Fence, OperationLedger
from incident.amp_setup import AmpRuntime
from incident.contracts import TaskPayload, TaskProduct
from incident.local_transport import emit_message, environment_file, local_path


class CountedMcpClient:
    """Count actual modifying MCP calls, excluding ledger inspection queries."""
    def __init__(self, client, server, policy, amp, current_payload):
        self.client, self.server, self.policy = client, server, policy
        self.amp, self.current_payload = amp, current_payload

    async def tools(self):
        return await self.client.tools()

    async def call(self, name, arguments):
        payload = self.current_payload.get() or {}
        spec = self.policy.tools.get(payload.get("tool"), {})
        modifying = spec.get("risk") in ("write", "high") and spec.get("server") == self.server
        if modifying and "sql_template" in spec:
            try:
                modifying = name == spec.get("mcp_tool") and arguments == {"sql": spec["sql_template"].format(**payload.get("args", {}))}
            except (KeyError, ValueError):
                modifying = False
        elif modifying:
            modifying = name == spec.get("mcp_tool") or bool(spec.get("restart_sequence") and name == "stop_container")
        event = {"event": "mcp_modify_invocation", "transport": "local-aip-stdio",
                 "invocation_id": uuid.uuid4().hex, "server": self.server, "upstream_tool": name,
                 "tool": payload.get("tool"), "incident_id": payload.get("incident_id"),
                 "logical_task_id": payload.get("logical_task_id"), "operation_id": payload.get("operation_id")}
        if modifying:
            await self.amp.system.emit(event)
        result = await self.client.call(name, arguments)
        if modifying:
            await self.amp.system.emit({**event, "event": "mcp_modify_returned", "is_error": bool(result.get("isError"))})
        return result


async def serve(args):
    if args.env_file:
        os.environ.update(environment_file(args.env_file))
    amp = AmpRuntime(args.amp_directory, args.name, args.aic)
    await amp.start()
    output_lock = asyncio.Lock()

    async def output(value):
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with output_lock:
            sys.stdout.write(encoded)
            sys.stdout.flush()

    client = GroupPartnerMqClient(args.aic, access_emitter=amp.access,
                                   message_emitter=amp.message, message_system="local-stdio")
    client._group_id = args.group_id
    client._state = PartnerGroupState.JOINED
    channel = args.name + ".stdout"

    async def publish(message):
        await output(message.model_dump(mode="json", exclude_none=True))
        await emit_message(amp.message, message, "send", channel)
    client._publish_message = publish

    async with AsyncExitStack() as stack:
        current_payload = ContextVar("local_worker_payload", default=None)
        resource_scope = ["orders"]
        if args.role in ("database", "ops"):
            if not args.bridge_config:
                raise ValueError("database/ops workers require their own bridge configuration")
            from acps_mcp_bridge import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
            config_path = local_path(args.bridge_config)
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            def domain_path(value):
                path = Path(value)
                return path if path.is_absolute() else config_path.parent / path
            for filename in config.get("env_files", []):
                os.environ.update(environment_file(domain_path(filename)))
            if config.get("executor_aic", args.aic) != args.aic:
                raise ValueError("bridge executor differs from the bound worker AIC")
            if args.coordinator_aic not in config.get("allowed_callers", []):
                raise ValueError("coordinator is absent from the domain caller allowlist")
            authority = ApprovalAuthority(os.environ[config["approval_secret_env"]]) if config.get("approval_secret_env") else None
            policy = Policy.load(domain_path(config["policy"]), allowed_callers=config["allowed_callers"],
                                 approval_verifier=authority.verify if authority else None)
            ledger = OperationLedger(domain_path(config.get("ledger_path", args.ledger_path)),
                                     config.get("ledger_domain", policy.domain))
            clients = {}
            for name, server in config["servers"].items():
                raw_client = await stack.enter_async_context(McpStdioClient(ServerConfig(**server)))
                clients[name] = CountedMcpClient(raw_client, name, policy, amp, current_payload)
            secret_values = [os.environ[name] for server in config["servers"].values()
                             for name in server.get("env_names", []) if name in os.environ]
            from domains.ops.guard import labeled_container
            executor = await Bridge(policy, clients, ledger, args.aic, audit=amp.audit_event,
                                    resource_guard=labeled_container, secret_values=secret_values).initialize()
            tools = list(policy.tools)
            resource_scope = policy.resources
        else:
            from incident.partners import ApplicationPartner, VerificationPartner
            if args.role == "application":
                executor = ApplicationPartner(args.aic, OperationLedger(args.ledger_path, "application"),
                    base_url=args.base_url, allowed_callers=[args.coordinator_aic])
                tools = ["application.status", "application.pool_rebuild", "application.config_rollback"]
            else:
                executor = VerificationPartner(args.aic, base_url=args.base_url or "http://127.0.0.1:8088",
                    allowed_callers=[args.coordinator_aic], duration=args.verification_duration)
                tools = ["incident.verification"]

        states = {}
        async def crash(point, payload):
            if args.crash_point != point or args.crash_tool != payload["tool"]:
                return
            if not args.experiment_id or args.role != "database":
                raise ValueError("crash hooks are restricted to explicit database experiment workers")
            await amp.system.emit({"event": "experiment_worker_crash", "experiment_id": args.experiment_id,
                "crash_point": point, "incident_id": payload["incident_id"],
                "logical_task_id": payload["logical_task_id"], "operation_id": payload.get("operation_id")})
            os._exit({"after_observation": 81, "before_modification": 82, "after_applied": 83}[point])

        async def handler(command, is_mentioned):
            if not is_mentioned:
                return
            key = (command.sessionId, command.taskId)
            saved = states.get(key)
            if command.command == TaskCommandType.Start:
                if saved:
                    await client.send_task_result(command.taskId, command.sessionId, saved["state"], products=saved.get("products"))
                    return saved.get("output")
                try:
                    if len(command.dataItems or []) != 1:
                        raise ValueError("one task data item required")
                    item = command.dataItems[0]
                    value = item.data if isinstance(item, StructuredDataItem) else json.loads(item.text)
                    payload = TaskPayload.model_validate(value).model_dump(exclude_none=True)
                    if payload["incident_id"] != command.sessionId:
                        raise ValueError("incident id differs from the local AIP session")
                except (ValueError, TypeError, AttributeError):
                    await client.reject_task(command.taskId, command.sessionId, "invalid ifc/1.0 task data")
                    return {"status": "rejected"}
                await client.accept_task(command.taskId, command.sessionId)
                await client.start_working(command.taskId, command.sessionId)
                amp.sampler.active += 1
                started = time.monotonic()
                try:
                    token = current_payload.set(payload)
                    if (args.crash_point == "before_modification" and payload["kind"] == "act"
                            and payload["tool"] == args.crash_tool):
                        authorized = executor.policy.authorize(payload, args.coordinator_aic)
                        executor.ledger.record_received(payload["operation_id"],
                            {"tool": authorized.alias, "args": payload.get("args", {}), "resources": executor.policy.resources},
                            Fence(**payload["fence"]))
                        await crash("before_modification", payload)
                    result = await executor.execute(payload, args.coordinator_aic)
                    if result.get("status") == "ok":
                        if payload["kind"] == "observe":
                            await crash("after_observation", payload)
                        elif payload["kind"] == "act" and result.get("operation", {}).get("state") in ("applied", "skipped_already_applied", "reconciled_applied"):
                            await crash("after_applied", payload)
                    # Add identity to the describe document, too, so selection
                    # never accepts a capability response without its executor.
                    if isinstance(result.get("description"), dict):
                        result["description"]["executor_aic"] = args.aic
                    product = TaskProduct.model_validate(result).model_dump(exclude_none=True)
                    success = product["status"] == "ok"
                except Exception as exc:
                    product = {"schema_version": "ifc/1.0", "incident_id": payload["incident_id"],
                        "logical_task_id": payload["logical_task_id"], "executor_aic": args.aic,
                        "status": "unknown" if payload["kind"] in ("act", "resume") else "tool_error",
                        "facts": [], "reason": type(exc).__name__}
                    success = False
                finally:
                    current_payload.reset(token)
                    amp.sampler.active -= 1
                amp.sampler.record((time.monotonic()-started)*1000, success)
                products = [Product(id="product-" + command.taskId, name=payload["tool"],
                                    dataItems=[StructuredDataItem(data=product)])]
                states[key] = {"state": TaskState.AwaitingCompletion, "products": products, "output": product}
                await client.submit_for_completion(command.taskId, command.sessionId, products)
                return product
            elif saved and command.command == TaskCommandType.Complete:
                saved["state"] = TaskState.Completed
                await client.complete_task(command.taskId, command.sessionId)
            elif saved and command.command == TaskCommandType.Get:
                await client.send_task_result(command.taskId, command.sessionId, saved["state"], products=saved.get("products"))
            elif saved and command.command == TaskCommandType.Cancel:
                saved["state"] = TaskState.Canceled
                await client.cancel_task(command.taskId, command.sessionId)

        client.set_command_handler(handler)
        await output({"event": "ready", "mode": "local-aip-stdio", "role": args.role,
                      "name": args.name, "aic": args.aic, "tools": tools,
                      "resource_scope": resource_scope,
                      "identity_binding": "local-process-channel"})
        try:
            while True:
                line = await asyncio.to_thread(sys.stdin.buffer.readline, 2**20 + 1)
                if not line:
                    break
                if len(line) > 2**20:
                    raise ValueError("task envelope exceeds local IPC size limit")
                command = TaskCommand.model_validate_json(line)
                if (command.senderId != args.coordinator_aic or command.senderRole != "leader"
                        or command.groupId != args.group_id or not command.sessionId or not command.taskId
                        or command.mentions != [args.aic]):
                    raise ValueError("TaskCommand differs from its bound local coordinator channel")
                await emit_message(amp.message, command, "receive", args.name + ".stdin")
                await client._handle_task_command(command)
                await emit_message(amp.message, command, "ack", args.name + ".stdin")
        finally:
            await amp.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=["database", "ops", "application", "verification"], required=True)
    parser.add_argument("--aic", required=True)
    parser.add_argument("--coordinator-aic", required=True)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--bridge-config")
    parser.add_argument("--ledger-path", required=True)
    parser.add_argument("--amp-directory", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--verification-duration", type=float, default=30)
    parser.add_argument("--experiment-id")
    parser.add_argument("--crash-point", choices=["after_observation", "before_modification", "after_applied"])
    parser.add_argument("--crash-tool", default="db.restore_writes")
    args = parser.parse_args()
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(json.dumps({"event": "startup_error", "mode": "local-aip-stdio", "error_class": type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
