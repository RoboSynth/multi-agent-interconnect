"""Small MCP server for registered Nginx route versions in this experiment."""
from __future__ import annotations

import os
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("incident-pilot-route")
ROOT = Path(__file__).resolve().parents[2]
ROUTE = Path(os.environ.get("INCIDENT_ROUTE_FILE", ROOT / "runtime/nginx/conf/route.conf")).resolve()
NATIVE = os.environ.get("INCIDENT_OPS_BACKEND", "native") == "native"
VERSIONS = {"v1": "127.0.0.1:8081", "v2": "127.0.0.1:8082"} if NATIVE else {"v1": "app-v1:8000", "v2": "app-v2:8000"}


def native_configuration():
    path = ROOT / "deploy/native-runtime.json"
    config = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if os.name == "nt" and config.get("native_drive"):
        drive = config["native_drive"]
        if not re.fullmatch(r"[D-Z]:", drive, re.I):
            raise ValueError("Native Nginx drive must be an experiment data-drive letter")
        if not Path(drive + "/").exists():
            subprocess.run(["subst.exe", drive, str(ROOT)], check=True, capture_output=True, timeout=5)
        if not (Path(drive + "/") / "domains/ops/route_mcp.py").samefile(Path(__file__)):
            raise ValueError("Nginx drive is mapped to another workspace")
    return config


@mcp.tool()
def route_status() -> dict:
    text = ROUTE.read_text(encoding="utf-8")
    versions = [version for version, upstream in VERSIONS.items()
                if re.search(r"set\s+\$order_upstream\s+" + re.escape(upstream) + r"\s*;", text)]
    return {"route_version": versions[0] if len(versions) == 1 else "unknown"}


@mcp.tool()
def route_rollback(target_version: str = "v2") -> dict:
    if target_version not in VERSIONS:
        raise ValueError("Route version is not registered")
    # Paths/commands are local configuration; remote data selects only a version.
    original = ROUTE.read_text(encoding="utf-8")
    new, count = re.subn(r"set\s+\$order_upstream\s+[^;\r\n]+;",
                        lambda _: "set $order_upstream " + VERSIONS[target_version] + ";", original)
    if count != 1:
        raise ValueError("Route file must contain exactly one registered upstream setting")
    native = native_configuration() if NATIVE else {}
    reload_binary = os.environ.get("INCIDENT_NGINX_BINARY", native.get("nginx_bin", "docker"))
    nginx_container = os.environ.get("INCIDENT_NGINX_CONTAINER", "incident-pilot-nginx")
    if Path(reload_binary).name.lower() in {"docker", "docker.exe"}:
        inspect_run = subprocess.run([reload_binary, "inspect", "--format", '{{index .Config.Labels "incident-pilot"}}',
                                      nginx_container], capture_output=True, text=True, timeout=5, check=True)
        if not inspect_run.stdout.strip() or "<no value>" in inspect_run.stdout:
            raise ValueError("Nginx container lacks experiment label")
        reload_command = [reload_binary, "exec", nginx_container, "nginx", "-s", "reload"]
        validate_command = [reload_binary, "exec", nginx_container, "nginx", "-t"]
    else:
        prefix = Path(os.environ.get("INCIDENT_NGINX_PREFIX", native.get("nginx_prefix", ROOT / "runtime/nginx"))).as_posix().rstrip("/") + "/"
        reload_command = [reload_binary, "-p", prefix, "-s", "reload"]
        validate_command = [reload_binary, "-p", prefix, "-t"]
    try:
        ROUTE.write_text(new, encoding="utf-8")
        subprocess.run(validate_command, capture_output=True, timeout=10, check=True)
        subprocess.run(reload_command, capture_output=True, timeout=10, check=True)
        # Nginx acknowledges reload before old workers have drained. Confirm
        # the actual public route using fresh connections, not the signal exit.
        deadline = time.monotonic() + 8
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base_url = os.environ.get("INCIDENT_ORDER_BASE_URL") or (
            f"http://127.0.0.1:{native.get('order_port', 8088)}" if NATIVE else "http://nginx")
        endpoint = base_url.rstrip("/") + "/health"
        while True:
            try:
                request = urllib.request.Request(endpoint, headers={"Connection": "close"})
                with opener.open(request, timeout=1) as response:
                    if json.load(response).get("api_version") == target_version:
                        break
            except (OSError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Public Nginx route did not converge to the registered version")
            time.sleep(0.2)
    except BaseException:
        ROUTE.write_text(original, encoding="utf-8")
        try:
            subprocess.run(reload_command, capture_output=True, timeout=10, check=True)
        except Exception:
            pass
        raise
    return route_status()


if __name__ == "__main__":
    mcp.run(transport="stdio")
