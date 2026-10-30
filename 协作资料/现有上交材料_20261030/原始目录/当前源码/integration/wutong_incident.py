"""Run the existing incident business workflow through four formal Wutong AICs."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import wutong_smoke as transport
from acps_sdk.aip.aip_group_runtime import get_endpoint_url
from run_pilot import Lab
from services import execute_business_action

ROLES = ("application", "database", "verification")
ACTIONS = {"application": {"inspect", "repair_endpoint"},
           "database": {"inspect", "resume"}, "verification": {"verify"}}


def save_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_event(path, event, **values):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": transport.utc_now(), "event": event, **values},
                                ensure_ascii=False) + "\n")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    for name in ("discovery_url", "mq_auth_url"):
        parsed = urlparse(config[name])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{name} must be the real HTTPS service URL")
    if not Path(config["trust_bundle"]).is_absolute():
        raise ValueError("trust_bundle must be an absolute path")
    identities, brokers = set(), set()
    for role in ("leader", *ROLES):
        agent = config["agents"][role]
        agent["aic"] = agent["aic"].strip().upper()
        valid, reason = transport.validate_aic_format(agent["aic"])
        if not valid:
            raise ValueError(f"{role} AIC: {reason}")
        identities.add(agent["aic"])
        for field in ("cert", "key"):
            if not Path(agent[field]).is_absolute():
                raise ValueError(f"{role}.{field} must be an absolute path")
        parsed = urlparse(agent["endpoint"])
        if parsed.scheme != "amqps" or not parsed.port or parsed.username or parsed.password:
            raise ValueError(f"{role} requires a real AMQPS endpoint")
        endpoint = transport.parse_amqp_endpoint_url(agent["endpoint"], aic=agent["aic"])
        if endpoint.inbox != transport.build_inbox_queue_name(agent["aic"]):
            raise ValueError(f"{role} Inbox must match its AIC")
        brokers.add((endpoint.host, endpoint.port, endpoint.vhost))
        if role in ROLES and agent.get("skill_id") != f"incident.{role}":
            raise ValueError(f"{role}.skill_id must be incident.{role}")
    if len(identities) != 4 or len(brokers) != 1:
        raise ValueError("Four distinct AICs on the same official broker/vhost are required")
    return config


def certificate_context(config, role):
    agent = config["agents"][role]
    fields = {f"{role}_aic": agent["aic"], f"{role}_cert": agent["cert"],
              f"{role}_key": agent["key"], "trust_bundle": config["trust_bundle"]}
    if agent.get("key_password_env"):
        fields[f"{role}_key_password_env"] = agent["key_password_env"]
    context, _ = transport.validate_certificates(
        fields, role, transport.read_pem_certificates(config["trust_bundle"]))
    return context


def runtime_options(config, role, context, record):
    agent = config["agents"][role]
    endpoint = transport.parse_amqp_endpoint_url(agent["endpoint"], aic=agent["aic"])
    return {"leader_aic": agent["aic"], "allowed_peer_aic": config["agents"]["leader"]["aic"]
            if role != "leader" else config["agents"]["application"]["aic"],
            "rabbitmq_config": {"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                                "user": None, "password": None, "auth_service_url": config["mq_auth_url"]},
            "ssl_context": context, "record": record, "identity_binding_enabled": True}


def validate_business_payload(role, payload, *, database):
    if not isinstance(payload, dict) or payload.get("capability") != role:
        raise ValueError("Task capability does not match this worker")
    action = payload.get("action")
    if action not in ACTIONS[role]:
        raise ValueError(f"Unsupported {role} action")
    required = {"capability", "action"}
    if action == "repair_endpoint":
        required |= {"database_url", "expected_revision"}
        if payload.get("database_url") != database:
            raise ValueError("Repair destination is not the disposable database")
    elif action == "resume":
        required.add("expected_revision")
    if set(payload) != required:
        raise ValueError("Unexpected or missing business task fields")
    if "expected_revision" in payload and type(payload["expected_revision"]) is not int:
        raise ValueError("expected_revision must be an integer")
    return {key: value for key, value in payload.items() if key != "capability"}


class BusinessTask:
    def __init__(self, client, command, role, payload, target, database, record):
        self.client, self.role, self.payload = client, role, payload
        self.session_id, self.task_id = command.sessionId, command.taskId
        self.target, self.database, self.record = target, database, record
        self.state, self.products = None, None

    async def command(self, command):
        kind = command.command
        self.record("business_command", role=self.role, command=command.model_dump(mode="json"))
        if kind == transport.TaskCommandType.Start:
            if self.state is not None:
                await self.client.send_task_result(self.task_id, self.session_id, self.state, products=self.products)
                return
            self.state = transport.TaskState.Accepted
            await self.client.accept_task(self.task_id, self.session_id)
            self.state = transport.TaskState.Working
            await self.client.start_working(self.task_id, self.session_id)
            self.record("business_action_started", role=self.role, task_id=self.task_id, payload=self.payload)
            try:
                output = await execute_business_action(self.role, self.payload, target=self.target, database=self.database)
                self.record("business_action_returned", role=self.role, task_id=self.task_id, output=output)
                if self.state in (transport.TaskState.Canceled, transport.TaskState.Failed):
                    return
                value = {"capability": self.role, "action": self.payload["action"], "result": output,
                         "agent_aic": self.client.partner_aic, "observed_utc": transport.utc_now()}
                self.products = [transport.Product(id=f"business-{self.task_id}", name=self.payload["action"],
                    dataItems=[transport.TextDataItem(text=json.dumps(value, ensure_ascii=False))])]
                self.state = transport.TaskState.AwaitingCompletion
                await self.client.submit_for_completion(self.task_id, self.session_id, self.products)
            except Exception as exc:
                if self.state != transport.TaskState.Canceled:
                    self.state = transport.TaskState.Failed
                    await self.client.fail_task(self.task_id, self.session_id, f"{type(exc).__name__}: {exc}")
                self.record("business_action_failed", role=self.role, task_id=self.task_id,
                            error=f"{type(exc).__name__}: {exc}")
        elif kind == transport.TaskCommandType.Complete:
            if self.state in (transport.TaskState.AwaitingCompletion, transport.TaskState.Completed):
                self.state = transport.TaskState.Completed
                await self.client.complete_task(self.task_id, self.session_id)
        elif kind == transport.TaskCommandType.Cancel:
            if self.state not in (transport.TaskState.Completed, transport.TaskState.Failed, transport.TaskState.Canceled):
                self.state = transport.TaskState.Canceled
                await self.client.cancel_task(self.task_id, self.session_id)
        elif kind == transport.TaskCommandType.Get and self.state is not None:
            await self.client.send_task_result(self.task_id, self.session_id, self.state, products=self.products)


class IncidentRuntime(transport.InboundProbeLeader):
    def __init__(self, *, role, target, database, **kwargs):
        super().__init__(**kwargs)
        self.role, self.target, self.database = role, target, database

    async def _probe_command(self, client, command, is_mentioned):
        if (not is_mentioned or command.senderRole != "leader" or command.senderId != self.allowed_peer_aic
                or command.groupId != client.group_id or not command.sessionId or not command.taskId):
            self.record("business_command_ignored", role=self.role, reason="identity/context mismatch")
            return
        tasks = self._inbound_probes.setdefault(client.group_id, {})
        task = tasks.get(command.taskId)
        if task and task.session_id != command.sessionId:
            self.record("business_command_ignored", role=self.role, reason="task/session collision")
            return
        if task is None:
            if command.command != transport.TaskCommandType.Start:
                return
            try:
                text = "\n".join(item.text for item in command.dataItems or [] if isinstance(item, transport.TextDataItem))
                payload = validate_business_payload(self.role, json.loads(text), database=self.database)
                if len(tasks) >= 64:
                    raise ValueError("Group task capacity reached")
            except (ValueError, TypeError) as exc:
                await client.reject_task(command.taskId, command.sessionId, str(exc))
                self.record("business_command_rejected", role=self.role, reason=str(exc))
                return
            task = BusinessTask(client, command, self.role, payload, self.target, self.database, self.record)
            tasks[command.taskId] = task
        await task.command(command)


async def worker_main(args):
    output = Path(args.output).resolve()
    event_path = output / f"worker-{args.worker}-events.jsonl"
    record = lambda event, **values: append_event(event_path, event, **values)
    result = {"role": args.worker, "pid": os.getpid(), "ready": False, "cleanup_errors": []}
    runtime = None
    try:
        config = load_config(args.config)
        for value in (args.target, args.database):
            parsed = urlparse(value or "")
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
                raise ValueError("Workers may only operate on this run's loopback services")
        runtime = IncidentRuntime(role=args.worker, target=args.target, database=args.database,
            **runtime_options(config, args.worker, certificate_context(config, args.worker), record))
        await asyncio.wait_for(runtime.start_inbound(), args.timeout)
        result.update(ready=True, aic=config["agents"][args.worker]["aic"])
        save_json(output / f"worker-{args.worker}.ready.json", result)
        deadline = asyncio.get_running_loop().time() + 600
        while not (output / f"worker-{args.worker}.stop").exists():
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError("Worker service lifetime exceeded")
            await asyncio.sleep(0.2)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        record("worker_failed", error=result["error"])
    finally:
        if runtime:
            try:
                await transport.close_runtime(runtime, args.timeout, record)
            except Exception as exc:
                result["cleanup_errors"].append(f"{type(exc).__name__}: {exc}")
        save_json(output / f"worker-{args.worker}-result.json", result)
    return 0 if result["ready"] and not result.get("error") and not result["cleanup_errors"] else 1


class PlatformLab(Lab):
    def __init__(self, output, config, args):
        super().__init__(output)
        self.config, self.args = config, args
        self.runtime, self.session = None, None
        self.workers, self.discovered, self.tasks = {}, {}, []
        self.worker_runtime_pids = {}

    async def setup(self):
        self.database, _ = await self.launch("database")
        self.target, _ = await self.launch("target")
        for role in ROLES:
            handle = (self.output / f"worker-{role}.log").open("w", encoding="utf-8")
            self.handles.append(handle)
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", role,
                       "--config", str(Path(self.args.config).resolve()), "--output", str(self.output),
                       "--target", self.target, "--database", self.database, "--timeout", str(self.args.timeout)]
            process = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.processes.append(process)
            self.workers[role] = process
        deadline = asyncio.get_running_loop().time() + self.args.timeout
        for role, process in self.workers.items():
            ready = self.output / f"worker-{role}.ready.json"
            while not ready.exists():
                if process.poll() is not None:
                    raise RuntimeError(f"{role} worker exited; see worker-{role}.log")
                if asyncio.get_running_loop().time() > deadline:
                    raise TimeoutError(f"{role} worker did not open its formal Inbox")
                await asyncio.sleep(0.1)
            info = json.loads(ready.read_text(encoding="utf-8"))
            if info["aic"] != self.config["agents"][role]["aic"]:
                raise RuntimeError(f"{role} worker readiness identity mismatch")
            self.worker_runtime_pids[role] = info["pid"]
            self.event("platform_worker_started", **info, launcher_pid=process.pid, runtime_pid=info["pid"])

    async def connect(self):
        from wutong_discovery import discover_skill
        self.runtime = transport.InboundProbeLeader(**runtime_options(
            self.config, "leader", certificate_context(self.config, "leader"), self.event))
        await asyncio.wait_for(self.runtime.start_inbound(), self.args.timeout)
        self.session = await asyncio.wait_for(self.runtime.create_group_session(
            "incident-" + uuid.uuid4().hex, []), self.args.timeout)
        for role in ROLES:
            expected = self.config["agents"][role]
            acs = await asyncio.wait_for(discover_skill(self.config["discovery_url"], expected["skill_id"],
                                                       record=self.event), self.args.timeout)
            if acs.get("aic") != expected["aic"]:
                raise RuntimeError(f"ADP selected an unexpected {role} identity")
            discovered_endpoint = get_endpoint_url(acs, "AMQP", aic=acs["aic"])
            if not discovered_endpoint:
                raise RuntimeError(f"ADP {role} ACS has no AMQP Inbox endpoint")
            actual = transport.parse_amqp_endpoint_url(discovered_endpoint, aic=acs["aic"])
            configured = transport.parse_amqp_endpoint_url(expected["endpoint"], aic=expected["aic"])
            if actual != configured:
                raise RuntimeError(f"ADP {role} endpoint differs from this run's formal identity endpoint")
            self.discovered[role] = {"aic": acs["aic"], "endpoint": discovered_endpoint, "acs": acs}
            self.event("adp_partner_selected", role=role, **self.discovered[role])
            await asyncio.wait_for(self.runtime.invite_partner(self.session.session_id,
                transport.ACSObject(aic=acs["aic"]), partner_acs_data=acs), self.args.timeout + 2)
            if self.session.invitation_routes.get(acs["aic"]) != "inbox":
                raise RuntimeError("An official Inbox invitation route was not selected")

    async def call(self, mode, role, payload):
        selected = self.discovered[role]
        task_id = "business-" + uuid.uuid4().hex
        self.calls += 1
        row = {"case": self.case_id, "role": role, "aic": selected["aic"], "task_id": task_id,
               "session_id": self.session.session_id, "group_id": self.session.group_id,
               "payload": payload, "completed": False}
        self.tasks.append(row)
        self.event("platform_action_start", **row)
        try:
            await asyncio.wait_for(self.runtime.start_task(self.session.session_id,
                task_content=json.dumps({"capability": role, **payload}, ensure_ascii=False),
                task_id=task_id, target_partners=[selected["aic"]]), self.args.timeout)
            snapshot = await transport.wait_for_state(self.session, task_id, selected["aic"],
                                                      transport.TaskState.AwaitingCompletion, self.args.timeout)
            product = json.loads(snapshot.get("product_text") or "null")
            if (not isinstance(product, dict) or product.get("capability") != role
                    or product.get("action") != payload["action"] or product.get("agent_aic") != selected["aic"]
                    or not isinstance(product.get("result"), dict)):
                raise RuntimeError("Actual platform business product failed identity/action validation")
            await asyncio.wait_for(self.runtime.complete_task(self.session.session_id, task_id,
                                    target_partner=selected["aic"]), self.args.timeout)
            await transport.wait_for_state(self.session, task_id, selected["aic"],
                                           transport.TaskState.Completed, self.args.timeout)
            row["states"] = [message.status.state.value for message in self.session.message_history
                if isinstance(message, transport.TaskResult) and message.taskId == task_id
                and message.senderId == selected["aic"]]
            if not {"accepted", "working", "awaiting-completion", "completed"}.issubset(row["states"]):
                raise RuntimeError("Business task lifecycle states are incomplete")
            row.update(completed=True, product=product)
            self.event("platform_action_complete", **row)
            return product["result"]
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            self.event("platform_action_failed", **row)
            raise

    async def shutdown(self):
        errors = []
        if self.session:
            save_json(self.output / "messages.json", [item.model_dump(mode="json") for item in self.session.message_history])
            try:
                await asyncio.wait_for(self.runtime.dissolve_group_session(self.session.session_id), self.args.timeout)
            except Exception as exc:
                errors.append(f"group: {type(exc).__name__}: {exc}")
        if self.runtime:
            try:
                await transport.close_runtime(self.runtime, self.args.timeout, self.event)
            except Exception as exc:
                errors.append(f"leader: {type(exc).__name__}: {exc}")
        for role in self.workers:
            (self.output / f"worker-{role}.stop").write_text("stop\n", encoding="utf-8")
        deadline = asyncio.get_running_loop().time() + self.args.timeout
        while any(process.poll() is None for process in self.workers.values()):
            if asyncio.get_running_loop().time() > deadline:
                break
            await asyncio.sleep(0.1)
        for role, process in self.workers.items():
            if process.poll() != 0:
                errors.append(f"{role} worker exit={process.poll()}; see worker result/log")
        self.close()
        if not all(process.poll() is not None for process in self.processes):
            errors.append("An owned test process remained active")
        return errors


async def main_run(args):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    output = Path(args.output).resolve() if args.output else ROOT / "integration" / "artifacts" / ("incident-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    result = {"mode": "wutong-business-workflow", "started_utc": transport.utc_now(),
              "passed": False, "results": [], "cleanup_errors": [],
              "deployment": "one local Leader process and three independent formal Partner processes",
              "diagnosis": "existing deterministic policy; real HTTP/SQLite business effects",
              "output": str(output)}
    lab, reserved = None, None
    try:
        config = load_config(args.config)
        lab = PlatformLab(output, config, args)
        reserved = socket.socket()
        reserved.bind(("127.0.0.1", 0))
        lab.closed_port = reserved.getsockname()[1]
        lab.ports.add(lab.closed_port)
        await lab.setup()
        await lab.connect()
        for scenario in args.scenarios.split(","):
            if scenario not in {"combined", "healthy", "stale_endpoint", "database_paused", "unknown_fault"}:
                raise ValueError(f"Unsupported scenario: {scenario}")
            result["results"].append(await lab.run_case("wutong-adp", scenario, 1))
        result["passed"] = all(row["passed"] for row in result["results"]) and all(task["completed"] for task in lab.tasks)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        append_event(output / "events.jsonl", "run_failed", error=result["error"])
    finally:
        if lab:
            result["cleanup_errors"] = await lab.shutdown()
            result["tasks"], result["discovered"] = lab.tasks, lab.discovered
            result["workers"] = {role: {"launcher_pid": process.pid,
                                       "runtime_pid": lab.worker_runtime_pids.get(role),
                                       "exit_code": process.poll()}
                                 for role, process in lab.workers.items()}
            result["processes_stopped"] = all(process.poll() is not None for process in lab.processes)
        if reserved:
            reserved.close()
        result["passed"] = result["passed"] and not result["cleanup_errors"]
        result["finished_utc"] = transport.utc_now()
        save_json(output / "RESULT.json", result)
        report = ["# 梧桐故障业务运行", "", f"结果：{'通过' if result['passed'] else '失败'}", "",
                  "四个正式身份；三个 Partner 独立进程；业务动作经梧桐 AIP 消息执行。", "",
                  "| 场景 | HTTP 前→后 | 修改次数 | 数据相同 | 正式 AIP 任务数 | 结果 |",
                  "|---|---|---:|---|---:|---|"]
        for row in result["results"]:
            report.append(f"| {row['scenario']} | {row['before_status']}→{row['after_status']} | {row['mutations']} | {row['data_unchanged']} | {row['aip_tasks']} | {row['passed']} |")
        report += ["", f"错误：{result.get('error', '无')}", f"清理错误：{result['cleanup_errors']}",
                   "", "诊断沿用规则；业务后端为本机隔离 HTTP/SQLite。平台消息、ADP选择、动作产物和进程信息见 RESULT.json、messages.json、events.jsonl 及各 worker 记录。", ""]
        (output / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "output": str(output), "error": result.get("error"),
                      "cleanup_errors": result["cleanup_errors"]}, ensure_ascii=False))
    return 0 if result["passed"] else 1


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--worker", choices=ROLES)
    result.add_argument("--config", required=True)
    result.add_argument("--output")
    result.add_argument("--scenarios", default="combined")
    result.add_argument("--timeout", type=int, default=30)
    result.add_argument("--target")
    result.add_argument("--database")
    return result


def main():
    args = parser().parse_args()
    if not 5 <= args.timeout <= 120:
        raise ValueError("--timeout must be 5..120 seconds")
    return asyncio.run(worker_main(args) if args.worker else main_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
