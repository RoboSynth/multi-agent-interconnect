"""One-time read-only projection of this four-plan batch; never executes resources."""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

BATCH = Path(__file__).resolve().parent
ROOT = BATCH / "checkout"
OUTPUT = BATCH / "access-results-publication"
RESULTS = ROOT / "eval/results/platform/access-validation-20261019"
TARGET = "evidence/access-validation-results-20261019"
PROJECT = "incident-pilot-access-validation-20261019"
SOURCES = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original(path):
    rel = path.relative_to(BATCH).as_posix()
    SOURCES.setdefault(rel, {"original_path_relative_to_batch": rel, "sha256": sha(path), "bytes": path.stat().st_size,
                             "projections": []})
    return path


def load(path):
    return json.loads(original(path).read_bytes())


def rows(path):
    return [json.loads(line) for line in original(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write(rel, value, origins=(), rule="explicit field whitelist"):
    path = OUTPUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    bind(rel, origins, rule)


def bind(rel, origins, rule):
    for origin in origins:
        record = SOURCES[original(origin).relative_to(BATCH).as_posix()]
        record["projections"].append({"projected_path": rel, "sha256": sha(OUTPUT / rel), "rule": rule})


def jsonlines(rel, values, origin, rule):
    path = OUTPUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n" for row in values), encoding="utf-8")
    bind(rel, [origin], rule)


def pick(value, keys):
    return {key: value[key] for key in keys if key in value}


def immutable_counts(path):
    original(path)
    before = {p.name: (sha(p), p.stat().st_size) for p in path.parent.glob(path.name+"*") if p.is_file()}
    connection = sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)
    try:
        tables = [name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {name: connection.execute('SELECT count(*) FROM "'+name.replace('"', '""')+'"').fetchone()[0] for name in tables}
    finally:
        connection.close()
    after = {p.name: (sha(p), p.stat().st_size) for p in path.parent.glob(path.name+"*") if p.is_file()}
    assert before == after, "immutable query changed original or sidecars"
    return {"read_mode": "mode=ro&immutable=1", "table_rows": counts,
            "database_and_sidecars_before_equal_after": True,
            "sidecars_present_before_and_after": sorted(before), "raw_database_sha256": sha(path)}


EVENT_KEYS = "event aic owner_aic session_id group_id inbox phase error_class role reason skill_id task_id logical_task_id operation_id tool status started_at finished_at elapsed_ms".split()
AMP_ENVELOPE = "schema_version log_id log_type timestamp aic trace_id span_id parent_span_id correlation_id".split()


def project_event(row):
    result = pick(row, EVENT_KEYS)
    if row.get("event") == "official_discovery":
        response = row.get("response", {}).get("result", {})
        result["discovered_aics"] = sorted(response.get("acsMap", {}))
        result["route_statuses"] = [pick(route, ["status", "durationMs"]) for route in response.get("routes", [])]
    return result


def project_amp(row):
    result = pick(row, AMP_ENVELOPE)
    body = row.get("body", {})
    kind = row["log_type"]
    if kind == "system":
        result["body"] = project_event(body)
    elif kind == "access":
        result["body"] = pick(body, ["caller", "callee", "durationMs"])
        result["body"]["request"] = pick(body.get("request", {}), ["method", "route"])
        result["body"]["response"] = pick(body.get("response", {}), ["statusCode"])
    elif kind == "message":
        result["body"] = pick(body, ["eventType", "operationName", "system", "deliveryAttempt", "messageId", "payloadSizeBytes", "settlement"])
        result["body"]["attributes"] = pick(body.get("attributes", {}), ["groupId", "msgType", "taskId"])
    elif kind == "audit":
        result["body"] = {key: pick(body.get(key, {}), fields) for key, fields in {
            "actor": ["id", "type"], "action": ["name", "type"], "target": ["type", "id"], "result": ["status"]}.items()}
    elif kind == "heartbeat":
        result["body"] = pick(body, ["uptimeSeconds"])
    elif kind == "metrics":
        # Numeric measurement blocks; no machine paths or request/product bodies.
        result["body"] = pick(body, ["loadMetrics", "uptimeSeconds", "windowMetrics"])
    else:
        raise ValueError("unreviewed AMP type: "+kind)
    return result


def h00_projection(value):
    out = pick(value, "run_id duration_seconds requests success failed unknown completed_workflows unresolved_intents resolved_unknown_intents passed".split())
    out["events"] = [pick(row, ["phase", "method", "elapsed_seconds", "http_status", "outcome"]) for row in value.get("events", [])]
    return out


def main():
    OUTPUT.mkdir(exist_ok=False)
    prepared_path = BATCH / "plan-preparation/prepared-summary.json"
    prepared = load(prepared_path)
    auth_path = BATCH / "authorization/user-four-case.json"
    auth = load(auth_path)
    assert sha(prepared_path) == auth["prepared_summary_sha256"]
    assert auth["source_commit"] == prepared["source_commit"]
    assert auth["plans"] == {row["key"]: row["plan_sha256"] for row in prepared["plans"]}
    assert auth["batch_plans_sha256"] == prepared["batch_plans_sha256"]
    write("authorization-recorded.json", auth, [auth_path], "Original JSON values retained; original bytes retained locally")
    assert auth["user_confirmation"]["exact_answer"] == "授权4次，确认七身份无其他消费者"
    write("authorization-verification.json", {
        "question_id": "call_eed3d32ab9a1402ebcb0e50876f1ed1e",
        "recorded_reply_matches_actual_user_reply": True,
        "original_answer_contains_replacement_character": any(ord(char) == 0xfffd for char in auth["user_confirmation"]["exact_answer"]),
        "recorded_answer_codepoints": [hex(ord(char)) for char in auth["user_confirmation"]["exact_answer"]],
        "recorded_authorization_sha256": sha(auth_path),
        "note": "Original JSON read as bytes and parsed directly. Exact Unicode reply is correct and matches the conversation; console display encoding is not used to judge the stored content."}, [auth_path])

    aggregate_path = BATCH / "execution/result.json"
    aggregate = load(aggregate_path)
    aggregate_projection = dict(aggregate)
    aggregate_projection["traceback"] = re.sub(r'File "[^"]*run_authorized\.py"', 'File "<batch>/run_authorized.py"', aggregate["traceback"])
    write("original-aggregate-result-projection.json", aggregate_projection, [aggregate_path], "All aggregate result values retained except absolute traceback filenames projected to <batch>; missing third case is not filled in this original projection")
    observation_path = BATCH / "execution-observation.json"
    observation = load(observation_path)
    write("execution-observation.json", observation, [observation_path], "All original JSON values")

    sources = prepared["source_sha256"]
    for rel, expected in sources.items():
        assert sha(ROOT / rel) == expected
    source_bindings = {"source_commit": prepared["source_commit"], "prepared_summary_sha256": sha(prepared_path),
        "batch_plans_sha256": prepared["batch_plans_sha256"], "source_file_count": len(sources),
        "source_sha256": sources, "images": prepared["image_results"],
        "deployment_sha256": prepared["deployment_sha256"], "execution_script_sha256": prepared["execution_script_sha256"],
        "case_snapshot_checks": [], "prepared_status_is_historical": prepared["status"]}

    case_rows, case_origins, all_events = [], [], {}
    for plan_row in prepared["plans"]:
        key = plan_row["key"]
        plan_path = ROOT / plan_row["plan"]
        plan = load(plan_path)
        assert sha(plan_path) == plan_row["plan_sha256"]
        write("plans/"+key+".json", {"plan_sha256": sha(plan_path), **pick(plan, "schema_version case crash_point method repeat model_calls enable_llm transport backend project effects image_id identities recover_access evidence_limits".split())}, [plan_path], "Drop private filesystem/config paths and their raw values; preserve declared public identity, effects, image and case scope")
        receipt_path = BATCH / "execution" / key / "receipt.json"
        if not receipt_path.exists():
            assert not (RESULTS / key).exists()
            case_rows.append({"order": plan_row["order"], "key": key, "case": plan_row["case"], "point": plan_row["point"], "plan_sha256": plan_row["plan_sha256"], "status": "not_attempted", "actual_exit_code": None,
                "model_calls": None, "crash_point_reached": None, "independent_final_H00_passed": None,
                "reason": "Batch stopped after preceding cleanup guard failure; no individual receipt or case output exists"})
            continue
        receipt = load(receipt_path)
        case_origins.append(receipt_path)
        assert receipt["plan_sha256"] == plan_row["plan_sha256"]
        assert receipt["batch_authorization_sha256"] == sha(auth_path)
        write("cases/"+key+"/receipt.json", receipt, [receipt_path], "All original JSON values")
        f10 = key.startswith("f10")
        result_path = RESULTS / key / ("wrapper-result.json" if f10 else "results.json")
        result = load(result_path)
        snapshot_path = RESULTS / key / ("experiment.json" if f10 else "results.json")
        snapshot = load(snapshot_path)["source_sha256"]
        assert snapshot == sources
        for rel, expected in snapshot.items():
            assert sha(RESULTS / key / "source" / rel) == expected
        source_bindings["case_snapshot_checks"].append({"case": key, "source_file_count": len(snapshot), "all_match_prepared_source_and_frozen_copy": True, "result_original_sha256": sha(snapshot_path)})
        result_projection = pick(result, "schema_version case method crash_point experiment_id incident_id operation_id status model_calls started_at finished_at products error_class close_error_class close_requested close_checks evaluation_exit_code cleanup_warning_events resource_and_worker_restore".split())
        write("cases/"+key+"/result-projection.json", result_projection, [result_path], "Explicit execution/outcome fields; source map and H00 exported separately; no source private config copied")
        h00 = h00_projection(result["independent_final_H00"])
        assert h00["passed"] and h00["duration_seconds"] >= 30 and h00["completed_workflows"] == 10
        assert h00["requests"] == h00["success"] == len(h00["events"]) == 30
        write("cases/"+key+"/final-H00.json", h00, [result_path], "Metrics and all 30 phase/method/timing/status/outcome rows; order identifiers and item payloads omitted")
        transport = RESULTS / key / ("transport" if f10 else "coordinator")
        event_path = transport / "events.jsonl"
        events = rows(event_path)
        all_events[key] = dict(Counter(row["event"] for row in events))
        jsonlines("cases/"+key+"/events.jsonl", [project_event(row) for row in events], event_path, "Lifecycle/task/error fields; discovery reduced to returned public AICs and route status/timing; no request/product/config bodies")
        for path in sorted((transport / "amp").glob("*.jsonl")):
            jsonlines("cases/"+key+"/amp/"+path.name, [project_amp(row) for row in rows(path)], path,
                "All rows in this case file only; reviewed envelope/body fields; signatures, arbitrary descriptions, routing addresses and payloads omitted. Modified projections are not signature-verification evidence.")
        injection_path = RESULTS / key / ("private/injections.jsonl" if f10 else "injections.jsonl")
        jsonlines("cases/"+key+"/injections.jsonl", [pick(row, "scenario action backend cause precondition_pool_rebuilds completed_at".split()) for row in rows(injection_path)], injection_path, "Recorded injection/restore action metadata only, no command output")
        row = {"order": plan_row["order"], "key": key, "case": plan_row["case"], "point": plan_row["point"], "plan_sha256": plan_row["plan_sha256"],
            "status": receipt["status"], "actual_exit_code": receipt["actual_exit"]["actual_exit_code"],
            "model_calls": result["model_calls"], "crash_point_reached": None if f10 else False,
            "independent_final_H00_passed": h00["passed"], "h00_duration_seconds": h00["duration_seconds"], "h00_completed_workflows": h00["completed_workflows"],
            "cleanup_and_recovery_verified_in_original_receipt": receipt["cleanup_and_recovery_verified"],
            "error_class": result.get("error_class"), "close_error_class": result.get("close_error_class")}
        if f10:
            f10_path = RESULTS / key / "results.json"
            f10_result = load(f10_path)
            assert len(f10_result) == 1
            write("cases/"+key+"/F10-evaluation-result.json", f10_result, [f10_path], "All original evaluation metric values")
        else:
            journal_path = transport / "journal.sqlite"
            journal = immutable_counts(journal_path)
            assert all(value == 0 for value in journal["table_rows"].values())
            assert not any("crash" in event or "interruption" in event for event in all_events[key])
            write("cases/"+key+"/coordinator-journal-inspection.json", journal, [journal_path], "Immutable read-only table counts and database SHA only; SQLite files not published")
            recovery_path = RESULTS / key / "access-recovery.json"
            recovery = load(recovery_path)
            for entry in recovery:
                assert entry["log_before"] == entry["log_after"]
                assert entry["journal_before"] == entry["journal_after"]
            write("cases/"+key+"/access-recovery.json", {"recorded_recovery": recovery,
                "attribution": "The six database rows were already present in the shared project volume after F10. Both failed E1 attempts have empty coordinator task journals and no products; these counts do not demonstrate six new E1 task records or new case-specific recovery.",
                "new_case_specific_access_rows_proven": False}, [recovery_path])
            row["coordinator_task_attempts"] = journal["table_rows"]["task_attempts"]
        case_rows.append(row)

    assert Counter(row["status"] for row in case_rows) == {"completed": 1, "failed": 2, "not_attempted": 1}
    assert len(aggregate["cases"]) == 2 and len(case_origins) == 3
    write("source-bindings.json", source_bindings, [prepared_path], "Prepared source/image hashes plus all three result source snapshots and 498 archived-source file hash checks")
    stop_path = BATCH / "execution/stop/result.json"
    stop = load(stop_path)
    assert stop["status"] == "ACTUALLY_STOPPED" and len(stop["owned_ids"]) == len(stop["requested_ids"]) == 10
    stop_ids = set(stop["owned_ids"])
    own_fields = "id project service running image_id created started_at recovery".split()
    for phase in ["before", "confirmed", "after"]:
        path = BATCH / "execution/stop" / (phase+".json")
        values = [pick(row, own_fields) for row in load(path) if row["id"] in stop_ids]
        assert len(values) == 10 and all(row["project"] == PROJECT for row in values)
        assert sum(row["running"] for row in values) == (0 if phase == "after" else 10)
        write("stop/"+phase+"-owned-containers.json", values, [path], "Only exact ten stopped owned IDs, no unrelated project inventory")
    write("stop/result.json", stop, [stop_path], "All original JSON values")
    keeper_path = BATCH / "execution/keeper.exit.json"
    keeper = load(keeper_path)
    assert keeper["terminal"] and keeper["actual_exit_code"] == 0
    write("stop/keeper-exit.json", keeper, [keeper_path], "All original JSON values")

    summary = {"schema_version": "access-validation-archive/1", "project": PROJECT,
        "source_commit": prepared["source_commit"], "prepared_plan_count": 4, "attempted": 3,
        "completed": 1, "failed": 2, "not_attempted": 1, "model_calls_total_for_attempted_cases": 0,
        "outer_actual_exit_code": observation["actual_exit_code"], "cases": case_rows,
        "count_basis": "Four prepared plans and all three individual execution receipt.json files; aggregate result is preserved as a projection and omits the third receipt because its cleanup guard raised before append.",
        "aggregate_case_count": 2, "individual_receipt_count": 3,
        "independent_final_H00_passed_count": 3, "coordinator_event_counts": all_events,
        "owned_project_stop": {"status": stop["status"], "owned_container_count": 10, "after_running_count": 0, "volumes_retained": stop["volumes_retained"], "keeper_actual_exit_code": keeper["actual_exit_code"]},
        "remaining_owned_group_close": {"group_id": "group-incident-cef7f4c704374de1a376eab9ed086e60", "status": "pending_external_cleanup_receipt", "note": "Separate owned_cleanup_finish agent owns the live normal SDK close. This archive neither executes nor assumes that close; parent may add a final supplemental receipt."},
        "historical_results": "This batch is separate. Original 22/12 outcomes and historical missing access are not modified or backfilled."}
    write("summary.json", summary, case_origins+[observation_path, aggregate_path])
    with (OUTPUT / "cases.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = sorted(set().union(*(row.keys() for row in case_rows)))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: "unknown" if row.get(key) is None else row[key] for key in fields} for row in case_rows])

    readme = """# 本批四计划正式复验：结果归档

本批准备4项，实际尝试3项：**F10/M0通过1项，E1-a失败2项，最后after_applied未尝试1项**。模型调用0。计数以四份绑定计划及三份individual receipt为准，外层执行实际退出码1。原aggregate仅收前两例；第三例的清理守卫抛异常后未append，不能据aggregate误写为只尝试两例。原件保持不变，投影与原件SHA映射见`original-sha-map.json`。

| 例项 | 结果 | 实际达到阶段 | 最后独立H00 |
| --- | --- | --- | --- |
| F10/M0 | completed，exit0 | 复合故障与修复，平台通信 | 30.016秒，30请求成功，10完整流程 |
| E1-a after_observation | failed，exit1 | group-create ConnectTimeout；未到中断点 | 30秒，30请求成功，10完整流程 |
| E1-a before_modification | failed，exit1 | 发现后invite ConnectError；close也ConnectError，未到中断点 | 30秒，30请求成功，10完整流程 |
| E1-a after_applied | not_attempted | 上一例清理守卫停止后续；无receipt/结果目录 | unknown |

两个E1 coordinator journal均以`mode=ro&immutable=1`读取，所有表计数0，products为空，没有执行到声明的主智能体中断点，不能据此宣称接续恢复通过。该查询前后数据库与既有sidecar的SHA和大小相同。数据库access恢复记录中的6行属于F10后共享卷已有记录，两个E1恢复前后log/journal SHA均相同；这是保留既有记录的证据，不是本E1新生成6行。备库access为0；不追补旧批次缺失日志。

本批自有10容器经两次身份核实后实际停止，after快照running=0；卷保留。keeper实际exit0。before_modification留下的`group-incident-cef7f4c704374de1a376eab9ed086e60`正常SDK关闭由另一任务单独处理，本归档暂标pending；最终清理收据需另附，不能回改原失败及原close错误。

`source-bindings.json`保留冻结提交、166份源码SHA、两镜像ID、4份计划及授权绑定；三例各166份冻结副本逐一相符。授权原JSON以原始字节直接解析，原文与会话实际回复逐字符一致，`authorization-recorded.json`保留原值，`authorization-verification.json`记录核验。

发布内容仅为显式白名单：结果、H00全部30步的阶段/耗时/HTTP状态、case内生命周期事件和AMP的有用信封/状态/计时字段、恢复记录、原件SHA及自有停机快照。原始私密config、SQLite、stdout/stderr.bin、命令输出、业务正文、任意系统description和签名均未复制；AMP投影不用于密码学验签。全部取自本批文件，没有拼接长窗口或旧22/12数据。`publication-files.json`提供精确源与仓库目标映射，父任务上传前仍需完整库存扫描。

本目录由只读归档脚本产生，没有启动资源、平台、模型或故障；未尝试最后一例。新的补充清理证据应独立追加并保留本次pending快照。
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    shutil.copyfile(Path(__file__), OUTPUT / Path(__file__).name)
    # Read-only originals are rehashed after all analysis. Raw SQLite/binaries stay local.
    assert all(sha(BATCH / rel) == entry["sha256"] for rel, entry in SOURCES.items())
    write("original-sha-map.json", {"schema_version": 1, "batch_relative_source_root": "p0-current-source-validation-20261019", "originals_unchanged_after_projection": True,
        "projection_policy": "Explicit whitelists; no raw config, SQLite or stdout/stderr binaries copied. Original records remain local.", "files": list(SOURCES.values())})
    files = [path for path in sorted(OUTPUT.rglob("*")) if path.is_file()]
    entries = [{"source_relative": path.relative_to(OUTPUT).as_posix(), "target_relative": TARGET+"/"+path.relative_to(OUTPUT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in files]
    write("publication-files.json", {"schema_version": 1, "source_root": "access-results-publication", "entries": entries,
        "manifest_target": TARGET+"/publication-files.json", "self_handling": "Copy this manifest itself in addition to entries; no recursive self-hash.",
        "close_receipt_status": "pending_external_cleanup_receipt", "raw_originals_unchanged": True})
    print(json.dumps({"attempted": 3, "completed": 1, "failed": 2, "not_attempted": 1,
        "publication_files_including_manifest": len(entries)+1, "originals_bound": len(SOURCES),
        "publication_manifest_sha256": sha(OUTPUT / "publication-files.json")}))


if __name__ == "__main__":
    main()
