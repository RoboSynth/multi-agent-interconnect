"""Initialize the project's loopback-only PostgreSQL without Windows services.

Secrets are generated into domain-local env files, never printed or placed in
coordinator configuration. Re-running reuses the existing identities/passwords.
"""
from pathlib import Path
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runtime/private"
ENVIRONMENT = {
    "postgres-superuser": {"PGUSER": "postgres"},
    "application": {"PGUSER": "orders_app"},
    "database": {"PGUSER": "orders_agent"},
}


def read_env(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#"))


def native_root():
    result = ROOT
    root = ROOT.resolve()
    if os.name == "nt" and not str(root).isascii():
        # Defer this filesystem change until existing-cluster identities pass.
        temporary = Path(tempfile.gettempdir())
        legacy = temporary / "incident-pilot-runtime-01a148fe"
        try:
            if os.path.lexists(legacy) and legacy.resolve() == root:
                return legacy
        except (OSError, RuntimeError):
            pass  # An unrelated or unresolvable legacy alias is never changed.
        identity = os.path.normcase(str(root))
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        result = temporary / ("incident-pilot-runtime-" + suffix)
        if not os.path.lexists(result):
            command = "New-Item -ItemType Junction -Path '" + str(result).replace("'", "''") + "' -Target '" + str(root).replace("'", "''") + "' | Out-Null"
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], check=True)
        if result.resolve() != root:
            raise RuntimeError("runtime alias does not target this project")
    return result


def prepare():
    runtime_file = ROOT / "deploy/native-runtime.json"
    runtime = json.loads(runtime_file.read_text(encoding="utf-8-sig")) if runtime_file.exists() else {}
    selected_data = Path(runtime.get("pgdata", ROOT / "runtime/pgdata"))
    if not selected_data.is_absolute():
        selected_data = ROOT / selected_data
    missing = [name for name in ENVIRONMENT if not (PRIVATE / (name + ".env")).is_file()]
    if (selected_data / "PG_VERSION").exists() and missing:
        raise RuntimeError("Existing PostgreSQL cluster is missing identity env files: " + ", ".join(missing)
                           + ". Restore the matching files before preparation; no passwords were generated.")
    native = native_root()
    runtime.setdefault("postgres_bin", str(native / "tools/runtime/pgsql/bin"))
    runtime.setdefault("pgdata", str(native / "runtime/pgdata"))
    bin_path, data = (Path(runtime[name]) for name in ("postgres_bin", "pgdata"))
    if not bin_path.is_absolute():
        bin_path = ROOT / bin_path
    if not data.is_absolute():
        data = ROOT / data
    PRIVATE.mkdir(parents=True, exist_ok=True)
    domains = {}
    for domain, values in ENVIRONMENT.items():
        path = PRIVATE / (domain + ".env")
        if path.exists():
            domains[domain] = read_env(path)
            continue
        env = {"PGHOST": "127.0.0.1", "PGPORT": "55432", "PGDATABASE": "orders",
               **values, "PGPASSWORD": secrets.token_urlsafe(32)}
        if domain == "application":
            env["APP_ADMIN_TOKEN"] = secrets.token_urlsafe(32)
        path.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
        domains[domain] = env
    admin = domains["postgres-superuser"]
    if not (data / "PG_VERSION").exists():
        password_file = PRIVATE / "initdb-password.txt"
        password_file.write_text(admin["PGPASSWORD"], encoding="utf-8")
        try:
            subprocess.run([str(bin_path / "initdb.exe"), "-D", str(data), "-U", "postgres",
                "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C",
                "--pwfile=" + str(native / "runtime/private/initdb-password.txt")], check=True)
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run([str(bin_path / "pg_ctl.exe"), "status", "-D", str(data)], capture_output=True)
    if status.returncode:
        # pg_ctl cannot create another restricted token when already inside the
        # Codex sandbox. Run the same server directly under the current token.
        log_path = native / "runtime/postgres.log"
        with log_path.open("ab") as log:
            process = subprocess.Popen([str(bin_path / "postgres.exe"), "-D", str(data),
                "-p", "55432", "-h", "127.0.0.1"], stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for _ in range(60):
            ready = subprocess.run([str(bin_path / "pg_isready.exe"), "-h", "127.0.0.1", "-p", "55432"], capture_output=True)
            if ready.returncode == 0:
                break
            if process.poll() is not None:
                raise RuntimeError("local PostgreSQL exited; inspect runtime/postgres.log")
            time.sleep(.25)
        else:
            raise TimeoutError("local PostgreSQL did not start")
    env = {**os.environ, **admin, "PGDATABASE": "postgres"}

    def sql(statement, database="postgres"):
        result = subprocess.run([str(bin_path / "psql.exe"), "-X", "-v", "ON_ERROR_STOP=1", "-At",
            "-d", database], input=statement, env=env, text=True, encoding="utf-8", capture_output=True)
        if result.returncode:
            # Do not include SQL/passwords in errors.
            raise RuntimeError("database preparation command failed: " + result.stderr.splitlines()[0])
        return result.stdout

    for domain in ("application", "database"):
        item = domains[domain]
        role, password = item["PGUSER"], item["PGPASSWORD"]
        if sql(f"SELECT 1 FROM pg_roles WHERE rolname='{role}';").strip() != "1":
            sql(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;")
    if sql("SELECT 1 FROM pg_database WHERE datname='orders';").strip() != "1":
        sql("CREATE DATABASE orders OWNER orders_agent;")
    sql((ROOT / "business/order_app/schema.sql").read_text(encoding="utf-8"), "orders")
    sql("""REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE orders TO orders_app, orders_agent;
GRANT USAGE ON SCHEMA public TO orders_app, orders_agent;
GRANT SELECT,INSERT,UPDATE ON orders TO orders_app;
GRANT SELECT,INSERT ON operation_receipts TO orders_app;
GRANT SELECT ON orders, operation_receipts TO orders_agent;
GRANT pg_read_all_stats, pg_signal_backend TO orders_agent;
""", "orders")
    summary = {"host": "127.0.0.1", "port": 55432, "database": "orders",
               "data_directory": str(data), "secrets_directory": str(PRIVATE),
               "roles": {k: v["PGUSER"] for k, v in domains.items()}}
    (ROOT / "runtime/database-setup.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    runtime.setdefault("nginx_bin", str(native / "tools/runtime/nginx-1.30.6/nginx.exe"))
    runtime.setdefault("nginx_prefix", str(native / "runtime/nginx"))
    runtime_file.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    prepare()
