"""Normally close exactly one attested group left by the authorized four-case batch."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import ssl
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH / "checkout"
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk"), str(BATCH / "plan-preparation")]
import batch_scope
from eval import platform_resume_experiment as e1

KEY = "e1a-before_modification-r1"
SESSION = "incident-cef7f4c704374de1a376eab9ed086e60"
GROUP = "group-" + SESSION
UNKNOWN_SESSION = "incident-7bed224810f3458b8e32433dcdfa1744"
PROJECT = "incident-pilot-access-validation-20261019"
AIC = "1.2.156.3088.1.BUPT.8N4WSS.C5CSM6.2MXPZ1.19CW"
FAILED = ROOT / "eval/results/platform/access-validation-20261019" / KEY
PLAN = ROOT / "runtime/private/access-validation-plans-20261019" / KEY / "plan.json"
AUTH = BATCH / "execution/batch-authorization.json"
SUMMARY = BATCH / "plan-preparation/prepared-summary.json"
EFFECTS = [
    "Connect the original coordinator certificate to its original AMQPS endpoint without consuming",
    "Bind only the recorded existing cef7 group/session; create no group, queue, Inbox, worker or task",
    "Call official dissolve_group_session once: DISBAND, delete this group's ACL, leader queue and exchange",
    "Close the connection and preserve failed-run records, journals, stopped containers and volumes",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(value):
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT.resolve()) and path.is_file(), "Input must exist in the frozen checkout")
    return path


def scope():
    plan = load(PLAN)
    summary = load(SUMMARY)
    auth = batch_scope.validate_authorization(AUTH, summary)
    require(auth["user_confirmation"] == {
        "question_id": "call_eed3d32ab9a1402ebcb0e50876f1ed1e",
        "exact_answer": "授权4次，确认七身份无其他消费者",
    }, "This batch's actual user authorization is required")
    require(auth["plans"][KEY] == sha(PLAN), "Original case plan changed")
    require(plan["case"] == "E1-a" and plan["crash_point"] == "before_modification", "Wrong case")
    config_path = local(plan["config"])
    config = load(config_path)
    require(config["leader"]["aic"] == AIC == plan["identities"]["coordinator"], "Coordinator identity mismatch")
    require(plan["model_calls"] == 0, "Unexpected model scope")
    profile = [config_path, local(config["leader"]["cert"]), local(config["leader"]["key"]),
               local(config["trust_bundle"])]
    for path in profile:
        require(plan["file_sha256"].get(path.relative_to(ROOT).as_posix()) == sha(path),
                "Original coordinator config/certificate fingerprint changed")
    require(isinstance(config["mq_auth_url"], str) and config["mq_auth_url"], "Original ACL endpoint is required")
    events_path = FAILED / "coordinator/events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    created = [row for row in events if row.get("event") == "group_session_created"]
    expected = {"session_id": SESSION, "group_id": GROUP, "owner_aic": AIC}
    require(len(created) == 1 and all(created[0].get(key) == value for key, value in expected.items()),
            "Unique original group creation/owner evidence is required")
    require(not any(row.get("event") == "group_session_close_completed" for row in events),
            "Group is already recorded closed")
    require(not any((FAILED / "coordinator" / name).exists() for name in ("messages.json", "messages.jsonl")),
            "Unexpected original message history")
    journal = FAILED / "coordinator/journal.sqlite"
    journal_hash = sha(journal)
    # immutable=1 prevents SQLite's read-only WAL mode from creating sidecars.
    with sqlite3.connect(journal.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        counts = {name: connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                  for name in ("coordinator_terms", "takeover_events", "task_attempts", "task_events")}
    require(all(value == 0 for value in counts.values()), "Original journal contains a task or operation")
    require(sha(journal) == journal_hash, "Journal bytes changed during immutable inspection")
    sidecars = [path for path in journal.parent.iterdir() if path.name.startswith(journal.name + "-")]
    for path in sidecars:
        require(path.name in {journal.name + "-wal", journal.name + "-shm"}, "Unexpected journal sidecar")
        if path.name.endswith("-wal"):
            require(path.stat().st_size == 0, "Nonempty WAL must be reconciled before group cleanup")
    result_path = FAILED / "results.json"
    result = load(result_path)
    exit_path = BATCH / "execution" / KEY / "runner.exit.json"
    exit_receipt = load(exit_path)
    require(result["status"] == "failed" and result["products"] == []
            and result["resource_and_worker_restore"] == "completed"
            and result["close_error_class"] == "ConnectError"
            and exit_receipt["terminal"] is True and exit_receipt["actual_exit_code"] == 1,
            "Failed coordinator must be terminal with the original close failure retained")
    require(e1.healthy(result["independent_final_H00"]), "Independent final H00 did not pass")
    batch_result_path = BATCH / "execution/result.json"
    batch_result = load(batch_result_path)
    require(batch_result["status"] == "failed" and batch_result["project"] == PROJECT
            and batch_result.get("finished_at"), "Batch is not terminal")
    stop_path = BATCH / "execution/stop/result.json"
    stop = load(stop_path)
    after_path = BATCH / "execution/stop/after.json"
    after = load(after_path)
    stopped = [row for row in after if row["project"] == PROJECT]
    require(stop["status"] == "ACTUALLY_STOPPED" and stop["volumes_retained"] is True
            and len(stop["owned_ids"]) == 10 and set(stop["owned_ids"]) == set(stop["requested_ids"])
            and len(stopped) == 10 and {row["id"] for row in stopped} == set(stop["owned_ids"])
            and all(row["running"] is False for row in stopped), "Exact ten owned containers must be stopped")
    keeper_path = BATCH / "execution/keeper.exit.json"
    keeper = load(keeper_path)
    require(keeper["terminal"] is True and keeper["actual_exit_code"] == 0, "Keeper is not stopped")
    unknown_events_path = ROOT / "eval/results/platform/access-validation-20261019/e1a-after_observation-r1/coordinator/events.jsonl"
    unknown_events = [json.loads(line) for line in unknown_events_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    require(not any(row.get("event") == "group_session_created" for row in unknown_events)
            and any(row.get("event") == "group_session_creation_started" and row.get("session_id") == UNKNOWN_SESSION
                    for row in unknown_events), "Unknown remote creation outcome changed")
    sdk = ROOT / "vendor/ACPs-community/acps-sdk/acps_sdk/aip"
    sources = [ROOT / "eval/platform_resume_experiment.py", ROOT / "eval/targets.py", ROOT / "integration/wutong_smoke.py",
               *[sdk / name for name in ("aip_group_leader.py", "aip_group_auth.py", "aip_group_runtime.py")]]
    for path in sources:
        name = path.relative_to(ROOT).as_posix()
        if name != "integration/wutong_smoke.py":
            require(plan["file_sha256"].get(name) == sha(path), "Original cleanup source changed")
    # The transport-close helper is outside the E1 source list; bind it to the
    # same immutable published Git commit instead of inventing a plan binding.
    batch_scope.source_commit(summary["source_commit"],
        {"integration/wutong_smoke.py": sha(ROOT / "integration/wutong_smoke.py")})
    lock = ROOT / "artifacts/new7-platform-healthy-plan-20261018/ownership" / (hashlib.sha256(AIC.encode()).hexdigest() + ".lock")
    require(lock.is_file() and lock.stat().st_size >= 1, "Original same-identity lock must already exist")
    inputs = [PLAN, AUTH, SUMMARY, config_path, events_path, journal, *sidecars, result_path, exit_path,
              batch_result_path, stop_path, after_path, keeper_path, unknown_events_path,
              *profile[1:], local(plan["target_config"]), BATCH / "plan-preparation/batch_scope.py", *sources]
    return {
        "schema_version": "owned-group-close-scope/1", "group_id": GROUP, "session_id": SESSION,
        "coordinator_aic": AIC, "project": PROJECT, "effects": EFFECTS,
        "runner_sha256": sha(__file__), "journal_counts": counts,
        "untouched_unknown_group": "group-" + UNKNOWN_SESSION,
        "input_sha256": {path.relative_to(BATCH).as_posix(): sha(path) for path in inputs},
    }, plan, config


def run_readonly(argv, output, stem):
    completed = subprocess.run(argv, env=e1.clean_environment(), capture_output=True, timeout=30)
    (output / (stem + ".stdout.bin")).write_bytes(completed.stdout)
    (output / (stem + ".stderr.bin")).write_bytes(completed.stderr)
    save(output / (stem + ".exit.json"), {"actual_exit_code": completed.returncode, "terminal": True,
         "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
         "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(), "finished_at": now()})
    require(completed.returncode == 0, "Read-only runtime prerequisite failed")
    return completed.stdout.decode("utf-8-sig")


def runtime_preflight(plan, output):
    from eval.targets import DockerTarget
    target = DockerTarget.from_file(local(plan["target_config"]), root=ROOT)
    require(target.project == PROJECT, "Target is another project")
    rows = run_readonly(target.docker + ["ps", "--no-trunc", "--format",
        '{{.ID}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}'],
        output, "live-container-inventory").splitlines()
    running = [line.split("\t") for line in rows]
    require(not any(len(row) == 3 and row[1].startswith("incident-pilot") for row in running),
            "An incident project container is still running")
    command = ("$p=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?(3(\\.12)?)?\\.exe$' "
        "-and $_.CommandLine -like '*incident-pilot*' -and $_.CommandLine -match "
        "'(platform_worker\\.py|acps_mcp_bridge|platform_resume_experiment\\.py|run_authorized\\.py|run_f10\\.py|workbench_host\\.py|platform_smoke\\.py)' }); "
        "ConvertTo-Json -Compress -InputObject @($p | ForEach-Object {$_.ProcessId})")
    pids = json.loads(run_readonly(["powershell.exe", "-NoProfile", "-Command", command], output, "live-coordinator-processes"))
    require(pids == [], "A platform coordinator or worker is still alive")
    return {"incident_project_containers_running": 0, "platform_coordinator_or_worker_processes": 0,
            "preexisting_stop_and_keeper_receipts_verified": True}


class SdkEvents(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.rows = []

    def emit(self, record):
        message = record.getMessage()
        match = re.search(r"event=([A-Za-z0-9_]+)", message)
        if not match:
            return
        row = {"event": match[1], "level": record.levelname}
        if match[1] == "group_acl_client_request_done":
            ack = re.search(r"method=(\S+) path=(\S+) status=(\d+)", message)
            if ack:
                row.update(method=ack[1], exact_owned_group_path=ack[2] == "/groups/" + AIC + "/" + GROUP,
                           status=int(ack[3]))
        self.rows.append(row)


async def close_group(config, output, report):
    from acps_sdk.aip.aip_group_leader import GroupLeader, GroupLeaderMqClient, GroupLeaderSession, GroupLeaderState
    from acps_sdk.aip.aip_group_runtime import parse_amqp_endpoint_url, build_group_exchange_name, build_group_queue_name
    from integration.wutong_smoke import close_runtime
    context = ssl.create_default_context(cafile=config["trust_bundle"])
    context.load_cert_chain(config["leader"]["cert"], config["leader"]["key"])
    endpoint = parse_amqp_endpoint_url(config["leader"]["endpoint"], aic=AIC)
    runtime = GroupLeader(leader_aic=AIC, ssl_context=context, identity_binding_enabled=True,
        rabbitmq_config={"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                        "user": None, "password": None, "auth_service_url": config["mq_auth_url"]})
    mq = GroupLeaderMqClient(leader_aic=AIC, rabbitmq_host=endpoint.host, rabbitmq_port=endpoint.port,
        rabbitmq_vhost=endpoint.vhost, rabbitmq_user=None, rabbitmq_password=None,
        ssl_context=context, identity_binding_enabled=True)
    events = SdkEvents()
    file_log = logging.FileHandler(output / "sdk.log", encoding="utf-8")
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(events)
    logger.addHandler(file_log)

    def record(event, **fields):
        with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")

    try:
        await asyncio.wait_for(mq.connect(), 20)
        runtime._connection = mq._connection
        mq._group_id = GROUP
        mq._exchange_name = build_group_exchange_name(AIC, GROUP)
        mq._exchange = await mq._channel.get_exchange(mq._exchange_name, ensure=False)
        mq._leader_queue = await mq._channel.get_queue(build_group_queue_name(AIC, GROUP, AIC), ensure=False)
        mq._state = GroupLeaderState.READY
        runtime.group_sessions[SESSION] = GroupLeaderSession(SESSION, GROUP, mq)
        require(set(runtime.group_sessions) == {SESSION}, "Unexpected group binding")
        require(runtime._inbox_channel is None and runtime._inbox_queue is None, "Inbox must not be declared")
        report["official_dissolve_calls"] += 1
        await asyncio.wait_for(runtime.dissolve_group_session(SESSION), 30)
        report["official_dissolve_returned"] = True
    finally:
        runtime._connection = mq._connection
        try:
            # dissolve_group_session pops the sole session before awaiting. close()
            # therefore closes only transport; it cannot retry that group's delete.
            await close_runtime(runtime, 15, record)
        finally:
            logger.removeHandler(events)
            logger.removeHandler(file_log)
            file_log.close()
            names = [row["event"] for row in events.rows]
            report["sdk_events"] = events.rows
            report["cleanup_warning_events"] = [name for name in names if name in e1.CLEANUP_EVENTS]
            report["close_checks"] = {
                "no_group_sessions": not runtime.group_sessions,
                "no_inbox_created": runtime._inbox_channel is None and runtime._inbox_queue is None,
                "connection_closed": runtime._connection is None or runtime._connection.is_closed,
                "owned_group_disconnected": mq.state == GroupLeaderState.DISCONNECTED,
                "no_cleanup_warnings": not report["cleanup_warning_events"],
                "acl_delete_acknowledged": any(row.get("event") == "group_acl_client_request_done"
                    and row.get("method") == "DELETE" and row.get("exact_owned_group_path") is True
                    and 200 <= row.get("status", 0) < 400 for row in events.rows),
                "leader_queue_cleanup_attempted_once": names.count("queue_delete_attempt") == 1,
                "exchange_cleanup_attempted_once": names.count("exchange_delete_attempt") == 1,
            }
            save(output / "result.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    expected, plan, config = scope()
    prepared = HERE / "prepared-v2.json"
    if not args.execute:
        require(not prepared.exists(), "Keep existing preparation evidence")
        save(prepared, {"status": "prepared_not_executed", "scope": expected})
        print(json.dumps({"status": "prepared_not_executed", "group_id": GROUP}), flush=True)
        return 0
    require(load(prepared) == {"status": "prepared_not_executed", "scope": expected}, "Prepared inputs changed")
    output = HERE / "attempt-1"
    require(not output.exists(), "This cleanup attempt is single-use; retain its result")
    output.mkdir(mode=0o700)
    report = {"status": "failed", "group_id": GROUP, "session_id": SESSION, "coordinator_aic": AIC,
        "project": PROJECT, "started_at": now(), "prepared_sha256": sha(prepared),
        "new_groups": 0, "new_tasks": 0, "new_inbox_consumers": 0, "official_dissolve_calls": 0,
        "original_failure_retained": True, "unknown_group_untouched": "group-" + UNKNOWN_SESSION, "effects": EFFECTS}
    save(output / "result.json", report)
    try:
        os.environ.clear()
        os.environ.update(CLEAN_ENV)
        with e1.coordinator_lock(AIC):
            report["preflight"] = runtime_preflight(plan, output)
            asyncio.run(close_group(config, output, report))
            require(report.get("official_dissolve_returned") is True and all(report["close_checks"].values()),
                    "Official close did not pass every cleanup check")
            require(scope()[0] == expected, "Original failure evidence changed")
            report["status"] = "passed"
    except BaseException as error:
        report["error_class"] = type(error).__name__
        raise
    finally:
        report["completed_at"] = now()
        save(output / "result.json", report)
        print(json.dumps({key: report[key] for key in ("status", "group_id", "completed_at")}), flush=True)
    return 0


CLEAN_ENV = e1.clean_environment()
if __name__ == "__main__":
    raise SystemExit(main())
