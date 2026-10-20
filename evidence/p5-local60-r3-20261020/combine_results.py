"""Derive one 60-cell view while retaining both raw sessions and the interruption."""
import shutil
from report import ROOT, BATCH, ARTIFACTS, RUN, OUTPUT, load, save, sha, validate_inputs


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha(target) != sha(source):
        raise ValueError("Existing derived copy differs: " + str(target))
    shutil.copyfile(source, target)
    if sha(target) != sha(source):
        raise ValueError("Copy mismatch: " + str(source))


def main():
    original = BATCH / "matrix"
    continuation = BATCH / "continuation/matrix"
    plan = load(BATCH / "continuation/plan.json")
    for name, expected in load(BATCH / "continuation/original-matrix-bindings.json")["files"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Original interrupted evidence changed: " + name)
    if load(BATCH / "continuation/execution-result.json")["status"] != "EVALUATOR_FINISHED":
        raise ValueError("Continuation has not finished")
    first, second = load(original / "results.json"), load(continuation / "results.json")
    if len(first) != 44 or len(second) != 16:
        raise ValueError("Expected 44 original and 16 continuation terminal cells")
    rows = first + second
    experiments = [load(p / "experiment.json") for p in (original, continuation)]
    for key in ("source_sha256", "method_definition_ids", "verification_definition_id",
                "sampling", "budgets", "held_out_instances", "model", "model_base_url"):
        if experiments[0][key] != experiments[1][key]:
            raise ValueError("Session configuration mismatch: " + key)
    save(RUN / "results.json", rows)
    result_bytes = (original / "results.jsonl").read_bytes() + (continuation / "results.jsonl").read_bytes()
    (RUN / "results.jsonl").write_bytes(result_bytes)
    copy(original / "experiment.json", RUN / "experiment.json")
    for name in experiments[0]["source_sha256"]:
        for source in (original, continuation):
            if sha(source / "source" / name) != experiments[0]["source_sha256"][name]:
                raise ValueError("Frozen source mismatch: " + name)
        copy(original / "source" / name, RUN / "source" / name)
    interruption = {**plan["interrupted_attempt"], "classification": "USER_STOPPED_EXCLUDED",
                    "user_clarification": "User confirmed intentional exit; excluded from all experiment statistics"}
    bindings = {"kind": "DERIVED_TWO_SESSION_VIEW", "original_terminal_cells": 44,
                "continuation_terminal_cells": 16, "counted_experiment_cells": 60,
                "excluded_user_stopped_record": interruption, "sessions": {},
                "terminal_incident_sources": {}, "complete_total_cost_available": False}
    message_bytes = b""
    line_offset = 0
    for label, source, group in (("original", original, first), ("continuation", continuation, second)):
        messages = (source / "transport/messages.jsonl").read_bytes()
        bindings["sessions"][label] = {
            "matrix": str(source.relative_to(ROOT)),
            "results_sha256": sha(source / "results.json"),
            "experiment_sha256": sha(source / "experiment.json"),
            "messages_sha256": sha(source / "transport/messages.jsonl"),
            "combined_message_start_line": line_offset + 1,
            "message_lines": len(messages.splitlines())}
        line_offset += len(messages.splitlines())
        message_bytes += messages
        for name in ("results.json", "results.jsonl", "experiment.json", "transport/messages.jsonl"):
            copy(source / name, OUTPUT / "raw-sessions" / label / name)
        for row in group:
            name = row["incident_id"] + ".json"
            copy(source / "incidents" / name, RUN / "incidents" / name)
            bindings["terminal_incident_sources"][row["incident_id"]] = label
            cell = f"{row['scenario']}-{row['method']}-{row['repeat']}"
            for path in (source / "workloads" / cell).rglob("*"):
                if path.is_file():
                    copy(path, RUN / path.relative_to(source))
    (RUN / "transport").mkdir(parents=True, exist_ok=True)
    (RUN / "transport/messages.jsonl").write_bytes(message_bytes)
    interrupted = interruption
    copy(original / "incidents" / (interrupted["incident_id"] + ".json"),
         OUTPUT / "interrupted-attempt" / (interrupted["incident_id"] + ".json"))
    cell = "-".join(str(part) for part in interrupted["cell"])
    for path in (original / "workloads" / cell).rglob("*"):
        if path.is_file():
            copy(path, OUTPUT / "interrupted-attempt/workload" / path.relative_to(original / "workloads" / cell))
    save(OUTPUT / "interrupted-attempt/README.json", interrupted)
    bindings["combined_results_sha256"] = sha(RUN / "results.json")
    bindings["combined_messages_sha256"] = sha(RUN / "transport/messages.jsonl")
    save(OUTPUT / "continuation-provenance.json", bindings)
    validate_inputs()
    print("Combined 44 + 16 terminal cells; original interrupted attempt retained separately.")


if __name__ == "__main__":
    main()
