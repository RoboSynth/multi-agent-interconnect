"""Summarize every recorded cell without discarding failures or rule fallbacks."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


def med(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(median(values), 3) if values else None


def confirmation_time(events, onset):
    relevant = [event for event in events if event["at_monotonic"] >= onset]
    bad = [event for event in relevant if event["outcome"] != "success"]
    if not bad:
        return None
    healthy = [event for event in relevant if event["outcome"] == "success"
               and event["at_monotonic"] > bad[-1]["at_monotonic"]]
    completed = 0
    for index, event in enumerate(healthy):
        completed += event["completed_workflows"]
        span = event["at_monotonic"] - healthy[0]["at_monotonic"] + 1
        if index + 1 >= 30 and span >= 30 and completed >= 10 and event["completed_workflows"]:
            return round(event["at_monotonic"] + 1 - onset, 3)
    return None


def summarize(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    rows = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    m1_definitions = {row.get("method_definition_id", manifest.get("method_definition_ids", {}).get("M1", "observation-only-v1"))
                      for row in rows if row["method"] == "M1"}
    if len(m1_definitions) > 1:
        raise ValueError("M1 method definitions differ; report these cohorts separately")
    m1_scope = ("M1 freely selects observations, guarded actions and verification; no rule fallback."
                if m1_definitions == {"free-tools-v1"} else
                "Historical M1 freely selects observations and shares evidence-based repair rules.")
    # Keep raw rows immutable. Derive the earliest qualifying prefix rather than
    # treating the later observer-stop time as the recovery confirmation time.
    injections = []
    process_log = directory / "private/inject-process.jsonl"
    if process_log.exists():
        for line in process_log.read_text(encoding="utf-8").splitlines():
            process = json.loads(line)
            if process["action"] == "apply" and process["returncode"] == 0:
                injections.append((process["scenario"], json.loads(process["stdout"])))
    for index, row in enumerate(rows):
        row["recovery_confirmed_earliest_seconds"] = None
        requests = directory / "workloads" / f"{row['scenario']}-{row['method']}-{row['repeat']}" / "requests.jsonl"
        if row["scenario"] != "H00" and index < len(injections) and injections[index][0] == row["scenario"] and requests.exists():
            events = [json.loads(line) for line in requests.read_text(encoding="utf-8").splitlines()]
            row["recovery_confirmed_earliest_seconds"] = confirmation_time(events, injections[index][1]["started_monotonic"])
    (directory / "analysis-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    expected = len(manifest["scenarios"]) * len(manifest["methods"]) * manifest["repeats"]
    groups, controls = [], []
    fault_rows = [row for row in rows if row["scenario"] != "H00"]
    control_rows = [row for row in rows if row["scenario"] == "H00"]
    def passed_control(row):
        # Legacy rows without attempted-action accounting cannot prove zero actions.
        return (row["status"] == "completed" and row.get("control_passed") is True
                and row.get("modification_attempts") == 0)
    for scenario in manifest["scenarios"]:
        for method in manifest["methods"]:
            selected = [row for row in rows if row["scenario"] == scenario and row["method"] == method]
            if scenario == "H00":
                attempts = [row.get("modification_attempts") for row in selected]
                controls.append({"scenario": scenario, "method": method, "n": len(selected),
                    "control_passed": sum(passed_control(row) for row in selected),
                    "modification_attempts": sum(attempts) if all(type(value) is int for value in attempts) else None,
                    "median_control_observation_seconds": med(selected, "control_observation_seconds"),
                    "median_tokens": med(selected, "tokens")})
                continue
            successful = [row for row in selected if row["status"] == "completed" and row["continuous_recovery_confirmed"]]
            groups.append({"scenario": scenario, "method": method, "n": len(selected),
                "completed_and_confirmed": len(successful),
                "diagnosis_correct": sum(bool(row["diagnosis_exact_match"]) for row in selected),
                "model_sources": dict(Counter(row["model_source"] for row in selected)),
                "model_fallbacks": sum(row["model_fallbacks"] for row in selected),
                "model_failures": sum(row["model_failures"] for row in selected),
                "unnecessary_high_privilege_calls": sum(row["unnecessary_high_privilege_calls"] for row in selected),
                "median_probes": med(selected, "probes"), "median_modifications": med(selected, "modifications"),
                "median_coordination_and_verification_seconds": med(selected, "seconds"),
                "median_success_recovery_observed_seconds": med(successful, "recovery_observed_seconds"),
                "median_success_recovery_confirmed_earliest_seconds": med(successful, "recovery_confirmed_earliest_seconds"),
                "median_tokens": med(selected, "tokens"), "median_model_calls": med(selected, "model_calls"),
                "median_approval_wait_seconds": med(selected, "approval_wait_seconds")})
    complete = len(rows) == expected and all(group["n"] == manifest["repeats"] for group in groups + controls)
    recovered = sum(row["status"] == "completed" and row["continuous_recovery_confirmed"] for row in fault_rows)
    platform = manifest.get("transport") == "wutong-amqps"
    result = {"expected_cells": expected, "recorded_cells": len(rows), "matrix_complete": complete,
        "completed_and_confirmed": recovered,
        "fault_recorded_cells": len(fault_rows),
        "fault_expected_cells": sum(scenario != "H00" for scenario in manifest["scenarios"]) * len(manifest["methods"]) * manifest["repeats"],
        "recovery_rate": recovered / len(fault_rows) if fault_rows else None,
        "healthy_control_recorded_cells": len(control_rows),
        "healthy_control_passed": sum(passed_control(row) for row in control_rows),
        "healthy_control_groups": controls,
        "diagnosis_correct": sum(bool(row["diagnosis_exact_match"]) for row in fault_rows),
        "M1_method_definition_ids": sorted(m1_definitions),
        "token_usage_complete": all(row["token_usage_complete"] for row in rows), "groups": groups,
        "limits": ["Wutong AMQPS transport; resource and source scope remain those recorded in experiment.json." if platform else
            "Local native-process/AIP-stdio evidence; not formal platform AMQPS/ADP.",
            m1_scope,
            "Recovery time is a 1rps observation estimate; total coordination time includes 30s domain verification.",
            "Raw recovery_confirmed_seconds is the later observer-stop time; analysis-rows derives earliest 30s/10-flow confirmation from original requests and injection timestamps.",
            "Held-out instances vary workload seeds and resource revisions/PIDs within the same fault families.",
            "H00 is a separate healthy control: 30 seconds, 10 workflows, no failed/unknown/pending requests or attempted resource actions. It is excluded from recovery rates; legacy H00 rows without this proof are not counted as passed.",
            "Recovery medians use only completed, continuously confirmed cells; failure counts and every raw row remain visible."]}
    (directory / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    text = ["# 梧桐传输调度实验" if platform else "# 本地模型调度实验", "",
        f"记录 {len(rows)}/{expected} 项；协调完成且持续业务恢复 {result['completed_and_confirmed']} 项；"
        f"证据诊断精确匹配 {result['diagnosis_correct']} 项。", "",
        f"故障恢复 {recovered}/{len(fault_rows)}；健康对照 {result['healthy_control_passed']}/{len(control_rows)}，健康对照不计入恢复分母。", "",
        "耗时是协调与域验证总耗时；恢复为 1 rps 采样估计。表格保留失败计数，未完成矩阵不作完整实验结论。", "",
        "| 场景 | 方法 | 完成/记录 | 诊断正确 | 探测中位数 | 总耗时秒 | 成功恢复估计秒 | token中位数 | 回退/模型失败 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for group in groups:
        text.append(f"| {group['scenario']} | {group['method']} | {group['completed_and_confirmed']}/{group['n']} | "
            f"{group['diagnosis_correct']} | {group['median_probes']} | {group['median_coordination_and_verification_seconds']} | "
            f"{group['median_success_recovery_observed_seconds']} | {group['median_tokens']} | "
            f"{group['model_fallbacks']}/{group['model_failures']} |")
    if controls:
        text.extend(["", "健康对照（H00）", "",
            "| 方法 | 通过/记录 | 资源修改尝试 | 业务观察秒中位数 | token中位数 |",
            "| --- | --- | --- | --- | --- |"])
        for group in controls:
            text.append(f"| {group['method']} | {group['control_passed']}/{group['n']} | "
                f"{group['modification_attempts']} | {group['median_control_observation_seconds']} | {group['median_tokens']} |")
    text.extend(["", *["- " + limit for limit in result["limits"]], ""])
    (directory / "report.md").write_text("\n".join(text), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = summarize(args.directory)
    print(json.dumps({key: result[key] for key in ("expected_cells", "recorded_cells", "matrix_complete", "completed_and_confirmed", "diagnosis_correct")}))
