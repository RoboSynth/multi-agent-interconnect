"""Complete the same frozen matrix after a Windows restart, retaining attempt 45."""
import ast
import asyncio
from datetime import datetime, timezone
import difflib
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ORIGINAL = BATCH / "matrix"
sys.path.insert(0, str(ROOT))
import eval.run as evaluator


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    original = load(ORIGINAL / "results.json")
    methods = ["MR", "M0", "M1", "M2v2"]
    order = [(scenario, method, repeat + 1) for scenario in ["F01", "F02", "F06", "F07", "F10"]
             for repeat in range(3) for method in methods[repeat:] + methods[:repeat]]
    keys = [(row["scenario"], row["method"], row["repeat"]) for row in original]
    if keys != order[:44]:
        raise ValueError("Original 44 completed cells differ from the planned prefix")
    for name, expected in load(HERE / "original-matrix-bindings.json")["files"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Interrupted matrix evidence changed: " + name)
    frozen = load(ORIGINAL / "experiment.json")["source_sha256"]
    evaluator.check_sources(frozen)
    source = inspect.getsource(evaluator.run)
    marker = "                for method in ordered_methods:\n"
    if source.count(marker) != 1:
        raise ValueError("Unexpected frozen evaluator loop")
    guarded = source.replace(marker, marker +
        "                    if (scenario, method, repeat + 1) in completed_cell_keys:\n"
        "                        continue\n")
    before, after = ast.parse(source), ast.parse(guarded)
    loops = [node for node in ast.walk(after)
             if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "method"]
    if len(loops) != 1 or not isinstance(loops[0].body[0], ast.If):
        raise ValueError("Unexpected continuation transformation")
    del loops[0].body[0]
    if ast.dump(before) != ast.dump(after):
        raise ValueError("Continuation changes more than the skip guard")
    (HERE / "guarded-run.py").write_text(guarded, encoding="utf-8")
    (HERE / "guard.diff").write_text("".join(difflib.unified_diff(
        source.splitlines(True), guarded.splitlines(True),
        fromfile="frozen eval.run.run", tofile="external continuation orchestration")), encoding="utf-8")
    namespace = dict(vars(evaluator), completed_cell_keys=set(keys))
    exec(compile(guarded, str(HERE / "guarded-run.py"), "exec"), namespace)
    plan = {
        "original_terminal_cells": 44, "remaining_cells": 16, "planned_order": order,
        "remaining_cell_keys": order[44:], "source_sha256": frozen,
        "original_results_sha256": sha(ORIGINAL / "results.json"),
        "original_matrix_bindings_sha256": sha(HERE / "original-matrix-bindings.json"),
        "guard_semantic_diff_verified": True, "guarded_runner_sha256": sha(HERE / "guarded-run.py"),
        "interrupted_attempt": {
            "cell": order[44], "incident_id": "inc-57686eb6d967418d",
            "classification": "WINDOWS_RESTART_INTERRUPTED", "terminal_row": False,
            "system_event_1074_at_utc": "2026-10-20T07:13:19Z",
            "evaluator_exit_code": 1073807364, "cleanup_exit_code": 3221225794,
            "model_cost_complete": False,
        },
        "authorization": "Continue the user-authorized full60 matrix after restart, preserve original results",
    }
    save(HERE / "plan.json", plan)
    return plan, namespace["run"]


def main():
    os.environ["INCIDENT_LLM_API_KEY"] = ""
    plan, run = prepare()
    if "--plan-only" in sys.argv:
        print(json.dumps({"status": "CONTINUATION_READY", "remaining_cells": 16, "guard_verified": True}))
        return 0
    config = load(ROOT / "runtime/local-coordinator.json")
    if (config["mode"] != "local-aip-stdio" or config.get("automatic_takeover") is not False
            or not config["coordinator_aic"].startswith("local-")
            or any(not worker["aic"].startswith("local-") for worker in config["workers"])):
        raise ValueError("Continuation requires isolated local identities")
    args = evaluator.build_parser().parse_args([])
    for key, value in load(BATCH / "execution-intent.json")["arguments"].items():
        setattr(args, key, Path(value) if key in {"config", "runtime", "output", "target_config"}
                and value is not None else value)
    args.output = HERE / "matrix"
    if args.output.exists():
        raise ValueError("Continuation output already exists")
    start = datetime.now(timezone.utc).isoformat()
    save(HERE / "execution-intent.json", {
        "started_at": start, "arguments": vars(args), "remaining_cells": 16,
        "plan_sha256": sha(HERE / "plan.json"), "source_sha256": plan["source_sha256"],
    })
    try:
        code = asyncio.run(run(args))
        rows = load(args.output / "results.json")
        if [(row["scenario"], row["method"], row["repeat"]) for row in rows] != [
                tuple(key) for key in plan["remaining_cell_keys"]]:
            raise ValueError("Continuation did not finish the exact remaining16 cells")
        result = {"status": "EVALUATOR_FINISHED", "exit_code": code, "terminal_cells": len(rows)}
    except BaseException as error:
        traceback.print_exc()
        code, result = 1, {"status": "EVALUATOR_FAILED", "exit_code": 1,
                          "error_class": type(error).__name__, "error": str(error)}
    result.update(started_at=start, finished_at=datetime.now(timezone.utc).isoformat())
    save(HERE / "execution-result.json", result)
    print(json.dumps(result), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
