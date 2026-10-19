"""Validate by default; run exactly four serial cases only after new batch authorization."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "plan-preparation"))
import batch_scope as scope

HERE = scope.BATCH / "execution"
SERVICES = {"postgres", "nginx", "app-v1", "app-v2", "application-agent", "database-agent",
            "database-backup-agent", "ops-agent", "verification-agent", "onboarding-agent"}


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    # Docker timestamps have nanosecond precision; datetime accepts the prefix.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def command(argv, directory, stem, timeout=180):
    e1, *_ = scope.product()
    started = time.monotonic()
    try:
        process = subprocess.run([str(x) for x in argv], cwd=scope.ROOT, env=e1.clean_environment(),
                                 capture_output=True, timeout=timeout)
        out, err = process.stdout, process.stderr
        receipt = dict(actual_exit_code=process.returncode, terminal=True)
    except subprocess.TimeoutExpired as error:
        out, err = error.stdout or b"", error.stderr or b""
        receipt = dict(terminal=False, error_class="TimeoutExpired", observation="command timeout; resources must be reinspected")
    (directory / (stem + ".stdout.bin")).write_bytes(out)
    (directory / (stem + ".stderr.bin")).write_bytes(err)
    scope.save(directory / (stem + ".exit.json"), dict(**receipt, finished_at=now(),
        duration_seconds=round(time.monotonic()-started, 3), stdout_sha256=hashlib.sha256(out).hexdigest(),
        stderr_sha256=hashlib.sha256(err).hexdigest()))
    if not receipt.get("terminal") or receipt.get("actual_exit_code") != 0:
        raise RuntimeError(stem + " failed; original outputs and exit/timeout retained")
    return out.decode("utf-8-sig")


def inventory(directory, stem, target):
    ids = command(target.docker + ["ps", "-aq", "--no-trunc"], directory, stem + "-ids").split()
    template = ('{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
        '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
        '"running":{{json .State.Running}},"image_id":{{json .Image}},'
        '"created":{{json .Created}},"started_at":{{json .State.StartedAt}},'
        '"recovery":{{json (index .Config.Labels "incident-pilot.recovery")}}}')
    rows = [json.loads(row) for row in command(target.docker + ["inspect", "--format", template, *ids],
        directory, stem + "-inspect").splitlines()] if ids else []
    scope.save(directory / (stem + ".json"), rows)
    return rows


def prove_owned(rows, original_ids, expected_images, launch_at):
    """Never adopt a pre-existing ID or a same-label container with wrong identity."""
    owned = [row for row in rows if row["project"] == scope.PROJECT]
    if (len(owned) != len({row["id"] for row in owned})
            or len(owned) != len({row["service"] for row in owned})):
        raise RuntimeError("Duplicate project identities; preserve for review")
    for row in owned:
        if (row["id"] in original_ids or row["service"] not in SERVICES
                or row["image_id"] != expected_images[row["service"]]
                or timestamp(row["created"]) < timestamp(launch_at)
                or row["running"] and timestamp(row["started_at"]) < timestamp(launch_at)):
            raise RuntimeError("Container project/service/image/creation/start ownership not proven")
    return owned


def match_registered(rows, registered):
    live = {row["id"]: row for row in rows if row["project"] == scope.PROJECT}
    if set(live) != set(registered):
        raise RuntimeError("Owned container set changed; never stop an unregistered replacement")
    for identity, original in registered.items():
        current = live[identity]
        if any(current[key] != original[key] for key in ("id", "project", "service", "image_id", "created", "started_at")):
            raise RuntimeError("Registered container identity/start time changed unexpectedly")
    return list(live.values())


def restored_registration(rows, registered, initial, restored, case_started_at, expected_images):
    """Accept only the exact DB old/new IDs attested by this owned E1 child."""
    database = {"database-agent", "database-backup-agent"}
    prior = {item["service"]: item for item in registered.values()}
    current = {item["service"]: item for item in rows if item["project"] == scope.PROJECT}
    if set(current) != set(prior) or len(current) != len([row for row in rows if row["project"] == scope.PROJECT]):
        raise RuntimeError("Project services changed during E1 replacement")
    for service, old in prior.items():
        item = current[service]
        if service not in database:
            if any(item[key] != old[key] for key in ("id", "project", "service", "image_id", "created", "started_at")):
                raise RuntimeError("Non-DB identity/start changed during E1")
            continue
        if (initial.get(service, {}).get("container_id") != old["id"]
                or restored.get(service, {}).get("container_id") != item["id"]
                or restored.get(service, {}).get("image_id") != expected_images[service]
                or initial[service].get("image_id") != expected_images[service]
                or item["id"] == old["id"] or item["running"] is not True):
            raise RuntimeError("DB replacement differs from the child's original/restored identities")
        prove_owned([item], set(registered), expected_images, case_started_at)
    return {item["id"]: item for item in current.values()}


def refresh_after_case(row, registered, expected_images, target):
    directory = HERE / ("ownership-after-" + row["key"])
    directory.mkdir()
    rows = inventory(directory, "current", target)
    output = scope.local(row["output"])
    initial_path, restored_path = output / "initial-domains.json", output / "restored-domains.json"
    if row["case"] == "E1-a" and initial_path.exists() and restored_path.exists():
        receipt = scope.load(HERE / row["key"] / "receipt.json")
        registered = restored_registration(rows, registered, scope.load(initial_path), scope.load(restored_path),
                                           receipt["started_at"], expected_images)
        scope.save(directory / "registration.json", dict(owned=registered, initial_domains_sha256=scope.sha(initial_path),
            restored_domains_sha256=scope.sha(restored_path), child_receipt_sha256=scope.sha(HERE / row["key"] / "receipt.json")))
    else:
        # A child that never switched DB workers may keep the original exact IDs.
        match_registered(rows, registered)
        scope.save(directory / "registration.json", dict(owned=registered, unchanged_ids=True))
    return registered


def close_safe(result):
    checks = result.get("close_checks", {})
    expected = {"no_group_sessions", "no_inbound_groups", "inbox_cancelled", "connection_closed",
                "owned_group_disconnected", "no_cleanup_warnings"}
    return set(checks) == expected and all(value is True for value in checks.values())


def safe_to_continue(result):
    e1, *_ = scope.product()
    return (result.get("resource_and_worker_restore") == "completed" and close_safe(result)
        and not result.get("cleanup_warning_events") and e1.healthy(result.get("independent_final_H00", {}))
        and not any(key in result for key in ("close_error_class", "restore_error_class", "H00_error_class",
                                              "restore_or_H00_error_class", "access_recovery_error_class")))


def case_authorization(plan, path):
    # Exact product schema; provenance is retained separately by the launcher.
    return dict(schema_version="platform-e1-authorization/" + plan["schema_version"].rsplit("/", 1)[1],
        authorized=True, plan_sha256=scope.sha(path), experiment_id=plan["experiment_id"],
        incident_id=plan["incident_id"], output=plan["output"], case=plan["case"],
        crash_point=plan["crash_point"], effects=plan["effects"], exclusive_coordinator=True,
        no_other_identity_consumers=True, no_active_or_unknown_operations=True, recover_access=True)


def run_case(row, summary, authorization_path, consumed):
    # Frozen inputs and fresh batch authorization are checked again before each effect.
    scope.validate_summary(allow_consumed=consumed)
    scope.validate_authorization(authorization_path, summary)
    e1, *_ = scope.product()
    directory = HERE / row["key"]
    directory.mkdir(exist_ok=False)
    if row["case"] == "F10":
        argv = [sys.executable, scope.BATCH / "run_f10.py", "--execute", "--authorization-file", authorization_path]
        result_path = scope.local(row["output"]) / "wrapper-result.json"
    else:
        path = scope.local(row["plan"])
        plan = e1.validate_plan(path)
        auth = scope.PRIVATE / row["key"] / "authorization.json"
        if auth.exists():
            raise RuntimeError("Never reuse a per-case authorization")
        scope.save(auth, case_authorization(plan, path))
        argv = [sys.executable, scope.ROOT / "eval/platform_resume_experiment.py", "--execute", "--plan", path,
                "--authorization-file", auth, "--approve-high"]
        result_path = scope.local(row["output"]) / "results.json"
    receipt = dict(key=row["key"], started_at=now(), plan_sha256=row["plan_sha256"],
                   batch_authorization_sha256=scope.sha(authorization_path), status="running")
    scope.save(directory / "receipt.json", receipt)
    print(json.dumps(dict(event="starting", key=row["key"], at=now())), flush=True)
    try:
        command(argv, directory, "runner", timeout=None)
    except Exception as error:
        receipt["launcher_error_class"] = type(error).__name__
    result = scope.load(result_path) if result_path.exists() else {}
    exit_path = directory / "runner.exit.json"
    actual_exit = scope.load(exit_path) if exit_path.exists() else {}
    safe = safe_to_continue(result)
    passed = result.get("status") == "completed" and actual_exit.get("terminal") is True and actual_exit.get("actual_exit_code") == 0
    receipt.update(status="completed" if passed else "failed", finished_at=now(),
                   actual_exit=actual_exit, cleanup_and_recovery_verified=safe)
    scope.save(directory / "receipt.json", receipt)
    consumed.append(row["key"])
    print(json.dumps(dict(event=receipt["status"], key=row["key"], safe_to_continue=safe, at=now())), flush=True)
    if not safe:
        raise RuntimeError("Stop subsequent cases: cleanup/restoration/H00 unproven")
    return receipt


def keeper_start(target):
    e1, *_ = scope.product()
    stop = HERE / "keeper.stop"
    code = ("import os,json,time;from pathlib import Path\np=Path(" + repr(target.docker_path(stop)) + ")\n"
            "print(json.dumps({'pid':os.getpid(),'status':'ready'}),flush=True)\nwhile not p.exists(): time.sleep(.25)\n")
    with (HERE / "keeper.stdout.bin").open("wb") as out, (HERE / "keeper.stderr.bin").open("wb") as err:
        process = subprocess.Popen(["wsl.exe", "-d", target.wsl_distro, "--exec", "python3", "-u", "-c", code],
            stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=e1.clean_environment())
    scope.save(HERE / "keeper.json", dict(windows_pid=process.pid, started_at=now(), stop_file=str(stop)))
    return process, stop


def keeper_ready(process):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned keeper exited before readiness")
        rows = (HERE / "keeper.stdout.bin").read_bytes().splitlines()
        if rows:
            ready = json.loads(rows[0])
            if ready.get("status") != "ready" or type(ready.get("pid")) is not int:
                raise RuntimeError("Invalid keeper handshake")
            return
        time.sleep(.1)
    raise RuntimeError("Keeper observation timed out; preserve original handle, never launch another")


def execute(summary, target, authorization_path):
    if HERE.exists():
        raise ValueError("Preserve existing execution; no batch restart")
    HERE.mkdir()
    scope.save(HERE / "batch-authorization.json", scope.load(authorization_path))
    startup = HERE / "startup"
    startup.mkdir()
    keeper = None
    before = None
    launch_at = None
    expected = {}
    registered = {}
    rows_done = []
    report = dict(status="failed", project=scope.PROJECT, started_at=now(), cases=rows_done)
    try:
        keeper, stop_file = keeper_start(target)
        keeper_ready(keeper)
        before = inventory(startup, "before", target)
        if any(row["project"] == scope.PROJECT for row in before):
            raise RuntimeError("Never adopt an existing project")
        if any(row["running"] and (str(row["project"]).startswith("incident-pilot") or row["recovery"]) for row in before):
            raise RuntimeError("Another project or recovery container is running")
        e1, *_ = scope.product()
        code = "import os,json;print(json.dumps([k for k in os.environ if k.startswith(('PG','COMPOSE_')) or k in " + repr(sorted(e1.RESOURCE_NAMES)) + "]))"
        if json.loads(command(["wsl.exe", "-d", target.wsl_distro, "--exec", "python3", "-c", code], startup, "linux-overrides")):
            raise RuntimeError("Linux resource/Compose environment overrides present")
        for port in target.ports.values():
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("A bound batch port is already occupied")
        references = {"agent": summary["image_results"]["agent"]["image_reference"],
                      "app": summary["image_results"]["app-v2"]["image_reference"],
                      "postgres": "postgres:16-alpine", "nginx": "nginx:1.27-alpine"}
        image_ids = {name: command(target.docker + ["image", "inspect", "--format", "{{.Id}}", ref], startup, "image-" + name).strip()
                     for name, ref in references.items()}
        if any(image_ids[key] != summary["image_results"][bound]["image_id"] for key, bound in (("agent", "agent"), ("app", "app-v2"))):
            raise RuntimeError("Actual runtime image differs from frozen build receipt")
        expected = {service: image_ids["agent" if service.endswith("agent") else "app" if service.startswith("app-v") else service]
                    for service in SERVICES}
        command(target.docker + ["image", "tag", image_ids["app"], scope.PROJECT + "-app-v1"], startup, "tag-app-v1")
        compose = target.compose + ["--profile", "isolated"]
        command(compose + ["config", "--quiet"], startup, "compose-config")
        scope.validate_summary()
        scope.validate_authorization(authorization_path, summary)
        launch_at = now()
        scope.save(startup / "launch-intent.json", dict(at=launch_at, expected_service_images=expected,
                   before_container_ids=[row["id"] for row in before]))
        command(compose + ["up", "-d", "--no-build", "--pull", "never", "--wait"], startup, "compose-up", timeout=300)
        after = inventory(startup, "after", target)
        owned = prove_owned(after, {row["id"] for row in before}, expected, launch_at)
        if {row["service"] for row in owned} != SERVICES or not all(row["running"] for row in owned):
            raise RuntimeError("Expected ten running services were not proven")
        registered = {row["id"]: row for row in owned}
        scope.save(startup / "ownership.json", registered)
        consumed = []
        for row in summary["plans"]:
            if keeper.poll() is not None:
                raise RuntimeError("Original keeper exited; do not restart it")
            try:
                rows_done.append(run_case(row, summary, authorization_path, consumed))
            finally:
                registered = refresh_after_case(row, registered, expected, target)
        report["status"] = "completed" if all(row["status"] == "completed" for row in rows_done) else "failed"
    except BaseException as error:
        report.update(error_class=type(error).__name__, traceback=traceback.format_exc())
    finally:
        stop_directory = HERE / "stop"
        stop_directory.mkdir()
        try:
            if launch_at is None:
                report["project_stop"] = "not_started"
            else:
                current = inventory(stop_directory, "before", target)
                if not registered:
                    # Compose may have partially created services before failing.
                    owned = prove_owned(current, {row["id"] for row in before}, expected, launch_at)
                    registered = {row["id"]: row for row in owned}
                    scope.save(stop_directory / "partial-ownership.json", registered)
                owned = match_registered(current, registered)
                recovery_ids = {"access-validation-20261019-" + row["key"] for row in summary["plans"] if row["case"] == "E1-a"}
                if any(row["running"] and row["recovery"] in recovery_ids for row in current):
                    raise RuntimeError("Recovery container still active; preserve it for ownership review")
                second = inventory(stop_directory, "confirmed", target)
                confirmed = match_registered(second, registered)
                if {row["id"]: row for row in confirmed} != {row["id"]: row for row in owned}:
                    raise RuntimeError("Container state/start changed before stop; do not race another owner")
                ids = [row["id"] for row in owned if row["running"]]
                if ids:
                    command(target.docker + ["stop", "--time", "30", *ids], stop_directory, "owned-stop", timeout=180)
                after = inventory(stop_directory, "after", target)
                stopped = match_registered(after, registered)
                if any(row["running"] for row in stopped):
                    raise RuntimeError("Owned stop requested but actual running containers remain")
                scope.save(stop_directory / "result.json", dict(status="ACTUALLY_STOPPED", requested_ids=ids,
                    owned_ids=list(registered), volumes_retained=True, completed_at=now()))
                report["project_stop"] = "ACTUALLY_STOPPED"
        except BaseException as error:
            report.update(status="failed", project_stop_error_class=type(error).__name__, project_stop_traceback=traceback.format_exc())
        finally:
            if keeper is not None:
                stop_file.write_text("stop this batch's original keeper\n", encoding="utf-8")
                try:
                    exit_code = keeper.wait(timeout=20)
                    scope.save(HERE / "keeper.exit.json", dict(terminal=True, actual_exit_code=exit_code, finished_at=now()))
                    if exit_code != 0:
                        report.update(status="failed", keeper_error_class="KeeperNonzeroExit")
                except subprocess.TimeoutExpired:
                    scope.save(HERE / "keeper.exit.json", dict(terminal=False, observation="stop requested; actual exit unconfirmed"))
                    report.update(status="failed", keeper_error_class="KeeperExitUnconfirmed")
        report["finished_at"] = now()
        scope.save(HERE / "result.json", report)
    return 0 if report["status"] == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-file", type=Path)
    args = parser.parse_args(argv)
    summary, _, target = scope.validate_summary()
    if not args.execute:
        print('{"status":"VALIDATED_NOT_EXECUTED","plan_count":4}')
        return 0
    # No keeper, Docker command, output directory or derived authorization before this.
    scope.validate_authorization(args.authorization_file, summary)
    return execute(summary, target, args.authorization_file.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
