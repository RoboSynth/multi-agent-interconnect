"""Prepare separate formal-platform drafts. Never registers or changes an identity."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from acps_mcp_bridge import Policy
from acps_mcp_bridge.acs_mapper import map_acs, validate_acs

SKILLS = {"application": "incident.application", "database": "db.observe",
          "ops": "ops.observe", "verification": "incident.verification"}


def public_url(value, schemes):
    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Platform endpoint must be public protocol configuration without URL credentials")
    return value


def identity(source):
    # Return only this identity's key path; never copy the full agents mapping.
    return {key: source[key] for key in ("aic", "cert", "key", "endpoint")}


def endpoint_template(endpoint):
    parsed = urlparse(public_url(endpoint, {"amqps"}))
    query = parse_qs(parsed.query)
    query["inbox"] = ["inbox_{AIC}"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True))).replace("%7BAIC%7D", "{AIC}")


def acs_base(name, aic, endpoint):
    return {"aic": aic or "", "active": False, "name": name, "version": "1.0.0", "protocolVersion": "02.02",
        "lastModifiedTime": datetime.now(timezone.utc).isoformat(),
        "description": "跨资源域故障协同；经标准身份、能力发现和群组任务提供受控诊断恢复。",
        "provider": {"name": "Incident Pilot"},
        "capabilities": {"streaming": False, "notification": False, "messageQueue": ["amqp:0.9.1"]},
        "endPoints": [{"transport": "AMQP", "url": endpoint, "security": [{"mtls": []}]}],
        "securitySchemes": {"mtls": {"type": "mutualTLS", "description": "独立 AIC clientAuth 证书与 AMQPS mTLS"}},
        "defaultInputModes": ["application/json"], "defaultOutputModes": ["application/json"]}


def declared_inventory(policy):
    inventory = {}
    for spec in policy.tools.values():
        tools = inventory.setdefault(spec["server"], [])
        if not any(tool["name"] == spec["mcp_tool"] for tool in tools):
            tools.append({"name": spec["mcp_tool"], "inputSchema": {"type": "object"}})
    return inventory


def native_skills(role, *, public_onboarding=False):
    descriptions = {
        "leader": ("incident.coordinate", "凭据不出域的跨资源域事故协调",
            "以 ifc/1.0 群组任务组织资源能力确认、证据探测、审批、幂等恢复与接续；协调方只持本身份和审批能力，不持应用或数据库凭据。"),
        "application": ("incident.application", "PostgreSQL 订单应用诊断与受控恢复",
            "以 ifc/1.0 返回订单应用版本、错误和连接池证据；执行登记配置回退及连接池重建；资源凭据只在应用域，修改经操作账本与隔离令牌。"),
        "verification": ("incident.verification", "订单请求解析与业务恢复验证",
            "以 ifc/1.0 核验订单创建、查询、取消与同键回执；解析事故原请求并运行恢复观察窗口，报告成功、失败和未知请求，不持资源管理凭据。"),
        "onboarding": ("aip.onboarding.check", "公开互联元数据检查",
            "以 ifc/1.0 检查官方 ADP/ACS 的身份、协议、技能与收件箱元数据；不探测目标运行端点，不持资源管理凭据。")}
    skill_id, name, description = descriptions[role]
    skill = {"id": skill_id, "name": name, "version": "1.0.0", "description": description,
        "tags": ["incident-pilot", "ifc/1.0", role], "inputModes": ["application/json"], "outputModes": ["application/json"],
        "examples": [json.dumps({"schema_version": "ifc/1.0", "incident_id": "inc-example", "logical_task_id": "lt-describe",
                                 "kind": "describe", "tool": "describe", "args": {}}, ensure_ascii=False)]}
    if role == "onboarding" and public_onboarding:
        skill["inputModes"].append("text/plain")
        skill["outputModes"].append("text/plain")
        skill["description"] += " 也接受包含一个合法 AIC 的自然语言，返回公开元数据检查及中文说明。"
        skill["examples"].append("检查 1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6 的公开元数据")
    return [skill]


def prepare(source: dict, output: Path, *, public_onboarding=False):
    onboarding = source["agents"].get("onboarding")
    if public_onboarding and not onboarding:
        raise ValueError("public_onboarding requires an onboarding identity")
    if onboarding and onboarding.get("aic") and any(
            agent.get("aic") == onboarding["aic"] for role, agent in source["agents"].items() if role != "onboarding"):
        raise ValueError("The onboarding identity must use an AIC distinct from every other role")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory to preserve previous preparation evidence")
    output.mkdir(parents=True, exist_ok=True)
    (output / "acs").mkdir(exist_ok=True)
    discovery = public_url(source["discovery_url"], {"https"})
    mq_auth = public_url(source["mq_auth_url"], {"https"})
    for agent in source["agents"].values():
        public_url(agent["endpoint"], {"amqps"})
        for key in ("cert", "key"):
            if not Path(agent[key]).is_absolute() or "-----BEGIN" in agent[key]:
                raise ValueError("Identity config must reference absolute certificate/key paths, not key contents")
    coordinator = {"mode": "wutong-amqps", "leader": identity(source["agents"]["leader"]),
        "discovery_url": discovery, "mq_auth_url": mq_auth, "trust_bundle": source["trust_bundle"],
        "skills": dict(SKILLS), "approval_env_file": str(ROOT / "runtime/private/approval.env")}
    if source["agents"].get("onboarding"):
        coordinator["skills"]["onboarding"] = "aip.onboarding.check"
    save = lambda name, value: (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save("coordinator.json", coordinator)
    readiness = {"external_registration_performed": False, "existing_identity_modified": False,
        "acs_inventory_source": "policy-declared tool inventory; not a fresh remote MCP discovery",
        "kafka": {"brokers": None, "security_protocol": None, "authentication": None, "platform_ingestion_tested": False},
        "identities": {}, "acs_validation": {}}
    leader_aic = coordinator["leader"]["aic"]
    leader_draft = acs_base("跨域故障协调智能体", leader_aic, coordinator["leader"]["endpoint"])
    leader_draft["skills"] = native_skills("leader")
    leader_validation = validate_acs(leader_draft)
    if leader_validation["official_registry_schema_valid"] is not True or not leader_validation["sdk_schema_valid"]:
        raise ValueError("Coordinator ACS draft failed official offline validation")
    save("acs/coordinator.acs.json", leader_draft)
    readiness["acs_validation"]["coordinator"] = {"official_registry_schema_valid": True, "sdk_schema_valid": True,
        "skill_ids": ["incident.coordinate"], "platform_review_required": True, "platform_approved": False}
    roles = [("application", "application"), ("database", "database"), ("verification", "verification"),
             ("database-backup", "database_backup"), ("ops", "ops")]
    if source["agents"].get("onboarding"):
        roles.append(("onboarding", "onboarding"))
    for role, source_role in roles:
        known = source["agents"].get(source_role) or source["agents"].get(role)
        if known and role in {"database-backup", "ops"} and known["aic"] in {
                value["aic"] for name, value in source["agents"].items() if name not in {role, source_role}}:
            raise ValueError("A new domain identity cannot reuse an existing AIC")
        domain = "database" if role == "database-backup" else role
        config = {"name": role, "role": domain, "aic": known["aic"] if known else None,
            "allowed_leaders": [leader_aic], "endpoint": known["endpoint"] if known else None,
            "cert": known["cert"] if known else None, "key": known["key"] if known else None,
            "trust_bundle": source["trust_bundle"], "mq_auth_url": mq_auth,
            "amp_directory": str(ROOT / "runtime/amp-platform"),
            "identity_status": "existing_local_certificate_reference" if known else "not_registered",
            "identity_placeholder": None if known else "待独立注册、审核、签发证书"}
        if domain == "application":
            config.update(env_file=str(ROOT / "runtime/private/application.env"), base_url="http://127.0.0.1:8082",
                          ledger_path=str(ROOT / "runtime/application-operations.sqlite"))
        elif domain == "verification":
            config.update(base_url="http://127.0.0.1:8088", verification_duration=30)
        elif domain == "onboarding":
            config.update(discovery_url=discovery, public_metadata_service=bool(public_onboarding))
        else:
            local_config = ROOT / "runtime" / ("database-bridge.json" if domain == "database" else "ops-bridge.json")
            if not local_config.exists():
                raise ValueError("Run domains/setup_local.py first so domain tool process paths are known")
            bridge_config = json.loads(local_config.read_text(encoding="utf-8-sig"))
            bridge_config.update(executor_aic=config["aic"], allowed_callers=[leader_aic])
            # Resolve references relative to their original local config, not
            # the new output directory. No environment file contents are read.
            for field in ("policy", "ledger_path", "audit_path"):
                if field in bridge_config and not Path(bridge_config[field]).is_absolute():
                    bridge_config[field] = str((local_config.parent / bridge_config[field]).resolve())
            bridge_config["env_files"] = [str((local_config.parent / value).resolve()) if not Path(value).is_absolute() else value
                                            for value in bridge_config.get("env_files", [])]
            bridge_path = output / (role + "-bridge.json")
            save(bridge_path.name, bridge_config)
            config["bridge_config"] = str(bridge_path)
            config["ledger_path"] = bridge_config["ledger_path"]
            policy = Policy.load(bridge_config["policy"], allowed_callers=[leader_aic])
            draft = map_acs(acs_base("跨域数据库协同智能体" if domain == "database" else "跨域入口运维智能体",
                            config["aic"], config["endpoint"] or endpoint_template(coordinator["leader"]["endpoint"])),
                            policy, declared_inventory(policy))
            validation = validate_acs(draft)
            if validation["official_registry_schema_valid"] is not True or not validation["sdk_schema_valid"]:
                raise ValueError("Generated ACS failed official offline schema validation")
            save("acs/" + role + ".acs.json", draft)
            readiness["acs_validation"][role] = {"official_registry_schema_valid": validation["official_registry_schema_valid"],
                "sdk_schema_valid": validation["sdk_schema_valid"], "skill_ids": [skill["id"] for skill in draft["skills"]],
                "platform_review_required": True, "platform_approved": False}
        if domain in {"application", "verification", "onboarding"}:
            names = {"application": "跨域订单应用智能体", "verification": "跨域业务验证智能体", "onboarding": "互联接入检查智能体"}
            draft = acs_base(names[domain], config["aic"], config["endpoint"])
            draft["skills"] = native_skills(domain, public_onboarding=public_onboarding)
            if domain == "onboarding" and public_onboarding:
                draft["defaultInputModes"].append("text/plain")
                draft["defaultOutputModes"].append("text/plain")
            validation = validate_acs(draft)
            if validation["official_registry_schema_valid"] is not True or not validation["sdk_schema_valid"]:
                raise ValueError("Native partner ACS draft failed official offline validation")
            save("acs/" + role + ".acs.json", draft)
            readiness["acs_validation"][role] = {"official_registry_schema_valid": True, "sdk_schema_valid": True,
                "skill_ids": [skill["id"] for skill in draft["skills"]], "platform_review_required": True, "platform_approved": False}
        save(role + ".json", config)
        readiness["identities"][role] = {"registered_identity_available": bool(known),
            "certificate_paths_exist": bool(known and all(Path(known[k]).is_file() for k in ("cert", "key"))),
            "ready_for_live_start": False, "new_contract_platform_run_tested": False,
            "blocking_reasons": ["new runtime and updated ACS require live acceptance"] if known
                                else ["new AIC, approval and certificate issuance are pending"]}
    # Public coordinator has its own identity and public skill filters only.
    if "agents" in coordinator or any(key in coordinator for key in ("servers", "env_files", "database_uri", "base_url")):
        raise AssertionError("Coordinator config includes a resource-domain setting")
    save("readiness.json", readiness)
    return readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "integration/private/incident/config.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--public-onboarding", action="store_true", help="Prepare an externally callable public metadata check")
    args = parser.parse_args()
    output = args.output or ROOT / "runtime" / ("platform-preparation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    result = prepare(json.loads(args.source.read_text(encoding="utf-8-sig")), output.resolve(),
                     public_onboarding=args.public_onboarding)
    print(json.dumps({"output": str(output.resolve()), "offline_acs_valid": list(result["acs_validation"]),
                      "pending_identities": [role for role, value in result["identities"].items() if not value["registered_identity_available"]],
                      "external_writes": False}))


if __name__ == "__main__":
    main()
