"""Prepare this acceptance cohort with existing file-only preparers; never execute it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "checkout"
PROFILE = ROOT / "runtime/private/acceptance-20261019"
PRIVATE = ROOT / "runtime/private/acceptance-plans-20261019"
RESULTS = ROOT / "eval/results/platform/acceptance-20261019"
PROJECT = "incident-pilot-acceptance-20261019"
IMAGE_REFERENCE = PROJECT + "-agent:local"
PORTS = {"app_v1": 48081, "app_v2": 48082, "order": 48088, "reply_drop": 48090}
POINTS = ("after_observation", "before_modification", "after_applied")
METHODS = ("from_scratch", "full_history", "resume_package")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def image_success(document):
    if (not isinstance(document, dict) or type(document.get("actual_exit_code")) is not int
            or document["actual_exit_code"] != 0 or document.get("process_terminal") is not True
            or type(document.get("inspect_exit_code")) is not int or document["inspect_exit_code"] != 0
            or document.get("image_reference") != IMAGE_REFERENCE
            or re.fullmatch(r"sha256:[0-9a-f]{64}", document.get("image_id", "")) is None):
        raise ValueError("An actually successful terminal build and image inspection for the exact acceptance tag is required")
    return document["image_id"]


def schedule():
    rows = []
    for repeat in (1, 2, 3):
        rows += [dict(case="E1-a", point=point, method=None, repeat=repeat) for point in POINTS]
        rows += [dict(case="E1-b", point="after_applied", method=method, repeat=repeat) for method in METHODS]
        rows.append(dict(case="E1-c", point="before_modification", method=None, repeat=repeat))
        if repeat == 1:
            rows.append(dict(case="F12/E5", point=None, method=None, repeat=1))
    for order, row in enumerate(rows, 1):
        parts = [row["case"].lower().replace("/", "-").replace("-", ""), row["method"] or row["point"], "r" + str(row["repeat"])]
        row.update(order=order, key="-".join(part for part in parts if part), first_round=order <= 8)
    return rows


def require_new(private=PRIVATE, results=RESULTS):
    if private.exists() or results.exists():
        raise ValueError("Acceptance plan and result roots must both be new; preserve prior attempts")


def inputs(image_path):
    image_id = image_success(load(image_path))
    require_new()
    # No runner, Controller, Docker client, transport or model object is constructed.
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
    from deploy.prepare_deployment import load_deployment
    from eval.targets import DockerTarget
    from eval import platform_resume_experiment as e1
    manifest = load_deployment(PROFILE / "deployment.json", root=ROOT)
    if manifest["mode"] != "seven" or manifest["project"] != PROJECT:
        raise ValueError("Only this explicit seven-role acceptance deployment is allowed")
    target_path, config_path = ROOT / manifest["target_config"], ROOT / manifest["coordinator_config"]
    target = DockerTarget.from_file(target_path, root=ROOT)
    if target.project != PROJECT or target.ports != PORTS:
        raise ValueError("Acceptance project or four explicit ports differ")
    config = load(config_path)
    primary = config["initial_participant_aics"]["database"]
    trusted = config["trusted_participant_aics"]["database"]
    if not isinstance(trusted, list) or len(trusted) != 2 or trusted.count(primary) != 1:
        raise ValueError("Coordinator must identify exactly one initial primary and one distinct backup")
    backup = next(aic for aic in trusted if aic != primary)
    e1.identities(config, primary, backup)
    return image_id, target_path, config_path, primary, backup


def authorization_fields():
    return """# Authorization expected fields (review documentation only)

No executable authorization JSON is generated. Preparation is not authorization.
Before any later execution, the operator must separately authorize the exact
plan SHA and effects and verify exclusive coordinator/identity/resource ownership.

E1 fields, matching eval.platform_resume_experiment.authorize:
schema_version, authorized, plan_sha256, experiment_id, incident_id, output,
case, crash_point, effects, exclusive_coordinator, no_other_identity_consumers,
no_active_or_unknown_operations. E1-b also requires method; E1-c additionally
requires interruption_mode=suspend and replay_attempts=1. Execution also needs
the existing --approve-high flag. Boolean preconditions must be genuinely true.

F12/E5 fields, matching eval.unknown_receipt_experiment.authorize_target:
schema_version, authorized, plan_sha256, experiment_id, project, output, effects,
exclusive_coordinator, no_other_identity_consumers, no_active_or_unknown_operations.
Its existing runner includes the missing-original-key control within the one case.

