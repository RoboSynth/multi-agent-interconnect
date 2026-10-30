"""Prepare three login tasks, or run one explicit longrun startup stage.

Preparation never registers a task, launches WSL/Docker, changes login/sleep
settings or consumes a platform identity. Runtime requires a prepared deployment.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.aic_lease import load, now, save
from ops.longrun_host import ManagedHost, local, prepare
from ops.schedule import Scheduler, ScheduleLock
from deploy.prepare_deployment import load_deployment, compose_command, GENERATED_ENV_KEYS
from tools.workbench_host import clean_environment

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", NS)


def task_xml(stage, config_path, python, user_sid, *, delay_seconds=0):
    if not user_sid.startswith("S-1-") or any(ch not in "S-0123456789" for ch in user_sid):
        raise ValueError("An explicit current-user Windows SID is required")
    if any(any(ch in str(value) for ch in ('"', '\r', '\n')) for value in (config_path, python, ROOT)):
        raise ValueError("Task paths must not contain quotes or newlines")
    task = ET.Element("{"+NS+"}Task", version="1.2")
    def child(parent, tag, text=None, **attrs):
        item = ET.SubElement(parent, "{"+NS+"}"+tag, **attrs)
        if text is not None:
            item.text = str(text)
        return item
    info = child(task, "RegistrationInfo")
    child(info, "Description", "IncidentPilot managed longrun " + stage)
    trigger = child(child(task, "Triggers"), "LogonTrigger")
    child(trigger, "Enabled", "true")
    child(trigger, "UserId", user_sid)
    if delay_seconds:
        child(trigger, "Delay", f"PT{delay_seconds}S")
    principal = child(child(task, "Principals"), "Principal", id="CurrentUser")
    child(principal, "UserId", user_sid)
    child(principal, "LogonType", "InteractiveToken")
    child(principal, "RunLevel", "LeastPrivilege")
    settings = child(task, "Settings")
    for tag, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("DisallowStartIfOnBatteries", "false"),
                       ("StopIfGoingOnBatteries", "false"), ("StartWhenAvailable", "true"),
                       ("Enabled", "true"), ("Hidden", "true"), ("ExecutionTimeLimit", "PT0S")):
        child(settings, tag, value)
    restart = child(settings, "RestartOnFailure")
    child(restart, "Interval", "PT1M")
    child(restart, "Count", "5")
    action = child(child(task, "Actions", Context="CurrentUser"), "Exec")
    # pythonw keeps a scheduled login launch from opening an interactive console.
    child(action, "Command", python)
    child(action, "Arguments", f'-B -u "{ROOT / "ops/startup.py"}" --config "{config_path}" --stage {stage}')
    child(action, "WorkingDirectory", ROOT)
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def prepare_tasks(config, output, *, user_sid, python, inspect_minutes=10, template_only=False):
    if inspect_minutes not in {10, 30}:
        raise ValueError("Choose 10 minutes (default) or explicitly 30 minutes")
    settings = load(config)
    python = local(python).resolve()
    if not template_only and not python.is_file():
        raise ValueError("Prepare the project's pythonw.exe before task generation")
    if not template_only:
        prepare(config)
    schedule = load(local(settings["scheduler_config"]))
    if schedule.get("workbench_url") != f'http://127.0.0.1:{settings.get("port", 8877)}':
        raise ValueError("Scheduler URL must match the managed loopback workbench")
    if str(local(schedule["directory"]).resolve()) != str(local(settings["schedule_directory"]).resolve()):
        raise ValueError("Host and scheduler must write the same longrun directory")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    schedule["inspect_interval_seconds"] = inspect_minutes * 60
    schedule["longrun_control_directory"] = str(local(settings["control_directory"]).resolve())
    save(output / "schedule.json", schedule)
    settings["scheduler_config"] = str((output / "schedule.json").resolve())
    save(output / "host.json", settings)
    documents = []
    for stage, delay in (("resources", 0), ("workbench", 60), ("scheduler", 90)):
        path = output / (stage + "-task.xml")
        path.write_bytes(task_xml(stage, (output / "host.json").resolve(), python, user_sid, delay_seconds=delay))
        documents.append(str(path))
    result = dict(status="template_prepared" if template_only else "prepared_not_registered", tasks=documents,
                  inspect_interval_seconds=inspect_minutes*60, network_attempted=False, tasks_registered=False,
                  processes_started=False, automatic_login_changed=False, sleep_settings_changed=False)
    save(output / "startup-plan.json", result)
    return result


async def wait_health(url, *, workbench=False, timeout=300):
    import httpx
    deadline = time.monotonic()+timeout
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(url)
                response.raise_for_status()
                value = response.json()
                if not workbench or (value.get("connected") is True and value.get("resource_credential_count") == 0
                                     and value.get("mode") == "wutong-amqps"):
                    return
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(2)
    raise TimeoutError("Dependent service did not become healthy")


async def resources(config, settings, target):
    manifest = load_deployment(local(settings["deployment_manifest"]))
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("COMPOSE_") and key.upper() not in GENERATED_ENV_KEYS}
    keeper = None
    try:
        if target.wsl_distro:
            keeper = subprocess.Popen(["wsl.exe", "-d", target.wsl_distro, "--exec", "sleep", "infinity"],
                cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if settings.get("start_wsl_docker") is True:
                # Opt-in service startup within the selected WSL distro only.
                await asyncio.to_thread(subprocess.run,
                    ["wsl.exe", "-d", target.wsl_distro, "-u", "root", "--exec", "systemctl", "start", "docker"],
                    cwd=ROOT, env=environment, check=True, timeout=60,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        command = compose_command(manifest, sanitized=True)
        await asyncio.to_thread(subprocess.run, command + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180",
            "postgres", "app-v1", "app-v2", "nginx"], cwd=ROOT, env=environment, check=True, timeout=240,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        await wait_health(target.order_url+"/ready")
        save(local(settings["control_directory"]) / "resources-ready.json",
             dict(project=target.project, checked_at=now(), keeper_pid=keeper.pid if keeper else None))
        while True:
            if keeper is not None and keeper.poll() is not None:
                raise RuntimeError("Owned WSL keeper exited")
            await asyncio.sleep(15)
    finally:
        if keeper is not None and keeper.poll() is None:
            keeper.terminate()
            await asyncio.to_thread(keeper.wait, timeout=15)


async def run_stage(config, stage):
    settings, target = prepare(config)
    if stage == "resources":
        await resources(config, settings, target)
    elif stage == "workbench":
        await wait_health(target.order_url+"/ready")
        await ManagedHost(settings, target).run()
    else:
        await wait_health(f'http://127.0.0.1:{settings.get("port", 8877)}/api/state', workbench=True)
        schedule = load(local(settings["scheduler_config"]))
        if not schedule.get("longrun_control_directory"):
            raise ValueError("Prepare managed startup configuration before starting the scheduler")
        with ScheduleLock(local(schedule["directory"])):
            await Scheduler(schedule).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--user-sid")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--inspect-minutes", type=int, choices=[10, 30], default=10)
    parser.add_argument("--template-only", action="store_true")
    parser.add_argument("--stage", choices=["resources", "workbench", "scheduler"])
    args = parser.parse_args(argv)
    if args.stage:
        # Filter only this new task process, reusing the existing host policy.
        # Domain credentials are read separately by Compose/domain processes.
        environment = clean_environment(dict(os.environ))
        os.environ.clear()
        os.environ.update(environment)
        settings = load(args.config)
        logs = local(settings["control_directory"]) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        name = args.stage + "-" + now().replace(":", "-") + "-" + uuid.uuid4().hex[:8] + ".log"
        with (logs / name).open("x", encoding="utf-8", buffering=1) as stream:
            sys.stdout = sys.stderr = stream
            try:
                asyncio.run(run_stage(args.config, args.stage))
            except BaseException:
                import traceback
                traceback.print_exc()
                raise
    else:
        if not args.output or not args.user_sid or not args.python:
            parser.error("Preparation requires --output, --user-sid and the project's pythonw.exe")
        print(json.dumps(prepare_tasks(args.config, args.output, user_sid=args.user_sid, python=args.python,
            inspect_minutes=args.inspect_minutes, template_only=args.template_only)))


if __name__ == "__main__":
    main()
