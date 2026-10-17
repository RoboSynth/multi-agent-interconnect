"""Run native fault scenarios through independent local AIP domain processes.

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
from eval.methods.free_tools import FreeToolSelector
from eval.observation import ContinuousObserver


async def inject(scenario, action, runtime, record, *, pool_rebuilds=0):
    process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT / "eval/inject.py"), scenario, action,
        "--backend", "native", "--runtime", str(runtime), "--record", str(record),
        "--pool-rebuilds", str(pool_rebuilds),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    record.parent.mkdir(parents=True, exist_ok=True)
    with (record.parent / "inject-process.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"scenario": scenario, "action": action, "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", "replace"), "stderr": stderr.decode("utf-8", "replace")}) + "\n")
    if process.returncode:
        raise RuntimeError(f"native {action} failed for {scenario}; " + stderr.decode("utf-8", "replace")[-1000:])
    return json.loads(stdout.decode("utf-8-sig"))


async def run(args):
    from incident.local_transport import LocalAipStdioTransport
    methods = args.methods.split(",")
    scenarios = args.scenarios.split(",")
    instance_seeds = [int(seed) for seed in args.instance_seeds.split(",")]
    if len(instance_seeds) < args.repeats:
        raise ValueError("provide at least one held-out instance seed per repeat")
    if any(m not in {"M0", "M1", "M2"} for m in methods):
        raise ValueError("methods must be M0,M1,M2")
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
    manifest = {"transport": "local-aip-stdio", "scenarios": scenarios, "methods": methods,
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
        "time_metrics": {"seconds": "coordinator diagnosis plus domain verification; not pure repair latency",
            "recovery_observed_seconds": "injection start to first successful request after the final bad sample; 1rps estimate",
            "recovery_confirmed_seconds": "injection start to 30-second healthy window with at least 10 completed workflows"},
        "symptom": "订单业务异常，请通过各资源域观察确认并恢复。",
        "M0": "frozen observation order, then confirmed repairs; no model calls",
        "method_definition_ids": {"M0": "fixed-observations-v1", "M1": "free-tools-v1", "M2": "evidence-ranked-v1"},
        "M1": "model freely selects the next observation, guarded action with arguments, or verification; no ranking or rule fallback",
        "M2": "model hypotheses, deterministic discrimination ranking, entry dependencies, disclosed rule fallback",
        "shared_safety": "same tool inventory, domain policy, signed approvals, operation ledgers, and 30-second business verification"}
    model_manifest = ROOT / "tools/runtime/local-model/manifest.json"
    if model_manifest.exists():
        manifest["local_model_artifact"] = json.loads(model_manifest.read_text(encoding="utf-8-sig"))
    model_server = ROOT / "tools/runtime/local-model/server.json"
    if model_server.exists() and args.model_base_url == "http://127.0.0.1:8089/v1":
        manifest["local_model_server"] = json.loads(model_server.read_text(encoding="utf-8-sig"))
    manifest["source_sha256"] = {}
    for relative in ("eval/run.py", "eval/methods/__init__.py", "eval/methods/free_tools.py", "incident/coordinator/hypothesis.py",
                     "incident/coordinator/planner.py", "incident/coordinator/engine.py",
                     "eval/observation.py", "eval/inject.py", "business/load.py",
                     "incident/contracts.py", "incident/local_transport.py", "incident/local_worker.py",
                     "incident/partners.py", "business/order_app/main.py", "business/order_app/store.py",
                     "acps_mcp_bridge/bridge.py", "acps_mcp_bridge/policy.py"):
        content = (ROOT / relative).read_bytes()
        manifest["source_sha256"][relative] = hashlib.sha256(content).hexdigest()
        snapshot = output / "source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(content)
    (output / "experiment.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    # Each experiment gets a fresh AIP journal/log location; resource ledgers remain domain-local.
    config["journal_path"] = str(output / "journal.sqlite")
    config["amp_directory"] = str(output / "amp")
    config["directory"] = str(output / "transport")
    config_path = output / "coordinator.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    transport = LocalAipStdioTransport(config_path)
    results = []
    try:
        await transport.start()
        for scenario in scenarios:
            for repeat in range(args.repeats):
                ordered_methods = methods[repeat % len(methods):] + methods[:repeat % len(methods)]
                for method in ordered_methods:
                    await inject(scenario, "restore", args.runtime, output / "private/injections.jsonl")
                    cell = output / "workloads" / f"{scenario}-{method}-{repeat + 1}"
                    observer = await ContinuousObserver(args.order_url, cell, seed=instance_seeds[repeat],
                        run_id="eval-" + uuid.uuid4().hex[:16]).start()
                    try:
                        await asyncio.sleep(3)
                        injection = await inject(scenario, "apply", args.runtime, output / "private/injections.jsonl",
                                                 pool_rebuilds=repeat % 3)
                        observer.fault_at = injection["started_monotonic"]
                        await asyncio.sleep(3)
                        hypothesis = HypothesisEngine(enabled=args.enable_llm and method != "M0",
                            base_url=args.model_base_url, model=args.model, seed=args.seed,
                            temperature=0, top_p=1, max_output_tokens=args.max_output_tokens,
                            max_calls=args.model_call_budget, token_budget=args.model_token_budget)
                        options = {"planner_factory": FixedPlanner, "eager_actions": False} if method == "M0" else {}
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
                        expected_actions = {"F01": {"ops.restart"}, "F02": {"ops.route_rollback"},
                            "F06": {"db.terminate_blocker"}, "F07": {"db.restore_writes", "application.pool_rebuild"},
                            "F10": {"ops.route_rollback", "db.restore_writes", "application.pool_rebuild"}}
                        expected_causes = {"F01": {"application_unavailable"}, "F02": {"stale_route"},
                            "F06": {"database_blocked"}, "F07": {"database_read_only"},
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
                            "seconds": state["elapsed_seconds"], "tokens": state["tokens"],
                            "recovery_observed_seconds": workload["recovery_observed_seconds"],
                            "recovery_confirmed_seconds": workload["recovery_confirmed_seconds"],
                            "continuous_recovery_confirmed": workload["recovery_confirmed"],
                            "fault_observed": workload["fault_observed"],
                            "workload_seed": instance_seeds[repeat], "precondition_pool_rebuilds": repeat % 3,
                            "approval_wait_seconds": round(approval_wait, 3),
                            "diagnosis_exact_match": set(state.get("diagnosed_causes", [])) == expected_causes.get(scenario, set()),
                            "model_enabled": hypothesis.enabled, "token_usage_complete": state["token_usage_complete"],
                            "model_calls": state["model_calls"], "model_fallbacks": state["model_source_counts"].get("rules", 0) if method == "M2" and hypothesis.enabled else 0,
                            "model_failures": sum(r["status"] != "validated" for r in state["model_requests"]),
                            "repair_action_match": set(actions) == expected_actions.get(scenario, set(actions)),
                            "high_privilege_calls": sum(t["kind"] == "act" and t["tool"] in high_tools for t in state["tasks"]),
                            "unnecessary_high_privilege_calls": sum(t["kind"] == "act" and t["tool"] in high_tools
                                and t["tool"] not in expected_actions.get(scenario, set()) for t in state["tasks"]),
                            "unnecessary_modifications": len([tool for tool in actions if tool not in expected_actions.get(scenario, actions)]),
                            "error": state["error"] or ""}
                        results.append(row)
                        with (output / "results.jsonl").open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                    finally:
                        if observer.task and not observer.task.done():
                            await observer.finish(grace_seconds=0)
                        await inject(scenario, "restore", args.runtime, output / "private/injections.jsonl")
    finally:
        await transport.close()
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if results:
            with (output / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
    return 0 if results and all(r["status"] == "completed" and r["continuous_recovery_confirmed"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/local-coordinator.json")
    parser.add_argument("--runtime", type=Path, default=ROOT / "deploy/native-runtime.json")
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
    parser.add_argument("--order-url", default="http://127.0.0.1:8088")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    raise SystemExit(asyncio.run(run(args)))
