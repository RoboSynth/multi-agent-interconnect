"""Deterministic plain-text input for the public, metadata-only check."""
from __future__ import annotations

import hashlib
import re

from acps_sdk.aic import validate_aic_format


_AIC = re.compile(r"(?<![A-Za-z0-9.])1\.2\.156\.3088(?:\.[A-Za-z0-9]+){6}(?![A-Za-z0-9]|\.[A-Za-z0-9])")
_UNSUPPORTED = re.compile(
    r"重启|删除|修改|更新|修复|写入|注入|停机|关机|停止|启动|清理|创建|安装|部署|卸载|恢复|回滚|"
    r"运行命令|执行命令|运行脚本|执行脚本|"
    r"深度|深探|主动探测|端点探测|探测端点|端口扫描|扫描端口|连通性|可达性|握手|"
    r"连接目标|连接端点|连接测试|证书校验|验证证书|证书验证|"
    r"\b(?:restart|reboot|delete|remove|modify|update|repair|write|inject|shutdown|execute|reset|"
    r"shell|bash|powershell|curl|wget|sql|ping|probe|scan|connect|connectivity|reachability|handshake|mtls|deep)\b",
    re.IGNORECASE,
)
# Accept only complete, explicitly negative clauses used in metadata requests.
# Do not strip a keyword inside a longer instruction or infer general negation.
_READ_ONLY_DISCLAIMERS = re.compile(
    r"(?:^|(?<=[。！？；，\n]))\s*"
    r"(?:不要修改资源|不要进行主动端点探测)\s*(?=$|[。！？；，\n])"
)
HELP = "请提供一个目标 AIC，例如：检查 1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6 的公开元数据。每次只检查一个目标；仅查询官方 ACS/ADP，不连接目标端点或修改资源。"


def prepare_text_request(text, *, session_id, task_id, executor_aic):
    """Return an IFC request and, for help/refusal, a result needing no lookup."""
    identifier = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    payload = dict(schema_version="ifc/1.0", incident_id="text-" + identifier(session_id),
        logical_task_id="text-" + identifier(session_id + "\0" + task_id), kind="describe",
        tool="describe", args={}, budget=dict(deadline_ms=30000))
    reason = None
    if len(text) > 2000:
        reason = "text_too_long"
    elif _UNSUPPORTED.search(_READ_ONLY_DISCLAIMERS.sub("", text)):
        reason = "read_only_metadata_check_required"
    else:
        candidates = set(match.group().upper() for match in _AIC.finditer(text))
        if len(candidates) != 1:
            reason = "target_aic_required" if not candidates else "single_target_aic_required"
        elif not validate_aic_format(next(iter(candidates)))[0]:
            reason = "invalid_target_aic"
    if reason:
        return payload, dict(schema_version="ifc/1.0", incident_id=payload["incident_id"],
            logical_task_id=payload["logical_task_id"], executor_aic=executor_aic,
            status="rejected", facts=[], reason=reason, help=HELP)
    payload.update(kind="observe", tool="aip.onboarding.check",
                   args=dict(target_aic=next(iter(candidates)), deep=False))
    return payload, None


def readable_result(output):
    """Render only the existing metadata result; never infer runtime health."""
    if output.get("help"):
        prefix = "此服务只接受公开元数据检查。" if output.get("reason") == "read_only_metadata_check_required" else "未发起检查。"
        return prefix + "\n" + output["help"]
    if output.get("status") != "ok":
        return "官方元数据查询未完成，请稍后重试；这不表示目标配置有误。\n" + HELP
    report = next((fact.get("value") for fact in output.get("facts", [])
                   if fact.get("key") == "onboarding_report"), None)
    if not isinstance(report, dict):
        return HELP
    status = "未在官方发现服务中找到" if not report.get("found") else "通过" if report.get("passed") else "存在待核对项"
    lines = [f"公开元数据体检：{report.get('target_aic', '')}", f"结果：{status}。"]
    for key, label in (("official_registry_schema_valid", "官方 ACS 结构"), ("sdk_schema_valid", "SDK 结构"),
                       ("protocol_version_valid", "协议版本"), ("inbox_endpoint_valid", "AMQPS Inbox 格式"),
                       ("skills_complete", "技能字段")):
        if key in report:
            lines.append(f"{label}：{'通过' if report[key] else '待核对'}。")
    lines.extend("建议：" + str(value) for value in report.get("suggestions", []))
    lines.append("仅核对公开 ACS/ADP；不代表目标运行可达、证书或 mTLS 验证通过。")
    return "\n".join(lines)
