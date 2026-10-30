"""Match exact captured native AIP starts to one access per sending/receiving agent."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def platform_pairing(records, *, task_ids=None, expected_participants=None):
    """Conservative local taskId pairing, independent of lifecycle success."""
    expected = set(task_ids) if task_ids is not None else None
    endpoints, actors = defaultdict(Counter), defaultdict(set)
    invalid, unrelated = 0, 0
    for record in records:
        if not isinstance(record, dict):
            invalid += 1
            continue
        task = record.get("correlation_id", record.get("correlationId"))
        if not isinstance(task, str) or not task:
            invalid += 1
            continue
        if expected is not None and task not in expected:
            unrelated += 1
            continue
        body = record.get("body")
        request = body.get("request") if isinstance(body, dict) else None
        caller = body.get("caller") if isinstance(body, dict) else None
        callee = body.get("callee") if isinstance(body, dict) else None
        caller = caller.get("aic") if isinstance(caller, dict) else None
        callee = callee.get("aic") if isinstance(callee, dict) else None
        actor = record.get("aic")
        if (not isinstance(request, dict) or request.get("method") != "start"
                or any(not isinstance(value, str) or not value for value in (caller, callee, actor))
                or caller == callee or callee.startswith("group:") or actor not in {caller, callee}):
            invalid += 1
            continue
        if expected_participants is not None and expected_participants.get(task) != (caller, callee):
            invalid += 1
            continue
        actors[task].add((caller, callee))
        endpoints[(task, caller, callee)][actor] += 1
    tasks = expected if expected is not None else set(actors)
    paired, missing, duplicate, conflicting = [], [], [], []
    for task in sorted(tasks):
        pairs = actors[task]
        if len(pairs) > 1:
            conflicting.append(task)
        elif len(pairs) == 1:
            caller, callee = next(iter(pairs))
            counts = endpoints[(task, caller, callee)]
            if any(counts[actor] > 1 for actor in (caller, callee)):
                duplicate.append(task)
            elif counts[caller] == counts[callee] == 1:
                paired.append(task)
            else:
                missing.append(task)
        else:
            missing.append(task)
    return {"task_count": len(tasks), "paired_task_count": len(paired),
            "pairing_rate": len(paired) / len(tasks) if tasks else None,
            "paired_task_ids": paired, "missing_endpoint_task_ids": missing,
            "duplicate_endpoint_task_ids": duplicate, "conflicting_task_ids": conflicting,
            "invalid_access_records": invalid, "unrelated_access_records_excluded": unrelated,
            "passed": bool(tasks) and len(paired) == len(tasks) and invalid == 0,
            "platform_ingestion_confirmed": None,
            "scope": "Local access records only: exactly one caller and one callee Start per taskId, with matching participant AICs. Duplicates/conflicts are excluded; pairing does not establish task success or Monitor ingestion."}


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
    actual, unrelated, records = Counter(), 0, []
    for path in Path(amp_directory).rglob("amp_access_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            records.append(record)
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
            "platform_pairing": platform_pairing(records, task_ids=starts, expected_participants=starts),
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
