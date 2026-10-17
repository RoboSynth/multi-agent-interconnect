"""Recreate local domain configs/secrets, MCP environment and ops supervisor."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
PRIVATE = RUNTIME / "private"


def preserve_secret(path, key):
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    values = dict(line.partition("=")[::2] for line in text.splitlines() if "=" in line)
    if key not in values:
        value = secrets.token_urlsafe(48)
        path.write_text(text.rstrip() + ("\n" if text else "") + key + "=" + value + "\n", encoding="utf-8")
        return value
    if len(values[key]) < 32:
        raise ValueError(f"Existing {key} is too short; replace it explicitly in its domain environment")
    return values[key]


def configure():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    preserve_secret(PRIVATE / "approval.env", "INCIDENT_APPROVAL_SECRET")
    ops_path = PRIVATE / "ops-bridge.env"
    if not ops_path.exists():
        ops_path.write_text("INCIDENT_OPS_BACKEND=native\n", encoding="utf-8")
    supervisor_token = preserve_secret(ops_path, "OPS_SUPERVISOR_TOKEN")
    base = {"allowed_callers": ["local-coordinator"], "approval_secret_env": "INCIDENT_APPROVAL_SECRET"}
    database = {**base, "executor_aic": "local-database-primary", "policy": "../domains/database/policy.yaml",
        "ledger_path": "database-operations.sqlite", "ledger_domain": "database", "audit_path": "database-amp-audit.jsonl",
        "env_files": ["private/approval.env", "private/database-bridge.env"],
        "servers": {"postgres": {"command": str(ROOT / ".venv-mcp-postgres/Scripts/postgres-mcp.exe"),
            "args": ["--access-mode=unrestricted"], "env_names": ["DATABASE_URI"], "timeout_seconds": 30}}}
    ops = {**base, "executor_aic": "local-ops", "policy": "../domains/ops/policy.native.yaml",
        "ledger_path": "ops-operations.sqlite", "ledger_domain": "ops", "audit_path": "ops-amp-audit.jsonl",
        "env_files": ["private/approval.env", "private/ops-bridge.env"], "servers": {}}
    for name, script in (("native", "native_mcp.py"), ("route", "route_mcp.py")):
        ops["servers"][name] = {"command": str(ROOT / ".venv/Scripts/python.exe"),
            "args": [str(ROOT / "domains/ops" / script)], "timeout_seconds": 30,
            "env": {"INCIDENT_OPS_BACKEND": "native"}}
    backup = {**database, "executor_aic": "local-database-backup"}
    for name, config in (("database-bridge", database), ("database-backup-bridge", backup), ("ops-bridge", ops)):
        path = RUNTIME / (name + ".json")
        if not path.exists():
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return supervisor_token


def supervisor_health(token):
    request = urllib.request.Request("http://127.0.0.1:8093/health", headers={"Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=1) as response:
            result = json.load(response)
        if result.get("service") != "incident-pilot-native-ops" or Path(result.get("project_root", "")).resolve() != ROOT:
            raise ValueError("Port 8093 belongs to another supervisor")
        return result
    except urllib.error.HTTPError as exc:
        if exc.code == 501 and (RUNTIME / "ops-supervisor.pid").exists():
            # Compatibility with the first local supervisor, which exposed
            # only POST /restart. Verify its live registered process identity.
            sys.path.insert(0, str(ROOT))
            from business.native_process import managed_process
            pid = int((RUNTIME / "ops-supervisor.pid").read_text(encoding="ascii"))
            if managed_process(pid, script_name=str(ROOT / "domains/ops/native_supervisor.py")):
                return {"ok": True, "service": "incident-pilot-native-ops", "pid": pid}
        raise ValueError("Port 8093 is occupied by a service that did not authenticate as this supervisor") from exc
    except urllib.error.URLError:
        return None


def start_supervisor(token):
    existing = supervisor_health(token)
    if existing:
        print("Native ops supervisor already running (identity checked).")
        return
    executable = ROOT / ".venv/Scripts/python.exe"
    with (RUNTIME / "ops-supervisor.stdout.log").open("ab") as out, (RUNTIME / "ops-supervisor.stderr.log").open("ab") as err:
        system_names = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "APPDATA",
                        "LOCALAPPDATA", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
                        "SYSTEMDRIVE", "HOMEDRIVE", "HOMEPATH", "USERNAME", "OS", "NUMBER_OF_PROCESSORS"}
        environment = {name: value for name, value in os.environ.items() if name.upper() in system_names}
        process = subprocess.Popen([str(executable), str(ROOT / "domains/ops/native_supervisor.py")],
            cwd=ROOT, env=environment, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    (RUNTIME / "ops-supervisor.pid").write_text(str(process.pid), encoding="ascii")
    for _ in range(30):
        if supervisor_health(token):
            print("Native ops supervisor started on 127.0.0.1:8093.")
            return
        time.sleep(0.2)
    raise RuntimeError("Native ops supervisor did not become ready; inspect runtime/ops-supervisor.stderr.log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Install isolated third-party PostgreSQL MCP environment")
    parser.add_argument("--provision-db", action="store_true", help="Create least-privilege bridge role using existing lab admin env")
    parser.add_argument("--start-supervisor", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This setup targets the local Windows experiment; use deploy/ for the container variant")
    token = configure()
    if args.install:
        directory = ROOT / ".venv-mcp-postgres"
        executable = directory / "Scripts/python.exe"
        if not executable.exists():
            venv.EnvBuilder(with_pip=True).create(directory)
        subprocess.run([str(executable), "-m", "pip", "install", "-r", str(ROOT / "domains/database/requirements.txt")], check=True)
    if args.provision_db:
        subprocess.run([str(ROOT / ".venv/Scripts/python.exe"), str(ROOT / "domains/database/provision_local.py")], check=True)
    if args.start_supervisor:
        start_supervisor(token)
    print("Local domain configs ready. Secrets were preserved/generated in runtime/private; no secret values printed.")


if __name__ == "__main__":
    main()
