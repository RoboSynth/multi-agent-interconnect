"""Prepare/validate four cloud cases; execute only with plan-bound authorization.

Preparation is file-only. Execution uses the existing cloud business project,
the official seven AICs and the long-running host's unified lease/handoff.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROJECT = "incident-pilot-new7-cloud-20261019"
PROFILE = "runtime/private/cloud-new7-20261019"
CONTROL = "runtime/private/cloud-longrun/control"
LEASES = "runtime/private/cloud-longrun/leases"
ROLES = ("application", "database", "database-backup", "ops", "verification", "onboarding")
SERVICES = tuple(role + "-agent" for role in ROLES)
LEGACY_F10 = "evidence/access-validation-prep-20261019/run_f10.py"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(value):
    result = (ROOT / value).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError("Batch paths must remain inside this checkout")
    return result


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def product():
    sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
    from eval import platform_resume_experiment as e1
    from eval.targets import DockerTarget
    from deploy.prepare_deployment import load_deployment
    return e1, DockerTarget, load_deployment


def schedule():
    return [dict(key="f10-m0-r1", case="F10", method="M0", point=None),
            *[dict(key="e1a-" + point + "-r1", case="E1-a", method=None, point=point)
              for point in ("after_observation", "before_modification", "after_applied")]]


def helper_paths():
    return [HERE / "cloud_batch.py", HERE / "managed_entrypoint.py", ROOT / "ops/domain_entry.py",
            ROOT / LEGACY_F10, ROOT / "evidence/access-validation-prep-20261019/plan-preparation/batch_scope.py"]


def entrypoint(role, session):
    return ["python", "/batch/entrypoint.py", "--role", role, "--session", session, "--"]


def overlay(directory, session):
    platform_command = ["python", "incident/platform_worker.py", "--config", "/domain/config.json"]
    bridge_command = ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"]
    return {"services": {role + "-agent": {
        "restart": "no", "entrypoint": entrypoint(role, session),
        "command": bridge_command if role in {"database", "database-backup", "ops"} else platform_command,
        "volumes": [
            {"type": "bind", "source": str(directory / "managed_entrypoint.py"), "target": "/batch/entrypoint.py", "read_only": True},
            {"type": "bind", "source": str(directory / "domain_entry.py"), "target": "/batch/domain_entry.py", "read_only": True}]
    } for role in ROLES}}


def prepare(directory, image_id, source_commit):
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id or "") is None:
        raise ValueError("An explicitly inspected agent image ID is required")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit or "") is None:
        raise ValueError("Record the current cloud source commit")
    if directory.exists():
        raise FileExistsError("Preserve an existing batch; use a new private directory")
    e1, DockerTarget, load_deployment = product()
    manifest = load_deployment(ROOT / PROFILE / "deployment.json", root=ROOT)
    target = DockerTarget.from_file(local(manifest["target_config"]), root=ROOT)
    if manifest["project"] != PROJECT or target.project != PROJECT or target.wsl_distro is not None:
        raise ValueError("Only the existing native-Linux cloud NEW7 project is in scope")
    config = load(local(manifest["coordinator_config"]))
    primary = config["initial_participant_aics"]["database"]
    backup = next(aic for aic in config["trusted_participant_aics"]["database"] if aic != primary)
    identities = e1.identities(config, primary, backup)
    directory.mkdir(parents=True, mode=0o700)
    batch_id = "cloud-four-20261020-" + uuid.uuid4().hex[:10]
    for source, name in ((HERE / "managed_entrypoint.py", "managed_entrypoint.py"),
                         (ROOT / "ops/domain_entry.py", "domain_entry.py")):
        shutil.copyfile(source, directory / name)
        (directory / name).chmod(0o644)
    import yaml
    (directory / "consumers.yml").write_text(yaml.safe_dump(overlay(directory, batch_id), sort_keys=False), encoding="utf-8")
    target_value = load(local(manifest["target_config"]))
    target_value["compose_files"].append(relative(directory / "consumers.yml"))
    save(directory / "target.json", target_value)
    from eval import prepare_platform_e1_worker as worker
    sources = {relative(p): sha(p) for p in sorted(e1.source_paths())}
    rows = []
    for item in schedule():
        case_directory = directory / item["key"]
        case_directory.mkdir()
        output = ROOT / "eval/results/platform" / batch_id / item["key"]
        plan_path = case_directory / "plan.json"
        if item["case"] == "F10":
            plan = dict(case="F10", method="M0", model_calls=0, config=manifest["coordinator_config"],
                        target_config=relative(directory / "target.json"), output=relative(output), file_sha256=sources)
            save(plan_path, plan)
        else:
            experiment = batch_id + "-" + item["key"]
            bundle = case_directory / "bundle"
            worker.prepare(bundle, experiment_id=experiment, incident_id=experiment,
                primary_aic=primary, backup_aic=backup, crash_point=item["point"], arm_primary=True)
            plan = e1.prepare(SimpleNamespace(config=str(local(manifest["coordinator_config"])),
                target_config=str(directory / "target.json"), output=str(output), plan=str(plan_path),
                domain_profile=str(ROOT / PROFILE), bundle=str(bundle), image_id=image_id,
                case="E1-a", method=None, recover_access=True))
        rows.append({**item, "plan": relative(plan_path), "plan_sha256": sha(plan_path), "output": relative(output)})
    frozen = set(helper_paths()) | {directory / name for name in ("managed_entrypoint.py", "domain_entry.py", "target.json", "consumers.yml")}
    frozen |= {local(name) for name in manifest["input_sha256"]}
    frozen |= {ROOT / PROFILE / "deployment.json"}
    document = dict(schema_version="cloud-four-revalidation/1", status="prepared_not_executed", batch_id=batch_id,
        prepared_at=now(), source_commit=source_commit, project=PROJECT, image_id=image_id, model_calls=0,
        identities=identities, ports=target.ports, control_directory=CONTROL, lease_directory=LEASES,
        target_config=relative(directory / "target.json"), config=manifest["coordinator_config"],
        domain_profile=PROFILE, results=relative(ROOT / "eval/results/platform" / batch_id),
        source_sha256=sources, helper_and_input_sha256={relative(p): sha(p) for p in sorted(frozen)}, cases=rows)
    save(directory / "batch-plan.json", document)
    validate(directory / "batch-plan.json")
    return document


def validate(path, *, consumed=()):
    plan = load(path)
    if (plan.get("schema_version") != "cloud-four-revalidation/1" or plan.get("project") != PROJECT
            or plan.get("model_calls") != 0 or plan.get("control_directory") != CONTROL
            or plan.get("lease_directory") != LEASES
            or [{key: row.get(key) for key in item} for row, item in zip(plan.get("cases", []), schedule())] != schedule()
            or len(plan.get("cases", [])) != 4):
        raise ValueError("Batch must bind exactly F10/M0 and the three E1-a points")
    e1, DockerTarget, _ = product()
    if plan["source_sha256"] != {relative(p): sha(p) for p in e1.source_paths()}:
        raise ValueError("Frozen product source changed")
    for name, expected in plan["helper_and_input_sha256"].items():
        if sha(local(name)) != expected:
            raise ValueError("Frozen helper/private input changed: " + name)
    target = DockerTarget.from_file(local(plan["target_config"]), root=ROOT)
    if target.project != PROJECT or target.wsl_distro is not None or target.ports != plan["ports"]:
        raise ValueError("Batch target changed")
    for row in plan["cases"]:
        case_path = local(row["plan"])
        if sha(case_path) != row["plan_sha256"]:
            raise ValueError("Case plan changed")
        if row["key"] not in consumed:
            if local(row["output"]).exists():
                raise FileExistsError("Never repeat or overwrite a consumed case")
            if row["case"] == "E1-a":
                case = e1.validate_plan(case_path)
                if case["recover_access"] is not True or case["image_id"] != plan["image_id"]:
                    raise ValueError("E1 must retain original-journal recovery and the bound image")
    return plan, target


def bind_authorization(path, record):
    plan, _ = validate(path)
    value = load(record)
    if (set(value) != {"received_at_utc", "user_confirmation"}
            or any(not isinstance(v, str) or not v.strip() for v in value.values())):
        raise ValueError("Supply the actual current user authorization record")
    target = path.parent / "authorization.json"
    if target.exists():
        raise FileExistsError("Preserve an existing authorization")
    save(target, dict(schema_version="cloud-four-authorization/1", authorized=True,
        batch_plan_sha256=sha(path), batch_id=plan["batch_id"], project=PROJECT, model_calls=0,
        inspection_handoff=True, fault_and_restore=True, original_journal_offline_recovery=True,
        normal_owned_sdk_cleanup=True, stop_owned_consumers=True, **value))
    return target


def validate_authorization(path, authorization):
    plan = load(path)
    auth = load(authorization)
    expected = dict(schema_version="cloud-four-authorization/1", authorized=True,
        batch_plan_sha256=sha(path), batch_id=plan["batch_id"], project=PROJECT, model_calls=0,
        inspection_handoff=True, fault_and_restore=True, original_journal_offline_recovery=True,
        normal_owned_sdk_cleanup=True, stop_owned_consumers=True)
    if (set(auth) != set(expected) | {"received_at_utc", "user_confirmation"}
            or any(type(auth[key]) is not type(value) or auth[key] != value for key, value in expected.items())
            or any(not isinstance(auth.get(key), str) or not auth[key].strip() for key in ("received_at_utc", "user_confirmation"))):
        raise ValueError("Authorization must bind this exact four-case cloud plan")
    return auth


def command(argv):
    e1, *_ = product()
    result = subprocess.run(argv, cwd=ROOT, env=e1.clean_environment(), capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError("Bound batch subprocess failed with exit " + str(result.returncode))
    return result.stdout


def inventory(target):
    ids = command(target.compose + ["ps", "-a", "-q"]).split()
    values = json.loads(command(target.docker + ["inspect", *ids])) if ids else []
    rows = {}
    for value in values:
        labels = value["Config"].get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        if labels.get("com.docker.compose.project") != PROJECT or service in rows:
            raise ValueError("Unexpected/duplicate project container")
        rows[service] = dict(id=value["Id"], image_id=value["Image"], service=service,
            running=value["State"]["Running"], exit_code=value["State"].get("ExitCode"),
            started_at=value["State"]["StartedAt"], created=value["Created"],
            entrypoint=value["Config"].get("Entrypoint"), experiment=labels.get("incident-pilot.experiment"))
    return rows


def registered_after(initial, output, row):
    allowed = {service: {value["id"]} for service, value in initial.items() if service in SERVICES}
    if row["case"] == "E1-a":
        for name in ("experimental-domains.json", "restored-domains.json"):
            if (output / name).exists():
                for service, value in load(output / name).items():
                    if service in {"database-agent", "database-backup-agent"}:
                        allowed[service].add(value["container_id"])
    return allowed


def stop_consumers(target, plan, initial, row, output):
    current = inventory(target)
    allowed = registered_after(initial, output, row)
    for role in ROLES:
        service, value = role + "-agent", current.get(role + "-agent", {})
        if (value.get("id") not in allowed.get(service, set()) or value.get("image_id") != plan["image_id"]
                or value.get("entrypoint") != entrypoint(role, plan["batch_id"])):
            raise ValueError("An unregistered/replaced batch consumer cannot be stopped")
    for service in ("postgres", "app-v1", "app-v2", "nginx"):
        if any(current[service][key] != initial[service][key] for key in ("id", "image_id", "started_at")):
            raise ValueError("Business container changed unexpectedly during the case")
    ids = [current[service]["id"] for service in SERVICES if current[service]["running"]]
    if ids:
        command(target.docker + ["stop", "--time", "30", *ids])
    after = inventory(target)
    receipts = []
    for role in ROLES:
        service = role + "-agent"
        value = after[service]
        if value["id"] != current[service]["id"] or value["running"] or value["exit_code"] != 0:
            raise ValueError("Batch consumer did not normally close its SDK")
        text = command(target.docker + ["logs", "--tail", "1000", value["id"]])
        candidates = []
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                candidates.append(item)
        if not any(item.get("status") == "managed_consumer_closed" and item.get("role") == role
                   and item.get("session") == plan["batch_id"] and item.get("sdk_cleanup_completed") is True
                   for item in candidates):
            raise ValueError("Missing the exact consumer SDK cleanup receipt")
        receipts.append(dict(service=service, id=value["id"], role=role, sdk_cleanup_completed=True))
    return dict(status="six_consumers_closed", receipts=receipts, volumes_retained=True)


async def f10_case(case_plan, target, *, runner=None, observer_factory=None):
    # Reuse the existing reviewed F10 wrapper's execution function, without its
    # consumed old launcher, private profile or authorization entry point.
    spec = importlib.util.spec_from_file_location("cloud_f10_wrapper", ROOT / LEGACY_F10)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.scope = SimpleNamespace(product=product, local=local, load=load, save=save,
                                    deployment=lambda: ({}, target))
    await module.execute(case_plan, runner=runner, observer_factory=observer_factory)
    return load(local(case_plan["output"]) / "wrapper-result.json")


async def execute(path, authorization):
    if os.name != "posix" or os.geteuid() != 0 or ROOT != Path("/opt/incident-pilot"):
        raise PermissionError("Execute as root only in the authorized cloud checkout")
    os.umask(0o077)
    plan, target = validate(path)
    validate_authorization(path, authorization)
    e1, *_ = product()
    from eval.leased_batch import run_leased_batch
    output = local(plan["results"])
    consumed = []

    async def run_case(row):
        validate(path, consumed=consumed)
        validate_authorization(path, authorization)
        before = await asyncio.to_thread(inventory, target)
        if any(before.get(service, {}).get("running") for service in SERVICES):
            raise ValueError("The previous owner has not closed every formal consumer")
        launch_evidence = path.parent / ("ownership-" + row["key"])
        launch_evidence.mkdir(exist_ok=False)
        save(launch_evidence / "before.json", before)
        result = {}
        initial = None
        case_plan = load(local(row["plan"]))
        case_output = local(row["output"])
        try:
            await asyncio.to_thread(command, target.compose + ["up", "-d", "--no-deps", "--force-recreate",
                                    "--no-build", "--pull", "never", *SERVICES])
            initial = await asyncio.to_thread(inventory, target)
            if any(not initial.get(service, {}).get("running") or initial[service]["image_id"] != plan["image_id"]
                   or initial[service]["id"] == before.get(service, {}).get("id") for service in SERVICES):
                raise ValueError("New exact batch consumers did not become running")
            save(launch_evidence / "started.json", initial)
            print(json.dumps(dict(event="case_started", key=row["key"], at=now())), flush=True)
            if row["case"] == "F10":
                result = await f10_case(case_plan, target)
            else:
                auth = dict(schema_version="platform-e1-authorization/2", authorized=True,
                    plan_sha256=sha(local(row["plan"])), experiment_id=case_plan["experiment_id"],
                    incident_id=case_plan["incident_id"], output=case_plan["output"], case="E1-a",
                    crash_point=case_plan["crash_point"], effects=case_plan["effects"], exclusive_coordinator=True,
                    no_other_identity_consumers=True, no_active_or_unknown_operations=True, recover_access=True)
                auth_path = local(row["plan"]).parent / "authorization.json"
                if auth_path.exists():
                    raise FileExistsError("Never reuse a case authorization")
                save(auth_path, auth)
                e1.authorize(case_plan, local(row["plan"]), auth_path, True)
                with e1.coordinator_lock(plan["identities"]["coordinator"]):
                    await e1.run_case(case_plan)
                result = load(case_output / "results.json")
        except Exception as error:
            if not result:
                result = dict(status="failed", launcher_error_class=type(error).__name__)
        finally:
            if initial is not None:
                try:
                    cleanup = await asyncio.to_thread(stop_consumers, target, plan, initial, row, case_output)
                    result["batch_consumer_cleanup"] = cleanup
                except Exception as error:
                    result["batch_consumer_cleanup_error_class"] = type(error).__name__
                    # The generic leased-batch gate must not return identities
                    # on a coordinator-only cleanup proof.
                    result["close_error_class"] = result.get("close_error_class", "BatchConsumerCleanupUnconfirmed")
            else:
                result["close_error_class"] = result.get("close_error_class", "BatchConsumerStartupOwnershipUnconfirmed")
            save(launch_evidence / "case-receipt.json", result)
            consumed.append(row["key"])
        return result

    report = await run_leased_batch(plan["cases"], output / "batch", aics=list(plan["identities"].values()),
        purpose=plan["batch_id"], run_case=run_case, control_directory=ROOT / CONTROL,
        lease_directory=ROOT / LEASES, handoff_timeout=840)
    print(json.dumps(dict(status=report["status"], cases=len(report["cases"]),
                          inspection_returned=report.get("lease", {}).get("identities_returned"))), flush=True)
    return 0 if report["status"] == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe", "prepare", "validate", "bind-authorization", "execute"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--image-id")
    parser.add_argument("--source-commit")
    parser.add_argument("--authorization-record", type=Path)
    parser.add_argument("--authorization-file", type=Path)
    args = parser.parse_args(argv)
    if args.action == "describe":
        print(json.dumps(dict(status="not_executed", cases=schedule(), model_calls=0,
                              control_directory=CONTROL, lease_directory=LEASES)))
        return 0
    if args.action == "prepare":
        plan = prepare(local(args.directory), args.image_id, args.source_commit)
        print(json.dumps(dict(status=plan["status"], batch_id=plan["batch_id"], cases=4)))
        return 0
    path = local(args.plan)
    if args.action == "bind-authorization":
        print(json.dumps(dict(status="bound_not_executed", authorization=str(bind_authorization(path, args.authorization_record)))))
        return 0
    if args.action == "validate":
        validate(path)
        print(json.dumps(dict(status="validated_not_executed", resource_platform_model_actions=0)))
        return 0
    return asyncio.run(execute(path, args.authorization_file))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
