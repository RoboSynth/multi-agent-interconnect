"""Audit frozen scheduling cells without rewriting their results or prompts.

Applied products are ledger reports, not a count of physical resource changes.
Task wall time includes transport/participant work; broker queue time is unknown.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scheduling_report import matrix_integrity
from incident.coordinator.planner import EvidencePlanner, PlanNode, PROBES, observation_cost

EXPECTED_ACTIONS = {
    "F01": {"ops.restart"}, "F02": {"ops.route_rollback"},
    "F06": {"db.terminate_blocker"},
    "F07": {"db.restore_writes", "application.pool_rebuild"},
    "F10": {"ops.route_rollback", "db.restore_writes", "application.pool_rebuild"},
}
HIGH_TOOLS = {"ops.restart", "db.restore_writes", "db.terminate_blocker"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def approval_seconds(state):
    return sum((datetime.fromisoformat(a["decided_at"]) - datetime.fromisoformat(a["requested_at"])).total_seconds()
               for a in state.get("approvals", []) if a.get("decided_at"))


def deterministic_requests(state):
    """Replay recorded M2 choices only to locate avoidable generation positions.

    These seconds belong to the old timeline. They are not a new-method runtime
    prediction: skipping a call may change later model outputs and task order.
    """
    steps = [task for task in state["tasks"] if task["kind"] != "act"]
    requests = state.get("model_requests", [])
    if len(steps) != len(requests) or any(request.get("status") != "validated" for request in requests):
        return {"alignment_complete": False, "count": None, "recorded_seconds": None, "reasons": {}}
    planner = EvidencePlanner()
    request_index = 0
    reasons = Counter()
    seconds = 0
    for task in state["tasks"]:
        if task["kind"] == "act":
            if task["status"] == "ok":
                planner.action_completed(PlanNode("replay", task["tool"], "act", "replay", "recorded action"))
            continue
        request = requests[request_index]
        request_index += 1
        available = {tool["tool"] for tool in request["context"]["tools"]}
        entry = {"ops.containers", "ops.route_status"} & available
        eligible = entry if entry - planner.observed else available
        required = planner.required_probe(eligible)
        choices = [probe for probe in PROBES if probe.tool in eligible and probe.tool not in planner.observed]
        reason = "required_probe" if required else "single_probe" if len(choices) == 1 else "verification" if not choices else None
        if reason is not None:
            reasons[reason] += 1
            seconds += request["seconds"]
        if task["kind"] == "observe" and task["status"] == "ok":
            planner.update(task["tool"], task["product"]["facts"])
    return {"alignment_complete": True, "count": sum(reasons.values()),
            "recorded_seconds": round(seconds, 3), "reasons": dict(reasons)}


def audit_cell(row, state):
    tasks = state["tasks"]
    expected = EXPECTED_ACTIONS[row["scenario"]]
    actions = [task for task in tasks if task["kind"] == "act"]
    projections = []
    for index, task in enumerate(tasks):
        operation = task.get("product", {}).get("operation", {}).get("state")
        projections.append({"index": index, "kind": task["kind"], "tool": task["tool"],
            "status": task["status"], "operation_state": operation, "elapsed_ms": task.get("elapsed_ms"),
            "cause_related_action": task["tool"] in expected if task["kind"] == "act" else None,
            "high_risk_action": task["kind"] == "act" and task["tool"] in HIGH_TOOLS})
    task_times = {kind: sum(task.get("elapsed_ms", 0) / 1000 for task in tasks if task["kind"] == kind)
                  for kind in ("observe", "act", "verify")}
    model_time = sum(request.get("seconds", 0) for request in state.get("model_requests", []))
    wait = approval_seconds(state)
    business_duration = sum(fact["value"]["duration_seconds"] for task in tasks if task["kind"] == "verify"
        for fact in task.get("product", {}).get("facts", []) if fact["key"] == "order_observation")
    unrelated = [task for task in actions if task["tool"] not in expected]
    def operation_count(selected, status):
        return sum(task.get("product", {}).get("operation", {}).get("state") == status for task in selected)
    return {"scenario": row["scenario"], "method": row["method"], "repeat": row["repeat"],
        "status": row["status"], "recovered": row["status"] == "completed" and row["continuous_recovery_confirmed"],
        "diagnosis_correct": bool(row["diagnosis_exact_match"]),
        "observations": sum(task["kind"] == "observe" for task in tasks),
        "observation_cost": observation_cost(tasks),
        "action_attempts": len(actions), "successful_action_tasks": sum(task["status"] == "ok" for task in actions),
        "applied_products": operation_count(actions, "applied"),
        "idempotent_skip_products": operation_count(actions, "skipped_already_applied"),
        "high_risk_calls": sum(task["tool"] in HIGH_TOOLS and task["status"] != "not_dispatched" for task in actions),
        "unrelated_action_attempts": len(unrelated), "unrelated_applied_products": operation_count(unrelated, "applied"),
        "unrelated_idempotent_skips": operation_count(unrelated, "skipped_already_applied"),
        "physical_side_effects": None,
        "seconds": row["seconds"], "tokens": row["tokens"], "model_calls": row["model_calls"],
        "token_usage_complete": row["token_usage_complete"],
        "timing": {"model_request_wall_seconds": round(model_time, 3),
            "observation_task_wall_seconds": round(task_times["observe"], 3),
            "action_task_wall_excluding_approval_seconds": round(task_times["act"] - wait, 3),
            "approval_wait_seconds": round(wait, 3), "verification_task_wall_seconds": round(task_times["verify"], 3),
            "verification_business_window_seconds": round(business_duration, 3),
            "verification_other_wall_seconds": round(task_times["verify"] - business_duration, 3),
            "unattributed_coordinator_seconds": round(row["seconds"] - model_time - sum(task_times.values()), 3),
            "model_inference_only_seconds": None, "broker_queue_seconds": None,
            "observation_network_rtt_seconds": None},
        "old_timeline_deterministic_requests": deterministic_requests(state) if row["method"] == "M2" else None,
        "tasks": projections}


def summarize_cells(cells):
    totals = ("observations", "action_attempts", "successful_action_tasks", "applied_products", "idempotent_skip_products",
        "high_risk_calls", "unrelated_action_attempts", "unrelated_applied_products", "unrelated_idempotent_skips", "tokens", "model_calls")
    output = []
    for method in dict.fromkeys(cell["method"] for cell in cells):
        selected = [cell for cell in cells if cell["method"] == method]
        output.append({"method": method, "n": len(selected), "recovered": sum(cell["recovered"] for cell in selected),
            "diagnosis_correct": sum(cell["diagnosis_correct"] for cell in selected),
            **{key: sum(cell[key] for cell in selected) for key in totals},
            "median_seconds": round(median(cell["seconds"] for cell in selected), 3),
            "total_seconds": round(sum(cell["seconds"] for cell in selected), 3),
            "timing_seconds": {key: round(sum(cell["timing"][key] for cell in selected), 3)
                if all(cell["timing"][key] is not None for cell in selected) else None for key in selected[0]["timing"]}})
    return output


def plot_audit(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none",
                         "axes.spines.top": False, "axes.spines.right": False})
    groups = summary["methods"]
    methods = [group["method"] for group in groups]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    parts = [("model_request_wall_seconds", "Model request wall", "#c87022"),
        ("observation_task_wall_seconds", "Observations", "#2878b5"),
        ("action_task_wall_excluding_approval_seconds", "Actions (excl. approval)", "#68727d"),
        ("approval_wait_seconds", "Approval wait", "#c897cd"),
        ("verification_task_wall_seconds", "Verification", "#278064"),
        ("unattributed_coordinator_seconds", "Unattributed", "#d6dadd")]
    bottom = [0] * len(groups)
    for key, label, color in parts:
        values = [group["timing_seconds"][key] / group["n"] for group in groups]
        axes[0].bar(methods, values, bottom=bottom, label=label, color=color)
        bottom = [old + new for old, new in zip(bottom, values)]
    axes[0].set_ylabel("Mean coordinator wall time per cell (s)")
    axes[0].set_title("All 45 frozen cells; failures retained", loc="left")
    axes[0].legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    width = .23
    for offset, key, title in [(-1, "observations", "Observations"), (0, "unrelated_action_attempts", "Unrelated action attempts"),
                              (1, "unrelated_applied_products", "Unrelated applied products")]:
        axes[1].bar([index + offset * width for index in range(len(groups))], [group[key] for group in groups], width, label=title)
    axes[1].set_xticks(range(len(methods)), methods)
    axes[1].set_ylabel("Recorded calls/products over 15 cells")
    axes[1].set_title("Applied product ≠ physical side effect", loc="left")
    axes[1].legend(fontsize=8, frameon=False)
    for axis in axes:
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    fig.text(.04, .025, "NEW7 Wutong AMQPS E3, 2026-10-18. Queue / network RTT / pure inference durations are not separately recorded.\n"
        "Verification includes an independent 30-second business window. No new method or held-out result is shown.", fontsize=8)
    fig.subplots_adjust(left=.07, right=.98, bottom=.21, top=.88, wspace=.28)
    for suffix in ("png", "svg"):
        fig.savefig(output / ("offline-comparison." + suffix), dpi=180, facecolor="white")
    plt.close(fig)


def audit(directory, output, *, plot=True):
    directory, output = Path(directory), Path(output)
    if directory.resolve() == output.resolve() or directory.resolve() in output.resolve().parents:
        raise ValueError("audit output must be outside the frozen source run")
    manifest = json.loads((directory / "experiment.json").read_bytes())
    rows = json.loads((directory / "results.json").read_bytes())
    integrity = matrix_integrity(rows, manifest)
    if not integrity["complete"] or len(rows) != 45:
        raise ValueError("expected the complete frozen 45-cell E3 matrix")
    cells, sources = [], []
    for row in rows:
        incident_path = directory / "incidents" / (row["incident_id"] + ".json")
        state = json.loads(incident_path.read_bytes())
        if state["id"] != row["incident_id"] or state["status"] != row["status"]:
            raise ValueError("incident/result binding differs")
        requests = state.get("model_requests", [])
        if (len(requests) != row["model_calls"] or state["tokens"] != row["tokens"]
                or (row["token_usage_complete"] and sum(request.get("usage", {}).get("total_tokens", 0)
                                                       for request in requests) != row["tokens"])):
            raise ValueError("frozen model counts or token usage differ")
        cell = audit_cell(row, state)
        if (cell["observations"], cell["successful_action_tasks"]) != (row["probes"], row["modifications"]):
            raise ValueError("frozen task counts differ")
        cell["incident_sha256"] = sha(incident_path)
        cells.append(cell)
        sources.append({"path": incident_path.relative_to(directory).as_posix(), "sha256": cell["incident_sha256"]})
    methods = summarize_cells(cells)
    retrospective = [cell["old_timeline_deterministic_requests"] for cell in cells if cell["method"] == "M2"]
    aligned = all(item["alignment_complete"] for item in retrospective)
    result = {"schema_version": "scheduling-offline-audit/1", "recorded_cells": len(cells), "matrix_integrity": integrity,
        "source_results_sha256": sha(directory / "results.json"), "source_experiment_sha256": sha(directory / "experiment.json"),
        "methods": methods, "source_incidents": sources,
        "old_M2_timeline_deterministic_requests": {"aligned_cells": sum(item["alignment_complete"] for item in retrospective),
            "count": sum(item["count"] for item in retrospective) if aligned else None,
            "recorded_seconds": round(sum(item["recorded_seconds"] for item in retrospective), 3) if aligned else None,
            "reasons": dict(sum((Counter(item["reasons"]) for item in retrospective), Counter()))},
        "limits": ["No new model, platform, resource or fault execution.",
            "Cause-related actions use evaluator ground truth only in offline analysis, never in coordinator inputs.",
            "Applied products are operation ledger reports; physical side-effect counts remain unknown.",
            "Idempotent skips are retained separately and never counted as physical modifications.",
            "No separate broker queue, pure inference or observation network RTT telemetry exists.",
            "M0 shares EvidencePlanner repairs with M2; F01+F07 is not guaranteed to defeat M0.",
            "Retrospective avoidable model seconds are not measured M2v2 savings."]}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("offline-summary.json", result), ("offline-cells.json", cells)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flat = [{key: value for key, value in cell.items() if key not in {"timing", "tasks", "old_timeline_deterministic_requests"}} for cell in cells]
    with (output / "offline-cells.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=flat[0])
        writer.writeheader()
        writer.writerows(flat)
    lines = ["# G4：冻结 E3 的离线动作与耗时核对", "", "保留原 45 格及全部失败；本次没有运行新故障、平台或模型。", "",
        "| 方法 | 恢复/15 | 诊断正确/15 | 观察总数 | act 尝试/ok | high 调用 | 无关 act 尝试/applied | 幂等跳过 | 耗时中位秒 | token 总数 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for group in methods:
        lines.append(f"| {group['method']} | {group['recovered']} | {group['diagnosis_correct']} | {group['observations']} | "
            f"{group['action_attempts']}/{group['successful_action_tasks']} | {group['high_risk_calls']} | "
            f"{group['unrelated_action_attempts']}/{group['unrelated_applied_products']} | {group['idempotent_skip_products']} | "
            f"{group['median_seconds']} | {group['tokens']} |")
    by_method = {group["method"]: group for group in methods}
    m0, m2 = by_method["M0"], by_method["M2"]
    m2_times = m2["timing_seconds"]
    delta = m0["observations"] - m2["observations"]
    lines += ["", "applied 是账本返回，不代表已证明实际产生一次物理副作用；幂等跳过单列。high 调用包含重放和被拒的请求。", "",
        f"M0/M2 的无关 act 尝试分别为 {m0['unrelated_action_attempts']}/{m2['unrelated_action_attempts']}，无关 applied 返回分别为 "
        f"{m0['unrelated_applied_products']}/{m2['unrelated_applied_products']}，未显示 M2 减少无关修改。M2 观察 {m2['observations']} 次、M0 {m0['observations']} 次，"
        f"减少 {delta} 次（{100 * delta / m0['observations']:.1f}%），但两者都恢复 {m2['recovered']}/15、{m0['recovered']}/15，M2 耗时更长。", "",
        f"M2 总耗时 {m2['total_seconds']:.3f} 秒，其中模型请求 {m2_times['model_request_wall_seconds']:.3f} 秒"
        f"（{100 * m2_times['model_request_wall_seconds'] / m2['total_seconds']:.1f}%）、观察任务 {m2_times['observation_task_wall_seconds']:.3f} 秒、"
        f"act {m2_times['action_task_wall_excluding_approval_seconds'] + m2_times['approval_wait_seconds']:.3f} 秒（含审批）、"
        f"独立验证任务 {m2_times['verification_task_wall_seconds']:.3f} 秒。模型请求是最大可优化项；其内部推理/排队不可分，验证任务中实际业务窗口与其他开销已在逐行 timing 中分列。", "",
        f"按原任务顺序回放，{result['old_M2_timeline_deterministic_requests']['count']} 次模型请求位于必选/唯一个观察或最终验证位置，"
        f"原时间线上合计 {result['old_M2_timeline_deterministic_requests']['recorded_seconds']} 秒。新 M2v2 只跳过这些无排名选择的位置；"
        "该数值不能当作新版节省耗时，后续模型输出和任务顺序可能改变，必须真实配对复验。", "",
        "M0 只固定观察顺序，修复仍继承同一个 EvidencePlanner；F01+F07 不会自动超出它的修复能力。F04 设计已存在，但原 M0/M2 均缺池容量回退规则，新增注入支持不等于有了恢复优势。", "",
        *["- " + limit for limit in result["limits"]], ""]
    (output / "offline-comparison.md").write_text("\n".join(lines), encoding="utf-8")
    if plot:
        plot_audit(result, output)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.directory, args.output)
    print(json.dumps({"recorded_cells": result["recorded_cells"], "methods": result["methods"]}))
