"""Prepare container-local worker configs and run the existing workbench."""
import json
import os
from pathlib import Path
import sys

ROOT = Path("/srv")
REVIEW = Path("/review")
STATE = Path("/state")
sys.path.insert(0, str(ROOT))
from tools.configure_local_coordinator import default_document


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def main():
    # These values populate worker-only files, never the coordinator environment.
    values = dict(line.split("=", 1) for line in (REVIEW / "compose.env").read_text().splitlines() if "=" in line)
    private = STATE / "private"
    private.mkdir(parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    project = values["COMPOSE_PROJECT_NAME"]
    (private / "application.env").write_text("APP_ADMIN_TOKEN=" + values["APP_ADMIN_TOKEN"] + "\n")
    (private / "database.env").write_text("DATABASE_URI=postgresql://bridge_operator:" +
                                         values["BRIDGE_DB_PASSWORD"] + "@postgres:5432/orders\n")
    (private / "ops.env").write_text("INCIDENT_OPS_BACKEND=docker\n")
    for path in private.glob("*.env"):
        path.chmod(0o600)
    common = {"allowed_callers": ["local-coordinator"], "approval_secret_env": "INCIDENT_APPROVAL_SECRET",
              "env_files": ["/review/approval.env"]}
    database = {**common, "executor_aic": "local-database-primary", "policy": "/srv/domains/database/policy.yaml",
                "ledger_path": "/state/database.sqlite", "ledger_domain": "database",
                "env_files": ["/review/approval.env", "/state/private/database.env"],
                "servers": {"postgres": {"command": "/opt/postgres-mcp/bin/postgres-mcp",
                             "args": ["--access-mode=unrestricted"], "env_names": ["DATABASE_URI"],
                             "timeout_seconds": 30}}}
    save(private / "database.json", database)
    save(private / "database-backup.json", {**database, "executor_aic": "local-database-backup"})
    policy = (ROOT / "domains/ops/policy.yaml").read_text().replace("incident-pilot-container", project)
    (private / "ops-policy.yaml").write_text(policy)
    ops = {**common, "executor_aic": "local-ops", "policy": "/state/private/ops-policy.yaml",
           "ledger_path": "/state/ops.sqlite", "ledger_domain": "ops",
           "env_files": ["/review/approval.env", "/state/private/ops.env"],
           "servers": {"docker": {"command": "/opt/docker-mcp/bin/mcp-server-docker", "timeout_seconds": 30},
                       "route": {"command": sys.executable, "args": ["/srv/domains/ops/route_mcp.py"],
                                 "timeout_seconds": 30,
                                 "env": {"INCIDENT_OPS_BACKEND": "docker", "INCIDENT_ROUTE_FILE": "/review/route/route.conf",
                                         "INCIDENT_NGINX_CONTAINER": project + "-nginx-1",
                                         "INCIDENT_ORDER_BASE_URL": "http://nginx"}}}}
    save(private / "ops.json", ops)
    config = default_document()
    config.update(python=sys.executable, directory="/state/transport", journal_path="/state/tasks.sqlite",
                  amp_directory="/state/amp", term_journal_path="/state/terms.sqlite",
                  approval_env_file="/review/approval.env", automatic_takeover=True)
    for worker in config["workers"]:
        role = worker["role"]
        if role == "application":
            worker.update(env_file="/state/private/application.env", base_url="http://app-v2:8000",
                          allowed_application_hosts=["app-v2"])
        elif role == "database":
            worker.pop("env_file", None)
            name = "database-backup" if worker.get("standby") else "database"
            worker["bridge_config"] = "/state/private/" + name + ".json"
        elif role == "ops":
            worker.pop("env_file", None)
            worker["bridge_config"] = "/state/private/ops.json"
        else:
            worker["base_url"] = "http://nginx"
    save(STATE / "coordinator.json", config)
    # Exec removes bootstrap variables; only workers load resource environment files.
    os.execv(sys.executable, [sys.executable, "/srv/workbench_server.py",
                            "--config", "/state/coordinator.json", "--output", "/state/workbench"])


if __name__ == "__main__":
    main()
