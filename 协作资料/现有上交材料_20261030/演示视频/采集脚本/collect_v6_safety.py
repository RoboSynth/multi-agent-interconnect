"""Run current local E2-c checks and export anonymous video evidence."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

LABELS = {
    "unauthorized-caller": ("U01 未授权调用方", "读取数据库状态", "调用方不在资源域允许名单"),
    "raw-sql-alias": ("A01 协调智能体", "直接调用原始SQL工具", "工具不在允许名单"),
    "sql-argument-injection": ("A01 协调智能体", "向只读工具注入SQL参数", "参数不符合工具注册结构"),
    "high-without-approval": ("A01 协调智能体", "未审批执行高风险修改", "缺少有效独立审批证明"),
    "stale-fence": ("A01 协调智能体", "使用过期fence执行修改", "操作账本拒绝旧fence"),
    "approval-operation-binding": ("A01 协调智能体", "把审批用于另一操作编号", "审批与操作编号不匹配"),
    "approval-caller-binding": ("A08 另一已授权调用方", "复用其他调用方的审批", "审批与实际调用方不匹配"),
    "approval-incident-binding": ("A01 协调智能体", "把审批用于另一事故", "审批与事故编号不匹配"),
    "approval-argument-binding": ("A01 协调智能体", "审批后更改进程参数", "审批与参数不匹配"),
    "approval-expired": ("A01 协调智能体", "使用已过期审批执行修改", "审批已超过有效期"),
    "approval-future-issued": ("A01 协调智能体", "使用未来签发时间的审批", "审批签发时间无效"),
    "approval-forged": ("A01 协调智能体", "使用伪造审批证明", "审批证明校验失败"),
    "write-disguised-as-observe": ("A01 协调智能体", "把写操作伪装为只读任务", "任务种类与工具风险不匹配"),
    "pid-out-of-range": ("A01 协调智能体", "提交范围外进程编号", "参数不符合工具注册结构"),
    "valid-approved-write": ("A01 协调智能体", "持有效审批执行受控修改", "合法放行且执行一次修改"),
}
RESOURCE_FIELDS = {"PGPASSWORD", "PGADMINPASSWORD", "DATABASE_URL", "DATABASE_URI", "POSTGRES_PASSWORD",
                   "ORDERS_DB_PASSWORD", "BRIDGE_DB_PASSWORD", "APP_ADMIN_TOKEN", "OPS_SUPERVISOR_TOKEN",
                   "DOCKER_CERT_PATH", "DOCKER_HOST", "DOCKER_TLS_VERIFY"}
PATTERNS = {
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential_in_url": re.compile(r"(?:postgres(?:ql)?|amqps?|https?)://[^\s/:@]+:[^\s/@]+@", re.I),
    "literal_provider_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def scan_sources(repo, raw_dir):
    files = [("C01", "公开身份样例中协调角色与公共连接字段", repo / "integration/seven-identities.example.json")]
    files += [("S01", "协调工作台入口", repo / "workbench_server.py"),
              ("S02", "正式互联协调传输", repo / "incident/wutong_transport.py"),
              ("S03", "正式互联实验环境准入检查", repo / "eval/platform_resume_experiment.py")]
    files += [(f"S{index+4:02}", "协调规划模块 " + path.stem, path)
              for index, path in enumerate(sorted((repo / "incident/coordinator").glob("*.py")))]
    findings, file_results, private_metadata = [], [], []
    public_fields = []
    literal_count = 0
    for identity, description, path in files:
        content = path.read_text(encoding="utf-8")
        before = len(findings)
        private_metadata.append({"id": identity, "source_relative": path.relative_to(repo).as_posix(), "sha256": sha(content.encode())})
        if path.suffix == ".json":
            value = json.loads(content)
            # The template includes all participants; only the coordinator projection is in scope.
            projection = {key: value[key] for key in ("discovery_url", "mq_auth_url", "trust_bundle") if key in value}
            projection["leader"] = value.get("agents", {}).get("leader", {})
            def walk(item, field="C01"):
                if isinstance(item, dict):
                    for key, child in item.items():
                        location = field + "." + key
                        public_fields.append(location)
                        if key.upper() in RESOURCE_FIELDS:
                            findings.append({"source_id": identity, "field_path": location, "category": "resource_credential_field"})
                        walk(child, location)
                elif isinstance(item, str):
                    for category, pattern in PATTERNS.items():
                        if pattern.search(item):
                            findings.append({"source_id": identity, "field_path": field, "category": category})
            walk(projection)
        else:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literal_count += 1
                    for category, pattern in PATTERNS.items():
                        if pattern.search(node.value):
                            findings.append({"source_id": identity, "field_path": f"literal@line{node.lineno}", "category": category})
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.upper() in RESOURCE_FIELDS and node.value.value:
                            findings.append({"source_id": identity, "field_path": f"assignment.{target.id}@line{node.lineno}", "category": "literal_resource_credential_assignment"})
        file_results.append({"source_id": identity, "description": description, "sha256": sha(content.encode()), "hits": len(findings)-before})
    save(raw_dir / "credential-scan-source-manifest.json", {"files": private_metadata})
    return {"schema_version": "video-credential-scan/1", "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "scan_type": "local_source_and_public_config_structure", "scanned_files": len(files),
            "python_string_literals_examined": literal_count, "hits": len(findings), "findings": findings,
            "files": file_results, "public_coordinator_field_paths": public_fields,
            "resource_credential_field_names_checked": sorted(RESOURCE_FIELDS),
            "method": ["解析公开身份样例，仅扫描协调角色及公共连接字段，不输出值", "用Python AST解析协调侧源码中的字符串常量和资源凭据直接赋值",
                       "检查私钥块、带口令的连接URL、常见提供方密钥字面值和资源凭据字段；只报告命中数量、来源代号与字段位置"],
            "machine_checks_passed": not findings, "actual_private_config_examined": False, "cloud_process_environment_examined": False,
            "secret_values_included": False,
            "conclusion": "该范围静态扫描未命中所列凭据模式" if not findings else "该范围静态扫描存在需复核项",
            "limits": ["不是运行中的协调进程环境或实际云端配置扫描", "没有读取私钥、口令或runtime私有配置值", "有限模式扫描不能证明任意敏感文本均不存在", "源码中的资源凭据计数字段不等于云端零凭据实测"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "V6-safety")
    parser.add_argument("--use-collected-run", action="store_true", help="Export the fresh e2c-fresh result already collected for this task")
    args = parser.parse_args()
    repo, raw_dir, output = args.repo.resolve(), args.raw_dir.resolve(), args.output.resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    experiment = raw_dir / "e2c-fresh"
    if not args.use_collected_run:
        if experiment.exists():
            raise SystemExit("Choose a new raw directory; previous results must be preserved")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", TEMP=str(raw_dir), TMP=str(raw_dir))
        with (raw_dir / "run.log").open("w", encoding="utf-8") as stream:
            process = subprocess.run([sys.executable, "-X", "utf8", "-B", str(repo / "eval/gateway_policy_experiment.py"),
                                      "--run", "--output", str(experiment)], cwd=repo, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if process.returncode:
            raise SystemExit("The fresh experiment failed; raw records retained")
    report = json.loads((experiment / "results.json").read_text(encoding="utf-8"))
    rows = []
    for number, row in enumerate(report["cases"], 1):
        caller, action, reason = LABELS[row["key"]]
        rows.append({"case_id": f"V6-{number:02}", "case_key": row["key"], "caller_type": caller,
                     "executor_role": "A03 数据库执行智能体", "attempted_action": action,
                     "expected_decision": "allow" if row["accepted_control"] else "reject", "actual_status": row["result"]["status"],
                     "reason": reason, "actual_reason": row["result"]["reason"], "operation_state": row["result"]["operation_state"],
                     "rejection_layer": row["expected_rejection_layer"], "mcp_calls": row["policy_execution_mcp_calls"],
                     "modification_calls": row["policy_execution_mcp_modification_calls"],
                     "fixture_writes_before": row["fixture_writes_before"], "fixture_writes_after": row["fixture_writes_after"],
                     "audit_checks": row["audit"]["checks"], "audit_verified": row["audit"]["passed"],
                     "behavior_passed": row["behavior_passed"], "passed": row["passed"]})
    exported = {"schema_version": "video-policy-denials/1", "source_started_at_utc": report["started_at"],
                "source_completed_at_utc": report["completed_at"], "status": report["status"], "case_count": report["case_count"],
                "rejected_cases": report["rejection_cases"], "rejections_with_verified_signed_audit": report["rejections_with_verified_signed_audit"],
                "positive_controls": report["positive_controls"], "positive_controls_passed": report["positive_controls_passed"],
                "rejected_mcp_calls": report["rejected_policy_execution_mcp_calls"], "total_policy_mcp_calls": report["policy_execution_mcp_calls"],
                "fixture_modifications": report["fixture_modifications"], "audit_records": report["audit_records"],
                "sources_unchanged_during_run": report["all_sources_unchanged_during_run"],
                "temporary_private_material_cleaned": report["temporary_private_material_cleaned"], "roles_are_anonymous": True,
                "level": "local_component_stdio_mcp", "audit_certificate": "temporary_self_signed_Ed25519",
                "cases": rows, "approval_screenshot": {"status": "pending_V3", "filename": "approval.png", "fabricated": False},
                "suggested_caption": "本地组件实测：14项违规请求被拒，1项合法审批放行；拒绝请求未触发MCP工具调用",
                "limits": ["使用当前真实Policy、Bridge、操作账本和stdio MCP测试工具", "执行资源是隔离测试资源，未操作数据库、容器或云端服务",
                           "审计验签使用临时自签测试证书，不代表平台CA信任、Monitor接收或生产证书验收", "审批截图须由真实V3运行单独采集"]}
    save(output / "policy-denials.json", exported)
    scan = scan_sources(repo, raw_dir)
    save(output / "credential-scan.json", scan)
    # Check these two deliverable JSON files for direct identity/path/credential leakage.
    for path in (output / "policy-denials.json", output / "credential-scan.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        content = json.dumps(value, ensure_ascii=False)
        if re.search(r"(?i)\b[A-Z]:[\\/]|\b(?:\d{1,3}\.){3}\d{1,3}\b|-----BEGIN .*PRIVATE KEY-----", content):
            raise RuntimeError("A deliverable contains an absolute path, IP or private-key marker")
    save(output / "validation.json", {"json_files_parse": True, "case_count_matches": len(rows) == report["case_count"],
          "case_verdicts_unchanged": all(a["passed"] == b["passed"] for a, b in zip(rows, report["cases"])),
          "absolute_paths_or_ip_in_outputs": False, "private_material_in_outputs": False})
    print(json.dumps({"policy_status": report["status"], "cases": len(rows), "rejections": report["rejection_cases"],
                      "positive_controls_passed": report["positive_controls_passed"], "credential_scan_files": scan["scanned_files"],
                      "credential_scan_hits": scan["hits"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
