"""Prepare an isolated deployment; launch only through the explicit --launch option."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("application", "verification", "database", "database-backup", "ops", "onboarding")
PROFILE = "isolated"
SCHEMA = "incident-deployment/1.1"
LEGACY_SCHEMA = "incident-deployment/1.0"
GENERATED_ENV_KEYS = ("POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "APP_ADMIN_TOKEN", "BRIDGE_DB_PASSWORD",
                      "ORDER_BIND", "APP_V1_PORT", "APP_V2_PORT", "ORDER_PORT", "REPLY_DROP_PORT")
COMPOSE_SCOPE_KEYS = ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
                      "COMPOSE_DISABLE_ENV_FILE", "COMPOSE_PATH_SEPARATOR", "COMPOSE_CONVERT_WINDOWS_PATHS")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path, root=ROOT):
    path = (root / path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Deployment paths must stay inside this checkout")
    return path


def relative(path, root=ROOT):
    return inside(path, root).relative_to(root.resolve()).as_posix()


def docker_path(path, wsl):
    value = Path(path).as_posix()
    if wsl:
        if not re.match(r"^[A-Za-z]:/", value):
            raise ValueError("WSL deployment needs a local Windows drive")
        return "/mnt/" + value[0].lower() + value[2:]
    return value


def validate_options(project, ports, reply_port, wsl):
    if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise ValueError("Invalid Compose project name")
    if (not isinstance(ports, dict) or set(ports) != {"app_v1", "app_v2", "order"}
            or any(type(port) is not int or not 1 <= port <= 65535 for port in (*ports.values(), reply_port))
            or len(set((*ports.values(), reply_port))) != 4):
        raise ValueError("Specify four distinct host ports between 1 and 65535")
    if wsl is not None and (not isinstance(wsl, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", wsl)):
        raise ValueError("Invalid WSL distribution")


def overlay_value(output, project, mode, wsl, *, schema=SCHEMA):
    if schema not in {SCHEMA, LEGACY_SCHEMA}:
        raise ValueError("Unsupported deployment overlay schema")
    route = docker_path(output / "nginx-runtime", wsl)
    services = {"nginx": {"volumes": [{"type": "bind", "source": route,
        "target": "/etc/nginx/runtime", "read_only": True}]}}
    if schema == SCHEMA:
        # The opt-in reply-loss proxy must reuse the already built application
        # image. Injector separately verifies its immutable ID against app-v2.
        application_image = project + "-app-v2:local"
        services.update({"app-v2": {"image": application_image}, "reply-drop": {"image": application_image}})
    if mode == "seven":
        for role in ROLES:
            services[role + "-agent"] = {"image": project + "-agent:local", "profiles": [PROFILE],
                "volumes": [{"type": "bind", "source": docker_path(output / "domains" / role, wsl),
                             "target": "/domain", "read_only": True}]}
        services["ops-agent"]["volumes"].append({"type": "bind", "source": route, "target": "/route"})
    return {"services": services}


def check_sources(source):
    """Check the seven prepared identities before creating any output or secrets."""
    identities = []
    for role in (*ROLES, "coordinator"):
        config = json.loads((source / (role + ".json")).read_text(encoding="utf-8-sig"))
        identity = config["leader"] if role == "coordinator" else config
        if any(not isinstance(identity.get(key), str) or not identity[key].strip() for key in ("aic", "endpoint")):
            raise ValueError("Seven mode requires all seven prepared identities")
        identities.append(identity["aic"])
        if role == "coordinator" and any(not Path(value).is_absolute()
                for value in (identity["cert"], identity["key"], config["trust_bundle"])):
            raise ValueError("Prepared coordinator certificate/key/trust paths must be absolute")
        for key in ("cert", "key"):
            material = Path(identity[key])
            if not material.is_absolute():
                material = source / material
            if not material.is_file():
                raise ValueError("Prepared identity certificate/key file is missing")
        trust = Path(config["trust_bundle"])
        if not trust.is_absolute():
            trust = source / trust
        if not trust.is_file():
            raise ValueError("Prepared identity trust bundle is missing")
    if len(set(identities)) != 7:
        raise ValueError("Seven mode requires seven distinct identities")


def identity_configs(path):
    """Translate registered identity references without requiring native DB/MCP setup."""
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    public = {key: raw[key] for key in ("discovery_url", "mq_auth_url", "trust_bundle")}
    for key in ("discovery_url", "mq_auth_url"):
        url = urlparse(public[key])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Identity metadata URLs must be public HTTPS configuration without credentials")
    trust = Path(public["trust_bundle"])
    if not trust.is_absolute() or not trust.is_file():
        raise ValueError("Identity trust bundle must reference an existing absolute file")
    identities = {}
    for role in (*ROLES, "coordinator"):
        source_role = {"database-backup": "database_backup", "coordinator": "leader"}.get(role, role)
        identity = {key: raw["agents"][source_role][key] for key in ("aic", "endpoint", "cert", "key")}
        url = urlparse(identity["endpoint"])
        if (not isinstance(identity["aic"], str) or not identity["aic"].strip() or url.scheme != "amqps"
                or not url.hostname or url.username or url.password):
            raise ValueError("Seven registered identities need nonempty AICs and credential-free AMQPS endpoints")
        if any(not Path(identity[key]).is_absolute() or not Path(identity[key]).is_file() for key in ("cert", "key")):
            raise ValueError("Identity certificate/key must reference existing absolute files")
        identities[role] = identity
    if len({row["aic"] for row in identities.values()}) != 7:
        raise ValueError("Seven mode requires seven distinct identities")
    result = {role: {**row, **public, "name": role, "role": "database" if role == "database-backup" else role,
                    "allowed_leaders": [identities["coordinator"]["aic"]]}
              for role, row in identities.items() if role != "coordinator"}
    result["coordinator"] = {**public, "leader": identities["coordinator"],
        "skills": {"application": "incident.application", "database": "db.observe", "ops": "ops.observe",
                   "verification": "incident.verification", "onboarding": "aip.onboarding.check"}}
    return result


def protect_output(output):
    """Keep host parents private; permit image UID 65534 to read its own bind root."""
    output.chmod(0o700)
    for path in output.rglob("*"):
        parts = path.relative_to(output).parts
        mounted_domain = len(parts) >= 2 and parts[0] == "domains" and parts[1] in ROLES
        path.chmod((0o755 if path.is_dir() else 0o644) if mounted_domain
                   else (0o700 if path.is_dir() else 0o600))


def prepare(output, project, ports, *, reply_port=8090, mode="business", source=None,
            identity_file=None, wsl=None, root=ROOT, public_onboarding=False):
    root = Path(root).resolve()
    output = inside(output, root)
    validate_options(project, ports, reply_port, wsl)
    if mode not in {"business", "seven"}:
        raise ValueError("Unknown deployment mode")
    if public_onboarding and mode != "seven":
        raise ValueError("public_onboarding requires seven mode")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose a new empty deployment directory; existing files are never overwritten")
    if source is not None and identity_file is not None:
        raise ValueError("Choose only one of --source and --identity-file")
    direct = None
    if mode == "seven":
        if identity_file is not None:
            direct = identity_configs(identity_file)
        elif source is not None:
            source = Path(source).resolve()
            check_sources(source)
        else:
            raise ValueError("Seven mode requires --identity-file or domains/setup_platform.py output")
    elif source is not None or identity_file is not None:
        raise ValueError("Identity source is only used by seven mode")
    output.mkdir(parents=True, exist_ok=True)
    values = {name: secrets.token_urlsafe(36) for name in
              ("POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD", "APP_ADMIN_TOKEN", "BRIDGE_DB_PASSWORD")}
    values.update(ORDER_BIND="127.0.0.1", APP_V1_PORT=str(ports["app_v1"]),
                  APP_V2_PORT=str(ports["app_v2"]), ORDER_PORT=str(ports["order"]), REPLY_DROP_PORT=str(reply_port))
    env = output / "compose.env"
    env.write_text("".join(name + "=" + value + "\n" for name, value in values.items()), encoding="utf-8")
    route = output / "nginx-runtime/route.conf"
    route.parent.mkdir()
    route.write_bytes((root / "deploy/nginx/route.default.conf").read_bytes())
    compose_files = ["deploy/compose.yml"]
    if mode == "seven":
        if direct is not None:
            source = output / "platform-source"
            source.mkdir()
            for role, config in direct.items():
                save(source / (role + ".json"), config)
        # Existing domain preparation owns credential separation and operations scope.
        sys.path.insert(0, str(ROOT))
        from deploy.prepare_agents import prepare as prepare_agents
        approval = output / "approval.env"
        approval.write_text("INCIDENT_APPROVAL_SECRET=" + secrets.token_urlsafe(36) + "\n", encoding="utf-8")
        report = prepare_agents(source, output / "domains", env, approval, project,
            include_onboarding=True, include_coordinator=True, ops_service="app-v2",
            public_onboarding=public_onboarding)
        if set(report["prepared"]) != set(ROLES) or report["pending_identities"]:
            raise ValueError("Seven-domain preparation is incomplete; do not launch this output")
        compose_files.append("deploy/agents.yml")
    overlay = output / "deployment.overlay.yml"
    save(overlay, overlay_value(output, project, mode, wsl))  # JSON is also valid YAML.
    compose_files.append(relative(overlay, root))
    common = {"project": project, "wsl_distro": wsl, "compose_files": compose_files,
              "env_file": relative(env, root), "route_file": relative(route, root), "ports": dict(ports)}
    target_path = None
    if mode == "seven":
        target_path = output / "target.json"
        save(target_path, {"schema_version": "incident-evaluator-target/1.0", "backend": "docker", **common,
                           "ports": {**ports, "reply_drop": reply_port}})
    # The route is deliberately mutable: normal reruns preserve a fault route until restored explicitly.
    inputs = [env, overlay, *(root / name for name in compose_files[:-1])]
    if target_path:
        inputs += [target_path, *(path for path in (output / "domains").rglob("*") if path.is_file()), output / "approval.env"]
    manifest = {"schema_version": SCHEMA, "mode": mode, **common, "reply_drop_port": reply_port,
        "profiles": [PROFILE] if mode == "seven" else [],
        "target_config": relative(target_path, root) if target_path else None,
        "coordinator_config": relative(output / "domains/coordinator/config.json", root) if mode == "seven" else None,
        "input_sha256": {relative(path, root): digest(path) for path in sorted(inputs)}}
    save(output / "deployment.json", manifest)
    if os.name != "nt":
        protect_output(output)
    return {"deployment_file": relative(output / "deployment.json", root), "mode": mode,
            "project": project, "ports": ports, "prepared_only": True, "resources_started": False,
            "platform_ready": False, "injector_target_available": target_path is not None}


def load_deployment(path, *, root=ROOT):
    root = Path(root).resolve()
    path = inside(path, root)
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    required = {"schema_version", "mode", "project", "wsl_distro", "compose_files", "env_file", "route_file",
                "ports", "reply_drop_port", "profiles", "target_config", "coordinator_config", "input_sha256"}
    if (not isinstance(manifest, dict) or set(manifest) != required
            or manifest["schema_version"] not in {SCHEMA, LEGACY_SCHEMA}):
        raise ValueError("Unsupported deployment manifest")
    mode = manifest["mode"]
    if mode not in {"business", "seven"}:
        raise ValueError("Unknown deployment mode")
    validate_options(manifest["project"], manifest["ports"], manifest["reply_drop_port"], manifest["wsl_distro"])
    output = path.parent
    expected_files = ["deploy/compose.yml"] + (["deploy/agents.yml"] if mode == "seven" else [])
    expected_files.append(relative(output / "deployment.overlay.yml", root))
    expected = {"compose_files": expected_files, "env_file": relative(output / "compose.env", root),
                "route_file": relative(output / "nginx-runtime/route.conf", root),
                "profiles": [PROFILE] if mode == "seven" else [],
                "target_config": relative(output / "target.json", root) if mode == "seven" else None,
                "coordinator_config": relative(output / "domains/coordinator/config.json", root) if mode == "seven" else None}
    if any(manifest[key] != value for key, value in expected.items()):
        raise ValueError("Manifest paths or profiles differ from this isolated deployment")
    for name in (*expected_files, manifest["env_file"], manifest["route_file"]):
        if not inside(name, root).is_file():
            raise ValueError("A required deployment input is missing")
    lines = [line for line in (output / "compose.env").read_text(encoding="utf-8-sig").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    environment = dict(line.split("=", 1) for line in lines if "=" in line)
    expected_environment = {"ORDER_BIND": "127.0.0.1", "APP_V1_PORT": str(manifest["ports"]["app_v1"]),
        "APP_V2_PORT": str(manifest["ports"]["app_v2"]), "ORDER_PORT": str(manifest["ports"]["order"]),
        "REPLY_DROP_PORT": str(manifest["reply_drop_port"])}
    if (set(environment) != set(GENERATED_ENV_KEYS) or len(lines) != len(environment)
            or any(environment.get(key) != value for key, value in expected_environment.items())):
        raise ValueError("Private environment bindings differ from the deployment manifest")
    if json.loads((output / "deployment.overlay.yml").read_text(encoding="utf-8")) != overlay_value(
            output, manifest["project"], mode, manifest["wsl_distro"], schema=manifest["schema_version"]):
        raise ValueError("Generated overlay no longer matches this deployment")
    hashes = manifest["input_sha256"]
    if not isinstance(hashes, dict) or not set((*expected_files, manifest["env_file"])) <= hashes.keys():
        raise ValueError("Deployment input fingerprints are incomplete")
    for name, expected_hash in hashes.items():
        file = inside(name, root)
        if not file.is_file() or digest(file) != expected_hash:
            raise ValueError("A prepared deployment input changed; preserve it and prepare a new directory")
    if mode == "seven":
        sys.path.insert(0, str(ROOT))
        from eval.targets import DockerTarget
        target = DockerTarget.from_file(manifest["target_config"], root=root)
        common = {key: manifest[key] for key in ("project", "wsl_distro", "compose_files", "env_file", "route_file", "ports")}
        target_json = json.loads(inside(manifest["target_config"], root).read_text(encoding="utf-8"))
        legacy_target = {"schema_version": "incident-evaluator-target/1.0", "backend": "docker", **common}
        expected_target = {**legacy_target, "ports": {**manifest["ports"], "reply_drop": manifest["reply_drop_port"]}}
        # Earlier preparations remain usable for their three-port experiments;
        # the F12 injector separately requires an explicitly bound fourth port.
        allowed_targets = (legacy_target, expected_target) if manifest["schema_version"] == LEGACY_SCHEMA else (expected_target,)
        if target_json not in allowed_targets:
            raise ValueError("Evaluator target differs from the deployment manifest")
        if target.project != manifest["project"]:
            raise ValueError("Evaluator project mismatch")
    return manifest


def compose_command(manifest, *, root=ROOT, sanitized=False):
    wsl = manifest["wsl_distro"]
    if wsl and os.name != "nt":
        raise ValueError("A WSL deployment must be launched from its Windows checkout")
    command = ["wsl.exe", "-d", wsl, "--exec", "docker"] if wsl else ["docker"]
    if wsl and sanitized:
        command = command[:4] + ["env", *(part for name in (*GENERATED_ENV_KEYS, *COMPOSE_SCOPE_KEYS)
                                         for part in ("-u", name)), "docker"]
    command += ["compose", "-p", manifest["project"], "--env-file", docker_path(inside(manifest["env_file"], root), wsl)]
    for name in manifest["compose_files"]:
        command += ["-f", docker_path(inside(name, root), wsl)]
    for profile in manifest["profiles"]:
        command += ["--profile", profile]
    return command


def launch(path, *, validate_only=False, root=ROOT):
    manifest = load_deployment(path, root=root)
    command = compose_command(manifest, root=root, sanitized=True)
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("COMPOSE_") and key.upper() not in GENERATED_ENV_KEYS}
    # The env file is passed only to Compose, never loaded into this process.
    actions = [["config", "--quiet"]]
    if not validate_only:
        if manifest["mode"] == "seven":
            # Six services share one project-specific image. Build it exactly once.
            actions += [["build", "app-v1", "app-v2"], ["build", "application-agent"],
                        ["up", "-d", "--no-build", "--wait"]]
        else:
            actions += [["up", "-d", "--build", "--wait"]]
    for action in actions:
        result = subprocess.run(command + action, env=environment, check=False)
        if result.returncode:
            return result.returncode
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--mode", choices=("business", "seven"), default="business")
    parser.add_argument("--source", type=Path, help="Existing domains/setup_platform.py output; no registration is performed")
    parser.add_argument("--identity-file", type=Path, help="Registered seven-identity source; skips native setup_local prerequisites")
    parser.add_argument("--public-onboarding", action="store_true", help="Allow external public-metadata checks in seven mode")
    parser.add_argument("--wsl")
    parser.add_argument("--app-v1-port", type=int, default=8081)
    parser.add_argument("--app-v2-port", type=int, default=8082)
    parser.add_argument("--order-port", type=int, default=8088)
    parser.add_argument("--reply-drop-port", type=int, default=8090)
    parser.add_argument("--launch", type=Path, help="Explicit startup, normally called by up.ps1/up.sh")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.launch is not None:
            if args.public_onboarding or any(value is not None for value in (args.output, args.project, args.source, args.identity_file, args.wsl)):
                parser.error("--launch accepts only its manifest and --validate-only")
            return launch(args.launch, validate_only=args.validate_only)
        if args.output is None or args.project is None or args.validate_only:
            parser.error("Preparation requires --output and --project")
        print(json.dumps(prepare(args.output, args.project,
            {"app_v1": args.app_v1_port, "app_v2": args.app_v2_port, "order": args.order_port},
            reply_port=args.reply_drop_port, mode=args.mode, source=args.source, identity_file=args.identity_file,
            wsl=args.wsl, public_onboarding=args.public_onboarding), ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError) as error:
        # File paths and validation reasons only; do not dump configs or env values.
        print("Deployment preparation/launch failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
