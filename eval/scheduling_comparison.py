"""Compare declared per-scenario versions while retaining the original F06 failures."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.scheduling_report import summarize


def wrong_blocking_targets(directory, row):
    state = json.loads((Path(directory) / "incidents" / (row["incident_id"] + ".json")).read_text(encoding="utf-8"))
    roots, wrong = set(), 0
    for task in state["tasks"]:
        if task["kind"] == "observe" and task["tool"] == "db.blocking_sessions":
            for fact in task.get("product", {}).get("facts", []):
                if fact["key"] != "blocking_sessions" or not isinstance(fact["value"], list):
                    continue
                edges = [entry for entry in fact["value"] if isinstance(entry, dict) and entry.get("blocking_pids")]
                waiting = {entry["pid"] for entry in edges}
                blocking = {pid for entry in edges for pid in entry["blocking_pids"]}
                roots = blocking - waiting
        if task["kind"] == "act" and task["tool"] == "db.terminate_blocker" and task.get("status") != "not_dispatched":
            wrong += task["args"].get("pid") not in roots
    return wrong


def compare(main, repaired, output):
    main, repaired, output = Path(main), Path(repaired), Path(output)
    first = json.loads((main / "experiment.json").read_text(encoding="utf-8"))
    second = json.loads((repaired / "experiment.json").read_text(encoding="utf-8"))
    for key in ("model", "sampling", "budgets", "held_out_instances", "continuous_workload", "symptom", "methods", "repeats"):
        if first[key] != second[key]:
            raise ValueError(f"comparison protocol differs: {key}")
    if first.get("local_model_artifact") != second.get("local_model_artifact"):
        raise ValueError("model artifact differs")
    if second["scenarios"] != ["F06"]:
        raise ValueError("the repair run must contain only F06")
    for directory in (main, repaired):
        result = summarize(directory)
        if not result["matrix_complete"]:
            raise ValueError(f"incomplete run: {directory.name}")
    originals = json.loads((main / "analysis-rows.json").read_text(encoding="utf-8"))
    repairs = json.loads((repaired / "analysis-rows.json").read_text(encoding="utf-8"))
    selected, historical = [], []
    for directory, rows, label in ((main, originals, "v2"), (repaired, repairs, "F06-v3")):
        for original in rows:
            row = {**original, "source_version": label, "source_run": directory.name,
                   "wrong_blocking_target_calls": wrong_blocking_targets(directory, original)}
            if label == "v2" and row["scenario"] == "F06":
                historical.append(row)
            else:
                selected.append(row)
    keys = {(row["scenario"], row["method"], row["repeat"]) for row in selected}
    expected = len(first["scenarios"]) * len(first["methods"]) * first["repeats"]
    if len(keys) != expected or len(selected) != expected:
        raise ValueError("selected cells are missing or duplicated")
    changes = {path: {"v2": first["source_sha256"].get(path), "F06-v3": second["source_sha256"].get(path)}
               for path in first["source_sha256"] | second["source_sha256"]
               if first["source_sha256"].get(path) != second["source_sha256"].get(path)}
    allowed = {"eval/inject.py", "incident/coordinator/planner.py"}
    output.mkdir(parents=True, exist_ok=True)
    result = {"single_frozen_source_run": False, "selected_cells": len(selected),
        "selected_completed_and_confirmed": sum(row["status"] == "completed" and row["continuous_recovery_confirmed"] for row in selected),
        "selected_diagnosis_correct": sum(row["diagnosis_exact_match"] for row in selected),
        "source_changes": changes, "root_source_changes_within_declared_repair_scope": set(changes) <= allowed,
        "source_by_scenario": {scenario: repaired.name if scenario == "F06" else main.name for scenario in first["scenarios"]},
        "historical_F06_cells": len(historical),
        "historical_F06_completed_and_confirmed": sum(row["status"] == "completed" and row["continuous_recovery_confirmed"] for row in historical),
        "historical_F06_wrong_blocking_target_calls": sum(row["wrong_blocking_target_calls"] for row in historical),
        "repair": "F06 injector uses orders_app rather than administrator; planner follows blocking_pids to roots, preserving SQL guards.",
        "sdk_versions": "v2 used serial native transport with pre-AMQPS-ordering-fix SDK; F06-v3 uses current SDK. See each run's SDK snapshot addendum.",
        "limits": "Per-scenario same-version comparisons; not one frozen 45-cell run. Same fault families with held-out workload/revision instances. Model output and usage are raw; stored context.local_hypotheses may reflect later list additions."}
    (output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in (("primary-rows", selected), ("historical-F06-v2", historical)):
        (output / (name + ".json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        with (output / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    lines = ["# 分场景版本的真实本地模型对比", "",
        f"主对比 {len(selected)} 项，持续恢复 {result['selected_completed_and_confirmed']} 项，"
        f"证据诊断匹配 {result['selected_diagnosis_correct']} 项。原 F06 失败 {len(historical)} 项完整保留。", "",
        "各场景内三方法使用相同版本/参数；此表不是单一源码冻结的45次运行。总耗时包含诊断与域验证，恢复为1rps采样估计。", "",
        "| 场景 | 方法 | 版本 | 恢复/样本 | 探测中位数 | 修改中位数 | 总耗时秒 | 采样恢复秒 | 最早持续确认秒 | token中位数 | 错误阻塞目标调用 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for scenario in first["scenarios"]:
        for method in first["methods"]:
            rows = [row for row in selected if row["scenario"] == scenario and row["method"] == method]
            successful = [row for row in rows if row["status"] == "completed" and row["continuous_recovery_confirmed"]]
            def med(key, values=rows):
                found = [row[key] for row in values if row.get(key) is not None]
                return round(median(found), 3) if found else None
            lines.append(f"| {scenario} | {method} | {rows[0]['source_version']} | {len(successful)}/{len(rows)} | "
                f"{med('probes')} | {med('modifications')} | {med('seconds')} | "
                f"{med('recovery_observed_seconds', successful)} | {med('recovery_confirmed_earliest_seconds', successful)} | "
                f"{med('tokens')} | {sum(row['wrong_blocking_target_calls'] for row in rows)} |")
    lines.extend(["", "修复范围：" + result["repair"], "", result["sdk_versions"], "", result["limits"], ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--repaired-f06", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.main, args.repaired_f06, args.output)
    print(json.dumps({key: result[key] for key in ("selected_cells", "selected_completed_and_confirmed", "selected_diagnosis_correct", "historical_F06_cells")}))
