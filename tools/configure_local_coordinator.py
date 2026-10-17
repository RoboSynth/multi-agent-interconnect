"""Write a coordinator config containing identity/routing, no resource secrets."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]


def configure():
    directory = ROOT / "runtime"
    directory.mkdir(parents=True, exist_ok=True)
    workers = [
        {"name": "应用团队", "role": "application", "aic": "local-application",
         "env_file": "runtime/private/application.env", "base_url": "http://127.0.0.1:8082"},
        {"name": "数据库主", "role": "database", "aic": "local-database-primary",
         "env_file": "runtime/private/database-bridge.env", "bridge_config": "runtime/database-bridge.json"},
        {"name": "数据库备", "role": "database", "aic": "local-database-backup", "standby": True,
         "env_file": "runtime/private/database-bridge.env", "bridge_config": "runtime/database-backup-bridge.json"},
        {"name": "运维团队", "role": "ops", "aic": "local-ops",
         "env_file": "runtime/private/ops-bridge.env", "bridge_config": "runtime/ops-bridge.json"},
        {"name": "业务验证", "role": "verification", "aic": "local-verification",
         "base_url": "http://127.0.0.1:8088", "verification_duration": 30},
    ]
    document = {"mode": "local-aip-stdio", "coordinator_aic": "local-coordinator", "python": sys.executable,
                "journal_path": "runtime/coordinator-journal.sqlite", "amp_directory": "artifacts/local-aip/amp",
                "term_journal_path": "runtime/coordinator-terms.sqlite",
                "approval_env_file": "runtime/private/approval.env", "llm_enabled": False, "workers": workers}
    path = directory / "local-coordinator.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(path))


if __name__ == "__main__":
    configure()
