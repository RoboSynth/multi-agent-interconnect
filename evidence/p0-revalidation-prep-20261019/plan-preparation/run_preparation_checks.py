"""Capture one guard/default/prepare sequence; project actions remain file-only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "checkout"
IMAGE = HERE.parent / "image-build/result.json"
RECORD = HERE / "preparation-checks.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(record):
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if RECORD.exists():
        raise ValueError("This verification record already exists; preserve it")
    record = dict(schema_version="revalidation-preparation-checks/1", started_at=datetime.now(timezone.utc).isoformat(),
        status="running", execution_authorization_written=False, project_actions="file_only",
        image_result_sha256=sha(IMAGE), tool_sha256={name: sha(HERE / name) for name in
            ("prepare_bound_plans.py", "test_prepare_bound_plans.py", "run_preparation_checks.py")}, stages=[])
    save(record)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    commands = [
        ("guards", [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", str(HERE), "-p", "test_prepare_bound_plans.py", "-v"]),
        ("describe", [sys.executable, "-B", "-X", "utf8", str(HERE / "prepare_bound_plans.py"), "--image-result", str(IMAGE)]),
        ("prepare", [sys.executable, "-B", "-X", "utf8", str(HERE / "prepare_bound_plans.py"), "--image-result", str(IMAGE), "--prepare"]),
    ]
    try:
        for label, command in commands:
            result = subprocess.run(command, env=env, cwd=HERE, capture_output=True, timeout=180)
            stdout_path, stderr_path = HERE / (label + ".stdout.txt"), HERE / (label + ".stderr.txt")
            stdout_path.write_bytes(result.stdout)
            stderr_path.write_bytes(result.stderr)
            row = dict(stage=label, argv=command, actual_exit_code=result.returncode,
                stdout=stdout_path.name, stderr=stderr_path.name,
                stdout_sha256=sha(stdout_path), stderr_sha256=sha(stderr_path))
            if label == "guards" and result.returncode == 0:
                row["passed_test_methods"] = 5
            if label in {"describe", "prepare"} and result.returncode == 0:
                row["summary"] = json.loads(result.stdout.decode("utf-8"))
            record["stages"].append(row)
            save(record)
            if result.returncode:
                raise RuntimeError(label + " failed with actual exit " + str(result.returncode))
        sys.dont_write_bytecode = True
        sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
        import prepare_bound_plans as helper
        from eval import platform_resume_experiment as e1
        summary = helper.load(HERE / "prepared-summary.json")
        assert summary["plan_count"] == 12 and len(summary["plans"]) == 12
        assert summary["first_round_distinct_cases"] == 4 and summary["remaining_repeat_plans"] == 8
        assert summary["project"] == helper.PROJECT and summary["ports"] == helper.PORTS
        assert summary["image_result_sha256"] == record["image_result_sha256"] == sha(IMAGE)
        assert summary["image_id"] == helper.image_success(helper.load(IMAGE))
        assert summary["execution_authorization_written"] is False
        assert summary["Docker_network_model_resource_actions"] == 0
        assert not helper.RESULTS.exists()
        expected = helper.schedule()
        for row, scheduled in zip(summary["plans"], expected):
            assert all(row[key] == value for key, value in scheduled.items())
            path = ROOT / row["plan"]
            assert sha(path) == row["plan_sha256"]
            plan = e1.validate_plan(path)
            assert plan["image_id"] == summary["image_id"] and plan["project"] == helper.PROJECT
            assert plan["output"] == row["output"] and not (ROOT / row["output"]).exists()
            assert all(plan["file_sha256"].get(name) == value for name, value in summary["source_sha256"].items())
        assert not list(helper.PRIVATE.rglob("*authorization*.json"))
        record.update(status="passed", finished_at=datetime.now(timezone.utc).isoformat(),
            final_validation=dict(plan_count=12, source_count=len(summary["source_sha256"]),
                validated_plans=12, expected_schedule_equal=True, source_image_config_bundle_hashes_equal=True,
                result_root_absent=True, authorization_json_count=0, resource_or_network_actions=0,
                prepared_summary_sha256=sha(HERE / "prepared-summary.json")))
        save(record)
        print(json.dumps(dict(status=record["status"], stages=len(record["stages"]),
            passed_test_methods=5, validated_plans=12, source_count=len(summary["source_sha256"]),
            image_id=summary["image_id"], execution_authorization_written=False)))
        return 0
    except Exception as error:
        record.update(status="failed", finished_at=datetime.now(timezone.utc).isoformat(), error_class=type(error).__name__)
        save(record)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
