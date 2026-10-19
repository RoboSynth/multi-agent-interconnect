"""Project selected cleanup evidence without publishing private runtime materials."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
REVIEW = BATCH / "review"
ROOT = BATCH / "checkout"
OUT = HERE / "publication"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if OUT.exists():
        raise ValueError("Preserve the existing publication projection")
    result = load(HERE / "attempt-1/result.json")
    actual_exit = load(HERE / "execution/runner.exit.json")
    probe = load(HERE / "readonly-probe-1/result.json")
    prepared = load(HERE / "prepared-v2.json")
    observation = load(BATCH / "execution-observation.json")
    if (result["status"] != "failed" or result["error_class"] != "ConnectError"
            or result["official_dissolve_calls"] != 1 or actual_exit["terminal"] is not True
            or actual_exit["actual_exit_code"] != 1 or probe["status"] != "completed"
            or probe["connection_closed"] is not True or len(probe["mq_resources"]) != 4
            or any(row["exists"] is not False or row.get("broker_not_found") is not True for row in probe["mq_resources"])
            or observation["not_attempted_cases"] != ["e1a-after_applied-r1"]):
        raise ValueError("Concrete cleanup/probe/batch receipts differ")
    current = {name: sha(BATCH / name) for name in prepared["scope"]["input_sha256"]}
    if current != prepared["scope"]["input_sha256"]:
        raise ValueError("Original frozen inputs changed")
    original = {
        "schema_version": "access-batch-owned-close-review/1", "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "status": "cleanup_failed_no_more_runs", "project": result["project"],
        "user_authorization": {"question_id": "call_eed3d32ab9a1402ebcb0e50876f1ed1e",
                               "exact_answer": "授权4次，确认七身份无其他消费者"},
        "known_created_group": {"group_id": result["group_id"], "coordinator_aic": result["coordinator_aic"],
            "ownership": "unique group_session_created matches frozen plan and original certificate CN",
            "original_journal_task_rows": 0, "original_messages_json_or_jsonl_present": False,
            "original_runner_terminal_exit": 1, "official_dissolve_calls": 1,
            "cleanup_terminal_exit": 1, "amqps_connected": True,
            "disband_failure": "broker NOT_FOUND: original owned exchange is absent",
            "acl_delete_result": "ConnectError; no HTTP acknowledgement; unknown whether ACL remains",
            "original_failure_retained": True, "new_tasks": 0, "new_inbox_consumers": 0},
        "intent_only_group": {"group_id": result["unknown_group_untouched"],
            "intent_attribution": "exact session UUID and coordinator AIC recorded by this batch before create await",
            "remote_creation_success": "unknown", "original_error_class": "ConnectTimeout",
            "original_http_and_rollback_acknowledgement": "not captured in this failed run",
            "acl_state": "unknown", "delete_requests_in_this_cleanup": 0},
        "readonly_probe": {"completed_at": probe["completed_at"], "resources": probe["mq_resources"],
            "acl_health_gets": probe["health"], "connection_closed": True,
            "interpretation": "four exact MQ resources absent now; health 200 is reachability, not proof that ACL entries are absent",
            "system_proxy_changed": False},
        "stopped_state": {"owned_container_count": 10, "actual_stop": "ACTUALLY_STOPPED",
            "keeper_terminal_exit": 0, "probe_incident_containers_running": 0,
            "probe_platform_coordinator_or_worker_processes": 0, "volumes_and_records_retained": True},
        "batch_state": {"attempted_cases": 3, "successful_cases": 1, "failed_cases": 2,
            "not_attempted_cases": ["e1a-after_applied-r1"], "new_fault_case_launched_by_cleanup": False},
        "source_boundaries": {"execution_checkout_commit": "a4d71e83444228a71499a75c932a2b9e7ba678f1",
            "original_plan_source_profile_and_evidence_hashes_unchanged": True,
            "local_sdk_namespace": "group_{leader_aic}_{group_id}; queue appends member AIC",
            "local_acl_namespace": "group_acl:{leader_aic}:{group_id}",
            "official_local_api_rules": "client certificate CN must equal leader route parameter; no group GET/list route in checked source",
            "deployed_server_policy_verified": False},
        "local_server_source_reference": {"scope": "separate original vendor copy; not the deployed server",
            "files": {name: sha(BATCH.parents[1] / "vendor/ACPs-community" / name) for name in (
                "mq-auth-server/app/api/groups.py", "mq-auth-server/app/services/group_acl.py")}},
        "sidecar_note": "Independent SQLite mode=ro inspection created an empty WAL and 32768-byte SHM. Original journal hash unchanged. Sidecars retained; subsequent checks use immutable=1.",
        "next_steps": [
            "Review the failed HTTP path and determine an explicit safe next cleanup attempt; do not silently retry this consumed attempt",
            "If cleaning ACLs later, target only the exact two recorded coordinator/group namespaces; retain 7bed creation outcome as unknown",
            "Use an ACL DELETE acknowledgement or an official authoritative ACL inspection before declaring full cleanup complete",
            "Review whether the original unused fourth plan can resume only after cleanup preconditions and exclusive identity ownership are rechecked",
        ],
        "evidence_sha256": {name: sha(BATCH / name) for name in [
            "execution-observation.json", "execution/result.json", "execution/stop/result.json", "execution/stop/after.json",
            "execution/keeper.exit.json", "owned-group-cleanup/prepared-v2.json", "owned-group-cleanup/attempt-1/result.json",
            "owned-group-cleanup/execution/runner.exit.json", "owned-group-cleanup/attempt-1/sdk.log",
            "owned-group-cleanup/readonly-probe-1/result.json", "review/access-batch-close-independent-review.json"]},
    }
    save(REVIEW / "access-batch-close-review.json", original)
    markdown = """# 本批遗留群组关闭复核

