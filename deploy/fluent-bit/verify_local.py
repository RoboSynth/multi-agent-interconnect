"""Actual portable Fluent Bit tail → six tagged stdout routes, with no Kafka."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import KINDS, render


async def emit_examples(directory):
    from acps_sdk.aip import TaskCommand, TaskCommandType, StructuredDataItem
    from acps_sdk.amp.group_access import GroupAccessMiddleware
    from incident.amp_setup import AmpRuntime
    from incident.local_transport import emit_message
    amp = AmpRuntime(directory, "routing", "local-routing-fixture")
    await amp.heartbeat.emit()
    await amp.metrics.emit()
    await amp.system.emit({"event": "local_routing_fixture"})
    amp.audit_event({"incident_id": "routing-fixture", "tool": "fixture.observe", "status": "ok"})
    command = TaskCommand(id="routing-message", sentAt=datetime.now(timezone.utc).isoformat(), senderRole="leader",
        senderId="local-routing-fixture", groupId="routing-group", sessionId="routing-fixture", taskId="routing-task",
        mentions=["local-routing-fixture"], command=TaskCommandType.Start,
        dataItems=[StructuredDataItem(data={"tool": "fixture.observe"})])
    await emit_message(amp.message, command, "send", "routing-only")
    async def success():
        return {"status": "ok"}
    await GroupAccessMiddleware(amp.access, amp.aic).run(command, success)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    executable = args.executable or next((ROOT / "tools/runtime/fluent-bit-5.1.3").rglob("fluent-bit.exe"))
    output = ROOT / "output" / ("fluent-bit-local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    logs, state = output / "inputs", output / "state"
    logs.mkdir(parents=True, exist_ok=False)
    state.mkdir()
    asyncio.run(emit_examples(logs))
    config = output / "stdout.conf"
    rendered = render(logs, state, Path(__file__).with_name("parsers.conf"), read_from_head=True)
    rendered = rendered.replace("    Read_From_Head True", "    Read_From_Head True\n    Exit_On_Eof True")
    config.write_text(rendered, encoding="utf-8")
    process = subprocess.Popen([str(executable), "-c", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    stdout, stderr = stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    (output / "stdout.log").write_text(stdout, encoding="utf-8")
    (output / "stderr.log").write_text(stderr, encoding="utf-8")
    observed = {kind: len(re.findall(r"\] amp\." + kind + r":", stdout)) for kind in KINDS}
    records = {kind: json.loads((logs / f"amp_{kind}_routing.jsonl").read_text(encoding="utf-8").splitlines()[0]) for kind in KINDS}
    preserved = {kind: record["log_id"] in stdout for kind, record in records.items()}
    result = {"passed": all(value == 1 for value in observed.values()) and all(preserved.values()),
        "executable": str(executable), "source": "official Windows portable ZIP, Fluent Bit 5.1.3",
        "routes_observed": observed, "log_ids_preserved": preserved, "synthetic_local_fixture": True,
        "returncode": process.returncode,
        "kafka_connected": False, "platform_ingestion_tested": False}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "output": str(output), "routes_observed": observed}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
