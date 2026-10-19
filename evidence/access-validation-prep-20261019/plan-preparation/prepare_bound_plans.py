"""Prepare exactly F10/M0 and three E1-a points; file-only, never authorize."""
from __future__ import annotations
import argparse
from types import SimpleNamespace
import batch_scope as scope


def prepare(commit):
    if scope.PRIVATE.exists() or scope.RESULTS.exists() or (scope.HERE / "prepared-summary.json").exists():
        raise ValueError("Preserve prior plans/results; preparation requires all new roots")
    e1, *_ = scope.product()
    manifest, target = scope.deployment()
    image_results = scope.images()
    sources = {p.relative_to(scope.ROOT).as_posix(): scope.sha(p) for p in sorted(e1.source_paths())}
    scope.source_commit(commit, sources)
    config_path = scope.local(manifest["coordinator_config"])
    config = scope.load(config_path)
    primary = config["initial_participant_aics"]["database"]
    trusted = config["trusted_participant_aics"]["database"]
    if not isinstance(trusted, list) or len(trusted) != 2 or trusted.count(primary) != 1:
        raise ValueError("Require exactly one primary and distinct backup")
    backup = next(value for value in trusted if value != primary)
    identities = e1.identities(config, primary, backup)
    from eval import prepare_platform_e1_worker as worker
    scope.PRIVATE.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        for item in scope.schedule():
            directory = scope.PRIVATE / item["key"]
            directory.mkdir()
            plan_path, output = directory / "plan.json", scope.RESULTS / item["key"]
            common = dict(config=str(config_path), target_config=str(scope.local(manifest["target_config"])),
                          output=str(output), plan=str(plan_path))
            if item["case"] == "F10":
                inputs = {**sources, **manifest["input_sha256"],
                          (scope.PROFILE / "deployment.json").relative_to(scope.ROOT).as_posix(): scope.sha(scope.PROFILE / "deployment.json")}
                plan = dict(schema_version="access-validation-f10-plan/1", case="F10", method="M0", repeat=1,
                            model_calls=0, enable_llm=False, transport="wutong-amqps", backend="docker",
                            project=scope.PROJECT, effects=scope.F10_EFFECTS, image_id=image_results["agent"]["image_id"],
                            identities=identities, file_sha256=inputs,
                            **{key: scope.local(value).relative_to(scope.ROOT).as_posix()
                               for key, value in common.items() if key != "plan"})
                scope.save(plan_path, plan)
                scope.validate_f10(plan)
            else:
                experiment = "access-validation-20261019-" + item["key"]
                bundle = directory / "bundle"
                worker.prepare(bundle, experiment_id=experiment, incident_id=experiment,
                               primary_aic=primary, backup_aic=backup, crash_point=item["point"], arm_primary=True)
                plan = e1.prepare(SimpleNamespace(**common, domain_profile=str(scope.PROFILE), bundle=str(bundle),
                    image_id=image_results["agent"]["image_id"], case="E1-a", method=None, recover_access=True))
                e1.validate_plan(plan_path)
            if any(plan["file_sha256"].get(name) != digest for name, digest in sources.items()):
                raise ValueError("Plans must share one exact source freeze")
            rows.append({**item, "plan": plan_path.relative_to(scope.ROOT).as_posix(),
                         "plan_sha256": scope.sha(plan_path), "output": output.relative_to(scope.ROOT).as_posix()})
        scope.source_commit(commit, sources)
        result = dict(schema_version="access-validation-batch/1", status="PLANS_PREPARED_VALIDATED_NOT_EXECUTED",
            source_commit=commit, project=scope.PROJECT, ports=scope.PORTS, plan_count=4,
            source_sha256=sources, image_results=image_results, deployment_sha256=scope.sha(scope.PROFILE / "deployment.json"),
            execution_script_sha256={name: scope.sha(scope.BATCH / name) for name in scope.EXECUTION_FILES},
            plans=rows, batch_plans_sha256=scope.canonical_sha(scope.plan_map(rows)),
            execution_authorization_written=False, resources_platform_model_started=False)
        scope.save(scope.HERE / "prepared-summary.json", result)
        scope.validate_summary()
        table = ["# New four-case access validation scope", "", "Prepared only; no execution authorization exists.", "",
                 "Source commit: `" + commit + "`", "", "Four-plan aggregate SHA256: `" + result["batch_plans_sha256"] + "`", "",
                 "| Order | Case | Point / method | Plan SHA256 |", "|---:|---|---|---|"]
        table += [f"| {r['order']} | {r['case']} | {r['point'] or r['method']} | {r['plan_sha256']} |" for r in rows]
        table += ["", "Project: `" + scope.PROJECT + "`; ports 60881/60882/60888/60890. Seven identities must have no other consumers.",
                  "F10/M0 runs once without a model. E1-a runs once at each of its three crash points, with explicit original-journal offline recovery.",
                  "Serial execution retains all failed outcomes and logs. Each case attempts normal close of only its proven owned group, resource restoration and independent 30s/10-workflow H00. Unsafe cleanup stops the remainder.",
                  "Authorization must additionally cover project startup, this exact four-plan hash, planned fault/repair actions, offline recovery containers, normal owned-group SDK close (queues/exchange/ACL), and final stop of this batch's owned processes while retaining volumes.",
                  "Default launcher behavior is validation only. --execute requires a separately supplied new batch authorization JSON and an actual new user confirmation; no executable authorization is generated by preparation.",
                  "Neither this batch nor a passing case retroactively repairs the old 22/12 cohorts or proves Monitor/Kafka ingestion, another machine or long-run stability."]
        (scope.HERE / "run-scope.md").write_text("\n".join(table) + "\n", encoding="utf-8")
        return result
    except Exception as error:
        scope.save(scope.PRIVATE / "preparation-failure.json", dict(status="FAILED_PARTIAL_PLANS_RETAINED",
                   error_class=type(error).__name__, validated_plans=rows, execution_authorization_written=False))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        result = prepare(args.source_commit)
    else:
        e1, *_ = scope.product()
        scope.deployment(); scope.images()
        scope.source_commit(args.source_commit, {p.relative_to(scope.ROOT).as_posix(): scope.sha(p) for p in e1.source_paths()})
        result = dict(status="FILE_SCOPE_VALIDATED_NO_WRITES", plan_count=4)
    print(scope.json.dumps({key: result[key] for key in ("status", "plan_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
