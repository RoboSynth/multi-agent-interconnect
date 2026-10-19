"""Prepare isolated container-domain mounts; never start or register an AIC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    return {name.strip(): value.strip().strip('"').strip("'")
            for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
            for name, separator, value in [line.partition("=")] if separator}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(source, output, business_env, approval_env, project, *, include_onboarding=False,
            include_coordinator=False, ops_service=None, public_onboarding=False):
    if public_onboarding and not include_onboarding:
        raise ValueError("public_onboarding requires include_onboarding")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; existing credentials are never overwritten")
    if not project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in project):
        raise ValueError("Invalid Compose project name")
    if ops_service is not None and (not ops_service or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in ops_service)):
        raise ValueError("Invalid managed Compose service")
    roles = ["application", "verification", "database", "database-backup", "ops"]
    if include_onboarding:
        roles.append("onboarding")
    source_configs = {role: json.loads((source / (role + ".json")).read_text(encoding="utf-8-sig"))
                      for role in roles}
    aic_roles = {}
    for role, config in source_configs.items():
        aic = config.get("aic")
        if aic:
            if aic in aic_roles:
                raise ValueError("Domain identities must use distinct AICs: " + aic_roles[aic] + " and " + role)
            aic_roles[aic] = role
    coordinator_source = None
    if include_coordinator:
        coordinator_source = json.loads((source / "coordinator.json").read_text(encoding="utf-8-sig"))
        if coordinator_source["leader"]["aic"] in aic_roles:
            raise ValueError("Coordinator and resource domains must use distinct AICs")
    business = read_env(business_env)
    approval = read_env(approval_env)["INCIDENT_APPROVAL_SECRET"]
    for name in ("APP_ADMIN_TOKEN", "ORDERS_DB_PASSWORD", "POSTGRES_PASSWORD"):
        if len(business.get(name, "")) < 24:
            raise ValueError("Missing or short business domain credential: " + name)
    if not business.get("BRIDGE_DB_PASSWORD"):
        business["BRIDGE_DB_PASSWORD"] = secrets.token_urlsafe(36)
        with Path(business_env).open("a", encoding="utf-8") as stream:
            stream.write("\nBRIDGE_DB_PASSWORD=" + business["BRIDGE_DB_PASSWORD"] + "\n")
    output.mkdir(parents=True, exist_ok=True)
    report = {"mode": "offline-container-domain-preparation", "network_attempted": False,
              "identities_started": False, "prepared": [], "pending_identities": [],
              "certificate_validation_performed": False, "ready_for_live_start": False,
              "database_provision_required": True, "term_journal": "isolated container resources use their own persistent authority"}
    identities = {}
    for role in roles:
        source_file = source / (role + ".json")
        config = source_configs[role]
        if not config.get("aic") or not config.get("endpoint"):
            report["pending_identities"].append(role)
            continue
        domain = output / role
        domain.mkdir()
        for field, filename in (("cert", "cert.pem"), ("key", "key.pem"), ("trust_bundle", "trust.pem")):
            original = Path(config[field])
            if not original.is_absolute():
                original = source_file.parent / original
            shutil.copyfile(original, domain / filename)
            config[field] = "/domain/" + filename
        config["amp_directory"] = "/state/amp-" + role
        config["evidence_path"] = "/state/platform-events.jsonl"
        config["ledger_path"] = "/state/operations.sqlite"
        config.pop("bridge_config", None)
        identities[role] = config["aic"]
        if role in {"application", "verification"}:
            config["base_url"] = "http://app-v2:8000" if role == "application" else "http://nginx"
            if role == "application":
                config["allowed_application_hosts"] = ["app-v2"]
                config["env_file"] = "/domain/domain.env"
                (domain / "domain.env").write_text("APP_ADMIN_TOKEN=" + business["APP_ADMIN_TOKEN"] + "\n", encoding="utf-8")
            save(domain / "config.json", config)
        elif role == "onboarding":
            # This domain checks public metadata. It receives no resource env file.
            config = {key: config[key] for key in ("aic", "endpoint", "allowed_leaders", "cert", "key",
                "trust_bundle", "mq_auth_url", "amp_directory", "evidence_path", "discovery_url")}
            config.update(name="onboarding", role="onboarding")
            config["public_metadata_service"] = bool(public_onboarding or source_configs[role].get("public_metadata_service") is True)
            save(domain / "config.json", config)
        else:
            database = role.startswith("database")
            uri = "postgresql://bridge_operator:" + quote(business["BRIDGE_DB_PASSWORD"], safe="") + "@postgres:5432/orders"
            environment = "INCIDENT_APPROVAL_SECRET=" + approval + "\n"
            if database:
                environment += "DATABASE_URI=" + uri + "\n"
                servers = {"postgres": {"command": "/opt/postgres-mcp/bin/postgres-mcp",
                    "args": ["--access-mode=unrestricted"], "env_names": ["DATABASE_URI"], "timeout_seconds": 30}}
            else:
                servers = {"docker": {"command": "/opt/docker-mcp/bin/mcp-server-docker", "timeout_seconds": 30},
                    "route": {"command": "python", "args": ["/srv/domains/ops/route_mcp.py"], "timeout_seconds": 30,
                        "env": {"INCIDENT_OPS_BACKEND": "docker", "INCIDENT_ROUTE_FILE": "/route/route.conf",
                            "INCIDENT_NGINX_CONTAINER": project + "-nginx-1", "INCIDENT_ORDER_BASE_URL": "http://nginx"}}}
            (domain / "domain.env").write_text(environment, encoding="utf-8")
            platform = {**config, "amp_directory": "/state/amp-" + role}
            bridge = {"executor_aic": config["aic"], "allowed_callers": config["allowed_leaders"],
                "policy": "/srv/domains/" + ("database" if database else "ops") + "/policy.yaml",
                "ledger_path": "/state/operations.sqlite", "ledger_domain": "database" if database else "ops",
                "audit_path": "/state/audit-" + role + ".jsonl", "approval_secret_env": "INCIDENT_APPROVAL_SECRET",
                "env_files": ["/domain/domain.env"], "servers": servers, "platform": platform}
            if not database and ops_service is not None:
                import yaml
                policy = yaml.safe_load((ROOT / "domains/ops/policy.yaml").read_text(encoding="utf-8"))
                container = project + "-" + ops_service + "-1"
                policy["resources"].update(compose_project=project, compose_service=ops_service, container_name=container)
                policy["tools"]["ops.containers"]["fixed_arguments"] = {"all": True, "filters": {"label": [
                    "incident-pilot", "com.docker.compose.project=" + project, "com.docker.compose.service=" + ops_service]}}
                for alias in ("ops.restart", "ops.logs"):
                    policy["tools"][alias]["input_schema"] = {"type": "object", "properties": {}, "additionalProperties": False}
                    policy["tools"][alias].setdefault("fixed_arguments", {})["container_id"] = container
                (domain / "policy.yaml").write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")
                bridge["policy"] = "/domain/policy.yaml"
            save(domain / "bridge.json", bridge)
        report["prepared"].append(role)
    if include_coordinator:
        original = coordinator_source
        domain = output / "coordinator"
        domain.mkdir()
        leader = {key: original["leader"][key] for key in ("aic", "endpoint")}
        for field, filename in (("cert", "cert.pem"), ("key", "key.pem")):
            shutil.copyfile(original["leader"][field], domain / filename)
            leader[field] = str((domain / filename).resolve())
        shutil.copyfile(original["trust_bundle"], domain / "trust.pem")
        (domain / "approval.env").write_text("INCIDENT_APPROVAL_SECRET=" + approval + "\n", encoding="utf-8")
        trusted = {role: [aic] for role, aic in identities.items() if role != "database-backup"}
        if "database-backup" in identities:
            trusted.setdefault("database", []).append(identities["database-backup"])
        coordinator = {"mode": "wutong-amqps", "leader": leader,
            "discovery_url": original["discovery_url"], "mq_auth_url": original["mq_auth_url"],
            "trust_bundle": str((domain / "trust.pem").resolve()),
            "approval_env_file": str((domain / "approval.env").resolve()),
            "term_journal_path": str((domain / "coordinator-terms.sqlite").resolve()),
            "term_namespace": project + "/orders", "trusted_participant_aics": trusted,
            "skills": {role: skill for role, skill in original["skills"].items() if role in trusted},
            "participant_describe_timeout_seconds": 30}
        if "database" in identities:
            coordinator["initial_participant_aics"] = {"database": identities["database"]}
        save(domain / "config.json", coordinator)
        report["coordinator_prepared"] = True
    save(output / "readiness.json", report)
    return report


def provision_database(business_env, project, wsl=None):
    if not project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in project):
        raise ValueError("Invalid Compose project name")
    password = read_env(business_env)["BRIDGE_DB_PASSWORD"]
    prefix = ["wsl.exe", "-d", wsl, "--exec", "docker"] if wsl else ["docker"]
    target = project + "-postgres-1"
    inspection = subprocess.run(prefix + ["inspect", target], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=True)
    details = json.loads(inspection.stdout)
    if len(details) != 1 or details[0]["Config"]["Labels"].get("incident-pilot") != "true":
        raise ValueError("Target is not an incident-pilot container")
    sql = (ROOT / "domains/database/bootstrap.sql").read_text(encoding="utf-8")
    sql += "\nALTER ROLE bridge_operator PASSWORD '" + password.replace("'", "''") + "';\n"
    result = subprocess.run(prefix + ["exec", "-i", details[0]["Id"], "psql", "-U", "postgres", "-d", "orders",
                            "-v", "ON_ERROR_STOP=1"], input=sql, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode:
        # Do not surface SQL/connection diagnostics that could contain credentials.
        raise RuntimeError("Container database bridge provisioning failed")
    return {"mode": "isolated-container-database-provision", "passed": True,
            "container": target, "role": "bridge_operator", "platform_attempted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="domains/setup_platform.py output directory")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/container-domains")
    parser.add_argument("--business-env", type=Path, required=True)
    parser.add_argument("--approval-env", type=Path, default=ROOT / "runtime/private/approval.env")
    parser.add_argument("--project", default="incident-pilot-container")
    parser.add_argument("--include-onboarding", action="store_true", help="Prepare the optional public-metadata domain")
    parser.add_argument("--public-onboarding", action="store_true", help="Allow external AICs to use only the public metadata check")
    parser.add_argument("--include-coordinator", action="store_true", help="Prepare a separate Windows coordinator identity/config")
    parser.add_argument("--ops-service", help="Opt in to exact Compose project/service/container operations scope")
    parser.add_argument("--provision-db-only", action="store_true", help="Apply the existing least-privilege bootstrap to this labeled database")
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.provision_db_only:
        print(json.dumps(provision_database(args.business_env.resolve(), args.project, args.wsl)))
        return
    if args.source is None:
        parser.error("--source is required for config preparation")
    print(json.dumps(prepare(args.source.resolve(), args.output.resolve(), args.business_env.resolve(),
                             args.approval_env.resolve(), args.project, include_onboarding=args.include_onboarding,
                             include_coordinator=args.include_coordinator, ops_service=args.ops_service,
                             public_onboarding=args.public_onboarding), ensure_ascii=False))


if __name__ == "__main__":
    main()
