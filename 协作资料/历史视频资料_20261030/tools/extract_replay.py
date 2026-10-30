"""Extract the real cloud F10 run (17 AIP tasks) from its two-sided access logs.

Source: evidence/cloud-four-revalidation-20261020/audit/f10-m0-r1/access/*.jsonl
Each task: the coordinator's send record (start) and the callee's record (end).
Usage: python extract_replay.py <team-repo-root> <output.json>
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROLES = {"0WS5": "app", "116V": "db", "0DY5": "ops", "0HIQ": "ver"}


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main(root, output):
    base = Path(root) / "evidence/cloud-four-revalidation-20261020/audit/f10-m0-r1/access"
    sends, ends, sources = {}, {}, {}
    for path in sorted(base.glob("*.jsonl")):
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            body = record["body"]
            key = record["correlation_id"]
            row = {"time": parse(record["timestamp"]), "route": body["request"]["route"],
                   "callee": body["callee"]["aic"], "status": body["response"]["statusCode"]}
            (sends if body["callee"]["aic"] != record["aic"] else ends)[key] = row
    t0 = min(row["time"] for row in sends.values())
    tasks = []
    for key, send in sorted(sends.items(), key=lambda kv: kv[1]["time"]):
        end = ends[key]
        tasks.append({"task": key, "route": send["route"], "domain": ROLES[send["callee"][-4:]],
                      "start": round((send["time"] - t0).total_seconds(), 3),
                      "end": round((end["time"] - t0).total_seconds(), 3), "status": end["status"]})
    Path(output).write_text(json.dumps({
        "incident": "cloud F10 / M0, batch cloud-four-20261020, Wutong AMQPS",
        "t0_utc": t0.isoformat(), "tasks": tasks, "paired": len(tasks),
        "source_files_sha256": sources}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(tasks), "tasks from", t0.isoformat())


if __name__ == "__main__":
    main(*sys.argv[1:])
