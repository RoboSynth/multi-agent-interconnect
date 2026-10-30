"""Deployment-only NEW7 stage-5 startup and stage-7 supervision handoff.

Default prints an action plan. --execute is explicit. Business startup is also
the workbench systemd unit's repeatable ExecStartPre; it never builds an image.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

BUSINESS = ("postgres", "app-v1", "app-v2", "nginx")


def local(value, root):
    path = Path(value)
    return path if path.is_absolute() else root / path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def clean_environment():
    return {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "wt.ioa.pub,127.0.0.1,localhost"}


class CommandFailed(RuntimeError):
    def __init__(self, step, returncode):
        super().__init__(step)
        self.step, self.returncode = step, returncode


async def command(argv, *, root, step, timeout=600):
    result = await asyncio.to_thread(subprocess.run, argv, cwd=root, env=clean_environment(),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        # Provider/Compose stderr may contain configuration: retain no raw text.
        raise CommandFailed(step, result.returncode)
    return result.stdout


def initialize_host(root, host_config, deployment):
    """Generate only missing first-run host/schedule JSON; never overwrite them."""
    if host_config.exists():
        return
    from deploy.prepare_deployment import load_deployment
    manifest = load_deployment(deployment)
    directory = host_config.parent
    schedule_path = directory / "schedule.json"
    if schedule_path.exists():
        raise FileExistsError("A schedule already exists without this host config; preserve it for inspection")
    control, schedule_directory = directory / "control", root / "runtime/private/cloud-new7-schedule"
    schedule = load(root / "ops/schedule.new7.example.json")
    schedule.update(directory=str(schedule_directory), target_config=manifest["target_config"],
                    inspect_interval_seconds=600, longrun_control_directory=str(control),
                    keep_awake=False, drill_auto_approvals=[])
    host = dict(deployment_manifest=str(deployment), scheduler_config=str(schedule_path),
        schedule_directory=str(schedule_directory), control_directory=str(control),
        output_directory=str(root / "artifacts/cloud-longrun-workbench"),
        lease_directory=str(root / "runtime/private/cloud-longrun/leases"),
        port=8877, start_wsl_docker=False)
    save(schedule_path, schedule)
    save(host_config, host)


async def start_business(target, *, root, run=command):
    await run(target.compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180", *BUSINESS],
              root=root, step="business_up", timeout=240)
    return dict(status="ready", services=list(BUSINESS), no_build=True)


def start_temporary_host(root, host_config, control):
    control.mkdir(parents=True, mode=0o700, exist_ok=True)
    log = control / ("temporary-host-launch-" + uuid.uuid4().hex + ".log")
    argv = [str(root / ".venv/bin/python"), "-B", str(root / "ops/startup.py"),
            "--config", str(host_config), "--stage", "workbench"]
    with log.open("xb") as stream:
        return subprocess.Popen(argv, cwd=root, env=clean_environment(), stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)


async def wait_workbench(settings, *, root):
    from ops.startup import wait_health
    await wait_health(f'http://127.0.0.1:{settings.get("port", 8877)}/api/state', workbench=True)
    deadline = asyncio.get_running_loop().time() + 15
    while True:
        state = load(local(settings["control_directory"], root) / "host.json")
        if state.get("status") == "running":
            return state
        if state.get("status") == "quarantined" or asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError("Managed host did not report running after workbench readiness")
        await asyncio.sleep(.25)


def close_receipt(text, service, session):
    role = service.removesuffix("-agent")
    for line in reversed(text.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (isinstance(row, dict) and row.get("status") == "managed_consumer_closed"
                and row.get("session") == session and row.get("role") == role
                and row.get("sdk_cleanup_completed") is True):
            return dict(service=service, role=role, session=session, sdk_cleanup_completed=True)
    raise RuntimeError("Managed domain has no matching final SDK cleanup receipt")


async def stage5(root, host_config, deployment, evidence, settings, target, *,
                 consumers_factory=None, run=command, launch=start_temporary_host, wait_ready=wait_workbench,
                 business_ready=False):
    if consumers_factory is None:
        from ops.longrun_host import ComposeConsumers
        consumers_factory = ComposeConsumers
    report = dict(status="failed", phase=5, fault_injections=0, model_calls=0, scheduler_started=False,
                  collector_started=False)
    step = "business_up"
    try:
        report["business"] = (dict(status="already_ready", services=list(BUSINESS), reused=True)
            if business_ready else await start_business(target, root=root, run=run))
        session = "cloud-stage5-" + uuid.uuid4().hex
        consumers = consumers_factory(target, session=session)
        step = "temporary_domains_start"
        await consumers.start()
        report["temporary_domain_session"] = session
        report["temporary_domain_ids"] = dict(consumers.owned)
        step = "six_domain_health"
        health_output = evidence / "health"
        await run([str(root / ".venv/bin/python"), "-B", "/etc/incident-pilot/cloud_healthy.py",
            "--project-root", str(root), "--config", str(local(settings["coordinator_config"], root)),
            "--deployment", str(deployment), "--output", str(health_output),
            "--lease-directory", str(local(settings["lease_directory"], root)), "--execute"],
            root=root, step=step, timeout=600)
        health = load(health_output / "results.json")
        if health.get("status") != "completed" or health.get("close_status") != "completed":
            raise RuntimeError("Healthy coordinator did not finish and close normally")
        report["health"] = dict(status=health["status"], close_status=health["close_status"],
            completed_products=len(health.get("completed_products", [])), evidence=str(health_output))
        step = "temporary_domains_stop"
        # Existing ComposeConsumers.stop checks exact container IDs, waits for
        # the SDK signal adapter, requires ExitCode=0 and proves none remain running.
        await consumers.stop()
        step = "temporary_domain_close_receipts"
        receipts = []
        for service, identifier in report["temporary_domain_ids"].items():
            text = await run(target.docker + ["logs", "--tail", "1000", identifier],
                             root=root, step=step)
            receipts.append(close_receipt(text, service, session))
        report["temporary_domain_close_receipts"] = receipts
        report["temporary_domains_closed"] = True
        step = "persistent_workbench_start"
        control = local(settings["control_directory"], root)
        process = launch(root, host_config, control)
        report["persistent_pid"] = process.pid
        if process.poll() is not None:
            raise RuntimeError("Persistent managed workbench exited during startup")
        state = await wait_ready(settings, root=root)
        if process.poll() is not None or state.get("pid") != process.pid:
            raise RuntimeError("Persistent workbench PID differs from the managed host")
        report.update(status="completed", host_session=state["session_id"], identities_running=7,
                      coordinator_amp_directory=str(local(settings["output_directory"], root) / "transport/amp"))
    except Exception as error:
        report.update(error_class=type(error).__name__, failed_step=step, preserve_runtime=True)
        if isinstance(error, CommandFailed):
            report["returncode"] = error.returncode
    save(evidence / "result.json", report)
    return report


async def migrate(root, host_config, evidence, settings, *, run=command, wait_ready=wait_workbench):
    report, step = dict(status="failed", phase=7), "old_host_stop"
    try:
        stop_report = evidence / "old-host-stop.json"
        await run([str(root / ".venv/bin/python"), "-B", "/etc/incident-pilot/stop_managed_host.py",
            "--project-root", str(root), "--host-config", str(host_config), "--timeout", "840",
            "--exit-timeout", "15", "--report", str(stop_report)], root=root, step=step, timeout=880)
        closed = load(stop_report)
        if not (closed.get("status") == "stopped" and closed.get("exact_process_exited") is True
                and closed.get("consumers_closed") is True and closed.get("lease_released") is True):
            raise RuntimeError("Previous supervisor did not confirm exact-process and SDK cleanup")
        report["old_host_stop"] = closed
        step = "systemd_reload"
        await run(["/usr/bin/systemctl", "daemon-reload"], root=root, step=step)
        step = "systemd_workbench_start"
        await run(["/usr/bin/systemctl", "enable", "--now", "incident-workbench.service"], root=root, step=step)
        state = await wait_ready(settings, root=root)
        main_pid = int((await run(["/usr/bin/systemctl", "show", "--property=MainPID", "--value",
                                  "incident-workbench.service"], root=root, step="systemd_pid")).strip())
        if state.get("pid") != main_pid or state.get("session_id") == closed["host_session"]:
            raise RuntimeError("Systemd did not start the new exclusive managed workbench PID")
        report["systemd_workbench_pid"] = main_pid
        for unit in ("incident-scheduler.service", "incident-collector.service"):
            step = unit
            await run(["/usr/bin/systemctl", "enable", "--now", unit], root=root, step=step)
        report.update(status="completed", identities_running=7, inspect_interval_seconds=600,
                      daily_report_timer="install_and_verify_separately")
    except Exception as error:
        report.update(error_class=type(error).__name__, failed_step=step, preserve_runtime=True)
        if isinstance(error, CommandFailed):
            report["returncode"] = error.returncode
    save(evidence / "result.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["business", "stage5", "migrate"])
    parser.add_argument("--project-root", type=Path, default=Path("/opt/incident-pilot"))
    parser.add_argument("--host-config", type=Path)
    parser.add_argument("--deployment", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--business-ready", action="store_true",
                        help="Stage 5 only: reuse the four business services already verified by the deployer")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    host_config = args.host_config or root / "runtime/private/cloud-longrun/host.json"
    deployment = args.deployment or root / "runtime/private/cloud-new7-20261019/deployment.json"
    if not args.execute:
        print(json.dumps(dict(status="prepared_not_executed", action=args.action, host_config=str(host_config),
            deployment=str(deployment), business_services=list(BUSINESS), image_builds=0, platform_started=False)))
        return 0
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise PermissionError("Cloud runtime supervision requires root on Linux")
        os.umask(0o077)
        sys.path[:0] = [str(root), str(root / "vendor/ACPs-community/acps-sdk")]
        if args.action == "stage5":
            initialize_host(root, host_config, deployment)
        from ops.longrun_host import prepare
        settings, target = prepare(host_config)
        if args.action == "business":
            result = asyncio.run(start_business(target, root=root))
        else:
            evidence = args.evidence or root / "evidence" / ("cloud-" + args.action + "-" + uuid.uuid4().hex)
            evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
            result = asyncio.run(stage5(root, host_config, deployment, evidence, settings, target,
                                       business_ready=args.business_ready)
                if args.action == "stage5" else migrate(root, host_config, evidence, settings))
        print(json.dumps(result))
        return 0 if result["status"] in {"ready", "completed"} else 1
    except Exception as error:
        print(json.dumps(dict(status="failed", error_class=type(error).__name__, preserve_runtime=True)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