All 22 outputs must remain absent before their individual run. Never run these
plans concurrently: they share the same seven identities and deployment.
Run the first eight distinct cases first; review their actual outcomes before
continuing repeats 2 and 3. Every case retains the existing normal-close,
worker/resource-restore and independent-H00 checks. The generated plans do not
claim image import attestation or successful runtime checks.
"""


def prepare(image_path):
    image_id, target_path, config_path, primary, backup = inputs(image_path)
    from eval import prepare_platform_e1_worker as worker
    from eval import platform_resume_experiment as e1
    from eval import unknown_receipt_experiment as f12
    source_before = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(e1.source_paths())}
    PRIVATE.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        for item in schedule():
            directory = PRIVATE / item["key"]
            directory.mkdir()
            plan_path, output = directory / "plan.json", RESULTS / item["key"]
            common = dict(target_config=str(target_path), config=str(config_path), plan=str(plan_path), output=str(output))
            if item["case"] == "F12/E5":
                plan = f12.prepare_target(SimpleNamespace(**common))
                f12.validate_target_plan(plan_path)
            else:
                experiment = "acceptance-20261019-" + item["key"]
                bundle = directory / "bundle"
                worker.prepare(bundle, experiment_id=experiment, incident_id=experiment,
                    primary_aic=primary, backup_aic=backup, crash_point=item["point"],
                    arm_primary=True, suspend_primary=item["case"] == "E1-c")
                plan = e1.prepare(SimpleNamespace(**common, domain_profile=str(PROFILE), bundle=str(bundle),
                    image_id=image_id, case=item["case"], method=item["method"]))
                e1.validate_plan(plan_path)
            if any(plan["file_sha256"].get(name) != value for name, value in source_before.items()):
                raise ValueError("A prepared plan does not bind the same current source freeze")
            rows.append({**item, "plan": plan_path.relative_to(ROOT).as_posix(), "plan_sha256": digest(plan_path),
                         "output": output.relative_to(ROOT).as_posix(), "validated": True})
        if source_before != {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(e1.source_paths())}:
            raise ValueError("Source changed during preparation; preserve partial plans and do not execute them")
        if RESULTS.exists():
            raise ValueError("Result root was unexpectedly created during preparation")
        (PRIVATE / "AUTHORIZATION-EXPECTED-FIELDS.md").write_text(authorization_fields(), encoding="utf-8")
        result = dict(status="PLANS_PREPARED_VALIDATED_NOT_EXECUTED", plan_count=len(rows), image_id=image_id,
            image_result_sha256=digest(image_path), project=PROJECT, ports=PORTS, source_sha256=source_before,
            first_round_distinct_cases=8, remaining_repeat_plans=14, plans=rows,
            execution_authorization_written=False, Docker_network_model_resource_actions=0)
        save(HERE / "prepared-summary.json", result)
        table = ["# Acceptance plan review scope", "", "Prepared and validated only. No execution authorization was generated.", "",
                 "Run order 1–8 covers all eight distinct cases; review actual results before repeats. Run serially.", "",
                 "| Order | Case | Point | Method | Repeat | Plan SHA256 |", "|---:|---|---|---|---:|---|"]
        table += [f"| {r['order']} | {r['case']} | {r['point'] or '—'} | {r['method'] or '—'} | {r['repeat']} | {r['plan_sha256']} |" for r in rows]
        table += ["", "E1-a: 9 plans; E1-b: 9 plans; E1-c: 3 plans; F12/E5: 1 plan with its existing missing-key control.",
                  "All plans share one deployment and identities. Existing runner preconditions, normal close, restoration and independent H00 remain required."]
        (HERE / "run-scope.md").write_text("\n".join(table) + "\n", encoding="utf-8")
        return result
    except Exception as error:
        save(PRIVATE / "preparation-failure.json", dict(status="PREPARATION_FAILED_PARTIALS_RETAINED",
             error_class=type(error).__name__, validated_plans=rows, execution_authorization_written=False))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-result", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true", help="Pure file preparation after source freeze; never execute")
    args = parser.parse_args(argv)
    if not args.prepare:
        image_id, *_ = inputs(args.image_result.resolve())
        result = dict(status="PREPARATION_SCOPE_VALIDATED_NO_WRITES", image_id=image_id,
                      project=PROJECT, ports=PORTS, plan_count=len(schedule()), first_round_distinct_cases=8,
                      plans=schedule(), Docker_network_model_resource_actions=0)
    else:
        result = prepare(args.image_result.resolve())
    print(json.dumps({key: result[key] for key in ("status", "plan_count", "image_id", "project", "ports")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