本次只执行了 1 次已授权的 cef7 官方 SDK 正常关闭，实际退出码 1，清理未通过。没有启动第 4 项故障实验，也没有重跑前 3 项。

- cef7 的唯一创建成功事件、原协调 AIC、冻结计划和证书 CN 一致；原 journal 任务表为空，没有业务消息。原 runner 已退出，10 个自有容器实际停止，keeper 退出码 0。
- AMQPS 连接成功；DISBAND 返回原 exchange 不存在。随后精确 ACL DELETE 连接报 ConnectError，没有删除确认；这次未执行队列和交换机删除。finally 已关闭连接，失败原件保留。
- 后续 1 次只读核查使用 AMQP passive 查询，cef7 与 7bed 的两个 exchange 和两个 leader queue 均由 broker 返回 NOT_FOUND，证明它们在核查时不存在。
- 7bed 仍只有本批创建意图，远端是否曾成功创建、ACL 是否残留未知。本次未向 7bed 发出删除请求。源码中的资源名和 ACL key 均包含精确 leader AIC 和随机 group_id；所读本地官方鉴权实现要求证书 CN 等于 leader 路径参数。该源码规则不代替已部署服务的实际策略证明。
- 原 ACL endpoint 的 /health GET 在默认代理行为与仅本客户端忽略代理两种模式下均返回 200。这是之后的可达性快照，不回填关闭失败，也不证明 ACL 已不存在。系统代理配置未变。

独立核查时 SQLite mode=ro 自动产生了空 WAL 和 32768 字节 SHM；原 journal SHA 与修改时间未变。两文件保留，后续核查使用 immutable=1；详细元数据见 independent review。

批次仍为 3 项已尝试（1 通过、2 失败）、第 4 项未执行。完整清理需得到精确 ACL 删除回执或权威只读 ACL 状态。下一步先审查失败和接续条件，当前不再追加真实运行或重试。

