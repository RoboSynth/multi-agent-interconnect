"""Project-local, key-free Qwen inference using official portable llama.cpp.

python tools/local_model.py setup
python tools/local_model.py start
INCIDENT_LLM_BASE_URL=http://127.0.0.1:8089/v1
INCIDENT_LLM_MODEL=Qwen3-1.7B-Q8_0
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "tools/runtime/local-model"
MODEL = "Qwen3-1.7B-Q8_0.gguf"
MODEL_REVISION = "90862c4b9d2787eaed51d12237eafdfe7c5f6077"
RELEASE = "b11707"
ARCHIVE = f"llama-{RELEASE}-bin-win-vulkan-x64.zip"
SOURCES = {
    ARCHIVE: f"https://github.com/ggml-org/llama.cpp/releases/download/{RELEASE}/{ARCHIVE}",
    MODEL: f"https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/{MODEL_REVISION}/{MODEL}",
}


def setup():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    manifest = {"llama_release": RELEASE, "model_revision": MODEL_REVISION, "files": []}
    for name, url in SOURCES.items():
        target = RUNTIME / name
        if not target.is_file():
            temporary = target.with_suffix(target.suffix + ".download")
            print(f"Downloading {name}", flush=True)
            with urllib.request.urlopen(url, timeout=90) as source, temporary.open("wb") as output:
                length = source.headers.get("Content-Length")
                received = 0
                checkpoint = 0
                while chunk := source.read(4 * 1024 * 1024):
                    output.write(chunk)
                    received += len(chunk)
                    if received - checkpoint >= 128 * 1024 * 1024:
                        checkpoint = received
                        print(f"{name}: {received}/{length or '?'} bytes", flush=True)
                if length and received != int(length):
                    raise RuntimeError(f"Incomplete download: {name}")
            temporary.replace(target)
        with target.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        manifest["files"].append({"name": name, "source": url, "bytes": target.stat().st_size,
                                  "sha256": digest})
    binary_root = RUNTIME / RELEASE
    with zipfile.ZipFile(RUNTIME / ARCHIVE) as archive:
        for member in archive.infolist():
            resolved = (binary_root / member.filename).resolve()
            if not resolved.is_relative_to(binary_root.resolve()):
                raise ValueError("Archive contains an unsafe path")
        archive.extractall(binary_root)
    (RUNTIME / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest), flush=True)


def status(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
        return json.load(response)


def start(port):
    binary = RUNTIME / RELEASE / "llama-server.exe"
    if not binary.is_file() or not (RUNTIME / MODEL).is_file():
        raise RuntimeError("Run setup first")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Port {port} is already occupied")
    args = [str(binary), "--model", str(RUNTIME / MODEL), "--alias", "Qwen3-1.7B-Q8_0",
            "--host", "127.0.0.1", "--port", str(port), "--ctx-size", "8192",
            "--n-gpu-layers", "99", "--parallel", "1", "--jinja", "--reasoning", "off",
            "--no-webui", "--cors-origins", f"http://127.0.0.1:{port}"]
    log = RUNTIME / "server.log"
    with log.open("ab") as output:
        child = subprocess.Popen(args, cwd=RUNTIME, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"Model server exited {child.returncode}; see {log}")
        try:
            health = status(port)
            info = {"pid": child.pid, "started_at": datetime.now(timezone.utc).isoformat(),
                    "base_url": f"http://127.0.0.1:{port}/v1", "model": "Qwen3-1.7B-Q8_0",
                    "health": health, "manifest": str(RUNTIME / "manifest.json")}
            (RUNTIME / "server.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
            print(json.dumps(info))
            return
        except (OSError, ValueError):
            time.sleep(1)
    raise RuntimeError(f"Model readiness timed out; see {log}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "start", "status"])
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()
    if args.action == "setup":
        setup()
    elif args.action == "start":
        start(args.port)
    else:
        print(json.dumps(status(args.port)))
