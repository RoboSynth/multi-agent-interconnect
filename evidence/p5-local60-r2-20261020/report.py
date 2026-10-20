"""Summarize this frozen 60-cell run, retaining failures and measurement limits."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics

ROOT = Path(os.environ.get("P5_LOCAL60_REPOSITORY", Path(__file__).resolve().parents[2]))
BATCH = ROOT / "evidence/p5-local60-r2-20261020"
ARTIFACTS = Path(os.environ.get("P5_LOCAL60_ARTIFACTS", ROOT.parent / "incident-pilot/artifacts/p5-local60-r2-20261020"))
RUN = BATCH / "matrix"
OUTPUT = ARTIFACTS / "publication"
METHODS = ["MR", "M0", "M1", "M2v2"]
SCENARIOS = ["F01", "F02", "F06", "F07", "F10"]
VERIFICATION = "carried-intents-then-fresh-window-v2"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def median(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(statistics.median(values), 6) if values else None


def confirmed(row):
    return row["status"] == "completed" and row["continuous_recovery_confirmed"] is True


def validate_inputs():
    rows, experiment = load(RUN / "results.json"), load(RUN / "experiment.json")
    expected = {(s, m, r) for s in SCENARIOS for m in METHODS for r in range(1, 4)}
    cells = [(r["scenario"], r["method"], r["repeat"]) for r in rows]
    if len(rows) != 60 or len(set(cells)) != 60 or set(cells) != expected:
        raise ValueError("Report requires the 60 unique planned terminal cells")
    if len({r["incident_id"] for r in rows}) != 60:
        raise ValueError("Each planned cell must retain a distinct raw incident")
    order = [(s, m, repeat + 1) for s in SCENARIOS for repeat in range(3)
             for m in METHODS[repeat:] + METHODS[:repeat]]
    if cells != order:
        raise ValueError("Recorded cells differ from the frozen method rotation")
    if any(r["workload_seed"] != [101, 202, 303][r["repeat"] - 1]
           or r["precondition_pool_rebuilds"] != r["repeat"] - 1 for r in rows):
        raise ValueError("Seed or connection-pool precondition differs from plan")
    if experiment.get("verification_definition_id") != VERIFICATION:
        raise ValueError("Unexpected verification definition")
    if experiment["method_definition_ids"]["M2v2"] != "evidence-ranked-per-incident-v5" \
            or experiment["method_definition_ids"]["MR"] != "symptom-runbook-guarded-v3":
        raise ValueError("Unexpected method definition")
    if experiment["transport"] != "local-aip-stdio" or experiment["resource_backend"] != "native":
        raise ValueError("Only this local/native batch can be summarized here")
    return rows, experiment


def main():
    rows, experiment = validate_inputs()
    incidents = {r["incident_id"]: load(RUN / "incidents" / (r["incident_id"] + ".json")) for r in rows}
    methods = {}
    for method in METHODS:
        group = [r for r in rows if r["method"] == method]
        good = [r for r in group if confirmed(r)]
        tasks = [t for r in group for t in incidents[r["incident_id"]]["tasks"]]
        acts = [t for t in tasks if t["kind"] == "act"]
        applied = [(t.get("product") or {}).get("operation") or {} for t in acts]
        applied = [op for op in applied if op.get("state") == "applied"]
        comparable = [op for op in applied if all(k in op and op[k] is not None
                      and op[k] != {"value": None} for k in ["before", "after"])]
        requests = [q for r in group for q in incidents[r["incident_id"]].get("model_requests", [])]
        carried = [f["value"] for t in tasks if t["tool"] == "incident.verification"
                   for f in (t.get("product") or {}).get("facts", [])
                   if f["key"] == "carried_symptom_intents" and f.get("value") is not None]
        methods[method] = {
            "cells": len(group), "strict_continuous_acceptance_passed": len(good),
            "recovery_confirmed": len(good), "unconfirmed": len(group) - len(good),
            "median_seconds_all_terminal": median(group, "seconds"),
            "median_seconds_confirmed_only": median(good, "seconds"),
            "median_recovery_observed_seconds_confirmed_only": median(good, "recovery_observed_seconds"),
            "fault_observed": sum(r["fault_observed"] is True for r in group),
            "probes": sum(r["probes"] for r in group),
            "cross_domain_observation_calls": sum(r["cross_organization_calls"] for r in group),
            "median_declared_resource_domains_contacted": median(group, "resource_organizations_contacted"),
            "sensitive_blocking_session_observations": sum(r["sensitive_observations"] for r in group),
            "weighted_probe_cost": sum(r["weighted_probe_cost"] for r in group),
            "action_attempts": sum(r["modification_attempts"] for r in group),
            "successful_action_tasks": sum(r["modifications"] for r in group),
            "unrelated_high_privilege_attempts": sum(r["unnecessary_high_privilege_calls"] for r in group),
            "unrelated_successful_action_tasks": sum(r["unnecessary_modifications"] for r in group),
            "rejected_actions": sum(r["rejected_actions"] for r in group),
            "skipped_runbook_actions": sum(r["runbook_skipped_actions"] for r in group),
            "action_operation_states": dict(Counter(((t.get("product") or {}).get("operation") or {}).get("state", "not_present") for t in acts)),
            "applied_receipts_equal_before_after": sum(op["before"] == op["after"] for op in comparable),
            "applied_receipts_unequal_before_after": sum(op["before"] != op["after"] for op in comparable),
            "applied_receipts_without_comparable_before_after": len(applied) - len(comparable),
            "repeated_action_tool_attempts_within_incident": sum(sum(n - 1 for n in Counter(
                t["tool"] for t in incidents[r["incident_id"]]["tasks"] if t["kind"] == "act").values()) for r in group),
            "model_calls": sum(r["model_calls"] for r in group),
            "min_model_calls_per_incident": min(r["model_calls"] for r in group),
            "max_model_calls_per_incident": max(r["model_calls"] for r in group),
            "model_failures": sum(r["model_failures"] for r in group),
            "disclosed_rule_fallbacks": sum(r["model_fallbacks"] for r in group),
            "model_request_wall_seconds_sum": round(sum(q.get("seconds", 0) or 0 for q in requests), 6),
            "model_request_wall_seconds_median": median(requests, "seconds"),
            "tokens": sum(r["tokens"] for r in group),
            "token_usage_complete_in_all_cells": all(r.get("token_usage_complete") is True for r in group),
            "diagnosis_exact_matches": sum(r["diagnosis_exact_match"] is True for r in group),
            "verification_tasks_with_carried_intents": len(carried),
            "verification_tasks_with_unresolved_carried_intents": sum(c["unresolved_intents"] != 0 for c in carried),
        }
    bycell = {(r["scenario"], r["method"], r["repeat"]): r for r in rows}
    pairs = []
    for scenario in SCENARIOS:
        for repeat in range(1, 4):
            fixed, ranked = bycell[scenario, "M0", repeat], bycell[scenario, "M2v2", repeat]
            both = confirmed(fixed) and confirmed(ranked)
            pairs.append({"scenario": scenario, "repeat": repeat, "both_confirmed": both,
                "M0_seconds": fixed["seconds"], "M2v2_seconds": ranked["seconds"],
                "elapsed_ratio": ranked["seconds"] / fixed["seconds"] if both and fixed["seconds"] else None,
                "M0_recovery_observed_seconds": fixed["recovery_observed_seconds"],
                "M2v2_recovery_observed_seconds": ranked["recovery_observed_seconds"],
                "recovery_observed_ratio": ranked["recovery_observed_seconds"] / fixed["recovery_observed_seconds"]
                    if both and fixed["recovery_observed_seconds"] and ranked["recovery_observed_seconds"] is not None else None,
                "M0_weighted_probe_cost": fixed["weighted_probe_cost"], "M2v2_weighted_probe_cost": ranked["weighted_probe_cost"],
                "M0_sensitive_observations": fixed["sensitive_observations"], "M2v2_sensitive_observations": ranked["sensitive_observations"]})
    goodpairs = [p for p in pairs if p["both_confirmed"]]
    ratio = median(goodpairs, "elapsed_ratio")
    allpairs = len(goodpairs) == 15
    ratio_of_medians = (round(methods["M2v2"]["median_seconds_confirmed_only"] /
                              methods["M0"]["median_seconds_confirmed_only"], 6) if allpairs else None)
    actual_time_met = allpairs and ratio <= 1.3
    supplementary_time_met = allpairs and ratio_of_medians <= 1.3
    failed = [r for r in rows if not confirmed(r)]
    summary = {"status": "ALL_60_TERMINAL_CELLS_RECORDED", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local-aip-stdio/native; no Wutong identities or paid API", "terminal_cells": len(rows),
        "primary_metric": "Coordinator completed and independent continuous healthy confirmation; not physical mutation success rate",
        "verification_definition_id": VERIFICATION,
        "verification": experiment["verification"], "method_definition_ids": experiment["method_definition_ids"],
        "methods": methods,
        "paired_M2v2_vs_M0": {"confirmed_pairs": len(goodpairs), "median_paired_elapsed_ratio": ratio,
            "median_paired_recovery_observed_ratio": median(goodpairs, "recovery_observed_ratio"),
            "ratio_of_method_medians": ratio_of_medians, "criterion": 1.3,
            "criterion_met": actual_time_met,
            "criterion_contract": "All 15 pairs confirmed and median of per-pair elapsed ratios <= 1.3",
            "ratio_of_method_medians_le_1_3": supplementary_time_met,
            "M0_weighted_probe_cost_on_confirmed_pairs": sum(p["M0_weighted_probe_cost"] for p in goodpairs),
            "M2v2_weighted_probe_cost_on_confirmed_pairs": sum(p["M2v2_weighted_probe_cost"] for p in goodpairs),
            "M0_sensitive_observations_on_confirmed_pairs": sum(p["M0_sensitive_observations"] for p in goodpairs),
            "M2v2_sensitive_observations_on_confirmed_pairs": sum(p["M2v2_sensitive_observations"] for p in goodpairs)},
        "acceptance": {"M2v2_all_15_strictly_pass": methods["M2v2"]["recovery_confirmed"] == 15,
            "M0_all_15_strictly_pass": methods["M0"]["recovery_confirmed"] == 15,
            "M2v2_zero_unrelated_high_privilege_attempts": methods["M2v2"]["unrelated_high_privilege_attempts"] == 0,
            "M2v2_each_cell_1_to_2_model_calls": all(1 <= r["model_calls"] <= 2 for r in rows if r["method"] == "M2v2"),
            "all_15_pairs_and_median_elapsed_ratio_le_1_3": actual_time_met},
        "failure_classes": dict(Counter(r["error"].split(":", 1)[0] or r["status"] for r in failed)),
        "attempt_accounting": {"unique_planned_cells": 60, "terminal_cells": 60,
            "cost_totals_scope": "Recorded 60 terminal cells; any unrecorded interrupted attempts excluded",
            "extra_attempts_inferred": False},
        "limitations": ["Elapsed seconds include the final verification window; first-business-recovery time is reported separately",
            "Verification v2 resolves carried intents using their original keys before a fresh scoring window; earlier v1 results are not equivalent measurements",
            "Successful action tasks and before/after receipt comparisons do not prove distinct physical mutations",
            "Unrelated high-privilege counts are attempted tools including rejected attempts, not actual resource changes",
            "Observation domains are declared boundaries, not verified separate legal organizations",
            "All-cell costs include early failures; confirmed pairs are reported separately",
            "Five existing fault families with varied instances; no unseen-family generalization claim",
            "One local small model and one Windows machine; no cloud scheduling experiment in this batch"]}
    summary["acceptance"]["all_primary_criteria_met"] = all(summary["acceptance"].values())
    save(OUTPUT / "summary.json", summary)
    save(OUTPUT / "results.json", rows)
    save(OUTPUT / "paired-M2v2-M0.json", pairs)
    save(OUTPUT / "failed-cases.json", failed)
    for name, values in [("results.csv", rows), ("paired-M2v2-M0.csv", pairs)]:
        with (OUTPUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=values[0].keys())
            writer.writeheader()
            writer.writerows(values)
    bindings = {"source_sha256": experiment["source_sha256"],
        "method_definition_ids": experiment["method_definition_ids"], "verification_definition_id": VERIFICATION,
        "sampling": experiment["sampling"], "budgets": experiment["budgets"],
        "held_out_instances": experiment["held_out_instances"], "local_model_artifact": experiment.get("local_model_artifact"),
        "local_model_server": experiment.get("local_model_server"),
        "execution_intent_sha256": sha(BATCH / "execution-intent.json"), "results_sha256": sha(RUN / "results.json"),
        "experiment_sha256": sha(RUN / "experiment.json"),
        "raw_incident_sha256": {r["incident_id"]: sha(RUN / "incidents" / (r["incident_id"] + ".json")) for r in rows}}
    save(OUTPUT / "source-bindings.json", bindings)
    lines = ["# P5 第二批本地 60 格实际结果", "",
        "5 场景 × 4 方法 × 3 重复。表格只统计本批记录的 60 个唯一终态，原失败保留。", "",
        f"验证定义：`{VERIFICATION}`。先用原编号收敛快速检查遗留请求，再计分全新的 30 秒 / 10 完整流程窗口。两段均通过才确认恢复。", "",
        "| 方法 | 严格持续验收 | 已通过例中位耗时（秒） | 业务首次恢复中位（秒） | 观察调用 | 敏感观察 | 加权成本 | 无关高权限尝试 | 模型调用 | token |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for method in METHODS:
        m = methods[method]
        lines.append(f"| {method} | {m['recovery_confirmed']}/15 | {m['median_seconds_confirmed_only']} | {m['median_recovery_observed_seconds_confirmed_only']} | {m['probes']} | {m['sensitive_blocking_session_observations']} | {m['weighted_probe_cost']} | {m['unrelated_high_privilege_attempts']} | {m['model_calls']} | {m['tokens']} |")
    lines += ["", f"双方均通过 {len(goodpairs)}/15 个配对；逐配对耗时比中位数 {ratio}，两方法中位耗时比 {ratio_of_medians}。全部 15 对通过且前者 ≤1.3：{actual_time_met}。",
        "", f"业务首次恢复时间比中位数 {summary['paired_M2v2_vs_M0']['median_paired_recovery_observed_ratio']}，单独列出，避免固定验证时长掩盖等待。",
        "", f"M2v2 全部预定验收条件：{summary['acceptance']['all_primary_criteria_met']}。未通过格 {len(failed)} 个，见 failed-cases.json 及 failed-incidents/ 原始事故。",
        "", "成功动作任务数、无关动作尝试数和回执前后值差异分别统计；这些都不能直接当作实际资源修改次数。加权成本包括失败格，已恢复配对另列。",
        "", "本批同时改变了调度方法和最终验收定义，与上一批的通过率和耗时不构成只改算法的因果对照。两批原始结果均保留。",
        "", "本批只覆盖既有故障家族及不同种子，未验证新故障家族泛化、云端性能或其他团队使用。"]
    (OUTPUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "pass_counts": {m: methods[m]["recovery_confirmed"] for m in METHODS},
                      "acceptance": summary["acceptance"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
