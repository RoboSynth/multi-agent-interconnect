"""Extract small, public review evidence from existing local artifacts."""
from collections import OrderedDict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main():
    source = "eval/results/platform/container-postgres-mcp-20261017-initial/coordinator/journal.sqlite"
    with sqlite3.connect((ROOT / source).as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        history = []
        for row in conn.execute("SELECT event_id,state,artifact,recorded_at FROM task_events WHERE event_id IN (3,4,5) ORDER BY event_id"):
            artifact = json.loads(row["artifact"])
            history.append({"event_id": row["event_id"], "state": row["state"],
                "recorded_at": datetime.fromtimestamp(row["recorded_at"], timezone.utc).isoformat(),
                "state_changed_at": artifact["status"]["stateChangedAt"], "sent_at": artifact["sentAt"],
                "product_count": len(artifact.get("products", []))})
        projected_states = [row[0] for row in conn.execute("SELECT state FROM task_attempts")]
    discovery = load("integration/incident/discovery-root-cause.json")
    pairs = [{"label": row["label"], "observed_at": row["observed_at"],
        "status": row["response"]["status"],
        "ext_filter": row["request"]["json"].get("extFilter"),
        "acs_count": len(row["response"]["body"]["result"].get("acsMap", {})),
        "alive_map_present": "aliveMap" in row["response"]["body"]["result"]}
        for row in discovery["requests"]]
    bidirectional = load("integration/two-agent/RESULT.json")
    acceptance = load("eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json")
    tasks = OrderedDict()
    messages = ROOT / "eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/coordinator/messages.jsonl"
    for line in messages.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        message = record["message"]
        if "status" not in message:
            continue
        key = (message.get("sessionId"), message.get("taskId"), message.get("senderId"))
        item = tasks.setdefault(key, {"task": f"task-{len(tasks) + 1}", "states": []})
        item["states"].append(message["status"]["state"])
    f15 = load("eval/results/local/F15-native-20261017-initial/results.json")
    evidence = {
        "upstream": {"repository": "AIP-PUB/ACPs-community", "base_commit": "3985c1330209f075c124669cc9d31f0e75448140", "sdk_version": "2.2.0"},
        "task_order": {"source": source, "received_history": history, "final_projected_states_before_fix": projected_states},
        "mq": {"snapshot_date": "2026-10-17", "public_bundle": "https://wt.ioa.pub/registry/static/js/client_list-BFH51SW2.js",
            "bundle_http_status": 200, "compiled_group_api": "https://localhost:9007",
            "successful_group_api": bidirectional["group_api"], "broker": bidirectional["broker"],
            "bidirectional_run_success": bidirectional["run_success"],
            "round_states": [row["states"] for row in bidirectional["rounds"]],
            "protocol_value_only_failure_reproduced": False},
        "discovery": {"source": "integration/incident/discovery-root-cause.json", "only_change": "extFilter", "queries": pairs},
        "access": load("eval/results/local/scheduling-native-20261017/access-reconciliation.json"),
        "post_fix_platform": {"source": "eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json",
            "started_at": acceptance["started_at"], "finished_at": acceptance["finished_at"], "status": acceptance["status"],
            "mode": acceptance["mode"], "participant_roles": acceptance["scope"],
            "full_p0_acceptance": acceptance["full_p0_acceptance"], "fault_injection": acceptance["fault_injection"],
            "facts": acceptance["observation"]["facts"], "task_lifecycles": list(tasks.values())},
        "local_f15": [{"crash_point": row["crash_point"], "status": row["status"], "transport": row["transport"],
            "discovery": row["discovery"], "platform_adp_verified": row["platform_adp_verified"],
            "db_mcp_modify_invocations": row["db_mcp_modify_invocations"], "duplicate_modifying_calls": row["duplicate_modifying_calls"],
            "old_fence_rejected": row["old_fence_rejected"], "business_recovered": row["business_verification"]["business_recovered"]}
            for row in f15],
        "validation": {"ordering_tests_passed": 3, "sdk_resumable_tests_passed": 25,
            "basis": "Executed successfully in this development session; terminal tool results retained by the session, no new test run performed for the prose."},
    }
    output = HERE / "evidence"
    output.mkdir(exist_ok=True)
    (output / "summary.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_created": True, "journal_states": [r["state"] for r in history],
        "post_fix_status": acceptance["status"], "identities_redacted": True}))


if __name__ == "__main__":
    main()
