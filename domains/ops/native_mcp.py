"""MCP tools restricted to this project's registered native app-v2 process."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from business.native_process import managed_process
RUNTIME = ROOT / "deploy/native-runtime.json"
mcp = FastMCP("incident-pilot-native-ops")


def configuration():
    config = json.loads(RUNTIME.read_text(encoding="utf-8-sig"))
    if Path(config["project_root"]).resolve() != ROOT or config.get("backend") != "native":
        raise ValueError("Native runtime does not belong to this experiment")
    if Path(config["app_python"]).resolve() != ROOT / ".venv/Scripts/python.exe":
        raise ValueError("Native interpreter is not the registered experiment interpreter")
    return config


@mcp.tool()
def process_status() -> dict:
    config = configuration()
    pid = config.get("managed", {}).get("v2")
    record = managed_process(pid, script_name="run_app.py", version="v2") if pid else None
    return {"backend": "native", "container_state": "running" if record else "exited", "pid": pid,
            "registered_name": "app-v2"}


@mcp.tool()
def process_restart() -> dict:
    # The MCP SDK owns its stdio child job on Windows. Persistent applications
    # must be started by the separately managed resource-domain supervisor.
    values = {}
    for line in (ROOT / "runtime/private/ops-bridge.env").read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator:
            values[name] = value.strip()
    token = values.get("OPS_SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Native ops supervisor token is not provisioned")
    request = urllib.request.Request("http://127.0.0.1:8093/restart", data=b"{}", method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=20) as response:
        return json.load(response)


def restart_registered_process() -> dict:
    config = configuration()
    pid = config.get("managed", {}).get("v2")
    if pid:
        managed_process(pid, script_name="run_app.py", version="v2", terminate=True)
    secret_path = ROOT / "runtime/private/application.env"
    system_names = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "APPDATA",
                    "LOCALAPPDATA", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
                    "SYSTEMDRIVE", "HOMEDRIVE", "HOMEPATH", "USERNAME", "OS", "NUMBER_OF_PROCESSORS"}
    environment = {name: value for name, value in os.environ.items() if name.upper() in system_names}
    for line in secret_path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name in {"PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "APP_ADMIN_TOKEN"}:
            environment[name] = value.strip().strip('"').strip("'")
    environment.update(PGHOST="127.0.0.1", PGPORT=str(config["pgport"]), PGDATABASE="orders", PGUSER="orders_app")
    with (ROOT / "runtime/v2.stdout.log").open("ab") as stdout, (ROOT / "runtime/v2.stderr.log").open("ab") as stderr:
        process = subprocess.Popen([config["app_python"], str(ROOT / "business/run_app.py"), "--version", "v2",
            "--port", str(config["app_v2_port"])], cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW)
    config.setdefault("managed", {})["v2"] = process.pid
    temporary = RUNTIME.with_name(RUNTIME.name + ".ops.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(RUNTIME)
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{config['app_v2_port']}/ready", timeout=1) as response:
                if json.load(response).get("ok"):
                    return process_status()
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Registered experiment app-v2 did not become ready")


if __name__ == "__main__":
    mcp.run(transport="stdio")