本目录原始脚本是固定批次的归档证据，依赖原 BATCH 布局和本机私密配置，不是队友可直接启动的新实验入口。public projection 不含证书/私钥、运行配置或原始 SDK/异常输出，仅保留选定结果及原件哈希；原件全部保留在本机。
"""
    (REVIEW / "access-batch-close-review.md").write_text(markdown, encoding="utf-8")
    OUT.mkdir()
    entries = []
    copies = {
        "review/access-batch-close-review.md": "README.md",
        "review/access-batch-close-review.json": "review.json",
        "review/access-batch-close-independent-review.md": "independent-review.md",
        "review/access-batch-close-independent-review.json": "independent-review.json",
        "owned-group-cleanup/prepared-v2.json": "prepared-scope.json",
        "owned-group-cleanup/attempt-1/result.json": "close-result.json",
        "owned-group-cleanup/execution/runner.exit.json": "close-terminal-exit.json",
        "owned-group-cleanup/execution/intent.json": "close-execution-intent.json",
        "owned-group-cleanup/readonly-probe-1/result.json": "readonly-probe-result.json",
        "owned-group-cleanup/attempt-1/live-container-inventory.exit.json": "close-preflight-container-exit.json",
        "owned-group-cleanup/attempt-1/live-coordinator-processes.exit.json": "close-preflight-process-exit.json",
        "owned-group-cleanup/readonly-probe-1/live-container-inventory.exit.json": "probe-preflight-container-exit.json",
        "owned-group-cleanup/readonly-probe-1/live-coordinator-processes.exit.json": "probe-preflight-process-exit.json",
        "owned-group-cleanup/close_owned_group.py": "scripts/close_owned_group.py",
        "owned-group-cleanup/launch_once.py": "scripts/launch_once.py",
        "owned-group-cleanup/readonly_remote_probe.py": "scripts/readonly_remote_probe.py",
        "owned-group-cleanup/prepare_publication.py": "scripts/prepare_publication.py",
    }
    for source, destination in copies.items():
        path = OUT / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BATCH / source, path)
        entries.append({"source": source, "published": destination, "projection": "exact_copy",
                        "source_sha256": sha(BATCH / source), "published_sha256": sha(path), "bytes": path.stat().st_size})
    raw_log = HERE / "attempt-1/sdk.log"
    projected = OUT / "sdk-events-projected.json"
    save(projected, {"original_sha256": sha(raw_log), "events": result["sdk_events"],
        "broker_exchange_not_found": True, "exact_owned_group_id": result["group_id"],
        "acl_request_method": "DELETE", "acl_request_exact_owned_path": True,
        "acl_acknowledgement": False, "omitted": ["endpoint URL", "raw exception text"]})
    entries.append({"source": "owned-group-cleanup/attempt-1/sdk.log", "published": projected.name,
                    "projection": "selected_events_and_owned_resource_outcome",
                    "source_sha256": sha(raw_log), "published_sha256": sha(projected), "bytes": projected.stat().st_size})
    excluded = []
    for path in sorted(HERE.rglob("*")):
        if path.is_file() and not path.is_relative_to(OUT) and path.relative_to(BATCH).as_posix() not in copies:
            excluded.append({"source": path.relative_to(BATCH).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size,
                             "publication": "not copied; original retained"})
    save(OUT / "manifest.json", {"schema_version": "owned-cleanup-publication-manifest/1", "files": entries,
        "excluded_originals": excluded, "private_runtime_files_copied": 0,
        "original_frozen_inputs_rechecked": len(current), "script_is_fixed_batch_archive": True})
    # Minimal content validation; the root publication workflow performs its full
    # repository inventory scan before committing these selected files.
    boundary = re.escape(b"-" * 5)
    sensitive = re.compile(boundary + rb"BEGIN (?:(?:RSA |EC |OPENSSH )?PRIVATE KEY|CERTIFICATE)" + boundary)
    for path in OUT.rglob("*"):
        if path.is_file() and sensitive.search(path.read_bytes()):
            raise ValueError("Unexpected credential material in projection")
    print(json.dumps({"publication_files": len(entries) + 1, "manifest_sha256": sha(OUT / "manifest.json"),
                      "original_inputs_unchanged": len(current), "status": original["status"]}), flush=True)


if __name__ == "__main__":
    main()
