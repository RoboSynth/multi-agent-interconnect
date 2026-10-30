"""Local ops-domain supervisor whose services survive MCP transport shutdown."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domains.ops.native_mcp import restart_registered_process

LOCK = threading.Lock()


def read_token():
    path = ROOT / "runtime/private/ops-bridge.env"
    records = dict(line.partition("=")[::2] for line in path.read_text(encoding="utf-8-sig").splitlines() if "=" in line)
    token = records.get("OPS_SUPERVISOR_TOKEN", "")
    if len(token) < 32:
        raise ValueError("Ops supervisor token must contain at least 32 characters")
    return token


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        expected = "Bearer " + self.server.domain_token
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.send_error(403)
            return
        if self.path not in {"/restart", "/shutdown"} or self.headers.get("Content-Length") != "2" or self.rfile.read(2) != b"{}":
            self.send_error(400)
            return
        shutdown = self.path == "/shutdown"
        if not LOCK.acquire(blocking=not shutdown):
            self.send_error(409, "Supervisor operation is still active")
            return
        try:
            if getattr(self.server, "shutdown_requested", False):
                result, code = {"error_class": "ShutdownInProgress"}, 409
            elif shutdown:
                self.server.shutdown_requested = True
                result, code = {"status": "SHUTDOWN_REQUESTED", "pid": os.getpid(), "project_root": str(ROOT)}, 200
            else:
                result = restart_registered_process()
                code = 200
        except Exception as exc:
            result, code = {"error_class": type(exc).__name__}, 500
        finally:
            LOCK.release()
        try:
            body = json.dumps(result).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        finally:
            if shutdown and code == 200:
                # An accepted shutdown must proceed even if its caller drops
                # the response. The caller still verifies actual process exit.
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self):
        if self.path != "/health" or not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + self.server.domain_token):
            self.send_error(403)
            return
        body = json.dumps({"ok": True, "service": "incident-pilot-native-ops", "pid": os.getpid(),
                           "project_root": str(ROOT)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8093), Handler)
    server.domain_token = read_token()
    try:
        server.serve_forever()
    finally:
        server.server_close()
