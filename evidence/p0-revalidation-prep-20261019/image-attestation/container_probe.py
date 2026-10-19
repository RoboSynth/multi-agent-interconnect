"""No-network, read-only image source/dependency attestation, never a worker."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

EXPECTED_SOURCES = __EXPECTED_SOURCES__
SDK_PREFIX = "vendor/ACPs-community/acps-sdk/acps_sdk/"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert os.getuid() == os.getgid() == 65534
    assert os.getpid() > 1, "--init must keep this Python outside namespace PID 1"
    assert os.statvfs("/").f_flag & os.ST_RDONLY
    interfaces = sorted(p.name for p in Path("/sys/class/net").iterdir())
    assert interfaces == ["lo"]
    assert not any(Path(p).exists() for p in ("/domain", "/experiment", "/srv/runtime", "/srv/integration/private"))
    sensitive_names = [k for k in os.environ if k.upper().startswith("PG") or k.upper() in {
        "DATABASE_URI", "DATABASE_URL", "APP_ADMIN_TOKEN", "POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD",
        "BRIDGE_DB_PASSWORD", "INCIDENT_APPROVAL_SECRET", "OPS_SUPERVISOR_TOKEN", "DOCKER_HOST",
        "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY", "INCIDENT_LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"
    } or k.upper().endswith(("_API_KEY", "_TOKEN", "_PASSWORD", "_SECRET"))]
    assert not sensitive_names, "Resource/credential environment must be absent"
    actual_sources = {name: digest(Path("/srv") / name) for name in EXPECTED_SOURCES}
    assert actual_sources == EXPECTED_SOURCES, "Copied source differs from the exact checkout"
    installed_sources = {}
    for name, expected in EXPECTED_SOURCES.items():
        if not name.startswith(SDK_PREFIX) or not name.endswith(".py"):
            continue
        module_name = "acps_sdk." + name[len(SDK_PREFIX):-3].replace("/", ".")
        module = importlib.import_module(module_name)
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(Path("/usr/local/lib/python3.12/site-packages")), "SDK must use installed copy"
        actual = digest(path)
        assert actual == expected, "Installed SDK source differs from checkout/vendor copy"
        installed_sources[module_name] = {"path": str(path), "sha256": actual}
    imported = {}
    for name in ("incident.platform_worker", "incident.local_worker", "acps_mcp_bridge.experiment",
                 "business.load", "business.receipts", "domains.ops.route_mcp", "workbench_server"):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(Path("/srv"))
        imported[name] = str(path)
    environments = {}
    for label, interpreter, distribution in (
        ("main", sys.executable, "acps-sdk"),
        ("postgres_mcp", "/opt/postgres-mcp/bin/python", "postgres-mcp"),
        ("docker_mcp", "/opt/docker-mcp/bin/python", "mcp-server-docker"),
    ):
        code = r'''
import importlib, importlib.metadata as md, json, sys
label, distribution = sys.argv[1:]
packages = {d.metadata["Name"]: d.version for d in md.distributions()}
d = md.distribution(distribution)
entrypoints = [e for e in d.entry_points if e.group == "console_scripts"]
imports = {}
if label != "main":
    assert entrypoints, "MCP distribution must provide a console entry point"
    for e in entrypoints:
        module_name = e.value.split(":", 1)[0]
        module = importlib.import_module(module_name)
        imports[module_name] = module.__file__
parse = None
if label == "postgres_mcp":
    import pglast
    assert md.version("pglast") == "7.2"
    parsed = pglast.parse_sql("SELECT 1")
    assert len(parsed) == 1
    parse = {"statement": "SELECT 1", "statement_count": len(parsed), "pglast_version": md.version("pglast")}
print(json.dumps({"python_version": sys.version, "executable": sys.executable,
    "packages": packages, "entry_point_imports": imports, "parse_sql": parse}))
'''
        proc = subprocess.run([interpreter, "-B", "-c", code, label, distribution], capture_output=True, timeout=45)
        assert proc.returncode == 0, f"{label} dependency/import probe exited {proc.returncode}"
        info = json.loads(proc.stdout.decode("utf-8"))
        info["import_probe_exit_code"] = proc.returncode
        info["import_stderr_sha256"] = hashlib.sha256(proc.stderr).hexdigest()
        info["import_stderr_bytes"] = len(proc.stderr)
        check = subprocess.run([interpreter, "-B", "-m", "pip", "check"], capture_output=True, timeout=45)
        info["pip_check"] = {"exit_code": check.returncode, "stdout": check.stdout.decode("utf-8"),
            "stderr_bytes": len(check.stderr), "stderr_sha256": hashlib.sha256(check.stderr).hexdigest()}
        environments[label] = info
        assert check.returncode == 0, f"{label} pip check exited {check.returncode}"
    print(json.dumps({"passed": True, "uid": os.getuid(), "gid": os.getgid(), "pid": os.getpid(),
        "root_read_only": True, "network_interfaces": interfaces, "resource_credential_environment_name_count": 0,
        "source_sha256": actual_sources, "source_count": len(actual_sources), "installed_sdk_sources": installed_sources,
        "loaded_import_paths": imported, "environments": environments,
        "participant_or_server_started": False, "platform_or_model_or_database_connections": 0,
        "scope": "Offline immutable image, imports, dependency checks and SELECT 1 parsing; not runtime acceptance"}))


if __name__ == "__main__":
    main()
