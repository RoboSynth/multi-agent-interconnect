"""Check archived exact-PID revival evidence and preserve per-run provenance."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(directories, output):
    rows = []
    for directory in directories:
        path = Path(directory) / "results.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        suspended, revived = data["old_primary_suspended"], data["old_primary_revived"]
        replay, healthy = data["old_primary_replay"], data["healthy_observation"]
        checks = {
            "identity_checked": suspended["identity_checked"] is True,
            "same_pid": suspended["pid"] == revived["pid"] and revived["same_process_alive"] is True,
            "suspend_resume_succeeded": suspended["suspend_ntstatus"] == revived["resume_ntstatus"] == 0,
            "old_primary_rejected": replay["executor_aic"] == "local-container-db-primary"
                and replay["status"] == "rejected"
                and replay["operation"]["state"] == "rejected_stale_fence",
            "one_backup_modification": data["mcp_modifying_calls"] == 1
                and data["revived_primary_mcp_modifying_calls"] == 0
                and data["backup_action"]["operation"]["state"] == "applied",
            "resource_restored": data["before"]["read_only"] is True
                and data["after_backup"]["read_only"] is False and data["cleanup"] == "restored",
            "healthy_window": healthy["passed"] is True and healthy["duration_seconds"] >= 30
                and healthy["completed_workflows"] >= 10 and healthy["unknown"] == 0
                and healthy["failed"] == 0 and healthy["unresolved_intents"] == 0,
        }
        rows.append({"run": Path(directory).name,
            "source_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_cohort": "historical_initial" if len(rows) == 0 else "supplemental_recheck",
            "pid": suspended["pid"], "checks": checks, "passed": all(checks.values()),
            "mcp_modifying_calls": data["mcp_modifying_calls"],
            "old_primary_mcp_modifying_calls": data["revived_primary_mcp_modifying_calls"],
            "healthy_seconds": healthy["duration_seconds"], "workflows": healthy["completed_workflows"]})
    result = {"experiment": "E1-c exact old-primary PID revival", "transport": "local-aip-stdio",
        "platform_adp_verified": False,
        "fence_enforcement": "shared resource-domain SQLite OperationLedger, not a PostgreSQL-native fence",
        "cohort_note": "Historical first result plus subsequent rechecks; not one newly frozen three-run experiment.",
        "runs": rows, "passed_runs": sum(row["passed"] for row in rows),
        "revived_primary_modifying_calls": sum(row["old_primary_mcp_modifying_calls"] for row in rows)}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E1-c 旧主同 PID 复活补证", "",
        "历史首轮与后续两次独立复验均保留。它们不是同一新冻结版本的三次实验；本表只合计可直接核对的隔离结果，不合并时延统计。", "",
        "| 运行 | 同 PID | 旧令牌拒绝 | MCP 修改调用（备 / 旧主） | 恢复窗口秒 / 完整流程 | 通过 |",
        "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['run']} | {row['pid']} | {row['checks']['old_primary_rejected']} | "
            f"{row['mcp_modifying_calls']} / {row['old_primary_mcp_modifying_calls']} | "
            f"{row['healthy_seconds']} / {row['workflows']} | {row['passed']} |")
    lines += ["", "每次均实际暂停旧主、由备恢复数据库写入，再恢复同一旧 PID 并派发原令牌命令；旧主未调用上游修改工具。",
        "隔离在资源域共享 SQLite 操作账本中执行。实际保护的资源是 PostgreSQL；本结果不代表 PostgreSQL 自身检查 fence，也不代表正式 AMQPS/ADP 接管。",
        "原始结果 SHA256 与逐项断言见 summary.json。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.runs, args.output)
    print(json.dumps({"recorded": len(summary["runs"]), "passed": summary["passed_runs"],
        "revived_primary_modifying_calls": summary["revived_primary_modifying_calls"]}))
