"""Nonsecret container-target paths and commands shared by evaluator processes."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_SERVICES = {"application-agent": "application", "verification-agent": "verification",
    "database-agent": "database", "database-backup-agent": "database", "ops-agent": "ops", "onboarding-agent": "onboarding"}
DOMAIN_SOURCE_FILES = ("acps_mcp_bridge/bridge.py", "acps_mcp_bridge/handover.py", "acps_mcp_bridge/policy.py", "incident/partners.py",
    "business/load.py",
    "incident/contracts.py", "incident/platform_worker.py", "domains/ops/guard.py",
    "domains/ops/route_mcp.py", "domains/ops/policy.yaml", "domains/ops/policy.native.yaml",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_leader.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_partner.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_auth.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/_task_order.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/ledger.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/journal.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/_message_tap.py",
    "vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py", "incident/amp_setup.py", "incident/recover_access.py")


def validate_platform_bindings(config, domains, *, selected=None, descriptions=None, project=None):
    """Bind formal ADP choices to the domains physically inspected in this target."""
    if set(domains) != set(DOMAIN_SERVICES):
        raise ValueError("Explicit platform target requires all six registered domain containers")
    role_aics = {role: {row["aic"] for name, row in domains.items() if DOMAIN_SERVICES[name] == role}
                 for role in ("application", "verification", "database", "ops")}
    trusted = config.get("trusted_participant_aics", {})
    initial = config.get("initial_participant_aics", {})
    if not isinstance(trusted, dict) or not isinstance(initial, dict):
        raise ValueError("Platform identity mappings must be objects")
    for role, expected in role_aics.items():
        if not isinstance(trusted.get(role), list) or set(trusted[role]) != expected:
            raise ValueError("Trusted role identities differ from the explicit container target")
        if role in initial and initial[role] not in expected:
            raise ValueError("Initial role identity differs from the explicit container target")
        if selected is not None and selected.get(role) not in expected:
            raise ValueError("Selected platform participant is outside the explicit container target")
        if selected is not None and role in initial and selected.get(role) != initial[role]:
            raise ValueError("Selected participant differs from this run's explicit initial identity")
    if initial.get("database") != domains["database-agent"]["aic"]:
        raise ValueError("Explicit platform target must initially select its primary database")
    if config.get("leader", {}).get("aic") in {row["aic"] for row in domains.values()}:
        raise ValueError("Coordinator and domain identities must be distinct")
    if descriptions is not None:
        scope = descriptions.get("ops", {}).get("resource_scope", {})
        if any(scope.get(key) != value for key, value in {"compose_project": project,
                "compose_service": "app-v2", "container_name": project+"-app-v2-1"}.items()):
            raise ValueError("Operations participant describes a different Compose resource")


@dataclass(frozen=True)
class DockerTarget:
    project: str
    wsl_distro: str | None
    compose_files: tuple[Path, ...]
    env_file: Path
    route_file: Path
    ports: dict[str, int]

    @classmethod
    def from_file(cls, path, *, root=ROOT):
        root = Path(root).resolve()
        def local(value):
            if not isinstance(value, str) or not value or "\x00" in value:
                raise ValueError("Target paths must be nonempty local paths")
            result = (root / value).resolve()
            if not result.is_relative_to(root) or not result.is_file():
                raise ValueError("Target file must exist inside this project")
            return result
        source = local(str(path))
        value = json.loads(source.read_text(encoding="utf-8-sig"))
        required = {"schema_version", "backend", "project", "wsl_distro", "compose_files", "env_file", "route_file", "ports"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Container target has unexpected or missing fields; credentials do not belong here")
        if value["schema_version"] != "incident-evaluator-target/1.0" or value["backend"] != "docker":
            raise ValueError("Unsupported container target schema/backend")
        if not isinstance(value["project"], str) or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", value["project"]) is None:
            raise ValueError("Invalid Compose project")
        distro = value["wsl_distro"]
        if distro is not None and (not isinstance(distro, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", distro) is None):
            raise ValueError("Invalid WSL distribution")
        files = value["compose_files"]
        if not isinstance(files, list) or not files or len(files) > 8:
            raise ValueError("compose_files must list the exact Compose inputs")
        files = tuple(local(name) for name in files)
        if len(set(files)) != len(files) or any(path.suffix not in {".yaml", ".yml"} for path in files):
            raise ValueError("Compose inputs must be distinct YAML files")
        ports = value["ports"]
        if (not isinstance(ports, dict) or set(ports) not in ({"app_v1", "app_v2", "order"}, {"app_v1", "app_v2", "order", "reply_drop"})
                or any(type(port) is not int or not 1 <= port <= 65535 for port in ports.values())
                or len(set(ports.values())) != len(ports)):
            raise ValueError("Target needs three or four distinct integer host ports")
        target = cls(value["project"], distro, files, local(value["env_file"]), local(value["route_file"]), dict(ports))
        # Reject unconvertible WSL paths before issuing any command.
        for file in (*target.compose_files, target.env_file, target.route_file):
            target.docker_path(file)
        return target

    def docker_path(self, path):
        path = Path(path)
        if self.wsl_distro:
            value = path.as_posix()
            if not re.match(r"^[A-Za-z]:/", value):
                raise ValueError("WSL target paths require a local Windows drive")
            return "/mnt/" + value[0].lower() + value[2:]
        return str(path)

    @property
    def docker(self):
        return ["wsl.exe", "-d", self.wsl_distro, "--exec", "docker"] if self.wsl_distro else ["docker"]

    @property
    def compose(self):
        command = self.docker + ["compose", "-p", self.project, "--env-file", self.docker_path(self.env_file)]
        for path in self.compose_files:
            command += ["-f", self.docker_path(path)]
        return command

    @property
    def order_url(self):
        return f"http://127.0.0.1:{self.ports['order']}"

    @property
    def reply_drop_url(self):
        if "reply_drop" not in self.ports:
            raise ValueError("F12 requires an explicit reply_drop host port")
        return f"http://127.0.0.1:{self.ports['reply_drop']}"

    def public_description(self):
        return {"project": self.project, "wsl_distro": self.wsl_distro, "ports": self.ports,
                "credentials": "read only by the separate injector/domain processes",
                "worker_version_boundary": "host source hashes alone do not prove externally running platform worker image versions"}
