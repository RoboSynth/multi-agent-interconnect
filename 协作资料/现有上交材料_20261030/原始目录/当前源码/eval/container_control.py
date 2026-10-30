"""Separate evaluator process for fixed isolated-container read-only/pool controls."""
import argparse
import json
from pathlib import Path
import subprocess

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["readonly-on", "readonly-off", "status", "rebuild-pools"])
    parser.add_argument("--project", default="incident-pilot-container")
    parser.add_argument("--wsl")
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    if not args.project or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in args.project):
        raise ValueError("Invalid isolated project name")
    docker = ["wsl.exe", "-d", args.wsl, "--exec", "docker"] if args.wsl else ["docker"]
    def command(values):
        result = subprocess.run(docker + values, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError("Container evaluator command failed")
        return result.stdout.strip()
    target = args.project + "-postgres-1"
    record = json.loads(command(["inspect", target]))[0]
    labels = record["Config"].get("Labels") or {}
    if labels.get("incident-pilot") != "true" or labels.get("com.docker.compose.project") != args.project:
        raise ValueError("Target is not this isolated incident-pilot database")
    if args.action == "rebuild-pools":
        environment = {k.strip(): v.strip().strip('"').strip("'") for line in args.env_file.read_text(encoding="utf-8-sig").splitlines()
                       if "=" in line and not line.lstrip().startswith("#") for k, _, v in [line.partition("=")]}
        with httpx.Client(trust_env=False, timeout=10) as client:
            for key, default in (("APP_V1_PORT", "18081"), ("APP_V2_PORT", "18082")):
                port = int(environment.get(key, default))
                response = client.post(f"http://127.0.0.1:{port}/admin/pool/rebuild", json={},
                                       headers={"Authorization": "Bearer " + environment["APP_ADMIN_TOKEN"]})
                response.raise_for_status()
        print(json.dumps({"action": args.action, "passed": True}))
        return
    if args.action != "status":
        setting = "on" if args.action == "readonly-on" else "off"
        command(["exec", "-i", record["Id"], "psql", "-U", "postgres", "-d", "orders", "-v", "ON_ERROR_STOP=1", "-At", "-c",
                 "ALTER ROLE orders_app SET default_transaction_read_only = " + setting])
    value = command(["exec", "-i", record["Id"], "psql", "-U", "postgres", "-d", "orders", "-At", "-c",
        "SELECT setting FROM pg_db_role_setting s, LATERAL unnest(s.setconfig) setting "
        "WHERE s.setrole=(SELECT oid FROM pg_roles WHERE rolname='orders_app') AND setting LIKE 'default_transaction_read_only=%'"])
    print(json.dumps({"action": args.action, "read_only": value == "default_transaction_read_only=on", "passed": True}))


if __name__ == "__main__":
    main()
