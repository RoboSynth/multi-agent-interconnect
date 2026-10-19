"""Formal E1 preparation and explicitly authorized execution.

Default: validate an existing private plan using files only. Preparation never
connects to Docker/platform/resources; execution is a separate, bound opt-in.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DB_SERVICES = ("database-agent", "database-backup-agent")
ROLES = ("application", "database", "database-backup", "ops", "verification", "onboarding")
CLEANUP_EVENTS = {"dissolve_notify_failed", "group_acl_delete_failed", "queue_cleanup_failed", "exchange_cleanup_failed"}
RESOURCE_NAMES = {"DATABASE_URL", "DATABASE_URI", "POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "BRIDGE_DB_PASSWORD",
                  "APP_ADMIN_TOKEN", "OPS_SUPERVISOR_TOKEN", "DOCKER_HOST", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY"}
EFFECTS = ["F07 apply and restore on the bound orders target", "replace only owned primary/backup database workers",
           "one primary after_applied exit83", "formal AMQPS ADP/describe/act/resume and owned group close",
           "approved db.restore_writes and application.pool_rebuild", "restore normal database workers and independent H00"]
POINTS = {
    "after_observation": {"exit_code": 81, "tool": "db.read_only_status", "ledger_state": None, "writer": "database-backup"},
    "before_modification": {"exit_code": 82, "tool": "db.restore_writes", "ledger_state": "received", "writer": "database-backup"},
    "after_applied": {"exit_code": 83, "tool": "db.restore_writes", "ledger_state": "applied", "writer": "database"},
}


METHODS = ("from_scratch", "full_history", "resume_package")


def effects(point, case="E1-a", method=None, *, recover_access=False):
    result = list(EFFECTS)
    result[2] = f"one primary {point} exit{POINTS[point]['exit_code']}"
    if case == "E1-b":
        result.append("one formal handover using " + method + "; same authority, remaining repairs and verification")
    elif case == "E1-c":
        result[2] = "one primary before_modification SIGSTOP and SIGCONT of the same Linux PID/start ticks"
        result.append("one resumed original stale-fence request; primary MCP modifications zero, backup one")
        result.append("retain the stopped primary group member until stale rejection evidence, then normal SDK removal")
    if recover_access:
        result.append("after owned database workers stop, replay each original domain access journal in an offline network-disabled container before normal worker restoration")
    return result


def validate_case(case, point, method):
    if not (case == "E1-a" and method is None or
            case == "E1-b" and point == "after_applied" and method in METHODS or
            case == "E1-c" and point == "before_modification" and method is None):
        raise ValueError("E1-a has no method; E1-b requires after_applied/method; E1-c requires before_modification/no method")


def validate_interruption(case, primary, backup):
    from acps_mcp_bridge.experiment import ExperimentSpec
    for role, document in (("primary", primary), ("backup", backup)):
        spec = ExperimentSpec.from_document(document, experiment_id=primary["experiment_id"],
            executor_aic=primary["primary_aic"] if role == "primary" else primary["backup_aic"])
        expected_mode = "suspend" if case == "E1-c" and role == "primary" else "exit"
        if spec.worker_role != role or getattr(spec, "interruption_mode", "exit") != expected_mode:
            raise ValueError("Worker interruption mode differs from the planned case")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local(path):
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError("E1 input/output must stay inside this project")
    return result


def source_paths():
    # Same bounded source categories as eval.run.freeze_sources, without writes.
    paths = set((ROOT / "eval").glob("*.py")) | set((ROOT / "eval/methods").glob("*.py"))
    for directory in ("incident", "acps_mcp_bridge", "business", "domains", "vendor/ACPs-community/acps-sdk/acps_sdk"):
        paths.update(p for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in {".py", ".yaml", ".sql"}
                     and not {"__pycache__", "private", "runtime", ".git"}.intersection(p.relative_to(ROOT).parts))
    paths.update(ROOT / name for name in ("requirements-lock.txt", "requirements-high-score.txt", "deploy/compose.yml",
        "deploy/agents.yml", "deploy/Dockerfile.agent", "business/order_app/Dockerfile"))
    paths.update((ROOT / "deploy").glob("*.yml")); paths.update((ROOT / "deploy").glob("*.yaml"))
    paths.update(p for p in (ROOT / "domains").rglob("requirements.txt")
                 if not {"private", "runtime"}.intersection(p.relative_to(ROOT).parts))
    paths.update(ROOT / name for name in ("vendor/ACPs-community/acps-sdk/pyproject.toml", "deploy/Dockerfile.docker-mcp")
                 if (ROOT / name).is_file())
    return paths


def identities(config, primary, backup):
    expected = {"coordinator": config["leader"]["aic"], "database": primary, "database-backup": backup}
    trusted = config["trusted_participant_aics"]
    if set(trusted.get("database", [])) != {primary, backup} or config["initial_participant_aics"].get("database") != primary:
        raise ValueError("E1 requires exact trusted primary/backup and initial primary")
    for role in ("application", "ops", "verification", "onboarding"):
        if len(trusted.get(role, [])) != 1:
            raise ValueError("E1 requires one exact trusted identity per other role")
        expected[role] = trusted[role][0]
    if len(set(expected.values())) != 7 or set(config["skills"]) != {"application", "database", "ops", "verification", "onboarding"}:
        raise ValueError("E1 requires seven distinct identities and all five role skill queries")
    return expected


def configuration_inputs(config_path, profile, target, bundle):
    config = load(config_path)
    inputs = {config_path, target.env_file, target.route_file, *target.compose_files}
    for value in (config["trust_bundle"], config["leader"]["cert"], config["leader"]["key"], config["approval_env_file"]):
        if not Path(value).is_absolute():
            raise ValueError("Formal coordinator paths must be absolute Windows/local paths")
        inputs.add(local(value))
    for role in (*ROLES, "coordinator"):
        directory = profile / "domains" / role
        if not directory.is_dir():
            raise ValueError("Explicit NEW7 domain profile is incomplete")
        inputs.update(local(p) for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in
                      {".json", ".yaml", ".yml", ".env", ".pem", ".crt", ".key"})
    inputs.update(local(p) for p in bundle.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return inputs


def prepare(args):
    from eval.targets import DockerTarget
    target = DockerTarget.from_file(local(args.target_config))
    config_path, profile, bundle = local(args.config), local(args.domain_profile), local(args.bundle)
    config = load(config_path)
    primary, backup = load(bundle / "primary.json"), load(bundle / "backup.json")
    experiment, incident = primary["experiment_id"], primary["incident_id"]
    point = primary["crash_point"]
    if point not in POINTS or (primary["crash_tool"], primary["armed"], backup["armed"], backup["crash_point"]) != (
            POINTS[point]["tool"], True, False, None):
        raise ValueError("An exact armed E1 primary interruption and unarmed backup are required")
    case, method = getattr(args, "case", "E1-a"), getattr(args, "method", None)
    validate_case(case, point, method)
    validate_interruption(case, primary, backup)
    if any(primary[k] != backup[k] for k in ("experiment_id", "incident_id", "primary_aic", "backup_aic")):
        raise ValueError("Worker role documents differ in identity or experiment scope")
    if any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value) is None for value in (experiment, incident)):
        raise ValueError("Experiment/incident IDs must be preallocated safe exact names")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id) is None:
        raise ValueError("An exact deployed agent image ID is required")
    expected = identities(config, primary["primary_aic"], primary["backup_aic"])
    if not config.get("approval_env_file") or not config.get("term_journal_path") or not config.get("term_namespace"):
        raise ValueError("Persistent term authority and own approval file are required")
    # Only this explicit profile's fixed domain inputs, never AMP/history/SQLite.
    inputs = configuration_inputs(config_path, profile, target, bundle) | {local(args.target_config)}
    files = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(inputs | source_paths())}
    output = local(args.output)
    if not output.is_relative_to(ROOT / "eval/results/platform") or output.exists():
        raise ValueError("E1 output must be a new eval/results/platform directory")
    recover_access = getattr(args, "recover_access", False)
    if type(recover_access) is not bool:
        raise ValueError("recover_access must be an explicit boolean")
    plan = dict(schema_version="platform-e1-plan/3" if case == "E1-c" else "platform-e1-plan/2", case=case, crash_point=point,
        experiment_id=experiment, incident_id=incident, operation_id=incident + ":db-restore-writes",
        target_config=local(args.target_config).relative_to(ROOT).as_posix(),
        config=config_path.relative_to(ROOT).as_posix(), domain_profile=profile.relative_to(ROOT).as_posix(),
        bundle=bundle.relative_to(ROOT).as_posix(), output=output.relative_to(ROOT).as_posix(),
        project=target.project, identities=expected, image_id=args.image_id,
        file_sha256=files, model_calls=0, approve_high_required=True, effects=effects(point, case, method, recover_access=recover_access),
        evidence_limits=["MCP invocations are not physical side effects", "process-local ownership lock cannot exclude another host",
                         "normal close evidence is SDK return/local state/warnings, not a broker ACL inventory",
                         "one case only; no cross-method effectiveness claim"])
    if recover_access:
        plan["recover_access"] = True
    if case == "E1-c":
        plan.update(interruption_mode="suspend", replay_attempts=1)
        plan["evidence_limits"].append("one resumed pending original request, not additional AIP replay messages or physical effect counts")
    else:
        plan["evidence_limits"].append("no old-primary resurrection claim")
    if method is not None:
        plan["method"] = method
    path = local(args.plan)
    if path.exists() or output == path or path.is_relative_to(output):
        raise ValueError("Plan path must be new and separate from experiment output")
    validate_plan(document=plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, plan)
    return plan


def validate_plan(path=None, *, document=None):
    plan = load(path) if document is None else document
    version, point = plan.get("schema_version"), plan.get("crash_point")
    case, method = plan.get("case"), plan.get("method")
    if (version not in {"platform-e1-plan/1", "platform-e1-plan/2", "platform-e1-plan/3"} or point not in POINTS
            or version == "platform-e1-plan/1" and (point != "after_applied" or case != "E1-a" or "method" in plan)
            or (version == "platform-e1-plan/3") != (case == "E1-c")):
        raise ValueError("Unsupported formal E1 plan")
    validate_case(case, point, method)
    if case == "E1-c":
        if plan.get("interruption_mode") != "suspend" or type(plan.get("replay_attempts")) is not int or plan["replay_attempts"] != 1:
            raise ValueError("E1-c binds one suspended original request on the same process")
    elif "interruption_mode" in plan or "replay_attempts" in plan:
        raise ValueError("Legacy exit cases cannot acquire revival effects")
    if "recover_access" in plan and type(plan["recover_access"]) is not bool:
        raise ValueError("recover_access must be a boolean")
    if plan.get("effects") != effects(point, case, method, recover_access=plan.get("recover_access", False)) or plan.get("model_calls") != 0 or plan.get("approve_high_required") is not True:
        raise ValueError("E1 effect/model/approval contract changed")
    if not plan.get("file_sha256"):
        raise ValueError("Complete frozen E1 inputs are required")
    for name, expected in plan["file_sha256"].items():
        if not local(name).is_file() or digest(local(name)) != expected:
            raise ValueError("Frozen E1 input changed: " + name)
    required = {p.relative_to(ROOT).as_posix() for p in source_paths()}
    if not required <= plan["file_sha256"].keys():
        raise ValueError("Frozen E1 source set is incomplete")
    from eval.targets import DockerTarget
    target = DockerTarget.from_file(local(plan["target_config"]))
    if target.project != plan["project"]:
        raise ValueError("Target project changed")
    config = load(local(plan["config"]))
    if identities(config, plan["identities"]["database"], plan["identities"]["database-backup"]) != plan["identities"]:
        raise ValueError("Coordinator identities differ from plan")
    output = local(plan["output"])
    if not output.is_relative_to(ROOT / "eval/results/platform") or output.exists():
        raise ValueError("E1 output exists or is outside its owned results root")
    if plan["operation_id"] != plan["incident_id"] + ":db-restore-writes":
        raise ValueError("Operation differs from the preallocated incident")
    bundle = local(plan["bundle"])
    primary, backup, manifest = (load(bundle / name) for name in ("primary.json", "backup.json", "worker-source-manifest.json"))
    validate_interruption(case, primary, backup)
    common = {"experiment_id": plan["experiment_id"], "incident_id": plan["incident_id"],
              "primary_aic": plan["identities"]["database"], "backup_aic": plan["identities"]["database-backup"]}
    if any(document.get(k) != v for document in (primary, backup) for k, v in common.items()):
        raise ValueError("Worker bundle differs from the exact plan scope")
    if (primary.get("armed"), primary.get("crash_point"), primary.get("crash_tool"), primary.get("worker_role"),
        backup.get("armed"), backup.get("crash_point"), backup.get("worker_role")) != (
            True, point, POINTS[point]["tool"], "primary", False, None, "backup"):
        raise ValueError("Only the plan's exact primary interruption and unarmed backup are allowed")
    if manifest.get("schema_version") != "e1-worker-bundle/1" or manifest.get("experiment_id") != plan["experiment_id"]:
        raise ValueError("Worker bundle manifest scope differs")
    for name, expected in {**manifest["source_sha256"], **manifest["experiment_sha256"]}.items():
        candidate = (bundle / name).resolve()
        if not candidate.is_relative_to(bundle) or digest(candidate) != expected:
            raise ValueError("Worker bundle manifest fingerprint mismatch")
    expected_bundle_sources = {"source/eval/platform_database_worker.py", "source/acps_mcp_bridge/experiment.py", "source/incident/local_worker.py"}
    if set(manifest["source_sha256"]) != expected_bundle_sources or set(manifest["experiment_sha256"]) != {"primary.json", "backup.json"}:
        raise ValueError("Worker source/role manifest is incomplete")
    for name, expected in manifest["source_sha256"].items():
        if plan["file_sha256"].get(name.removeprefix("source/")) != expected:
            raise ValueError("Worker bundle differs from this frozen canonical source version")
    required_inputs = configuration_inputs(local(plan["config"]), local(plan["domain_profile"]), target, bundle)
    required_inputs.add(local(plan["target_config"]))
    if not {p.relative_to(ROOT).as_posix() for p in required_inputs} <= plan["file_sha256"].keys():
        raise ValueError("Required target/config/bundle files are absent from input freeze")
    import yaml
    expected_services = {}
    for role, service in (("primary", DB_SERVICES[0]), ("backup", DB_SERVICES[1])):
        expected_services[service] = dict(command=["python", "/experiment/source/eval/platform_database_worker.py",
            "--config", "/domain/bridge.json", "--experiment", "/experiment/" + role + ".json",
            "--experiment-id", plan["experiment_id"], "--trace", "/state/experiments/" + plan["experiment_id"] + "/" + role + ".jsonl",
            "--bundle-manifest", "/experiment/worker-source-manifest.json", "--bundle-sha", digest(bundle / "worker-source-manifest.json"), "--serve"],
            volumes=[dict(type="bind", source="${NEW7_E1_EXPERIMENT_ROOT:?Set the frozen E1 bundle WSL absolute directory}",
                          target="/experiment", read_only=True)],
            labels={"incident-pilot.experiment": plan["experiment_id"], "incident-pilot.e1-role": role})
    expected_services[DB_SERVICES[0]]["restart"] = "no"
    if case == "E1-c":
        expected_services[DB_SERVICES[0]]["init"] = True
    if yaml.safe_load((bundle / "e1-worker-overlay.yml").read_text(encoding="utf-8")) != {"services": expected_services}:
        raise ValueError("E1 overlay differs from the exact two-worker readonly bundle contract")
    return plan


def authorize(plan, plan_path, authorization_path, approve_high):
    # This runs before imports/objects capable of network, Docker or journal I/O.
    if not authorization_path or approve_high is not True:
        raise ValueError("Execution requires bound authorization and --approve-high")
    auth = load(local(authorization_path))
    version = plan["schema_version"].rsplit("/", 1)[1]
    expected = dict(schema_version="platform-e1-authorization/" + version, authorized=True,
        plan_sha256=digest(plan_path), experiment_id=plan["experiment_id"], incident_id=plan["incident_id"],
        output=plan["output"], case=plan["case"], crash_point=plan["crash_point"], effects=plan["effects"],
        exclusive_coordinator=True, no_other_identity_consumers=True, no_active_or_unknown_operations=True)
    if plan["case"] == "E1-b":
        expected["method"] = plan["method"]
    elif plan["case"] == "E1-c":
        expected.update(interruption_mode=plan["interruption_mode"], replay_attempts=plan["replay_attempts"])
    if plan.get("recover_access"):
        expected["recover_access"] = True
    boolean_fields = ("authorized", "exclusive_coordinator", "no_other_identity_consumers", "no_active_or_unknown_operations")
    if plan.get("recover_access"):
        boolean_fields += ("recover_access",)
    if (auth != expected or any(type(auth.get(key)) is not bool for key in boolean_fields)
            or plan["case"] == "E1-c" and type(auth.get("replay_attempts")) is not int):
        raise ValueError("Authorization must exactly bind this plan, one case and ownership preconditions")
    forbidden = [name for name in os.environ if name.upper().startswith("PG") or name.upper() in RESOURCE_NAMES]
    if forbidden:
        raise ValueError("Resource credential/remote Docker variables must be absent from coordinator environment")
    return auth


@contextmanager
def coordinator_lock(aic):
    # Same identity lock as the prepared healthy/E3 entry and scheduled host.
    directory = ROOT / "artifacts/new7-platform-healthy-plan-20261018/ownership"
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory / (hashlib.sha256(aic.encode()).hexdigest() + ".lock")).open("a+b")
    if stream.seek(0, os.SEEK_END) == 0:
        stream.write(b"0"); stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


def clean_environment():
    names = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA",
             "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
    return {k: v for k, v in os.environ.items() if k.upper() in names} | {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}


class Controller:
    """Own two DB workers; keep Injector's original all-domain identity contract."""
    def __init__(self, plan, output):
        from eval.targets import DockerTarget
        self.plan, self.output = plan, output
        self.target = DockerTarget.from_file(local(plan["target_config"]))
        self.normal = self.target.compose
        self.overlay = self.normal + ["-f", self.target.docker_path(local(plan["bundle"]) / "e1-worker-overlay.yml")]
        if self.target.wsl_distro:
            self.overlay = self.overlay[:4] + ["env", "NEW7_E1_EXPERIMENT_ROOT=" + self.target.docker_path(local(plan["bundle"]))] + self.overlay[4:]
        self.original = self.current = None
        self.switched = False
        self.ownership_confirmed = False
        self.serial = 0
        self.access_recovery = []

    def command(self, argv):
        env = clean_environment()
        if not self.target.wsl_distro:
            env["NEW7_E1_EXPERIMENT_ROOT"] = str(local(self.plan["bundle"]))
        argv = [str(item) for item in argv]
        started = time.monotonic()
        # Windows/WSL diagnostics can use a different encoding even when the
        # command succeeds. Preserve both streams verbatim; only stdout is an
        # input to our JSON/text protocols, and stderr must never be surfaced.
        result = subprocess.run(argv, capture_output=True, env=env, timeout=180)
        with (self.output / "subprocess-exits.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(argv=argv, actual_exit_code=result.returncode,
                duration_seconds=round(time.monotonic() - started, 3),
                stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(result.stderr).hexdigest())) + "\n")
        if result.returncode:
            # Docker/MCP failures may include private env/config. Never surface stderr.
            raise RuntimeError("Owned E1 subprocess failed with exit " + str(result.returncode))
        return result.stdout.decode("utf-8", errors="strict")

    def inspect(self):
        ids = self.command(self.normal + ["ps", "-a", "-q"]).split()
        if not ids:
            raise ValueError("Owned target has no containers")
        records = json.loads(self.command(self.target.docker + ["inspect", *ids]))
        result = {}
        for item in records:
            labels = item.get("Config", {}).get("Labels") or {}
            service = labels.get("com.docker.compose.service")
            if (labels.get("incident-pilot") != "true" or labels.get("com.docker.compose.project") != self.plan["project"]
                    or service in result):
                raise ValueError("Unknown/duplicate container ownership")
            result[service] = item
        return result

    def owned_worker(self, item, service, *, experiment=False, running=True):
        if item["Image"] != self.plan["image_id"] or (running and item["State"]["Running"] is not True):
            raise ValueError("Owned database image/runtime differs from plan")
        mounts = [m for m in item["Mounts"] if m["Destination"] == "/domain"]
        role = "database" if service == "database-agent" else "database-backup"
        expected = self.target.docker_path(local(self.plan["domain_profile"]) / "domains" / role)
        if len(mounts) != 1 or mounts[0]["RW"] is not False or mounts[0]["Source"].rstrip("/") != expected.rstrip("/"):
            raise ValueError("Owned database config mount mismatch")
        if not item["HostConfig"]["ReadonlyRootfs"]:
            raise ValueError("Owned database must retain read-only root filesystem")
        if experiment:
            labels = item["Config"]["Labels"]
            extra = [m for m in item["Mounts"] if m["Destination"] == "/experiment"]
            if (labels.get("incident-pilot.experiment") != self.plan["experiment_id"] or
                labels.get("incident-pilot.e1-role") != ("primary" if service == DB_SERVICES[0] else "backup") or
                len(extra) != 1 or extra[0]["RW"] is not False or
                extra[0]["Source"].rstrip("/") != self.target.docker_path(local(self.plan["bundle"])).rstrip("/")):
                raise ValueError("Experiment worker ownership/mount mismatch")
            if service == DB_SERVICES[0] and item["HostConfig"]["RestartPolicy"]["Name"] != "no":
                raise ValueError("Experimental primary restart must be disabled")
            import yaml
            overlay = yaml.safe_load((local(self.plan["bundle"]) / "e1-worker-overlay.yml").read_text(encoding="utf-8"))
            if item["Config"].get("Cmd") != overlay["services"][service]["command"]:
                raise ValueError("Experimental command differs from the frozen worker bundle")
        elif item["Config"].get("Cmd") != ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"]:
            raise ValueError("Normal database command differs from its owned entrypoint")

    def owned_database(self, records, *, experiment=False, running=True):
        for service in DB_SERVICES:
            self.owned_worker(records[service], service, experiment=experiment, running=running)
        shared = [{m.get("Name") for m in records[s]["Mounts"] if m["Destination"] == "/state" and m["Type"] == "volume"}
                  for s in DB_SERVICES]
        if (not shared[0] or shared[0] != shared[1] or len(shared[0]) != 1
                or any(not name.startswith(self.plan["project"] + "_") for name in shared[0])):
            raise ValueError("Primary/backup must share exactly one operation state volume")

    def assert_stable_others(self, records):
        if set(records) != set(self.original):
            raise ValueError("Unexpected target service added or removed")
        for name, old in self.original.items():
            if name not in DB_SERVICES:
                new = records[name]
                if (new["Id"], new["Image"], new["State"]["StartedAt"]) != (old["Id"], old["Image"], old["State"]["StartedAt"]):
                    raise ValueError("An unowned service changed during E1")

    def injector(self, action, expected=None):
        self.serial += 1
        argv = [sys.executable, ROOT / "eval/inject.py", "F07", action, "--backend", "docker",
                "--target-config", local(self.plan["target_config"]), "--record", self.output / "injections.jsonl"]
        from eval.targets import DOMAIN_SOURCE_FILES
        sources = {name: self.plan["file_sha256"][name] for name in DOMAIN_SOURCE_FILES}
        argv += ["--expected-sources", json.dumps(sources), "--expected-compose-hashes", json.dumps({str(p): digest(p) for p in self.target.compose_files})]
        if expected is not None:
            argv += ["--expected-domains", json.dumps(expected)]
        proof = json.loads(self.command(argv).strip().splitlines()[-1])
        save(self.output / (str(self.serial).zfill(2) + "-injector-" + action + ".json"), proof)
        return proof["target_proof"]["domains"]

    def ledger_probe(self, container):
        code = ("import json,sqlite3;from pathlib import Path;c=json.loads(Path('/domain/bridge.json').read_text());"
                "p=Path(c['ledger_path']);p=p if p.is_absolute() else Path('/domain')/p;"
                "r={'exists':p.exists(),'operations':[]};"
                "conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) if p.exists() else None;"
                "r['operations']=[dict(zip(['operation_id','state'],row)) for row in conn.execute('SELECT operation_id,state FROM operations')] if conn else [];"
                "print(json.dumps(r))")
        return json.loads(self.command(self.target.docker + ["exec", container, "python", "-c", code]))

    def future_configuration(self):
        """Check what both future up commands would use, before stopping anyone.

        Compose render contains private env values; retain only hashes/bindings.
        No build/pull is permitted as part of this experiment.
        """
        # Render all definitions, including NEW7's profile-gated domains. This
        # flag is local to config inspection and never added to an up command.
        normal_text = self.command(self.normal + ["--profile", "*", "config", "--format", "json"])
        extra_text = self.command(self.overlay + ["--profile", "*", "config", "--format", "json"])
        normal, extra = json.loads(normal_text), json.loads(extra_text)
        if ({k: v for k, v in normal.items() if k != "services"} != {k: v for k, v in extra.items() if k != "services"}
                or set(normal["services"]) != set(extra["services"])):
            raise ValueError("E1 overlay changed the target service/network/volume graph")
        proof = {}
        for name, value in normal["services"].items():
            changed = extra["services"][name]
            if name not in DB_SERVICES:
                if value != changed:
                    raise ValueError("E1 overlay changed an unowned service")
                continue
            mutable = {"command", "volumes", "restart", "labels"}
            if self.plan["case"] == "E1-c" and name == DB_SERVICES[0]:
                if changed.get("init") is not True:
                    raise ValueError("Suspended primary requires init so the worker is not namespace PID 1")
                mutable.add("init")
            if {k: v for k, v in value.items() if k not in mutable} != {k: v for k, v in changed.items() if k not in mutable}:
                raise ValueError("E1 overlay changed database permissions/image/environment")
            proof[name] = {}
            for label, document in (("normal", value), ("experiment", changed)):
                reference = document["image"]
                actual = self.command(self.target.docker + ["image", "inspect", "--format", "{{.Id}}", reference]).strip()
                if actual != self.plan["image_id"]:
                    raise ValueError("Future Compose image differs from the frozen deployed E1 image")
                proof[name][label] = dict(image_reference=reference, image_id=actual)
            if value["command"] != ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"]:
                raise ValueError("Normal Compose database entrypoint is not the expected owned worker")
            import yaml
            spec = yaml.safe_load((local(self.plan["bundle"]) / "e1-worker-overlay.yml").read_text(encoding="utf-8"))["services"][name]
            labels = value.get("labels", {})
            if ("incident-pilot.experiment" in labels or changed["command"] != spec["command"]
                    or changed.get("labels") != labels | spec["labels"]
                    or changed.get("restart") != ("no" if name == DB_SERVICES[0] else value.get("restart"))):
                raise ValueError("Rendered experimental command/labels/restart differ from this case")
            volumes = changed.get("volumes", [])
            additional = [v for v in volumes if v.get("target") == "/experiment"]
            if (len(additional) != 1 or [v for v in volumes if v.get("target") != "/experiment"] != value.get("volumes", [])
                    or any(v.get("target") == "/experiment" for v in value.get("volumes", []))):
                raise ValueError("E1 overlay must add only its one readonly experiment mount")
            mount = additional[0]
            if (mount.get("type") != "bind" or mount.get("read_only") is not True
                    or mount.get("source", "").rstrip("/") != self.target.docker_path(local(self.plan["bundle"])).rstrip("/")
                    or set(mount) - {"type", "source", "target", "read_only", "bind"}
                    or set(mount.get("bind", {})) - {"create_host_path"}):
                raise ValueError("Rendered experiment mount has unexpected access or source")
        if set(proof) != set(DB_SERVICES):
            raise ValueError("Future configuration lacks the exact primary and backup")
        save(self.output / "future-compose-image-bindings.json", dict(services=proof,
            normal_render_sha256=hashlib.sha256(normal_text.encode()).hexdigest(),
            experiment_render_sha256=hashlib.sha256(extra_text.encode()).hexdigest(), raw_render_retained=False))

    def begin(self):
        self.original = self.inspect()
        self.owned_database(self.original)
        from eval.targets import DOMAIN_SERVICES
        required = {"postgres", "app-v1", "app-v2", "nginx", *DOMAIN_SERVICES}
        if (not required <= self.original.keys() or set(self.original) - required - {"fault-locker"}
                or any(not self.original[name]["State"]["Running"] for name in required)
                or self.original.get("fault-locker", {}).get("State", {}).get("Running", False)):
            raise ValueError("All explicit target services must be running before E1")
        self.future_configuration()
        self.current = self.injector("check")
        if any(row["image_id"] != self.plan["image_id"] for row in self.current.values()):
            raise ValueError("All formal domain images must match the frozen agent image")
        for service in DB_SERVICES:
            ledger = self.ledger_probe(self.original[service]["Id"])
            if ledger.get("exists") is not True:
                raise ValueError("Existing owned database ledger could not be observed")
            operations = ledger["operations"]
            if any(row["state"] != "applied" or row["operation_id"] == self.plan["operation_id"] for row in operations):
                raise ValueError("Existing active/unknown operation or reused experiment operation; preserve ledger")
        amp_source = "vendor/ACPs-community/acps-sdk/acps_sdk/amp/message_emitter.py"
        for row in self.current.values():
            actual = self.command(self.target.docker + ["exec", row["container_id"], "python", "-c",
                "import hashlib;from pathlib import Path;print(hashlib.sha256(Path('/srv/" + amp_source + "').read_bytes()).hexdigest())"]).strip()
            if actual != self.plan["file_sha256"][amp_source]:
                raise ValueError("Deployed AMP source differs from this post-E3 E1 version")
        save(self.output / "initial-domains.json", self.current)
        self.ownership_confirmed = True
        self.switched = True  # Partial stop/up must still trigger owned restoration.
        self.command(self.target.docker + ["stop", "--time", "20", *[self.original[s]["Id"] for s in DB_SERVICES]])
        stopped = self.inspect()
        if any(stopped[s]["State"]["Running"] for s in DB_SERVICES):
            raise ValueError("Prior database Inbox consumers did not stop")
        self.command(self.overlay + ["up", "-d", "--no-deps", "--force-recreate", "--no-build", "--pull", "never", *DB_SERVICES])
        records = self.inspect(); self.assert_stable_others(records); self.owned_database(records, experiment=True)
        self.experimental = {name: records[name]["Id"] for name in DB_SERVICES}
        self.experimental_started = {name: records[name]["State"]["StartedAt"] for name in DB_SERVICES}
        self.current = self.injector("check")  # Fresh full attestation, never reuse old StartedAt.
        save(self.output / "experimental-domains.json", self.current)

    def apply(self):
        self.injector("apply", self.current)

    def collect(self, payload):
        point = self.plan["crash_point"]
        contract = POINTS[point]
        records = self.inspect(); self.assert_stable_others(records)
        self.owned_database(records, experiment=True, running=False)
        primary = records[DB_SERVICES[0]]
        if any(records[name]["Id"] != identity for name, identity in self.experimental.items()):
            raise ValueError("An experimental worker was unexpectedly recreated")
        if any(records[name]["State"]["StartedAt"] != started for name, started in self.experimental_started.items()):
            raise ValueError("An experimental worker unexpectedly restarted")
        if (primary["State"]["Running"] or primary["State"]["ExitCode"] != contract["exit_code"]
                or not records[DB_SERVICES[1]]["State"]["Running"]):
            raise ValueError("Expected planned primary exit/remaining backup is not observed")
        paths = []
        for role in ("primary", "backup"):
            remote = "/state/experiments/" + self.plan["experiment_id"] + "/" + role + ".jsonl"
            text = self.command(self.target.docker + ["exec", records[DB_SERVICES[1]]["Id"], "python", "-c",
                    "from pathlib import Path;print(Path(" + repr(remote) + ").read_text(),end='')"])
            path = self.output / (role + "-trace.jsonl"); path.write_text(text, encoding="utf-8"); paths.append(path)
        from acps_mcp_bridge.experiment import operation_counts
        for role, path in zip(("primary", "backup"), paths):
            starts = [event for line in path.read_text(encoding="utf-8").splitlines()
                      if (event := json.loads(line)).get("event") == "experiment_worker_start"]
            expected_start = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
                executor_aic=self.plan["identities"]["database" if role == "primary" else "database-backup"],
                worker_role=role, armed=role == "primary", bundle_manifest_sha256=digest(local(self.plan["bundle"]) / "worker-source-manifest.json"),
                transport="wutong-amqps")
            if len(starts) != 1 or any(starts[0].get(k) != v for k, v in expected_start.items()):
                raise ValueError("Durable worker startup does not bind the exact manifest/identity/role")
        counts = operation_counts(paths, experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"])
        crashes = [load_event for line in paths[0].read_text(encoding="utf-8").splitlines()
                   if (load_event := json.loads(line)).get("event") == "experiment_worker_crash"]
        if len(crashes) != 1 or any(crashes[0].get(k) != v for k, v in {
                "crash_point": point, "exit_code": contract["exit_code"],
                "operation_id": None if point == "after_observation" else self.plan["operation_id"],
                "experiment_id": self.plan["experiment_id"], "incident_id": self.plan["incident_id"],
                "executor_aic": self.plan["identities"]["database"], "logical_task_id": payload["logical_task_id"],
                "tool": contract["tool"],
                "ledger_state": contract["ledger_state"], "AIP_product_submitted": False}.items()):
            raise ValueError("Durable crash marker differs from this planned interrupted request")
        expected = [{"executor_aic": self.plan["identities"][contract["writer"]], "operation_id": self.plan["operation_id"],
                     "invocations": 1, "returned": 1, "returned_errors": 0, "without_return": 0}]
        if counts["operations"] != expected:
            raise ValueError("Expected exactly one MCP invocation by the planned writer and none by the other worker")
        save(self.output / "mcp-operation-counts.json", counts)
        return {"expected_exit_code": contract["exit_code"], "actual_exit_code": primary["State"]["ExitCode"], "counts": counts}

    def recover_access(self, records):
        """Replay original journals without network or opening resource tools/credential files."""
        for service in DB_SERVICES:
            role = "database" if service == DB_SERVICES[0] else "database-backup"
            try:
                item = records[service]
                if item["State"]["Running"]:
                    raise ValueError("Access recovery requires stopped domain workers")
                domain = local(self.plan["domain_profile"]) / "domains" / role
                config = load(domain / "bridge.json")
                platform = config["platform"]
                directory = PurePosixPath(platform["amp_directory"])
                if (config["executor_aic"] != self.plan["identities"][role]
                        or platform["name"] != role or not directory.is_relative_to("/state")
                        or ".." in directory.parts):
                    raise ValueError("Recovery domain identity or original AMP directory differs")
                states = [m for m in item["Mounts"] if m["Destination"] == "/state" and m["Type"] == "volume"]
                originals = [m.get("Name") for m in self.original[service]["Mounts"]
                             if m["Destination"] == "/state" and m["Type"] == "volume"]
                if (len(states) != 1 or [states[0]["Name"]] != originals
                        or not states[0]["Name"].startswith(self.plan["project"] + "_")):
                    raise ValueError("Recovery state volume ownership differs")
                command = self.target.docker + ["run", "--rm", "--network", "none", "--read-only",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--label", "incident-pilot=true", "--label", "incident-pilot.recovery=" + self.plan["experiment_id"],
                    "--mount", "type=volume,src=" + states[0]["Name"] + ",dst=/state",
                    "--mount", "type=bind,src=" + self.target.docker_path(domain) + ",dst=/domain,readonly",
                    "--entrypoint", "python", self.plan["image_id"], "-m", "incident.recover_access",
                    "--config", "/domain/bridge.json", "--expected-aic", config["executor_aic"],
                    "--expected-name", role, "--expected-directory", platform["amp_directory"]]
                receipt = json.loads(self.command(command))
                if (receipt.get("schema_version") != "domain-access-recovery/1" or receipt.get("status") != "recovered"
                        or receipt.get("aic") != self.plan["identities"][role] or receipt.get("name") != role
                        or receipt.get("config_sha256") != digest(domain / "bridge.json")
                        or receipt.get("business_or_platform_actions") != 0):
                    raise ValueError("Access recovery receipt differs from the original domain")
                self.access_recovery.append(dict(service=service, **receipt))
            except Exception as error:
                self.access_recovery.append(dict(service=service, status="failed", error_class=type(error).__name__))
        save(self.output / "access-recovery.json", self.access_recovery)

    def restore(self):
        if not self.switched:
            return
        records = self.inspect(); self.assert_stable_others(records)
        # Refuse unrelated identities before any stop, even on a partial startup.
        for service in DB_SERVICES:
            allowed = {self.original[service]["Id"]}
            if hasattr(self, "experimental"):
                allowed.add(self.experimental[service])
            if records[service]["Id"] not in allowed:
                if hasattr(self, "experimental"):
                    raise ValueError("Unexpected replacement DB identity; preserve for owner review")
                # Compose may have replaced one worker before returning failure.
                # Adopt only this bundle's exact labels/image/RO mount/command.
            self.owned_worker(records[service], service,
                              experiment=records[service]["Id"] != self.original[service]["Id"], running=False)
        self.command(self.target.docker + ["stop", "--time", "20", *[records[s]["Id"] for s in DB_SERVICES]])
        if self.plan.get("recover_access"):
            stopped = self.inspect(); self.assert_stable_others(stopped)
            for service in DB_SERVICES:
                if stopped[service]["Id"] != records[service]["Id"] or stopped[service]["State"]["Running"]:
                    raise ValueError("Database worker did not stop or was replaced before access recovery")
            self.recover_access(stopped)
        self.command(self.normal + ["up", "-d", "--no-deps", "--force-recreate", "--no-build", "--pull", "never", *DB_SERVICES])
        records = self.inspect(); self.assert_stable_others(records); self.owned_database(records)
        if any(any(m["Destination"] == "/experiment" for m in records[s]["Mounts"]) for s in DB_SERVICES):
            raise ValueError("Normal worker restoration retained experiment mount")
        self.current = self.injector("check")
        save(self.output / "restored-domains.json", self.current)
        self.injector("restore", self.current)



class CleanupWarnings(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.events = []

    def emit(self, record):
        match = re.search(r"event=([A-Za-z0-9_]+)", record.getMessage())
        if match and match[1] in CLEANUP_EVENTS:
            self.events.append(match[1])


async def close_owned(transport, warnings):
    # Also closes a known group if start() failed during later describe tasks.
    owned = transport.session.session_id if transport.session else None
    runtime = transport.runtime
    if runtime and (set(runtime.group_sessions) - ({owned} if owned else set()) or runtime._inbound_groups):
        raise RuntimeError("Unexpected group ownership; preserve unknown groups for owner review")
    await transport.close()
    state = getattr(getattr(transport.session, "leader_mq_client", None), "_state", None)
    checks = dict(no_group_sessions=not runtime or not runtime.group_sessions,
        no_inbound_groups=not runtime or not runtime._inbound_groups,
        inbox_cancelled=not runtime or runtime._inbox_consumer_tag is None,
        connection_closed=not runtime or runtime._connection is None or runtime._connection.is_closed,
        owned_group_disconnected=owned is None or str(getattr(state, "value", state)).casefold() == "disconnected",
        no_cleanup_warnings=not warnings.events)
    if not all(checks.values()):
        raise RuntimeError("Owned group normal close did not pass all local/warning checks")
    return checks


def healthy(summary):
    return (summary.get("passed") is True and summary.get("duration_seconds", 0) >= 30
        and summary.get("completed_workflows", 0) >= 10 and summary.get("failed") == 0
        and summary.get("unknown") == 0 and summary.get("unresolved_intents") == 0
        and not summary.get("state", {}).get("pending", []))


def journal_resolution(journal, plan, original, session_id, *, coordinator_term=None):
    """Classify the expected lost primary acknowledgement without editing history."""
    from acps_sdk.aip.resumable import Fence
    rows = journal.list_tasks()
    pending = journal.list_tasks(in_flight_only=True)
    completed_resume = []
    completed_replay = []
    point = plan["crash_point"]
    resume_operation = original.get("operation_id") or plan["incident_id"] + ":observe:" + original["logical_task_id"]
    old_fence = Fence(**original.get("fence", {"coordinator_term": coordinator_term, "takeover_version": 0}))
    expected_fence = Fence(max(old_fence.coordinator_term, coordinator_term or 0), old_fence.takeover_version + 1).to_dict()
    for row in rows:
        if row.get("command") != "start" or not row.get("content"):
            continue
        content = json.loads(row["content"])
        completed = (row["session_id"] == session_id and row["partner_aic"] == plan["identities"]["database-backup"]
            and row["logical_task_id"] == original["logical_task_id"] and content.get("incident_id") == plan["incident_id"]
            and any(end["session_id"] == session_id and end["task_id"] == row["task_id"]
                    and end["partner_aic"] == row["partner_aic"] and end["state"] == "completed" for end in rows))
        if (completed and content.get("kind") == "resume" and content.get("operation_id") == resume_operation
                and content.get("args", {}).get("advance_fence") is True and content.get("fence") == expected_fence):
            completed_resume.append(row["task_id"])
        replay = original if original["kind"] == "observe" else {**original, "fence": expected_fence}
        if completed and content == replay:
            completed_replay.append(row["task_id"])
    if len(set(completed_resume)) != 1:
        raise ValueError("Exactly one actual completed backup resume is required in the journal")
    if point != "after_applied" and len(set(completed_replay)) != 1:
        raise ValueError("Interrupted observation/received action requires one completed original request on the backup")
    if len(pending) > 1:
        raise ValueError("Unexpected nonterminal attempts remain in the journal")
    for row in pending:
        if (row["session_id"] != session_id or row["partner_aic"] != plan["identities"]["database"]
                or row["command"] != "start" or row["logical_task_id"] != original["logical_task_id"]
                or not row.get("content") or json.loads(row["content"]) != original):
            raise ValueError("Nonterminal attempt is not the exact interrupted primary request")
    return dict(raw_in_flight_count=len(pending), expected_unacknowledged_primary_attempts=len(pending),
        unexpected_in_flight_count=0, completed_backup_resume_task_id=completed_resume[0], raw_journal_modified=False,
        completed_backup_replay_task_id=completed_replay[0] if completed_replay else None,
        basis=("Same primary PID/start ticks resumed its original stale request and was rejected; backup continuation and MCP counts verified."
               if plan["case"] == "E1-c" else
               f"Primary {point}/exit{POINTS[point]['exit_code']} and exact MCP counts were independently verified; backup continuation completed."))


async def run_case(plan, *, controller_factory=None, transport_factory=None, final_health=None):
    from incident.contracts import TaskPayload
    from eval.targets import validate_platform_bindings
    if transport_factory is None:
        from incident.wutong_transport import WutongTransport
        transport_factory = WutongTransport
    if controller_factory is None:
        if plan["case"] == "E1-c":
            from eval.platform_e1c_controller import RevivalController
            controller_factory = RevivalController
        else:
            controller_factory = Controller
    output = local(plan["output"]); output.mkdir(parents=True, exist_ok=False)
    source_hashes = {}
    for path in source_paths():
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != plan["file_sha256"].get(relative):
            raise ValueError("Source changed before snapshot: " + relative)
        copied = output / "source" / relative; copied.parent.mkdir(parents=True, exist_ok=True); copied.write_bytes(data)
        source_hashes[relative] = plan["file_sha256"][relative]
    controller = controller_factory(plan, output)
    transport = None; warnings = CleanupWarnings(); logging.getLogger().addHandler(warnings)
    report = dict(schema_version="platform-e1-result/3" if plan["case"] == "E1-c" else "platform-e1-result/2", case=plan["case"], crash_point=plan["crash_point"],
        experiment_id=plan["experiment_id"], incident_id=plan["incident_id"], operation_id=plan["operation_id"],
        status="failed", model_calls=0, source_sha256=source_hashes,
        started_at=datetime.now(timezone.utc).isoformat(), products=[])
    recorder = None
    deferred_removal = None
    if plan["case"] == "E1-b":
        report.update(method=plan["method"], model_tokens=0)
    elif plan["case"] == "E1-c":
        report.update(interruption_mode=plan["interruption_mode"], replay_attempts=plan["replay_attempts"])
    try:
        await asyncio.to_thread(controller.begin)
        config = load(local(plan["config"])); config["automatic_takeover"] = True
        transport = transport_factory(config, output / "coordinator")
        if plan["case"] == "E1-b":
            from eval.platform_handover import bind_handover
            recorder = bind_handover(transport, plan["method"], output)
        await asyncio.wait_for(transport.start(), 240)
        validate_platform_bindings(config, controller.current, selected=transport.selected,
                                   descriptions=transport.descriptions, project=plan["project"])
        expected_selected = {role: aic for role, aic in plan["identities"].items() if role in config["skills"]}
        if transport.selected != expected_selected:
            raise ValueError("Initial official participants differ from exact planned identities")
        if plan["case"] == "E1-c":
            from eval.platform_e1c_transport import DeferredPrimaryRemoval
            deferred_removal = DeferredPrimaryRemoval(transport, plan["identities"]["database"],
                                                       plan["identities"]["database-backup"])
        task_index = 0
        async def call(kind, tool, args=None):
            nonlocal task_index
            task_index += 1
            value = dict(incident_id=plan["incident_id"], logical_task_id=plan["incident_id"] + ":" + str(task_index),
                         kind=kind, tool=tool, args=args or {}, budget={"deadline_ms": 120000 if kind == "verify" else 15000})
            if kind == "act":
                role = "database" if tool.startswith("db.") else "application"
                active = getattr(transport, "active_fences", {}).get(role)
                value.update(operation_id=plan["operation_id"] if tool.startswith("db.") else plan["incident_id"] + ":pool-rebuild",
                             fence=active.to_dict() if active else {"coordinator_term": transport.term, "takeover_version": 0})
            payload = TaskPayload(**value).model_dump(exclude_none=True)
            if kind == "act":
                payload["approval"] = transport.issue_approval(payload)
            product = await transport.call(payload)
            report["products"].append({"payload": payload, "product": product})
            if product.get("status") != "ok":
                raise RuntimeError("Planned E1 product was not ok")
            return product
        baseline = await call("verify", "incident.verification")
        if not healthy({f["key"]: f["value"] for f in baseline.get("facts", [])}.get("order_observation", {})):
            raise ValueError("Initial target does not pass the clean business baseline")
        await asyncio.to_thread(controller.apply)
        if recorder is not None:
            # Same pre-interruption observations for each information method.
            await call("observe", "application.status")
        observed = await call("observe", "db.read_only_status")
        if {f["key"]: f["value"] for f in observed.get("facts", [])}.get("read_only") is not True:
            raise ValueError("F07 business precondition was not observed")
        interrupted = report["products"][-1]["payload"] if plan["crash_point"] == "after_observation" else None
        if interrupted is not None and observed.get("executor_aic") != plan["identities"]["database-backup"]:
            raise ValueError("Interrupted observation was not completed by the planned backup")
        product = await call("act", "db.restore_writes")
        expected_state = "skipped_already_applied" if plan["crash_point"] == "after_applied" else "applied"
        if (transport.selected["database"] != plan["identities"]["database-backup"]
                or product.get("executor_aic") != plan["identities"]["database-backup"]
                or product.get("operation", {}).get("state") != expected_state
                or product.get("operation", {}).get("operation_id") != plan["operation_id"]):
            raise ValueError("Expected formal backup continuation of the planned interruption was not confirmed")
        interrupted = interrupted or report["products"][-1]["payload"]
        report["worker_revival_and_mcp" if plan["case"] == "E1-c" else "worker_exit_and_mcp"] = await asyncio.to_thread(controller.collect, interrupted)
        if deferred_removal is not None:
            report["old_primary_removal"] = await deferred_removal.flush()
        reusable = {}
        if recorder is not None:
            from eval.platform_handover import verify_handover
            handover = verify_handover(transport, recorder, interrupted, product,
                                        backup_aic=plan["identities"]["database-backup"])
            reusable = handover["fresh_facts"]
            report["handover"] = handover["metrics"]
        resumed_at = time.monotonic()
        revision_fact = reusable.get("application_pool_revision")
        additional_observations = 0
        if revision_fact is None or type(revision_fact.get("value")) is not int:
            app = await call("observe", "application.status")
            revision_fact = next((f for f in app.get("facts", []) if f["key"] == "application_pool_revision"), None)
            additional_observations += 1
        revision = revision_fact.get("value") if revision_fact else None
        if type(revision) is not int or revision < 0:
            raise ValueError("Pool rebuild requires a fresh observed revision")
        await call("act", "application.pool_rebuild", {"expected_revision": revision})
        verified = await call("verify", "incident.verification")
        facts = {f["key"]: f["value"] for f in verified.get("facts", [])}
        if facts.get("business_recovered") is not True or not healthy(facts.get("order_observation", {})):
            raise ValueError("Formal verification did not confirm a clean 30s/10-workflow window")
        report["business_verification"] = facts["order_observation"]
        if recorder is not None:
            report.update(additional_post_handover_observations=additional_observations,
                reused_fact_keys=sorted(reusable), revision_fact=revision_fact,
                remaining_workflow_including_verification_seconds=time.monotonic()-resumed_at)
        report["journal_resolution"] = journal_resolution(transport.journal, plan, interrupted, transport.session.session_id,
                                                          coordinator_term=transport.term)
        if transport.runtime._pending_invitations:
            raise ValueError("Formal invitations are not terminal")
        report["task_phase_status"] = "completed"
    except Exception as error:
        report["error_class"] = type(error).__name__
    finally:
        if deferred_removal is not None:
            deferred_removal.detach()
        if transport is not None:
            try:
                report["close_checks"] = await close_owned(transport, warnings)
            except Exception as error:
                report["close_error_class"] = type(error).__name__
        logging.getLogger().removeHandler(warnings)
        report["cleanup_warning_events"] = warnings.events
        if not controller.ownership_confirmed:
            report["resource_and_worker_restore"] = "not_attempted_scope_unconfirmed"
            report["independent_final_H00_status"] = "not_attempted_scope_unconfirmed"
        else:
            try:
                await asyncio.to_thread(controller.restore)
                report["resource_and_worker_restore"] = "completed"
                if plan.get("recover_access"):
                    report["access_recovery"] = controller.access_recovery
                    if (len(controller.access_recovery) != 2 or any(row.get("status") != "recovered" for row in controller.access_recovery)):
                        report["access_recovery_error_class"] = "AccessRecoveryIncomplete"
                if final_health is None:
                    from business.load import OrderObserver
                    summary = await OrderObserver(controller.target.order_url, run_id=plan["experiment_id"] + "-final-H00",
                                                  expected_api_version="v2").observe(duration=30, min_complete=10)
                else:
                    summary = await final_health()
                report["independent_final_H00"] = summary
                if not healthy(summary):
                    raise RuntimeError("Independent final H00 failed")
            except Exception as error:
                report["restore_or_H00_error_class"] = type(error).__name__
        report["status"] = "completed" if (report.get("task_phase_status") == "completed"
            and "close_checks" in report and "independent_final_H00" in report
            and not any(key.endswith("error_class") for key in report)) else "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(output / "results.json", report)
    return 0 if report["status"] == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case", choices=("E1-a", "E1-b", "E1-c"), default="E1-a")
    parser.add_argument("--method", choices=METHODS)
    for name in ("config", "target-config", "domain-profile", "bundle", "output", "image-id"):
        parser.add_argument("--" + name)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--approve-high", action="store_true")
    parser.add_argument("--recover-access", action="store_true", help="Bind explicit offline recovery of original domain journals after worker stop")
    args = parser.parse_args(argv)
    if args.prepare and args.execute:
        raise ValueError("Preparation and execution are separate commands")
    if args.prepare:
        if any(getattr(args, key) is None for key in ("config", "target_config", "domain_profile", "bundle", "output", "image_id")):
            raise ValueError("Preparation requires explicit target, Windows config, profile, worker bundle, image and fresh output")
        prepare(args)
        print(json.dumps({"status": "FORMAL_E1_PLAN_PREPARED_NOT_EXECUTED", "resource_network_model_actions": 0}))
        return 0
    plan = validate_plan(local(args.plan))
    if not args.execute:
        print(json.dumps({"status": "FORMAL_E1_OFFLINE_PLAN_VALID", "resource_network_model_actions": 0}))
        return 0
    authorize(plan, local(args.plan), args.authorization_file, args.approve_high)
    with coordinator_lock(plan["identities"]["coordinator"]):
        return asyncio.run(run_case(plan))


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
