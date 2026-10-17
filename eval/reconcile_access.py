"""Match exact captured native AIP starts to one access per sending/receiving agent."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def reconcile(messages_file, amp_directory, *, transport="local-aip-stdio"):
    starts, states = {}, defaultdict(set)
    for line in Path(messages_file).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        message = row["message"]
        if row["direction"] == "send" and message.get("type") == "task-command" and message.get("command") == "start":
            starts[message["taskId"]] = (message["senderId"], row["worker_aic"])
        if row["direction"] == "receive" and message.get("type") == "task-result":
            states[message["taskId"]].add(message["status"]["state"])
    expected = Counter((actor, task_id) for task_id, actors in starts.items() for actor in actors)
    actual, unrelated = Counter(), 0
    for path in Path(amp_directory).rglob("amp_access_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if transport == "wutong-amqps" and record.get("correlation_id") not in starts:
                unrelated += 1
                continue
            actual[(record["aic"], record.get("correlation_id"))] += 1
    missing, extra = expected-actual, actual-expected
    required = {"accepted", "working", "awaiting-completion", "completed"}
    incomplete = [task_id for task_id in starts if not required <= states[task_id]]
    return {"captured_start_tasks": len(starts), "transport": transport,
            "expected_access_records": sum(expected.values()),
            "actual_access_records": sum(actual.values()), "missing_records": sum(missing.values()),
            "extra_records": sum(extra.values()), "incomplete_task_lifecycles": incomplete,
            "unrelated_access_records_excluded": unrelated,
            "passed": bool(starts) and not missing and not extra and not incomplete,
            "scope": "Exact captured starts versus both endpoints' AMP access records. Shared long-running domain logs are filtered by captured taskId only for wutong-amqps; no Monitor statistics inferred."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("messages", type=Path)
    parser.add_argument("amp", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--transport", choices=["local-aip-stdio", "wutong-amqps"], default="local-aip-stdio")
    args = parser.parse_args()
    result = reconcile(args.messages, args.amp, transport=args.transport)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
