"""Prepare twelve repair-revalidation plans using file-only preparers; never execute."""
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
PROFILE = ROOT / "runtime/private/revalidation-20261019"
PRIVATE = ROOT / "runtime/private/revalidation-plans-20261019"
RESULTS = ROOT / "eval/results/platform/revalidation-20261019"
PROJECT = "incident-pilot-revalidation-20261019"
IMAGE_REFERENCE = PROJECT + "-agent:local"
PORTS = {"app_v1": 58081, "app_v2": 58082, "order": 58088, "reply_drop": 58090}
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
        raise ValueError("An actually successful terminal build and image inspection for the exact revalidation tag is required")
    return document["image_id"]


def schedule():
    rows = []
    for repeat in (1, 2, 3):
        rows.append(dict(case="E1-a", point="after_observation", method=None, repeat=repeat))
        rows += [dict(case="E1-b", point="after_applied", method=method, repeat=repeat) for method in METHODS]
    for order, row in enumerate(rows, 1):
        parts = [row["case"].lower().replace("-", ""), row["method"] or row["point"], "r" + str(row["repeat"])]
        row.update(order=order, key="-".join(parts), first_round=order <= 4)
    return rows


def require_new(private=PRIVATE, results=RESULTS):
    if private.exists() or results.exists():
        raise ValueError("Revalidation plan and result roots must both be new; preserve prior attempts")


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
        raise ValueError("Only this explicit seven-role revalidation deployment is allowed")
    target_path, config_path = ROOT / manifest["target_config"], ROOT / manifest["coordinator_config"]
    target = DockerTarget.from_file(target_path, root=ROOT)
    if target.project != PROJECT or target.ports != PORTS:
        raise ValueError("Revalidation project or four explicit ports differ")
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
Before later execution, separately authorize the exact plan SHA and effects and
verify exclusive coordinator/identity/resource ownership. This batch is a repair
revalidation, not a full E1, E1-c or F12/E5 acceptance replacement.

E1 fields, matching eval.platform_resume_experiment.authorize:
schema_version, authorized, plan_sha256, experiment_id, incident_id, output,
case, crash_point, effects, exclusive_coordinator, no_other_identity_consumers,
no_active_or_unknown_operations. E1-b also requires method. Execution also needs
the existing --approve-high flag. Boolean preconditions must be genuinely true;
the process-local lock cannot prove that identities are idle on a teammate host.

All 12 outputs must remain absent before their individual run. Run serially because
the plans share seven identities and one deployment. Review the four distinct
first-round conditions before continuing repeats 2 and 3 (eight further plans).
Each case retains normal SDK group close, worker/resource restoration and an
independent 30-second/10-complete-workflow H00, including failure-path cleanup.

The requested later authorization should explicitly include starting this isolated
project; exactly the 12 bound cases; the planned F07, pool and owned database-worker
changes; and normal SDK close of groups created by this batch and proven owned by
the relevant case, even after a failure/interruption. Normal group close deletes
that group's remote queues, exchange and ACL. Preserve local evidence and any
failed/warning status. It must not cover unrelated/old/unknown groups or raw broker
deletion. Include final stopping of this batch's project processes while retaining
volumes, ledgers, failed results and unknown operations.

The generated plans do not prove image/import attestation, identity exclusivity,
successful runtime checks, broker ACL inventory or any execution authorization.
"""


def prepare(image_path):
    image_id, target_path, config_path, primary, backup = inputs(image_path)
    from eval import prepare_platform_e1_worker as worker
    from eval import platform_resume_experiment as e1
    source_before = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(e1.source_paths())}
    PRIVATE.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        for item in schedule():
            directory = PRIVATE / item["key"]
            directory.mkdir()
            plan_path, output = directory / "plan.json", RESULTS / item["key"]
            common = dict(target_config=str(target_path), config=str(config_path), plan=str(plan_path), output=str(output))
            experiment = "revalidation-20261019-" + item["key"]
            bundle = directory / "bundle"
            worker.prepare(bundle, experiment_id=experiment, incident_id=experiment,
                primary_aic=primary, backup_aic=backup, crash_point=item["point"], arm_primary=True)
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
            first_round_distinct_cases=4, remaining_repeat_plans=8, plans=rows,
            execution_authorization_written=False, Docker_network_model_resource_actions=0)
        save(HERE / "prepared-summary.json", result)
        table = ["# Repair revalidation plan review scope", "", "Prepared and validated only. No execution authorization was generated.", "",
                 "Run order 1–4 covers four distinct conditions; review actual results before repeats. Run serially.", "",
                 "| Order | Case | Point | Method | Repeat | Plan SHA256 |", "|---:|---|---|---|---:|---|"]
        table += [f"| {r['order']} | {r['case']} | {r['point']} | {r['method'] or '—'} | {r['repeat']} | {r['plan_sha256']} |" for r in rows]
        table += ["", "E1-a after_observation: 3 plans; E1-b after_applied: three methods × 3, nine plans.",
                  "This batch has no E1-c, F12/E5 or other E1-a points. Old results retain their original frozen source and verdicts.",
                  "All plans share one deployment and seven identities. Existing runner preconditions, normal SDK close (including failure cleanup), restoration and independent H00 remain required.",
                  "The source/image/configuration binding does not itself prove runtime acceptance or provide authorization."]
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
                      project=PROJECT, ports=PORTS, plan_count=len(schedule()), first_round_distinct_cases=4,
                      plans=schedule(), Docker_network_model_resource_actions=0)
    else:
        result = prepare(args.image_result.resolve())
    print(json.dumps({key: result[key] for key in ("status", "plan_count", "image_id", "project", "ports")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
