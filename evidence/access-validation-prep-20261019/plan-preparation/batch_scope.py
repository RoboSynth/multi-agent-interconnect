"""Shared file-only scope and authorization gates for exactly four new cases."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH / "checkout"
PROJECT = "incident-pilot-access-validation-20261019"
PROFILE = ROOT / "runtime/private/access-validation-20261019"
PRIVATE = ROOT / "runtime/private/access-validation-plans-20261019"
RESULTS = ROOT / "eval/results/platform/access-validation-20261019"
PORTS = dict(app_v1=60881, app_v2=60882, order=60888, reply_drop=60890)
EXECUTION_FILES = ("plan-preparation/batch_scope.py", "plan-preparation/prepare_bound_plans.py",
                   "run_authorized.py", "run_f10.py")
F10_EFFECTS = ["one F10 compound stale-route/read-only/pool fault on the bound project",
               "M0 fixed planner; no model calls; approved bound resource repairs",
               "normal SDK close of only the group created and owned by this case",
               "independent F10 restoration and 30-second/10-workflow final H00"]
BOOL_AUTH = ("authorized", "project_start_authorized", "exclusive_coordinator", "no_other_identity_consumers", "no_active_or_unknown_operations",
             "normal_owned_group_cleanup_authorized", "offline_access_recovery_authorized",
             "fault_and_resource_restore_authorized", "final_owned_project_stop_authorized")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def local(value):
    result = (ROOT / value).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError("Plan paths must remain in this checkout")
    return result


def product():
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
    from eval import platform_resume_experiment as e1
    from eval.targets import DockerTarget
    from deploy.prepare_deployment import load_deployment
    return e1, DockerTarget, load_deployment


def schedule():
    return [dict(order=1, key="f10-m0-r1", case="F10", point=None, method="M0", repeat=1),
            *[dict(order=index, key="e1a-" + point + "-r1", case="E1-a", point=point, method=None, repeat=1)
              for index, point in enumerate(("after_observation", "before_modification", "after_applied"), 2)]]


def images():
    result = {}
    for component, directory in (("agent", "image-build"), ("app-v2", "app-image-build")):
        path = BATCH / directory / "result.json"
        value = load(path)
        if (type(value.get("actual_exit_code")) is not int or value["actual_exit_code"] != 0
                or value.get("process_terminal") is not True or type(value.get("inspect_exit_code")) is not int
                or value["inspect_exit_code"] != 0 or value.get("image_reference") != PROJECT + "-" + component + ":local"
                or re.fullmatch(r"sha256:[0-9a-f]{64}", value.get("image_id", "")) is None):
            raise ValueError("Require terminal successful build/inspection receipts for both exact project images")
        result[component] = dict(result_sha256=sha(path), image_id=value["image_id"], image_reference=value["image_reference"])
    return result


def source_commit(commit, hashes):
    if re.fullmatch(r"[0-9a-f]{40}", commit or "") is None:
        raise ValueError("An explicit published source commit is required")
    git = shutil.which("git")
    if not git:
        raise ValueError("Git is required for the immutable source binding")
    ancestry = subprocess.run([git, "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
    listing = subprocess.run([git, "-C", str(ROOT), "ls-tree", "-r", "-z", commit], capture_output=True)
    if ancestry.returncode != 0 or listing.returncode != 0:
        raise ValueError("Source commit must exist in this checkout's ancestry")
    tree = {}
    for row in listing.stdout.split(b"\0"):
        if row:
            attributes, name = row.split(b"\t", 1)
            mode, kind, object_id = attributes.decode().split()
            tree[name.decode("utf-8")] = (kind, object_id)
    for name, expected in hashes.items():
        raw = local(name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if tree.get(name) != ("blob", blob) or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Source differs from the explicit immutable source commit: " + name)


def deployment():
    e1, DockerTarget, load_deployment = product()
    manifest = load_deployment(PROFILE / "deployment.json", root=ROOT)
    target = DockerTarget.from_file(local(manifest["target_config"]), root=ROOT)
    if manifest["mode"] != "seven" or manifest["project"] != PROJECT or target.project != PROJECT or target.ports != PORTS:
        raise ValueError("Only the exact new seven-identity project and four ports are allowed")
    return manifest, target


def plan_map(rows):
    return {row["key"]: row["plan_sha256"] for row in rows}


def validate_f10(plan):
    expected = dict(schema_version="access-validation-f10-plan/1", case="F10", method="M0", repeat=1,
                    model_calls=0, enable_llm=False, transport="wutong-amqps", backend="docker",
                    project=PROJECT, effects=F10_EFFECTS)
    if any(plan.get(key) != value or type(plan.get(key)) is not type(value) for key, value in expected.items()):
        raise ValueError("F10 must remain exactly one M0/no-model formal Docker case")
    for name, expected_hash in plan["file_sha256"].items():
        if sha(local(name)) != expected_hash:
            raise ValueError("Frozen F10 input changed")
    if local(plan["output"]) != RESULTS / "f10-m0-r1":
        raise ValueError("F10 output differs from its preallocated case")
    return plan


def validate_summary(path=HERE / "prepared-summary.json", *, allow_consumed=()):
    summary = load(path)
    if (summary.get("schema_version") != "access-validation-batch/1" or summary.get("project") != PROJECT
            or summary.get("ports") != PORTS or summary.get("plan_count") != 4
            or type(summary["plan_count"]) is not int or summary.get("execution_authorization_written") is not False):
        raise ValueError("Batch summary differs from the four-case scope")
    if summary.get("image_results") != images():
        raise ValueError("Image build receipt changed")
    manifest, target = deployment()
    if summary["deployment_sha256"] != sha(PROFILE / "deployment.json"):
        raise ValueError("Deployment manifest changed")
    e1, *_ = product()
    current = {p.relative_to(ROOT).as_posix(): sha(p) for p in e1.source_paths()}
    if current != summary["source_sha256"]:
        raise ValueError("Current source set/content differs from the frozen batch")
    source_commit(summary["source_commit"], current)
    if summary.get("execution_script_sha256") != {name: sha(BATCH / name) for name in EXECUTION_FILES}:
        raise ValueError("Batch execution/preparation helper changed after freeze")
    rows = summary.get("plans", [])
    if [{key: row.get(key) for key in scope} for row, scope in zip(rows, schedule())] != schedule() or len(rows) != 4:
        raise ValueError("Cases, order, point or information method changed")
    if summary.get("batch_plans_sha256") != canonical_sha(plan_map(rows)):
        raise ValueError("Four-plan aggregate binding differs")
    for row in rows:
        path = local(row["plan"])
        if sha(path) != row["plan_sha256"] or path != PRIVATE / row["key"] / "plan.json":
            raise ValueError("Individual frozen plan changed")
        if local(row["output"]) != RESULTS / row["key"]:
            raise ValueError("Unexpected case output")
        if row["key"] not in allow_consumed and local(row["output"]).exists():
            raise ValueError("Never retry or overwrite a consumed case")
        if row["case"] == "F10":
            plan = validate_f10(load(path))
        elif row["key"] in allow_consumed:
            plan = load(path)
        else:
            plan = e1.validate_plan(path)
        if row["case"] == "E1-a" and (plan.get("recover_access") is not True or plan.get("image_id") != summary["image_results"]["agent"]["image_id"]):
            raise ValueError("Every E1 case requires bound original-journal recovery and the exact image")
    return summary, manifest, target


def validate_authorization(path, summary, summary_path=HERE / "prepared-summary.json"):
    if path is None or not Path(path).is_file():
        raise ValueError("A new explicit four-case batch authorization file is required before execution")
    auth = load(path)
    fixed = dict(schema_version="access-validation-batch-authorization/1", project=PROJECT, plan_count=4,
                 source_commit=summary["source_commit"], prepared_summary_sha256=sha(summary_path),
                 batch_plans_sha256=summary["batch_plans_sha256"], plans=plan_map(summary["plans"]), model_calls=0,
                 **{key: True for key in BOOL_AUTH})
    if set(auth) != set(fixed) | {"user_confirmation", "received_at_utc"}:
        raise ValueError("Authorization fields must exactly match this batch")
    if any(auth[key] != value or type(auth[key]) is not type(value) for key, value in fixed.items()):
        raise ValueError("Authorization does not strictly bind the new batch and all its cleanup effects")
    confirmation = auth["user_confirmation"]
    if (not isinstance(confirmation, dict) or set(confirmation) != {"question_id", "exact_answer"}
            or any(not isinstance(value, str) or not value.strip() for value in confirmation.values())
            or not isinstance(auth["received_at_utc"], str) or not auth["received_at_utc"].strip()):
        raise ValueError("Record this batch's actual new user reply; no copied prior authorization")
    return auth
