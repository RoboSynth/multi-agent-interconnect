"""Supervise one platform workbench and six owned domain consumers.

An explicit --run starts services; default validation is offline. Pausing closes
the workbench transport AND domain containers before acknowledging lease release.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.aic_lease import AicLease, DEFAULT_DIRECTORY, LeaseBusy, LeaseQuarantined, load, now, save
from eval.targets import DockerTarget, DOMAIN_SERVICES, validate_platform_bindings
from deploy.prepare_deployment import load_deployment, GENERATED_ENV_KEYS, COMPOSE_SCOPE_KEYS


def local(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def prepare(path):
    settings = load(path)
    manifest_path = local(settings["deployment_manifest"])
    manifest = load_deployment(manifest_path)
    if manifest["mode"] != "seven":
        raise ValueError("Managed host requires the full seven-identity deployment manifest")
    settings["coordinator_config"] = manifest["coordinator_config"]
    settings["target_config"] = manifest["target_config"]
    settings["domain_directory"] = str(local(manifest["coordinator_config"]).parent.parent)
    config = load(local(settings["coordinator_config"]))
    if config.get("mode") != "wutong-amqps":
        raise ValueError("Managed longrun host requires wutong-amqps")
    target = DockerTarget.from_file(local(settings["target_config"]))
    domains = {}
    for service, role in {**DOMAIN_SERVICES, "database-backup-agent": "database-backup"}.items():
        directory = local(settings["domain_directory"]) / role
        domains[service] = (load(directory / "bridge.json")["platform"]
                            if role in {"database", "database-backup", "ops"}
                            else load(directory / "config.json"))
    validate_platform_bindings(config, domains, project=target.project)
    aics = [config["leader"]["aic"], *[row["aic"] for row in domains.values()]]
    if len(set(aics)) != 7:
        raise ValueError("Managed longrun host requires seven distinct identities")
    if set(config.get("trusted_participant_aics", {}).get("onboarding", [])) != {domains["onboarding-agent"]["aic"]}:
        raise ValueError("Onboarding identity must be bound to its own container")
    if type(settings.get("port", 8877)) is not int or not 1024 <= settings.get("port", 8877) <= 65535:
        raise ValueError("Invalid loopback workbench port")
    settings["aics"] = sorted(aics)
    return settings, target


class ComposeConsumers:
    """Never adopt/stop pre-existing running containers or replacements."""
    def __init__(self, target, *, session=None):
        self.target, self.owned = target, {}
        self.session = session or uuid.uuid4().hex
        self.entry_hash = hashlib.sha256((ROOT / "ops/domain_entry.py").read_bytes()).hexdigest()

    @property
    def compose(self):
        # The validated deployment starts with deploy/compose.yml, so the
        # override's ../ops mount resolves relative to that deploy directory.
        return self.target.compose + ["-f", self.target.docker_path(ROOT / "ops/longrun.consumers.yml")]

    async def command(self, args):
        def run():
            environment = {key: value for key, value in os.environ.items()
                           if not key.upper().startswith("COMPOSE_") and key.upper() not in GENERATED_ENV_KEYS}
            environment["INCIDENT_MANAGED_SESSION"] = self.session
            command = args
            if self.target.wsl_distro:
                command = args[:4] + ["env", *(part for key in (*GENERATED_ENV_KEYS, *COMPOSE_SCOPE_KEYS) for part in ("-u", key)),
                                     "INCIDENT_MANAGED_SESSION="+self.session] + args[4:]
            result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError("Owned longrun Docker operation failed; inspect project logs")
            return result.stdout
        return await asyncio.to_thread(run)

    async def inventory(self):
        ids = (await self.command(self.compose + ["ps", "-a", "-q", *DOMAIN_SERVICES])).split()
        rows = json.loads(await self.command(self.target.docker + ["inspect", *ids])) if ids else []
        result = {}
        for row in rows:
            labels = row["Config"]["Labels"]
            service = labels.get("com.docker.compose.service")
            if (labels.get("com.docker.compose.project") != self.target.project
                    or service not in DOMAIN_SERVICES or labels.get("incident-pilot") != "true"
                    or service in result):
                raise RuntimeError("Consumer ownership labels are inconsistent")
            result[service] = row
        return result

    async def start(self):
        if any(row["State"]["Running"] for row in (await self.inventory()).values()):
            raise RuntimeError("Existing consumers must be closed by their owner before managed startup")
        # Capture even partial startup so failure cleanup can stop exact IDs.
        try:
            await self.command(self.compose + ["up", "-d", "--no-build", "--no-deps", *DOMAIN_SERVICES])
        finally:
            self.owned = {service: row["Id"] for service, row in (await self.inventory()).items()}
        current = await self.inventory()
        if set(current) != set(DOMAIN_SERVICES) or not all(row["State"]["Running"] for row in current.values()):
            raise RuntimeError("Six owned consumers did not become running")
        if any("INCIDENT_MANAGED_SESSION="+self.session not in row["Config"].get("Env", [])
               or "/srv/ops/domain_entry.py" not in row["Config"].get("Cmd", []) for row in current.values()):
            raise RuntimeError("Managed consumer session/entry binding was not loaded")

    async def stop(self):
        current = await self.inventory()
        if any(service not in current or current[service]["Id"] != identifier
               for service, identifier in self.owned.items()):
            raise RuntimeError("Owned consumer was replaced; leave replacement untouched")
        if hashlib.sha256((ROOT / "ops/domain_entry.py").read_bytes()).hexdigest() != self.entry_hash:
            raise RuntimeError("Managed signal adapter changed while consumers were running")
        if self.owned:
            await self.command(self.target.docker + ["stop", "--time", "30", *self.owned.values()])
        after = await self.inventory()
        if any(row["State"]["Running"] for row in after.values()):
            raise RuntimeError("Consumer close was not confirmed")
        if any(after[service]["State"].get("ExitCode") != 0 for service in self.owned):
            raise RuntimeError("Managed consumer SDK close did not finish normally")
        self.owned.clear()


def idle(app):
    active = getattr(app.state, "active", None)
    transport = app.state.transport
    runs = list(app.state.engine.runs.values())
    return (not active or active.done()) and not any(
        run.get("status") in {"running", "awaiting_approval"}
        or any(row.get("status") == "pending" for row in run.get("approvals", [])) for run in runs
    ) and transport is not None and not transport.journal.list_tasks(in_flight_only=True)


async def close_owned_server(task, server, lease):
    """Cleanup failures quarantine identities, and never retain the local locks."""
    try:
        if not task.done():
            server.should_exit = True
        await task
    except BaseException as error:
        lease.quarantine("managed server final close failed", evidence={"error_class": type(error).__name__})
        raise
    finally:
        lease.release()


class ManagedHost:
    def __init__(self, settings, target):
        self.settings, self.target = settings, target
        self.control = local(settings["control_directory"])
        self.session = uuid.uuid4().hex
        self.lease_directory = local(settings.get("lease_directory", str(DEFAULT_DIRECTORY)))

    def state(self, status, **values):
        save(self.control / "host.json", dict(status=status, session_id=self.session, pid=os.getpid(),
            aics=self.settings["aics"], updated_at=now(), **values))

    def event(self, event, **values):
        directory = local(self.settings["schedule_directory"])
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(at=now(), event=event, host_session=self.session, **values)) + "\n")

    async def run(self):
        import uvicorn
        from fastapi.responses import JSONResponse
        from workbench_server import create_app
        # A separate host lock stops two supervisors from rewriting control state.
        with AicLease(["longrun-host:"+str(self.control.resolve())], purpose="longrun-supervisor",
                      directory=self.control / "host-lock"):
            finished_requests = set()
            pending_resume = None
            while True:
                lease = AicLease(self.settings["aics"], purpose="longrun-consumers",
                                 directory=self.lease_directory, owner={"host_session": self.session})
                try:
                    lease.acquire()
                except (LeaseBusy, LeaseQuarantined):
                    self.state("blocked", reason="exclusive identities unavailable; no consumers started")
                    raise
                consumers = ComposeConsumers(self.target, session=self.session)
                request, cleanup_error, reported_running = None, None, False
                app = create_app(local(self.settings["coordinator_config"]), local(self.settings["output_directory"]))
                original_lifespan = app.router.lifespan_context

                @asynccontextmanager
                async def lifespan(app):
                    nonlocal cleanup_error
                    try:
                        await consumers.start()
                        async with original_lifespan(app):
                            if app.state.transport is None:
                                raise RuntimeError("Workbench platform transport is not connected")
                            yield
                    except BaseException as error:
                        cleanup_error = type(error).__name__
                        raise
                    finally:
                        try:
                            await consumers.stop()
                        except BaseException as error:
                            cleanup_error = type(error).__name__
                            raise

                app.router.lifespan_context = lifespan

                @app.middleware("http")
                async def drain(request_http, call_next):
                    if request is not None and request_http.method == "POST" and request_http.url.path == "/api/incidents":
                        return JSONResponse({"detail": "planned idle handoff in progress"}, status_code=409)
                    return await call_next(request_http)

                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.settings.get("port", 8877)))
                task = asyncio.create_task(server.serve())
                self.state("starting")
                try:
                    while not task.done():
                        if server.started and request is None:
                            self.state("running")
                            if not reported_running and pending_resume is not None:
                                self.event("planned_pause_finished", **pending_resume)
                                pending_resume = None
                            reported_running = True
                        path = self.control / "handoff-request.json"
                        candidate = load(path) if path.exists() else None
                        if (candidate and candidate.get("host_session") == self.session
                                and candidate.get("action") == "stop_when_idle"
                                and candidate.get("request_id") not in finished_requests
                                and set(candidate.get("aics", [])) == set(self.settings["aics"])):
                            result_path = self.control / "handoff-result.json"
                            result = load(result_path) if result_path.exists() else {}
                            if (result.get("request_id") == candidate.get("request_id")
                                    and result.get("action") == "cancel" and request is not None
                                    and not server.should_exit):
                                finished_requests.add(candidate["request_id"])
                                self.event("planned_pause_cancelled", request_id=candidate["request_id"])
                                request = None
                            if result.get("request_id") != candidate.get("request_id") or result.get("action") != "cancel":
                                if request is None:
                                    request = candidate
                                    self.event("planned_pause_requested", request_id=request["request_id"], reason=request["owner"]["purpose"])
                                self.state("draining", request_id=request["request_id"])
                                if server.started and idle(app):
                                    server.should_exit = True
                        await asyncio.sleep(.25)
                    await task
                    if cleanup_error is not None or not request:
                        raise RuntimeError("Managed session did not close through a verified idle handoff")
                except BaseException as error:
                    lease.quarantine("managed consumers cleanup is unknown", evidence={"error_class": type(error).__name__})
                    self.state("quarantined", reason=type(error).__name__)
                    raise
                finally:
                    try:
                        await close_owned_server(task, server, lease)
                    except BaseException as error:
                        self.state("quarantined", reason=type(error).__name__)
                        raise
                self.state("paused", request_id=request["request_id"], consumers_closed=True, lease_released=True)
                self.event("planned_pause_started", request_id=request["request_id"], reason=request["owner"]["purpose"])
                while True:
                    path = self.control / "handoff-result.json"
                    result = load(path) if path.exists() else {}
                    if (result.get("request_id") == request["request_id"] and result.get("host_session") == self.session
                            and result.get("action") == "quarantine"):
                        self.state("quarantined", request_id=request["request_id"], reason=result.get("reason"))
                        self.event("planned_pause_quarantined", request_id=request["request_id"], reason=result.get("reason"))
                        raise LeaseQuarantined("Experiment cleanup was not fully verified")
                    if (result.get("request_id") == request["request_id"] and result.get("host_session") == self.session
                            and result.get("action") in {"resume", "cancel"}):
                        break
                    await asyncio.sleep(.25)
                pending_resume = dict(request_id=request["request_id"], reason=result["action"])
                finished_requests.add(request["request_id"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    settings, target = prepare(args.config)
    if args.run:
        asyncio.run(ManagedHost(settings, target).run())
    else:
        print(json.dumps(dict(status="prepared_not_started", aics=settings["aics"], project=target.project,
                              network_attempted=False, processes_started=False)))


if __name__ == "__main__":
    main()
