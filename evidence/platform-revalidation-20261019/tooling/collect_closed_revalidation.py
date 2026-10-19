"""Stage a terminal 12-case revalidation batch; no product imports or runtime actions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LEGACY_SHA256 = "c23e7355baa5f73ec49e817373407b15e843113972f4f1594c33782c4f2742cf"
LAUNCHER_SHA256 = "c62e43c204866c3f3d9d380b835c7b614e7520e1ff8e49692f84201ef39f501a"
FROZEN_COMMIT = "c75554d6b6de3bdaba53677e678a6fd35e4fef80"
TARGET = "evidence/platform-revalidation-20261019"
PROJECT = "incident-pilot-revalidation-20261019"
HEX = re.compile(r"[0-9a-f]{64}")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def require(value, message):
    if not value:
        raise ValueError(message)


def inside(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Expected relative input locator")
    path = (root / relative).resolve()
    require(path.is_relative_to(root), "Input locator escapes its root")
    return path


def healthy(value):
    if not isinstance(value, dict):
        return False
    return (value.get("passed") is True and type(value.get("duration_seconds")) in (int, float)
            and value["duration_seconds"] >= 30 and type(value.get("completed_workflows")) is int
            and value["completed_workflows"] >= 10
            and all(type(value.get(k)) is int and value[k] == 0 for k in ("failed", "unknown", "unresolved_intents"))
            and isinstance(value.get("state"), dict) and value["state"].get("pending") == [])


def terminal_process(value):
    return isinstance(value, dict) and value.get("terminal") is True and type(value.get("actual_exit_code")) is int


def collect(args):
    batch = args.batch.resolve()
    root = batch / "checkout"
    legacy_path = args.legacy or (HERE / "collect_results_v4.py" if (HERE / "collect_results_v4.py").is_file()
                                  else batch.parent / "p0-acceptance-prep-20261019/publication/collect_results_v4.py")
    legacy_raw = legacy_path.read_bytes()
    require(sha(legacy_raw) == LEGACY_SHA256, "Reviewed legacy collector hash mismatch")
    spec = importlib.util.spec_from_file_location("reviewed_acceptance_projection", legacy_path)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    legacy.BATCH, legacy.ROOT = batch, root

    class FrozenReader(legacy.Reader):
        def raw(self, path):
            path = Path(path).resolve()
            require(path.is_relative_to(batch), "Read outside this revalidation artifact")
            key = path.relative_to(batch).as_posix()
            previous = self.inputs.get(key)
            raw = super().raw(path)
            if previous is not None:
                require(raw is not None and sha(raw) == previous["sha256"], "Input changed while collecting: " + key)
            return raw

        def required(self, path):
            value = self.json(path)
            require(isinstance(value, dict), "Missing or invalid terminal JSON: " + str(Path(path).relative_to(batch)))
            return value

    reader = FrozenReader()
    prepared_path = batch / "plan-preparation/prepared-summary.json"
    prepared = reader.required(prepared_path)
    require(prepared.get("project") == PROJECT and prepared.get("plan_count") == 12
            and len(prepared.get("plans", [])) == 12, "Expected frozen 12-plan revalidation batch")
    require(set(prepared.get("ports", {}).values()) == {58081, 58082, 58088, 58090}, "Wrong batch ports")
    require(sha(reader.raw(batch / "run_authorized.py")) == LAUNCHER_SHA256, "Authorized launcher changed")
    source_map = prepared["source_sha256"]
    require(isinstance(source_map, dict) and source_map, "Missing frozen source map")
    for name, digest in source_map.items():
        require(isinstance(digest, str) and HEX.fullmatch(digest), "Invalid frozen source hash")
        require(sha(reader.raw(inside(root, name))) == digest, "Frozen checkout source mismatch: " + name)
    terminal_path = (args.terminal or HERE / "batch-terminal.json").resolve()
    terminal = reader.required(terminal_path)
    require(terminal.get("status") == "terminal" and terminal.get("actual_wait_observed") is True
            and terminal.get("expected_plans") == 12, "Root must first observe and record actual batch process termination")
    phases = terminal.get("phase_sessions")
    require(isinstance(phases, list) and phases and all(isinstance(p, dict) and p.get("terminal") is True
            and type(p.get("actual_os_exit_code")) is int and p.get("session_id") is not None for p in phases),
            "Missing actual terminal process/session observations")
    prepared_hash = reader.inputs[prepared_path.relative_to(batch).as_posix()]["sha256"]
    require(terminal.get("prepared_summary_sha256") == prepared_hash, "Terminal receipt not bound to prepared plans")
    original_path = root / "evidence/platform-acceptance-20261019/summary.json"
    original = reader.required(original_path)
    require(all(original.get("counts", {}).get(k) == n for k, n in (("prepared", 22), ("passed", 18), ("failed", 4))),
            "Original 22-case evidence no longer matches the retained verdicts")
    launcher_bindings = terminal.get("launcher_inputs_sha256")
    require(isinstance(launcher_bindings, dict) and "run_authorized.py" in launcher_bindings
            and set(launcher_bindings) <= {"run_authorized.py", "run_remaining_authorized.py"}
            and launcher_bindings["run_authorized.py"] == LAUNCHER_SHA256,
            "Root terminal receipt must bind the exact authorized launchers")
    require(len(phases) == 1 or "run_remaining_authorized.py" in launcher_bindings,
            "Continuation phase requires its own launcher hash binding")
    for name, digest in launcher_bindings.items():
        require(isinstance(digest, str) and HEX.fullmatch(digest)
                and sha(reader.raw(inside(batch, name))) == digest, "Authorized launcher binding mismatch: " + name)
    stop_ref = terminal.get("owned_project_stop_receipt", {})
    keeper_ref = terminal.get("owned_keeper_exit_receipt", {})
    require(isinstance(stop_ref, dict) and stop_ref.get("path") in
            {"execution/stop/result.json", "execution-rest/stop/result.json"}, "Expected exact final owned-project stop locator")
    final_execution = stop_ref["path"].split("/", 1)[0]
    require(isinstance(keeper_ref, dict) and keeper_ref.get("path") == final_execution + "/keeper.exit.json",
            "Final keeper exit must belong to the same execution stage as the final stop")
    stop_path = inside(batch, stop_ref["path"])
    stop = reader.required(stop_path)
    stop_process = reader.required(stop_path.parent / "compose-stop.exit.json")
    keeper_exit_path = inside(batch, keeper_ref["path"])
    keeper = reader.required(keeper_exit_path)
    require(stop.get("status") == "stopped" and stop.get("remaining_running_owned") == 0
            and terminal_process(stop_process) and stop_process["actual_exit_code"] == 0, "Owned project stop not actually terminal and verified")
    require(terminal_process(keeper) and keeper["actual_exit_code"] == 0, "Owned keeper has not acknowledged stop with a real terminal exit0")
    require(stop_ref.get("sha256") == reader.inputs[stop_ref["path"]]["sha256"], "Root stop receipt binding mismatch")
    require(keeper_ref.get("sha256") == reader.inputs[keeper_ref["path"]]["sha256"], "Root keeper exit receipt binding mismatch")
    after = reader.json(stop_path.parent / "after.json")
    require(isinstance(after, list) and not any(row.get("running") is True for row in after
            if isinstance(row, dict) and row.get("project") == PROJECT), "Final inventory still contains running owned containers")
    cases = []
    keys = set()
    for item in prepared["plans"]:
        key = item["key"]
        require(isinstance(key, str) and re.fullmatch(r"e1[ab]-[a-z_]+-r[123]", key) and key not in keys, "Invalid/duplicate prepared key")
        keys.add(key)
        plan_path, output = inside(root, item["plan"]), inside(root, item["output"])
        require(output == root / "eval/results/platform/revalidation-20261019" / key, "Output outside exact prepared batch")
        plan = reader.required(plan_path)
        require(sha(reader.raw(plan_path)) == item["plan_sha256"] and plan.get("project") == PROJECT
                and plan.get("output") == item["output"], "Prepared plan binding mismatch")
        require(all(plan.get("file_sha256", {}).get(name) == digest for name, digest in source_map.items()), "Plan source map mismatch")
        execution = batch / "execution" / key
        receipt_path, exit_path = execution / "receipt.json", execution / "runner.exit.json"
        base = {**legacy.scalar_fields(item, ("key", "case", "point", "method", "repeat")),
                "prepared_order": item["order"], "prepared_plan_sha256": item["plan_sha256"]}
        if not receipt_path.exists() and not exit_path.exists() and not output.exists():
            cases.append({**base, "state": "not_attempted", "actual_case_process_terminal": False,
                          "actual_case_exit_code": None, "result": None})
            continue
        receipt, runner = reader.required(receipt_path), reader.required(exit_path)
        for stream in ("stdout", "stderr"):
            captured = reader.raw(execution / ("runner." + stream + ".bin"))
            require(captured is not None and sha(captured) == runner.get(stream + "_sha256"), "Runner captured output hash mismatch: " + key)
        result_path = output / "results.json"
        result = reader.required(result_path)
        require(terminal_process(runner) and bool(receipt.get("finished_at")) and bool(result.get("finished_at")), "Attempt is not terminal: " + key)
        require(receipt.get("key") == key and receipt.get("order") == item["order"]
                and receipt.get("plan_sha256") == item["plan_sha256"]
                and receipt.get("actual_exit_code") == runner["actual_exit_code"], "Case receipt mismatch: " + key)
        require(result.get("case") == plan.get("case") == item["case"] and result.get("crash_point") == item["point"]
                and all(result.get(k) == plan.get(k) for k in ("experiment_id", "incident_id", "operation_id"))
                and result.get("source_sha256") == source_map, "Case results do not match frozen plan/source: " + key)
        require(item["case"] != "E1-b" or result.get("method") == plan.get("method") == item["method"], "Handover method mismatch")
        for name, digest in source_map.items():
            require(sha(reader.raw(inside(output / "source", name))) == digest, "Case frozen source copy mismatch: " + key + "/" + name)
        raw_completed = result.get("status") == "completed" and runner["actual_exit_code"] == 0
        require(result.get("status") in {"completed", "failed"}
                and (result["status"] == "completed") == (runner["actual_exit_code"] == 0)
                and receipt.get("status") == ("completed" if raw_completed else "failed"), "Receipt/result/exit verdict mismatch: " + key)
        close = result.get("close_checks", {})
        six_close = isinstance(close, dict) and set(close) == set(legacy.CLOSE) and all(v is True for v in close.values())
        safe = (result.get("resource_and_worker_restore") == "completed" and healthy(result.get("independent_final_H00"))
                and six_close and not any(k in result for k in ("close_error_class", "restore_or_H00_error_class")))
        require(type(receipt.get("cleanup_and_recovery_verified")) is bool
                and receipt["cleanup_and_recovery_verified"] == safe, "Receipt recovery gate disagrees with underlying evidence: " + key)
        projection = legacy.case_result(reader, output, plan, item["case"])
        journal = result.get("journal_resolution", {})
        checks = {"runner_exit_zero": runner["actual_exit_code"] == 0,
                  "reported_completed": result["status"] == "completed",
                  "task_phase_completed": result.get("task_phase_status") == "completed",
                  "six_close_checks_true": six_close, "no_cleanup_warnings": result.get("cleanup_warning_events") == [],
                  "restoration_and_independent_H00": safe, "business_verification_healthy": healthy(result.get("business_verification")),
                  "no_error_class": not any(k.endswith("error_class") for k in result),
                  "journal_unexpected_inflight_zero": isinstance(journal, dict) and journal.get("unexpected_in_flight_count") == 0
                    and journal.get("raw_journal_modified") is False}
        if item["case"] == "E1-b":
            capture = projection.get("captured_resume_send") or {}
            checks["one_captured_and_acknowledged_resume"] = (capture.get("matching_resume_sends") == 1
                and capture.get("capture_parse_errors") == 0 and capture.get("acknowledged_metrics_match") is True
                and len(capture.get("sends", [])) == 1 and capture["sends"][0].get("backup_target_match") is True
                and capture["sends"][0].get("transport") == "wutong-amqps")
        cases.append({**base, "state": "passed" if all(checks.values()) else "failed",
                      "actual_case_process_terminal": True, "actual_case_exit_code": runner["actual_exit_code"],
                      "receipt": legacy.scalar_fields(receipt, ("status", "started_at", "finished_at", "plan_sha256", "actual_exit_code", "cleanup_and_recovery_verified", "launcher_error_class")),
                      "pass_checks": checks, "result": projection})
    counts = {"prepared": 12, **{state: sum(row["state"] == state for row in cases) for state in ("passed", "failed", "not_attempted")},
              "running_or_unconfirmed": 0, "unknown_awaiting_terminal_receipt": 0}
    require([item["order"] for item in prepared["plans"]] == list(range(1, 13)), "Prepared order changed")
    for label, expected in (("attempted_count", counts["passed"] + counts["failed"]), ("unattempted_count", counts["not_attempted"]),
                            ("passed_count", counts["passed"]), ("failed_count", counts["failed"])):
        require(terminal.get(label) == expected, "Root terminal count mismatch: " + label)
    require(terminal.get("plan_dispositions") == {row["key"]: row["state"] for row in cases}, "Terminal per-plan dispositions mismatch")
    report = {"schema_version": "revalidation-public-snapshot/1", "created_at": datetime.now(timezone.utc).isoformat(),
              "project": PROJECT, "frozen_source_commit": FROZEN_COMMIT, "ports": prepared["ports"], "image_id": prepared["image_id"],
              "prepared_summary_sha256": prepared_hash, "prepared_source_file_count": len(source_map),
              "prepared_source_map_sha256": sha(json.dumps(source_map, sort_keys=True, separators=(",", ":")).encode()),
              "counts": counts, "cases": cases,
              "original22": {"unchanged": True, "prepared": 22, "passed": 18, "failed": 4,
                             "evidence": "evidence/platform-acceptance-20261019/", "combined_success_rate_claimed": False,
                             "original_summary_sha256": reader.inputs[original_path.relative_to(batch).as_posix()]["sha256"]},
              "limits": ["This new 12-case batch is separate from the original frozen 22-case batch; no original verdict is replaced.",
                         "Pass requires underlying results, six normal-close gates, restoration, independent 30s/10-workflow H00, business verification and journal checks; exit0 alone is insufficient.",
                         "The unchanged original unknown business intents, T05, Kafka/Monitor, independent-machine and long-term gates remain separate.",
                         "Prepared, captured and acknowledged handover sizes remain separate; duplicated resume-package representations are not byte savings."]}
    closure = {"batch_process": legacy.scalar_fields(terminal, ("status", "actual_wait_observed", "recorded_at_utc")),
               "phase_sessions": [legacy.scalar_fields(p, ("session_id", "actual_os_exit_code", "terminal", "completion_chunk")) for p in phases],
               "final_owned_stop_receipt": stop_ref, "final_owned_keeper_exit_receipt": keeper_ref,
               "stop": legacy.scalar_fields(stop, ("status", "remaining_running_owned", "volumes_retained", "completed_at")),
               "compose_stop_process": legacy.scalar_fields(stop_process, ("terminal", "actual_exit_code", "completed_at", "duration_seconds")),
               "keeper_process": legacy.scalar_fields(keeper, ("terminal", "actual_exit_code", "finished_at")),
               "phase_exit_interpretation": "Phase OS exits are preserved individually; an outer first-round review gate exit1 does not replace any per-case verdict."}
    if final_execution == "execution-rest":
        prior_stop = reader.required(batch / "execution/stop/result.json")
        prior_process = reader.required(batch / "execution/stop/compose-stop.exit.json")
        prior_keeper = reader.required(batch / "execution/keeper.exit.json")
        require(terminal_process(prior_process) and terminal_process(prior_keeper), "Earlier stage stop/keeper observations are not terminal")
        closure["retained_prior_phase_closure"] = {
            "stop_source": "execution/stop/result.json", "keeper_source": "execution/keeper.exit.json",
            "stop": legacy.scalar_fields(prior_stop, ("status", "remaining_running_owned", "volumes_retained", "completed_at")),
            "compose_stop_process": legacy.scalar_fields(prior_process, ("terminal", "actual_exit_code", "completed_at", "duration_seconds")),
            "keeper_process": legacy.scalar_fields(prior_keeper, ("terminal", "actual_exit_code", "finished_at")),
            "original_receipts_retained": True}
    # Only known machine-root strings in allowlisted projections are normalized. Original bytes remain untouched.
    path_rules = [(str(root), "[checkout]"), (root.as_posix(), "[checkout]"),
                  (str(batch), "[batch]"), (batch.as_posix(), "[batch]")]
    def project(value):
        if isinstance(value, dict):
            return {k: project(v) for k, v in value.items()}
        if isinstance(value, list):
            return [project(v) for v in value]
        if isinstance(value, str):
            for prefix, replacement in path_rules:
                value = value.replace(prefix, replacement)
        return value
    for relative, bound in reader.inputs.items():
        require(sha((batch / relative).read_bytes()) == bound["sha256"], "Evidence changed before staging: " + relative)
    payloads = {"summary.json": encoded(project(report)), "closure-and-recovery.json": encoded(project(closure))}
    bindings = {"schema_version": "revalidation-input-bindings/1", "original_inputs": reader.inputs,
                "frozen_source_sha256": source_map, "collector_sha256": sha(Path(__file__).read_bytes()),
                "legacy_collector_sha256": LEGACY_SHA256, "authorized_launcher_inputs_sha256": launcher_bindings,
                "path_projection": {"mode": "explicit-known-root replacement in allowlisted projection values only",
                                    "root_tokens": ["[checkout]", "[batch]"], "original_inputs_modified": False},
                "published_projections": {name: {"sha256": sha(raw), "bytes": len(raw), "source_locators": list(reader.inputs)}
                                          for name, raw in payloads.items()}}
    payloads["source-inputs.json"] = encoded(bindings)
    payloads["tooling/collect_closed_revalidation.py"] = Path(__file__).read_bytes()
    payloads["tooling/collect_results_v4.py"] = legacy_raw
    payloads["README.md"] = ("# 新版修复正式复验（独立12例）\n\n"
        + f"准备12，尝试{counts['passed'] + counts['failed']}，通过{counts['passed']}，失败{counts['failed']}，未尝试{counts['not_attempted']}。\n\n"
        + "[结果与逐项判据](summary.json) · [真实进程终态与收尾](closure-and-recovery.json) · [原始输入与投影哈希](source-inputs.json)\n\n"
        + "原22例仍为18通过/4失败，保留原冻结源码和全部原判；本批不合并成功率，也不解除旧未知订单、T05、Kafka/Monitor、新机或长期验收。\n\n"
        + "复核使用tooling内两个固定哈希采集器，准备计划和原始结果保留其原目录结构；显式传 --batch <原始批次目录> --terminal <真实终态记录> --stage。默认不读取运行结果或写文件。"
        + "仅在真实父进程、逐例runner、Compose stop和keeper均已有终态收据后采集；候选目录须另行审阅及扫描，采集不等于发布。\n\n"
        + "原始私有计划/凭据/消息不复制；source-inputs逐项绑定原件字节SHA与公开投影。公开结果是字段白名单投影，已知本机根路径使用[checkout]/[batch]替换，不能作私有运行输入。"
        + "handover准备大小、完整IFC发送、替代方确认分列；wrapper次数不等于物理资源修改次数。\n").encode("utf-8")
    output = (args.output or HERE / ("evidence-stage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    require(output.is_relative_to(HERE) and not output.exists(), "Output must be a new directory within this publication directory")
    manifest = {"status": "STAGED_FOR_ROOT_REVIEW", "counts": counts, "original_inputs_modified": False,
                "checkout_modified": False, "tests_or_resource_calls": 0,
                "payloads": [{"target": TARGET + "/" + name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in payloads.items()]}
    for name, raw in payloads.items():
        path = output / "candidate" / TARGET / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (output / "staging-manifest.json").write_bytes(encoded(manifest))
    print(json.dumps({"status": manifest["status"], "output": str(output), "counts": counts,
                      "manifest_sha256": sha((output / "staging-manifest.json").read_bytes())}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--batch", type=Path, default=HERE.parent)
    parser.add_argument("--terminal", type=Path)
    parser.add_argument("--legacy", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.stage:
        print(json.dumps({"status": "PREPARED_NOT_STAGED", "runtime_input_reads": 0, "writes": 0,
                          "required": "--stage only after root records real terminal batch/runner/stop/keeper observations"}))
        return
    collect(args)


if __name__ == "__main__":
    main()
