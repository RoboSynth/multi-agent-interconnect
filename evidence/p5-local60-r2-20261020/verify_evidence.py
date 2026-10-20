"""Validate this batch's immutable raw records and derived tables offline."""
from datetime import datetime, timezone
import json
from pathlib import Path
from report import ARTIFACTS, BATCH, RUN, OUTPUT, METHODS, confirmed, load, save, sha, validate_inputs


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    rows, experiment = validate_inputs()
    intent = load(BATCH / "execution-intent.json")
    sources = experiment["source_sha256"]
    require(sources == intent["source_sha256"], "Evaluator source differs from execution intent")
    for name, expected in sources.items():
        require(sha(RUN / "source" / name) == expected, "Matrix source snapshot changed: " + name)
        require(sha(BATCH / "binding/source" / name) == expected, "Intent source snapshot changed: " + name)
    require(experiment["sampling"] == {"seed": 42, "temperature": 0, "top_p": 1, "max_tokens": 768}, "Sampling differs from plan")
    require(experiment["budgets"] == {"tasks": 40, "model_calls": 40, "model_total_tokens": 65536, "deadline_seconds": 600}, "Budgets differ from plan")
    require(experiment["model"] == "Qwen3-1.7B-Q8_0" and experiment["model_base_url"] == "http://127.0.0.1:8089/v1", "Model differs from plan")
    summary, derived = load(OUTPUT / "summary.json"), load(OUTPUT / "results.json")
    require(derived == rows, "Derived result rows differ from raw rows")
    bindings = load(OUTPUT / "source-bindings.json")
    require(bindings["results_sha256"] == sha(RUN / "results.json"), "Raw results SHA mismatch")
    require(bindings["experiment_sha256"] == sha(RUN / "experiment.json"), "Experiment SHA mismatch")
    require(bindings["execution_intent_sha256"] == sha(BATCH / "execution-intent.json"), "Execution intent SHA mismatch")
    for row in rows:
        path = RUN / "incidents" / (row["incident_id"] + ".json")
        require(sha(path) == bindings["raw_incident_sha256"][row["incident_id"]], "Raw incident SHA mismatch")
        incident = load(path)
        require(incident["id"] == row["incident_id"] and incident["status"] == row["status"], "Incident identity/status mismatch")
        require(incident["model_calls"] == row["model_calls"] and incident["tokens"] == row["tokens"], "Incident model cost mismatch")
    for method in METHODS:
        group = [r for r in rows if r["method"] == method]
        measured = summary["methods"][method]
        require(measured["strict_continuous_acceptance_passed"] == sum(confirmed(r) for r in group), "Pass-count mismatch")
        require(measured["model_calls"] == sum(r["model_calls"] for r in group), "Model calls mismatch")
        require(measured["tokens"] == sum(r["tokens"] for r in group), "Token count mismatch")
        require(measured["weighted_probe_cost"] == sum(r["weighted_probe_cost"] for r in group), "Probe cost mismatch")
    require(load(OUTPUT / "failed-cases.json") == [r for r in rows if not confirmed(r)], "Failure rows were dropped or altered")
    execution = load(BATCH / "execution-result.json")
    require(execution["status"] == "EVALUATOR_FINISHED", "Evaluator did not reach a normal batch finish")
    cleanup, healthy = load(ARTIFACTS / "cleanup-result.json"), load(ARTIFACTS / "final-h00.json")
    require(cleanup["status"] == "STOPPED" and cleanup["remaining_batch_listeners"] == [], "Owned local resources are not stopped")
    require(healthy["passed"] is True and healthy["duration_seconds"] >= 30 and healthy["requests"] >= 30
            and healthy["success"] == healthy["requests"] and healthy["completed_workflows"] >= 10
            and healthy["failed"] == healthy["unknown"] == healthy["unresolved_intents"] == 0, "Final independent H00 did not pass")
    receipt = {"status": "VERIFIED", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Recorded artifacts only; no model, services or fault injections executed by this verifier",
        "terminal_cells": 60, "source_files_verified_in_each_snapshot": len(sources),
        "raw_incidents_verified": 60, "results_sha256": sha(RUN / "results.json"),
        "verification_definition_id": experiment["verification_definition_id"],
        "evaluator_exit_code": execution["exit_code"], "cleanup_status": cleanup["status"],
        "strict_pass_counts": {m: summary["methods"][m]["recovery_confirmed"] for m in METHODS},
        "overall_time_criterion_met": summary["paired_M2v2_vs_M0"]["criterion_met"]}
    save(OUTPUT / "integrity-verification.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
