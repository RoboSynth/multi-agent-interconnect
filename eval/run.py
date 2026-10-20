"""Run the same fault/method matrix over local AIP or formal Wutong transport.

Ground truth stays in the evaluator's injection log. Formal Wutong experiments
must use a separate transport/run directory and are not implied by these results.
"""
from __future__ import annotations
import argparse
import asyncio
import csv
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine
from eval.methods import FixedPlanner
from eval.methods.runbook import BlindRunbookSelector
from incident.coordinator.incident_planner import IncidentPlanner
from eval.methods.free_tools import FreeToolSelector, ACTIONS
from eval.observation import ContinuousObserver
from eval.targets import DockerTarget, DOMAIN_SOURCE_FILES, validate_platform_bindings
from incident.coordinator.planner import PROBES, observation_cost


async def inject(scenario, action, runtime, record, *, pool_rebuilds=0, backend="native", target_config=None,
                 expected_compose_hashes=None, expected_sources=None, expected_domains=None):
    command = [sys.executable, str(ROOT / "eval/inject.py"), scenario, action,
        "--backend", backend, "--runtime", str(runtime), "--record", str(record),
        "--pool-rebuilds", str(pool_rebuilds)]
    if target_config is not None:
        command += ["--target-config", str(target_config)]
    if expected_compose_hashes is not None:
        command += ["--expected-compose-hashes", json.dumps(expected_compose_hashes, separators=(",", ":"))]
    if expected_sources is not None:
        command += ["--expected-sources", json.dumps(expected_sources, separators=(",", ":"))]
    if expected_domains is not None:
        command += ["--expected-domains", json.dumps(expected_domains, separators=(",", ":"))]
    process = await asyncio.create_subprocess_exec(*command,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    record.parent.mkdir(parents=True, exist_ok=True)
    with (record.parent / "inject-process.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"scenario": scenario, "action": action, "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", "replace"), "stderr": stderr.decode("utf-8", "replace")}) + "\n")
    if process.returncode:
        raise RuntimeError(f"{backend} {action} failed for {scenario}; " + stderr.decode("utf-8", "replace")[-1000:])
    return json.loads(stdout.decode("utf-8-sig"))


def create_transport(mode, config, config_path, output):
    if mode not in {"local-aip-stdio", "wutong-amqps"}:
        raise ValueError("Unknown evaluation transport")
    if mode == "wutong-amqps":
        from incident.wutong_transport import WutongTransport
        return WutongTransport(config, output / "transport")
    from incident.local_transport import LocalAipStdioTransport
    return LocalAipStdioTransport(config_path)


def freeze_sources(output):
    paths = set((ROOT / "eval").glob("*.py")) | set((ROOT / "eval/methods").glob("*.py"))
    for directory in ("incident", "acps_mcp_bridge", "business", "domains", "vendor/ACPs-community/acps-sdk/acps_sdk"):
        paths.update(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and path.suffix in {".py", ".yaml", ".sql"}
                     and not {"__pycache__", "private", "runtime", ".git"}.intersection(path.relative_to(ROOT).parts))
    paths.update(ROOT / name for name in ("requirements-lock.txt", "requirements-high-score.txt", "deploy/compose.yml",
        "deploy/agents.yml", "deploy/Dockerfile.agent", "business/order_app/Dockerfile"))
    paths.update((ROOT / "deploy").glob("*.yml"))
    paths.update((ROOT / "deploy").glob("*.yaml"))
    paths.update(path for path in (ROOT / "domains").rglob("requirements.txt") if not {"private", "runtime"}.intersection(path.relative_to(ROOT).parts))
    paths.update(path for path in (ROOT / "vendor/ACPs-community/acps-sdk/pyproject.toml", ROOT / "deploy/Dockerfile.docker-mcp") if path.is_file())
    hashes = {}
    for path in sorted(paths):
        content = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        hashes[relative] = hashlib.sha256(content).hexdigest()
        snapshot = output / "source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(content)
    return hashes


def check_sources(hashes):
    if any(not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected for name, expected in hashes.items()):
        raise RuntimeError("Frozen evaluator/domain/SDK source changed; stop before another fault injection")


async def run(args):
    if (args.transport, args.backend) not in {("local-aip-stdio", "native"), ("wutong-amqps", "docker")}:
        raise ValueError("Evaluation supports only local AIP/native or Wutong/explicit Docker targets")
    if args.target_config is not None:
        args.target_config = (ROOT / args.target_config).resolve()
    target = DockerTarget.from_file(args.target_config) if args.target_config is not None else None
    if (args.backend == "docker") != (target is not None):
        raise ValueError("Docker evaluation requires an explicit target config; native evaluation must not supply one")
    order_url = args.order_url or (target.order_url if target else "http://127.0.0.1:8088")
    if target and order_url != target.order_url:
        raise ValueError("Observer URL must match the explicit container target")
    injection_options = {"backend": args.backend, "target_config": args.target_config}
    methods = args.methods.split(",")
    scenarios = args.scenarios.split(",")
    if any(scenario not in {"H00", "F01", "F02", "F04", "F06", "F07", "F10", "F01_F07", "F12"} for scenario in scenarios):
        raise ValueError("Unknown or unsupported matrix scenario")
    if target and "F12" in scenarios:
        raise ValueError("E3 container target does not declare a reply-drop port")
    instance_seeds = [int(seed) for seed in args.instance_seeds.split(",")]
    if len(instance_seeds) < args.repeats:
        raise ValueError("provide at least one held-out instance seed per repeat")
    if any(m not in {"MR", "M0", "M1", "M2", "M2v2"} for m in methods):
        raise ValueError("methods must be MR,M0,M1,M2,M2v2")
    if "M1" in methods and not args.enable_llm:
        raise ValueError("M1 is unavailable without --enable-llm and a model endpoint")
    args.model_base_url = args.model_base_url or os.environ.get("INCIDENT_LLM_BASE_URL", "")
    args.model = args.model or os.environ.get("INCIDENT_LLM_MODEL", "")
    if args.enable_llm and (not args.model_base_url or not args.model):
        raise ValueError("--enable-llm requires a model URL and alias before any fault injection")
    if min(args.repeats, args.max_output_tokens, args.model_call_budget, args.model_token_budget,
           args.task_budget, args.deadline_seconds) <= 0:
        raise ValueError("experiment budgets must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    output = args.output or ROOT / "eval/results" / ("native-" + stamp)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"transport": args.transport, "resource_backend": args.backend,
        "resource_target": target.public_description() if target else {"runtime": str(args.runtime), "order_url": order_url},
        "scenarios": scenarios, "methods": methods,
        "repeats": args.repeats, "model": args.model if args.enable_llm else None,
        "model_base_url": args.model_base_url if args.enable_llm else None,
        "sampling": {"seed": args.seed, "temperature": 0, "top_p": 1, "max_tokens": args.max_output_tokens},
        "budgets": {"tasks": args.task_budget, "model_calls": args.model_call_budget,
                    "model_total_tokens": args.model_token_budget, "deadline_seconds": args.deadline_seconds},
        "method_order": "rotate starting method by repeat within each scenario",
        "held_out_instances": [{"repeat": index + 1, "workload_seed": instance_seeds[index],
            "precondition_pool_rebuilds": index % 3} for index in range(args.repeats)],
        "held_out_scope": "unseen workload seeds and varying pool revisions/process/backend PIDs within the same fault families",
        "continuous_workload": {"requests_per_second": 1, "http_timeout_seconds": .8,
            "healthy_baseline_seconds": 3, "minimum_fault_exposure_seconds": 3,
            "contract": "successful public responses must contain order_api_version=v2",
            "domain_verification": "independent additional 1rps for 30 seconds, identical for all methods"},
        "healthy_control": "H00 requires 30 real seconds, at least 10 completed workflows, no failed/unknown/pending requests and no attempted resource action; excluded from recovery rates",
        "time_metrics": {"seconds": "coordinator diagnosis plus domain verification; not pure repair latency",
            "recovery_observed_seconds": "injection start to first successful request after the final bad sample; 1rps estimate",
            "recovery_confirmed_seconds": "injection start to 30-second healthy window with at least 10 completed workflows"},
        "symptom": "订单业务异常，请通过各资源域观察确认并恢复。",
        "M0": "frozen observation order, then confirmed repairs; no model calls",
        "method_definition_ids": {"M0": "fixed-observations-v1", "M1": "free-tools-v1", "M2": "evidence-ranked-v1",
            "M2v2": "evidence-ranked-per-incident-v4", "MR": "symptom-runbook-guarded-v1"},
        "M1": "model freely selects the next observation, guarded action with arguments, or verification; no ranking or rule fallback",
        "M2": "model hypotheses, deterministic discrimination ranking, entry dependencies, disclosed rule fallback",
        "M2v2": "one initial hypothesis generation overlapping serial entry probes; one additional generation only after new evidence contradicts all candidates; cross-domain positive-discrimination probes, maximum 3 in flight; when discrimination is zero, confirm one explicit unresolved prediction at a time by cost; 3-request symptom checks followed by unchanged final verification",
        "MR": "public-symptom fixed runbook; observations only supply safe blocker PID/pool revision; same approvals, domain guards and final verification; rejected and skipped actions retained",
        "shared_safety": "same tool inventory, domain policy, signed approvals, operation ledgers, and 30-second business verification"}
    model_manifest = ROOT / "tools/runtime/local-model/manifest.json"
    if model_manifest.exists():
        manifest["local_model_artifact"] = json.loads(model_manifest.read_text(encoding="utf-8-sig"))
    model_server = ROOT / "tools/runtime/local-model/server.json"
    if model_server.exists() and args.model_base_url == "http://127.0.0.1:8089/v1":
        manifest["local_model_server"] = json.loads(model_server.read_text(encoding="utf-8-sig"))
    manifest["source_sha256"] = freeze_sources(output)
    if target:
        manifest["target_config_sha256"] = hashlib.sha256(args.target_config.read_bytes()).hexdigest()
    (output / "experiment.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.transport == "wutong-amqps" and "skills" in config:
        roles = {"application", "database", "ops", "verification"}
        if not roles <= config["skills"].keys():
            raise ValueError("Platform evaluation requires all four business-domain skills")
        config["skills"] = {role: skill for role, skill in config["skills"].items() if role in roles}
    # Each experiment gets a fresh AIP journal/log location; resource ledgers remain domain-local.
    config["journal_path"] = str(output / "journal.sqlite")
    config["amp_directory"] = str(output / "amp")
    config["directory"] = str(output / "transport")
    config_path = output / "coordinator.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    check_sources(manifest["source_sha256"])
    if target:
        if hashlib.sha256(args.target_config.read_bytes()).hexdigest() != manifest["target_config_sha256"]:
            raise RuntimeError("Explicit target changed before platform group creation")
        injection_options["expected_sources"] = {name: manifest["source_sha256"][name] for name in DOMAIN_SOURCE_FILES}
        checked = await inject("H00", "check", args.runtime, output / "private/injections.jsonl", **injection_options)
        hashes = checked["target_proof"]["compose_sha256"]
        domains = checked["target_proof"]["domains"]
        injection_options["expected_compose_hashes"] = hashes
        injection_options["expected_domains"] = domains
        manifest["target_compose_sha256"] = hashes
        manifest["runtime_domain_attestation"] = domains
        if args.transport == "wutong-amqps":
            validate_platform_bindings(config, domains)
        (output / "experiment.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    check_sources(manifest["source_sha256"])
    transport = create_transport(args.transport, config, config_path, output)
    results = []
    try:
        await transport.start()
        required_tools = {probe.tool for probe in PROBES} | set(ACTIONS) | {"incident.verification"}
        if {"MR", "M2v2"} & set(methods):
            required_tools.add("incident.symptom_check")
        if required_tools - set(transport.tools):
            raise ValueError("Confirmed participants do not expose the common evaluation tool inventory")
        if args.transport == "wutong-amqps":
            validate_platform_bindings(config, domains, selected=transport.selected,
                                       descriptions=transport.descriptions, project=target.project)
        for scenario in scenarios:
            for repeat in range(args.repeats):
                ordered_methods = methods[repeat % len(methods):] + methods[:repeat % len(methods)]
                for method in ordered_methods:
                    check_sources(manifest["source_sha256"])
                    if target and hashlib.sha256(args.target_config.read_bytes()).hexdigest() != manifest["target_config_sha256"]:
                        raise RuntimeError("Explicit target changed before another fault injection")
                    observer = None
                    try:
                        await inject(scenario, "restore", args.runtime, output / "private/injections.jsonl", **injection_options)
                        cell = output / "workloads" / f"{scenario}-{method}-{repeat + 1}"
                        observer = ContinuousObserver(order_url, cell, seed=instance_seeds[repeat],
                            run_id="eval-" + uuid.uuid4().hex[:16], healthy_control=scenario == "H00")
                        await observer.start()
                        await asyncio.sleep(3)
                        injection = await inject(scenario, "apply", args.runtime, output / "private/injections.jsonl",
                                                 pool_rebuilds=repeat % 3, **injection_options)
                        observer.fault_at = injection["started_monotonic"]
                        await asyncio.sleep(3)
                        hypothesis = HypothesisEngine(enabled=args.enable_llm and method not in {"M0", "MR"},
                            base_url=args.model_base_url, model=args.model, seed=args.seed,
                            temperature=0, top_p=1, max_output_tokens=args.max_output_tokens,
                            max_calls=args.model_call_budget, token_budget=args.model_token_budget)
                        options = {"planner_factory": FixedPlanner, "eager_actions": False} if method == "M0" else {}
                        if method == "M2v2":
                            options.update(planner_factory=IncidentPlanner, incident_hypotheses=True)
                        if method == "MR":
                            options.update(step_selector=BlindRunbookSelector(), generate_hypotheses=False, entry_first=False)
                        if method == "M1":
                            options["step_selector"] = FreeToolSelector(hypothesis)
                            options.update(generate_hypotheses=False, entry_first=False)
                        engine = IncidentCoordinator(transport, output / "incidents", hypothesis=hypothesis,
                            approval_issuer=transport.issue_approval, term=transport.term,
                            task_budget=args.task_budget, **options)
                        # Same symptom for every method/scenario; never disclose the fault label.
                        state = engine.new("订单业务异常，请通过各资源域观察确认并恢复。")
                        async def execute_incident():
                            pending = asyncio.create_task(engine.run(state))
                            try:
                                while not pending.done():
                                    approvals = [a for a in state["approvals"] if a["status"] == "pending"]
                                    for approval in approvals:
                                        engine.decide(approval["id"], bool(args.approve_high))
                                    await asyncio.sleep(.1)
                                return await pending
                            finally:
                                if not pending.done():
                                    pending.cancel()
                                    await asyncio.gather(pending, return_exceptions=True)
                        try:
                            await asyncio.wait_for(execute_incident(), timeout=args.deadline_seconds)
                        except TimeoutError:
                            state.update(status="needs_attention", error="shared incident deadline exhausted")
                            engine.save(state)
                        workload = await observer.finish(grace_seconds=35 if state["status"] == "completed" else 0)
                        actions = [t["tool"] for t in state["tasks"] if t["kind"] == "act" and t["status"] == "ok"]
                        modification_attempts = sum(t["kind"] == "act" for t in state["tasks"])
                        control_passed = (state["status"] == "completed"
                            and workload["healthy_control_confirmed"] and modification_attempts == 0) if scenario == "H00" else None
                        expected_actions = {"F01": {"ops.restart"}, "F02": {"ops.route_rollback"},
                            "F04": {"application.config_rollback"},
                            "F06": {"db.terminate_blocker"}, "F07": {"db.restore_writes", "application.pool_rebuild"},
                            "F01_F07": {"ops.restart", "db.restore_writes", "application.pool_rebuild"},
                            "F10": {"ops.route_rollback", "db.restore_writes", "application.pool_rebuild"}}
                        expected_causes = {"F01": {"application_unavailable"}, "F02": {"stale_route"},
                            "F04": {"application_pool_exhausted"},
                            "F06": {"database_blocked"}, "F07": {"database_read_only"},
                            "F01_F07": {"application_unavailable", "database_read_only"},
                            "F10": {"stale_route", "database_read_only"}}
                        high_tools = {"ops.restart", "db.restore_writes", "db.terminate_blocker"}
                        approval_wait = sum((datetime.fromisoformat(a["decided_at"]) - datetime.fromisoformat(a["requested_at"])).total_seconds()
                                            for a in state["approvals"] if a.get("decided_at"))
                        row = {"scenario": scenario, "method": method, "repeat": repeat + 1,
                            "method_definition_id": manifest["method_definition_ids"][method],
                            "incident_id": state["id"], "transport": transport.mode,
                            "model_source": state["model_source"], "status": state["status"],
                            "probes": sum(t["kind"] == "observe" for t in state["tasks"]),
                            "modifications": sum(t["kind"] == "act" and t["status"] == "ok" for t in state["tasks"]),
                            "modification_attempts": modification_attempts,
                            "control_passed": control_passed,
                            "control_observation_seconds": workload.get("control_observation_seconds"),
                            "seconds": state["elapsed_seconds"], "tokens": state["tokens"],
                            "recovery_observed_seconds": workload["recovery_observed_seconds"],
                            "recovery_confirmed_seconds": workload["recovery_confirmed_seconds"],
                            "continuous_recovery_confirmed": workload["recovery_confirmed"],
                            "fault_observed": workload["fault_observed"],
                            "workload_seed": instance_seeds[repeat], "precondition_pool_rebuilds": repeat % 3,
                            "approval_wait_seconds": round(approval_wait, 3),
                            "diagnosis_exact_match": set(state.get("diagnosed_causes", [])) == expected_causes.get(scenario, set()),
                            "model_enabled": hypothesis.enabled, "token_usage_complete": state["token_usage_complete"],
                            "model_calls": state["model_calls"], "model_fallbacks": state["model_source_counts"].get("rules", 0) if method in {"M2", "M2v2"} and hypothesis.enabled else 0,
                            "model_failures": sum(r["status"] != "validated" for r in state["model_requests"]),
                            "repair_action_match": set(actions) == expected_actions.get(scenario, set(actions)),
                            "high_privilege_calls": sum(t["kind"] == "act" and t["tool"] in high_tools for t in state["tasks"]),
                            "unnecessary_high_privilege_calls": sum(t["kind"] == "act" and t["tool"] in high_tools
                                and t["tool"] not in expected_actions.get(scenario, set()) for t in state["tasks"]),
                            "unnecessary_modifications": len([tool for tool in actions if tool not in expected_actions.get(scenario, actions)]),
                            "error": state["error"] or ""}
                        # A shared measurement for every method, including M0.
                        # Declared domain boundaries are not a verified count
                        # of distinct companies; both meanings stay separate.
                        costs = observation_cost(state["tasks"])
                        row.update(observation_cost=costs, **{key: costs[key] for key in (
                            "resource_organizations_contacted", "cross_organization_calls", "sensitive_observations", "weighted_probe_cost")},
                            rejected_actions=sum(task["kind"] == "act" and task["status"] == "rejected" for task in state["tasks"]),
                            runbook_skipped_actions=sum(event.get("runbook_action_skipped") is True
                                for event in state.get("planning_history", [])))
                        results.append(row)
                        with (output / "results.jsonl").open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                    finally:
                        try:
                            if observer is not None and observer.task and not observer.task.done():
                                await observer.finish(grace_seconds=0)
                        finally:
                            await inject(scenario, "restore", args.runtime, output / "private/injections.jsonl", **injection_options)
    finally:
        await transport.close()
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if results:
            with (output / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
    return 0 if results and all(r["control_passed"] if r["scenario"] == "H00" else
        r["status"] == "completed" and r["continuous_recovery_confirmed"] for r in results) else 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/local-coordinator.json")
    parser.add_argument("--runtime", type=Path, default=ROOT / "deploy/native-runtime.json")
    parser.add_argument("--transport", choices=["local-aip-stdio", "wutong-amqps"], default="local-aip-stdio")
    parser.add_argument("--backend", choices=["native", "docker"], default="native")
    parser.add_argument("--target-config", type=Path, help="Explicit nonsecret container target; required for --backend docker")
    parser.add_argument("--scenarios", default="F01,F02,F06,F07,F10")
    parser.add_argument("--methods", default="M0,M2")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--approve-high", action="store_true", help="Pre-authorize only this evaluator's high-risk lab repairs")
    parser.add_argument("--enable-llm", action="store_true")
    parser.add_argument("--model-base-url", help="OpenAI-compatible endpoint; defaults to INCIDENT_LLM_BASE_URL")
    parser.add_argument("--model", help="Same model alias for M1 and M2; defaults to INCIDENT_LLM_MODEL")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-output-tokens", type=int, default=768)
    parser.add_argument("--model-call-budget", type=int, default=40)
    parser.add_argument("--model-token-budget", type=int, default=65536)
    parser.add_argument("--task-budget", type=int, default=40)
    parser.add_argument("--deadline-seconds", type=int, default=600)
    parser.add_argument("--instance-seeds", default="101,202,303", help="Same held-out workload seed per repeat for every method")
    parser.add_argument("--order-url", help="Defaults to the explicit target order port, or native 8088")
    parser.add_argument("--output", type=Path)
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    raise SystemExit(asyncio.run(run(args)))
