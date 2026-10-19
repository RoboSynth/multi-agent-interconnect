"""F12: real committed writes with lost replies, original-key recovery, and missing-key abstention."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from business.load import OrderObserver
from business.receipts import validate_committed_receipt

EFFECTS = ["one owned F12 reply-drop proxy and public route change on the bound target",
           "two committed creates with lost replies, one same-original-key retry",
           "formal coordinator recovery and original-key verification; missing-key abstention",
           "restore exact original route and stop only this session's proxy",
           "independent public v2 H00: 30 seconds, 30 requests, 10 complete workflows"]


def error_evidence(error, seen=None):
    seen = set() if seen is None else seen
    if id(error) in seen:
        return {"error_class": type(error).__name__, "already_recorded": True}
    seen.add(id(error))
    result = {"error_class": type(error).__name__, "message": str(error)}
    if isinstance(error, BaseExceptionGroup):
        result["errors"] = [error_evidence(child, seen) for child in error.exceptions]
    if error.__cause__ is not None:
        result["cause"] = error_evidence(error.__cause__, seen)
    if error.__context__ is not None and error.__context__ is not error.__cause__:
        result["context"] = error_evidence(error.__context__, seen)
    return result


async def resolve_unknown(client, base_url, original_key):
    if not original_key:
        # Payload similarity is not an idempotency key. Do not create a new one.
        return {"status": "unknown", "manual_required": True, "reason": "original_request_key_missing",
                "new_request_created": False}
    response = await client.get(base_url + "/receipts/" + quote(original_key, safe=""))
    if response.status_code != 200:
        return {"status": "unknown", "manual_required": True, "reason": "receipt_not_confirmed",
                "new_request_created": False}
    try:
        body = response.json()
        if body.get("order_api_version") != "v2":
            raise ValueError("A committed v2 receipt is required")
        validate_committed_receipt(body, original_key)
    except (ValueError, AttributeError):
        return {"status": "unknown", "manual_required": True, "reason": "receipt_not_confirmed",
                "new_request_created": False}
    return {"status": "committed", "manual_required": False, "receipt": body}


def target_inputs(config_path, target, target_path):
    """Reuse the existing evaluator freeze; secrets are hashed, never embedded."""
    from eval.platform_resume_experiment import local, load, source_paths
    config = load(config_path)
    inputs = source_paths() | {config_path, target_path, target.env_file, target.route_file, *target.compose_files}
    for value in (config["trust_bundle"], config["leader"]["cert"], config["leader"]["key"], config["approval_env_file"]):
        if not Path(value).is_absolute():
            raise ValueError("Coordinator certificate/key/trust/approval paths must be absolute")
        inputs.add(local(value))
    return inputs


def prepare_target(args):
    from eval.platform_resume_experiment import local, load, digest, save
    from eval.targets import DockerTarget
    target_path, config_path = local(args.target_config), local(args.config)
    target = DockerTarget.from_file(target_path)
    target.reply_drop_url
    config = load(config_path)
    output, path = local(args.output), local(args.plan)
    if (not output.is_relative_to(ROOT / "eval/results/platform") or output.exists()
            or path.exists() or path == output or path.is_relative_to(output)):
        raise ValueError("Use a new plan separate from a new eval/results/platform output directory")
    plan = {"schema_version": "platform-f12-plan/1", "case": "F12/E5", "effects": EFFECTS,
            "experiment_id": "f12-e5-" + uuid.uuid4().hex, "model_calls": 0,
            "target_config": target_path.relative_to(ROOT).as_posix(), "config": config_path.relative_to(ROOT).as_posix(),
            "output": output.relative_to(ROOT).as_posix(), "project": target.project,
            "coordinator_aic": config["leader"]["aic"],
            "file_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(target_inputs(config_path, target, target_path))}}
    validate_target_plan(document=plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, plan)
    return plan


def validate_target_plan(path=None, *, document=None):
    from eval.platform_resume_experiment import local, load, digest
    from eval.targets import DockerTarget
    plan = load(path) if document is None else document
    fields = {"schema_version", "case", "effects", "experiment_id", "model_calls", "target_config", "config",
              "output", "project", "coordinator_aic", "file_sha256"}
    if (set(plan) != fields or plan["schema_version"] != "platform-f12-plan/1" or plan["case"] != "F12/E5"
            or plan["effects"] != EFFECTS or plan["model_calls"] != 0
            or not isinstance(plan["experiment_id"], str) or not plan["experiment_id"].startswith("f12-e5-")
            or len(plan["experiment_id"]) != 39):
        raise ValueError("Unsupported or changed F12 plan scope")
    target_path, config_path = local(plan["target_config"]), local(plan["config"])
    target = DockerTarget.from_file(target_path)
    target.reply_drop_url
    if target.project != plan["project"] or load(config_path)["leader"]["aic"] != plan["coordinator_aic"]:
        raise ValueError("Target project/coordinator differs from plan")
    output = local(plan["output"])
    if not output.is_relative_to(ROOT / "eval/results/platform") or output.exists():
        raise ValueError("F12 output exists or is outside the owned platform results root")
    required = {p.relative_to(ROOT).as_posix() for p in target_inputs(config_path, target, target_path)}
    if not required <= plan["file_sha256"].keys():
        raise ValueError("F12 source/config/target freeze is incomplete")
    for name, expected in plan["file_sha256"].items():
        if digest(local(name)) != expected:
            raise ValueError("Frozen F12 input changed: " + name)
    return plan


def authorize_target(plan, plan_path, authorization_path):
    from eval.platform_resume_experiment import local, load, digest, RESOURCE_NAMES
    expected = {"schema_version": "platform-f12-authorization/1", "authorized": True,
                "plan_sha256": digest(plan_path), "experiment_id": plan["experiment_id"],
                "project": plan["project"], "output": plan["output"], "effects": plan["effects"],
                "exclusive_coordinator": True, "no_other_identity_consumers": True,
                "no_active_or_unknown_operations": True}
    if not authorization_path:
        raise ValueError("Execution requires authorization bound to this exact F12 plan")
    auth = load(local(authorization_path))
    flags = ("authorized", "exclusive_coordinator", "no_other_identity_consumers", "no_active_or_unknown_operations")
    if auth != expected or any(type(auth.get(key)) is not bool for key in flags):
        raise ValueError("Authorization must exactly bind this plan, effects, output and ownership preconditions")
    if any(name.upper().startswith("PG") or name.upper() in RESOURCE_NAMES for name in os.environ):
        raise ValueError("Remove resource credential/remote Docker variables from the coordinator environment")
    return auth


async def run_target(plan):
    """One authorized case. Fault ground truth never enters coordinator task data."""
    from eval.platform_resume_experiment import local, load, save, CleanupWarnings, close_owned
    from eval.targets import DockerTarget, validate_platform_bindings
    from eval.inject import Injector
    from eval.run import create_transport
    from incident.coordinator.engine import IncidentCoordinator
    from incident.coordinator.hypothesis import HypothesisEngine
    from incident.coordinator.planner import PROBES
    from deploy.verify import verify, healthy_window
    target_path, config_path = local(plan["target_config"]), local(plan["config"])
    target = DockerTarget.from_file(target_path)
    target.reply_drop_url
    output = local(plan["output"])
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    private = output / "private"
    private.mkdir(mode=0o700)
    report = {"schema_version": "platform-f12-result/1", "case": "F12/E5", "project": target.project,
              "experiment_id": plan["experiment_id"], "passed": False, "checks": [], "errors": [],
              "model_calls": 0, "started_at": datetime.now(timezone.utc).isoformat()}
    save(output / "result.json", report)
    controller = transport = None
    cleanup_warnings = CleanupWarnings()
    logging.getLogger().addHandler(cleanup_warnings)

    def check(name, passed, **evidence):
        report["checks"].append({"name": name, "passed": passed is True, **evidence})
        save(output / "result.json", report)
        if passed is not True:
            raise AssertionError(name)

    def count(key):
        return controller.sql("SELECT count(*), count(DISTINCT id) FROM orders WHERE request_key='" + key + "';").strip()

    try:
        controller = Injector(backend="docker", target_config=target_path)
        domains = controller.target_proof["domains"]
        config = load(config_path)
        roles = {"application", "database", "ops", "verification"}
        if not roles <= config.get("skills", {}).keys():
            raise ValueError("All four business-domain skills are required")
        config["skills"] = {role: skill for role, skill in config["skills"].items() if role in roles}
        validate_platform_bindings(config, domains)
        config.update(journal_path=str(private / "journal.sqlite"), amp_directory=str(private / "amp"),
                      directory=str(private / "transport"))
        run_config = private / "coordinator.json"
        save(run_config, config)
        transport = create_transport("wutong-amqps", config, run_config, private)
        await transport.start()
        required = {p.tool for p in PROBES} | {"ops.route_rollback", "incident.verification"}
        if required - set(transport.tools):
            raise ValueError("Selected participants lack the required normal observation/repair/verification tools")
        validate_platform_bindings(config, domains, selected=transport.selected,
                                   descriptions=transport.descriptions, project=target.project)
        controller.apply("F12")
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            cases = []
            item = "unknown-intent-" + uuid.uuid4().hex
            for name in ("original_key", "missing_key"):
                payload = {"request_key": "unknown-" + uuid.uuid4().hex, "item": item, "quantity": 1}
                case = {"name": name, "payload": payload}
                cases.append(case)
                save(private / "original-intents.json", cases)
                try:
                    await client.post(target.order_url + "/orders", json=payload, timeout=1.5)
                except httpx.ReadTimeout:
                    check(name + ": public response lost", True)
                else:
                    check(name + ": public response lost", False)
                check(name + ": committed once in bound database", count(payload["request_key"]) == "1|1")
            engine = IncidentCoordinator(transport, private / "incidents", hypothesis=HypothesisEngine(enabled=False),
                                         term=getattr(transport, "term", 1), generate_hypotheses=False)
            original, missing = cases
            state = engine.new("订单请求结果未知，请根据各域观察恢复入口并核对原请求。",
                               original_request_key=original["payload"]["request_key"], original_request_unknown=True)
            await asyncio.wait_for(engine.run(state), timeout=240)
            facts = state.get("result") or {}
            check("coordinator repairs and resolves the original intent before evaluator restoration",
                  state["status"] == "completed" and facts.get("business_recovered") is True
                  and facts.get("original_request_resolved") is True and facts.get("manual_required") is False
                  and healthy_window(facts.get("order_observation", {})))
            route_tasks = [row for row in state["tasks"] if row["tool"] == "ops.route_rollback" and row["status"] == "ok"]
            check("route recovery uses normal guarded action and fresh v2 observation",
                  len(route_tasks) == 1 and any(f["key"] == "route_version" and f["value"] == "v2" for f in state["facts"]))
            resolved = await resolve_unknown(client, target.order_url, original["payload"]["request_key"])
            check("public original-key receipt is committed", resolved["status"] == "committed")
            receipt = resolved["receipt"]
            validate_committed_receipt(receipt, original["payload"]["request_key"], operation_kind="create")
            retry = await client.post(target.order_url + "/orders", json=original["payload"])
            retry.raise_for_status()
            body = retry.json()
            check("same-original-key retry preserves v2 receipt and order identity", body.get("order_api_version") == "v2")
            validate_committed_receipt(body, original["payload"]["request_key"], operation_kind="create", order_id=receipt["order_id"])
            check("same-original-key retry leaves one order", count(original["payload"]["request_key"]) == "1|1")
            negative = engine.new("订单请求结果未知，原请求键已遗失，请核实业务状态并保留人工核对。",
                                  original_request_unknown=True)
            await asyncio.wait_for(engine.run(negative), timeout=180)
            facts = negative.get("result") or {}
            check("missing original key stays manual despite healthy fresh workflows",
                  negative["status"] == "needs_attention" and facts.get("service_recovered") is True
                  and facts.get("business_recovered") is False and facts.get("original_request_resolved") is False
                  and facts.get("manual_required") is True and facts.get("original_request_resolution") == "unknown_missing_key"
                  and healthy_window(facts.get("order_observation", {})))
            check("missing-key incident receives no hidden evaluator key or replacement payload",
                  all(row["kind"] != "act" for row in negative["tasks"])
                  and [row["args"] for row in negative["tasks"] if row["kind"] == "verify"] == [
                      {"original_request_key": None, "original_request_unknown": True}])
            check("both original intents remain unique; no same-payload replacement order",
                  count(missing["payload"]["request_key"]) == "1|1"
                  and controller.sql("SELECT count(*) FROM orders WHERE item='" + item + "';").strip() == "2")
            report["incidents"] = {"original_key": state["id"], "missing_key": negative["id"]}
    except Exception as error:
        report["errors"].append({"phase": "case", **error_evidence(error)})
    finally:
        try:
            if transport is not None:
                try:
                    report["close_checks"] = await close_owned(transport, cleanup_warnings)
                    report["transport_closed"] = True
                except Exception as error:
                    report["errors"].append({"phase": "transport_close", **error_evidence(error)})
        finally:
            if controller is not None:
                try:
                    controller.restore("F12")
                    proof = getattr(controller, "f12_proof", {})
                    report["restored"] = proof.get("route_restored") is True and proof.get("proxy_stopped") is True
                except Exception as error:
                    report["errors"].append({"phase": "restore", **error_evidence(error)})
                finally:
                    save(private / "injection-proof.json", getattr(controller, "f12_proof", {}))
            logging.getLogger().removeHandler(cleanup_warnings)
            report["cleanup_warning_events"] = cleanup_warnings.events
            save(output / "result.json", report)
    if report.get("restored") and not report["errors"]:
        try:
            healthy = await verify(target.order_url, output / "restored-h00")
            report["h00_status"] = healthy["status"]
            report["passed"] = healthy["status"] == "passed" and all(row["passed"] for row in report["checks"])
        except Exception as error:
            report["errors"].append({"phase": "restored_h00", **error_evidence(error)})
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    save(output / "result.json", report)
    return 0 if report["passed"] else 1


def wsl_path(path):
    value = str(Path(path).resolve())
    if len(value) < 3 or value[1] != ":":
        return value
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")


async def run(args):
    prefix = ["wsl.exe", "-d", args.wsl, "--exec"] if args.wsl else []
    docker = prefix + ["docker"]
    convert = wsl_path if args.wsl else str
    compose = prefix + ["env", "REPLY_DROP_PORT=" + str(args.proxy_port), "docker"] if args.wsl else ["docker"]
    compose += ["compose", "-p", args.project, "--env-file", convert(args.env_file),
                "-f", convert(ROOT / "deploy/compose.yml"), "--profile", "faults"]
    def command(argv, *, data=None):
        result = subprocess.run(argv, input=data, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                env={**os.environ, "REPLY_DROP_PORT": str(args.proxy_port)}, check=False)
        if result.returncode:
            raise RuntimeError("Docker command failed: " + result.stderr[-800:])
        return result.stdout.strip()
    def count(key):
        # Keys originate from uuid.hex here, never from task-supplied SQL text.
        query = "SELECT count(*), count(DISTINCT id) FROM orders WHERE request_key='" + key + "';"
        return command(docker + ["exec", "-i", args.project + "-postgres-1", "psql", "-U", "postgres", "-d", "orders", "-At", "-c", query])
    output = args.output or ROOT / ("eval/results/local/F12-container-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    if output.exists():
        raise ValueError("Choose a new output path to preserve prior evidence")
    report = {"scenario": "F12", "environment": "actual isolated Docker PostgreSQL/Nginx/FastAPI/reply-suppression proxy",
              "platform_group_tested": False, "passed": False, "checks": []}
    started = False
    def check(name, passed, **evidence):
        report["checks"].append({"name": name, "passed": bool(passed), **evidence})
        if not passed:
            raise AssertionError(name)
    try:
        command(compose + ["up", "-d", "--build", "--no-deps", "reply-drop"])
        started = True
        proxy = "http://127.0.0.1:" + str(args.proxy_port)
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            for attempt in range(30):
                try:
                    response = await client.get(proxy + "/health")
                    response.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 29:
                        raise
                    await asyncio.sleep(0.2)
            for missing in (False, True):
                key = "f12-docker-" + uuid.uuid4().hex
                payload = {"request_key": key, "item": "isolated-unknown-receipt", "quantity": 1}
                try:
                    await client.post(proxy + "/orders", json=payload, timeout=1.5)
                except httpx.ReadTimeout:
                    check("reply is lost after actual backend write", True, key_available_to_resolver=not missing)
                else:
                    check("reply is lost after actual backend write", False)
                check("PostgreSQL contains exactly one committed order", count(key) == "1|1")
                result = await resolve_unknown(client, args.url, None if missing else key)
                if missing:
                    check("missing original key remains unknown and requires manual resolution",
                          result["status"] == "unknown" and result["manual_required"] and not result["new_request_created"], result=result)
                    check("missing-key path creates no replacement order", count(key) == "1|1")
                else:
                    check("original key confirms the existing receipt", result["status"] == "committed", result=result)
                    retry = await client.post(args.url + "/orders", json=payload)
                    retry.raise_for_status()
                    check("original-key retry returns the existing order",
                          retry.json()["order_id"] == result["receipt"]["order_id"], response=retry.json())
                    check("same-key retry still leaves one database order", count(key) == "1|1")
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if started:
            try:
                command(compose + ["stop", "reply-drop"])
                report["proxy_stopped"] = True
            except Exception as exc:
                report["restore_error"] = type(exc).__name__
    if not report.get("error") and report.get("proxy_stopped"):
        healthy = await OrderObserver(args.url, run_id="f12-restored-" + uuid.uuid4().hex).observe(duration=30)
        report["healthy_observation"] = {k: v for k, v in healthy.items() if k not in {"events", "state"}}
        report["passed"] = healthy["passed"] and all(c["passed"] for c in report["checks"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenario": "F12", "passed": report["passed"], "output": str(output), "error": report.get("error")}))
    return 0 if report["passed"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Freeze a formal target plan using files only")
    parser.add_argument("--plan", type=Path, help="Formal F12/E5 plan; validation is offline unless --execute is supplied")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--target-config", type=Path)
    parser.add_argument("--config", type=Path, help="This target's own coordinator configuration")
    parser.add_argument("--wsl")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--url")
    parser.add_argument("--proxy-port", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.plan or args.target_config or args.config or args.prepare or args.execute or args.authorization_file:
        from eval.platform_resume_experiment import local, coordinator_lock
        if not args.plan or any(value is not None for value in (args.wsl, args.env_file, args.project, args.url, args.proxy_port)):
            parser.error("Formal F12 requires --plan and must not mix legacy scope overrides")
        if args.prepare:
            if args.execute or args.authorization_file or not all((args.config, args.target_config, args.output)):
                parser.error("Preparation requires config, target and new output, without execution/authorization")
            prepare_target(args)
            print(json.dumps({"status": "FORMAL_F12_PLAN_PREPARED_NOT_EXECUTED", "resource_network_model_actions": 0}))
            return 0
        if any((args.config, args.target_config, args.output)):
            parser.error("The frozen plan supplies config, target and output for validation/execution")
        plan = validate_target_plan(local(args.plan))
        if not args.execute:
            if args.authorization_file:
                parser.error("Authorization is only consumed with --execute")
            print(json.dumps({"status": "FORMAL_F12_OFFLINE_PLAN_VALID", "resource_network_model_actions": 0}))
            return 0
        authorize_target(plan, local(args.plan), args.authorization_file)
        with coordinator_lock(plan["coordinator_aic"]):
            return asyncio.run(run_target(plan))
    if not args.env_file:
        parser.error("Legacy container mode requires --env-file; formal mode uses --plan")
    args.project = args.project or "incident-pilot-container"
    args.url = args.url or "http://127.0.0.1:18088"
    args.proxy_port = args.proxy_port or 18090
    if not args.project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in args.project):
        raise ValueError("Invalid Compose project name")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
