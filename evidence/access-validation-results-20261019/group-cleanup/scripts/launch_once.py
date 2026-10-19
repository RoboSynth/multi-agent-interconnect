"""Retain exact outputs and actual terminal exit for the one authorized cleanup."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
directory = HERE / "execution"
directory.mkdir(exist_ok=False)
started = time.monotonic()
script = HERE / "close_owned_group.py"
(directory / "intent.json").write_text(json.dumps({
    "started_at": datetime.now(timezone.utc).isoformat(),
    "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    "user_question_id": "call_eed3d32ab9a1402ebcb0e50876f1ed1e",
    "exact_user_answer": "授权4次，确认七身份无其他消费者",
    "group_id": "group-incident-cef7f4c704374de1a376eab9ed086e60",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
completed = subprocess.run([sys.executable, str(script), "--execute"], capture_output=True)
(directory / "runner.stdout.bin").write_bytes(completed.stdout)
(directory / "runner.stderr.bin").write_bytes(completed.stderr)
receipt = {
    "terminal": True, "actual_exit_code": completed.returncode,
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "duration_seconds": round(time.monotonic() - started, 3),
    "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
}
(directory / "runner.exit.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt), flush=True)
raise SystemExit(completed.returncode)
