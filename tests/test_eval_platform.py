"""Offline transport, target isolation and common-evaluation-contract checks."""
import asyncio
import hashlib
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval.targets import DockerTarget, DOMAIN_SERVICES, DOMAIN_SOURCE_FILES, validate_platform_bindings
from eval.inject import Injector
from eval import run as runner


def profile(directory):
    root = Path(directory)
    for name in ("compose.yml", "agents.yml", "overlay.yml", "compose.env", "routes/route.conf"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("APP_ADMIN_TOKEN=unit-target-value\n" if name.endswith(".env") else "original\n", encoding="utf-8")
    value = {"schema_version": "incident-evaluator-target/1.0", "backend": "docker", "project": "incident-pilot-new7",
        "wsl_distro": None, "compose_files": ["compose.yml", "agents.yml", "overlay.yml"], "env_file": "compose.env",
        "route_file": "routes/route.conf", "ports": {"app_v1": 38081, "app_v2": 38082, "order": 38088}}
    path = root / "target.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path, value, DockerTarget.from_file(path, root=root)


def inspected(target):
    result = []
    for service in ("postgres", "app-v1", "app-v2", "nginx", *DOMAIN_SERVICES):
        row = {"Id": service+"-id", "Image": "sha256:unit-image", "Config": {"Env": ["DO_NOT_EXPORT=private-test-value"],
            "Labels": {"incident-pilot": "true", "com.docker.compose.project": target.project, "com.docker.compose.service": service}},
            "HostConfig": {"PortBindings": {}, "ReadonlyRootfs": True}, "Mounts": [],
            "NetworkSettings": {"Networks": {target.project+"_default": {}}}, "State": {"StartedAt": "2026-10-17T00:00:00Z"}}
        if service in {"app-v1", "app-v2", "nginx"}:
            internal = "80/tcp" if service == "nginx" else "8000/tcp"
            key = {"app-v1": "app_v1", "app-v2": "app_v2", "nginx": "order"}[service]
            row["HostConfig"]["PortBindings"][internal] = [{"HostIp": "127.0.0.1", "HostPort": str(target.ports[key])}]
        if service in {"nginx", "ops-agent"}:
            row["Mounts"] = [{"Type": "bind", "Destination": "/route" if service == "ops-agent" else "/etc/nginx/runtime",
                              "Source": target.docker_path(target.route_file.parent)}]
        if service == "postgres":
            row["Mounts"] = [{"Type": "volume", "Destination": "/var/lib/postgresql/data", "Name": target.project+"_orders-data"}]
        if service in DOMAIN_SERVICES:
            row["Mounts"].append({"Type": "bind", "Destination": "/domain", "Source": "/private/domain", "RW": False})
        result.append(row)
    return result


def domain_proof():
    sources = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in DOMAIN_SOURCE_FILES}
    return {name: {"aic": "unit-"+name, "role": role, "container_id": name+"-id", "image_id": "sha256:unit-image",
        "started_at": "2026-10-17T00:00:00Z",
        "base_url": "http://app-v2:8000" if role == "application" else "http://nginx" if role == "verification" else None,
        "source_sha256": sources} for name, role in DOMAIN_SERVICES.items()}


def platform_config(domains):
    return {"leader": {"aic": "unit-coordinator"}, "initial_participant_aics": {"database": domains["database-agent"]["aic"]},
        "trusted_participant_aics": {role: sorted(row["aic"] for name, row in domains.items() if DOMAIN_SERVICES[name] == role)
                                    for role in ("application", "verification", "database", "ops")}}


class TargetIsolationTests(unittest.TestCase):
    def test_schema_rejects_credentials_escaping_paths_invalid_names_and_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            path, value, _ = profile(directory)
            invalid = [{**value, "password": "not-accepted"}, {**value, "project": "--other"},
                {**value, "wsl_distro": "x;command"}, {**value, "route_file": "../other.conf"},
                {**value, "ports": {"app_v1": True, "app_v2": 38082, "order": 38088}},
                {**value, "ports": {"app_v1": 38088, "app_v2": 38082, "order": 38088}},
                {**value, "compose_files": ["compose.yml", "compose.yml"]}]
            for malformed in invalid:
                with self.subTest(malformed=malformed):
                    path.write_text(json.dumps(malformed), encoding="utf-8")
                    with self.assertRaises(ValueError), patch("eval.inject.run_command") as command:
                        DockerTarget.from_file(path, root=directory)
                    command.assert_not_called()

    def test_wsl_compose_preserves_space_paths_as_single_arguments(self):
        target = DockerTarget("incident-pilot-new7", "Ubuntu-22.04", (Path("D:/Workspace With Spaces/compose.yml"),),
            Path("D:/Workspace With Spaces/private/compose.env"), Path("D:/Workspace With Spaces/routes/route.conf"),
            {"app_v1": 38081, "app_v2": 38082, "order": 38088})
        self.assertEqual(target.compose[:6], ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "docker", "compose"])
        self.assertIn("/mnt/d/Workspace With Spaces/private/compose.env", target.compose)
        self.assertIn("/mnt/d/Workspace With Spaces/compose.yml", target.compose)
        self.assertEqual(target.order_url, "http://127.0.0.1:38088")

    def test_wrong_project_ports_route_or_database_volume_reject_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            records = inspected(target)
            invalid = []
            item = deepcopy(records); item[0]["Config"]["Labels"]["com.docker.compose.project"] = "incident-pilot-container"; invalid.append(item)
            item = deepcopy(records); item[1]["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostPort"] = "8081"; invalid.append(item)
            item = deepcopy(records); item[3]["Mounts"][0]["Source"] = "/old/routes"; invalid.append(item)
            item = deepcopy(records); next(row for row in item if row["Id"] == "ops-agent-id")["Mounts"][0]["Source"] = "/old/routes"; invalid.append(item)
            item = deepcopy(records); item[0]["Mounts"][0]["Name"] = "incident-pilot-container_orders-data"; invalid.append(item)
            invalid.append([row for row in deepcopy(records) if row["Id"] != "ops-agent-id"])
            for rows in invalid:
                with self.subTest(rows=rows), patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(rows)]) as command:
                    with self.assertRaises(ValueError):
                        Injector(backend="docker", target_config=path)
                    self.assertEqual(command.call_count, 2)
                    self.assertEqual(target.route_file.read_text(), "original\n")

    def test_explicit_target_uses_own_env_commands_ports_and_safe_inspection_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            domains = domain_proof()
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(inspected(target)), ""]) as command, \
                 patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service: domains[service]), patch.dict(os.environ, {"APP_ADMIN_TOKEN": "wrong-native-value"}):
                injector = Injector(backend="docker", target_config=path)
                self.assertEqual(injector._environment("APP_ADMIN_TOKEN"), "unit-target-value")
                injector.application(False)
                self.assertEqual(command.call_args.args[0], target.compose+["stop", "app-v2"])
                self.assertEqual(injector.runtime["order_port"], 38088)
                self.assertNotIn("DO_NOT_EXPORT", json.dumps(injector.target_proof))
                with self.assertRaises(ValueError):
                    injector.apply("F12")

    def test_stale_image_source_rejects_and_stable_image_reuses_verified_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            domains = domain_proof()
            wrong = deepcopy(domains); wrong["application-agent"]["source_sha256"]["incident/partners.py"] = "stale"
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(inspected(target))]), \
                 patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service: wrong[service]):
                with self.assertRaisesRegex(ValueError, "source differs"):
                    Injector(backend="docker", target_config=path)
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(inspected(target))]), \
                 patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service, **kw: deepcopy(domains[service])) as probe:
                injector = Injector(backend="docker", target_config=path, expected_domains=domains)
                self.assertTrue(injector.target_proof["domains"]["application-agent"]["source_digest_reused"])
                self.assertEqual(probe.call_count, 6)
                self.assertTrue(all(call.kwargs == {"include_sources": False} for call in probe.call_args_list))
            changed = deepcopy(inspected(target)); next(row for row in changed if row["Id"] == "ops-agent-id")["Image"] = "new-image"
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(changed)]), \
                 patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service, **kw: deepcopy(domains[service])) as probe:
                with self.assertRaisesRegex(ValueError, "image changed"):
                    Injector(backend="docker", target_config=path, expected_domains=domains)

    def test_same_container_and_image_cannot_reuse_changed_public_domain_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            domains = domain_proof()
            changed = deepcopy(domains); changed["application-agent"]["base_url"] = "http://old-native:8082"
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(inspected(target))]), \
                 patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service, **kw: changed[service]):
                with self.assertRaisesRegex(ValueError, "Public domain configuration changed"):
                    Injector(backend="docker", target_config=path, expected_domains=domains)
            records = inspected(target)
            next(row for row in records if row["Id"] == "application-agent-id")["State"]["StartedAt"] = "2026-10-17T01:00:00Z"
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command", side_effect=["ids", json.dumps(records)]), \
                 patch("eval.inject.Injector.runtime_domain") as probe:
                with self.assertRaisesRegex(ValueError, "Domain restarted"):
                    Injector(backend="docker", target_config=path, expected_domains=domains)
                probe.assert_not_called()

    def test_old_platform_aics_or_wrong_described_project_cannot_bind_to_new_target(self):
        domains = domain_proof(); config = platform_config(domains)
        validate_platform_bindings(config, domains)
        wrong = deepcopy(config); wrong["trusted_participant_aics"]["ops"] = ["old-180xx-ops"]
        with self.assertRaises(ValueError): validate_platform_bindings(wrong, domains)
        selected = {role: values[0] for role, values in config["trusted_participant_aics"].items()}
        selected["database"] = domains["database-agent"]["aic"]
        with self.assertRaises(ValueError):
            validate_platform_bindings(config, domains, selected=selected, descriptions={"ops": {"resource_scope": {"compose_project": "old"}}}, project="incident-pilot-new7")

    def test_runtime_probe_reads_only_fixed_sources_and_public_config_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, target = profile(directory)
            injector = object.__new__(Injector); injector.target = target
            with patch("eval.inject.run_command", return_value='{"aic":"unit-public"}') as command:
                self.assertEqual(injector.runtime_domain("domain-id", "ops-agent"), {"aic": "unit-public"})
                code = command.call_args.args[0][-1]
                self.assertIn("/domain/bridge.json", code)
                self.assertIn("Path('/srv')", code)
                self.assertNotIn("env_files", code)
                self.assertNotIn("read_pem", code)
                self.assertNotIn("os.environ", code)

    def test_changed_compose_is_rejected_before_docker_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            with patch("eval.inject.DockerTarget.from_file", return_value=target), patch("eval.inject.run_command") as command:
                with self.assertRaises(ValueError):
                    Injector(backend="docker", target_config=path, expected_compose_hashes={"old": "digest"})
                command.assert_not_called()


class EvaluationRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_native_inject_command_is_preserved_and_docker_passes_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            process = SimpleNamespace(communicate=AsyncMock(return_value=(b'{"started_monotonic":1}', b"")), returncode=0)
            with patch("eval.run.asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as launch:
                record = Path(directory) / "private/injections.jsonl"
                await runner.inject("F01", "apply", Path("native.json"), record)
                command = launch.call_args.args
                self.assertIn("native", command)
                self.assertNotIn("--target-config", command)
                await runner.inject("F01", "apply", Path("native.json"), record, backend="docker", target_config=Path("target.json"))
                command = launch.call_args.args
                self.assertEqual(command[command.index("--backend")+1], "docker")
                self.assertEqual(command[command.index("--target-config")+1], "target.json")

    async def test_invalid_target_or_observer_rejects_before_transport_or_injection(self):
        args = runner.build_parser().parse_args(["--transport", "wutong-amqps", "--backend", "docker"])
        with patch("eval.run.create_transport") as transport, patch("eval.run.inject", AsyncMock()) as inject:
            with self.assertRaises(ValueError):
                await runner.run(args)
            transport.assert_not_called(); inject.assert_not_called()
        args = runner.build_parser().parse_args(["--backend", "docker"])
        with patch("eval.run.DockerTarget.from_file") as target, patch("eval.run.create_transport") as transport:
            with self.assertRaises(ValueError): await runner.run(args)
            target.assert_not_called(); transport.assert_not_called()
        args = runner.build_parser().parse_args(["--transport", "wutong-amqps"])
        with patch("eval.run.create_transport") as transport:
            with self.assertRaises(ValueError):
                await runner.run(args)
            transport.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path, _, target = profile(directory)
            args = runner.build_parser().parse_args(["--transport", "wutong-amqps", "--backend", "docker", "--target-config", str(path), "--order-url", "http://127.0.0.1:8088"])
            with patch("eval.run.DockerTarget.from_file", return_value=target), patch("eval.run.create_transport") as transport:
                with self.assertRaises(ValueError):
                    await runner.run(args)
                transport.assert_not_called()

    def test_transport_factory_uses_existing_implementations(self):
        with patch("incident.wutong_transport.WutongTransport") as formal, patch("incident.local_transport.LocalAipStdioTransport") as local:
            runner.create_transport("wutong-amqps", {"leader": {}}, Path("config.json"), Path("output"))
            formal.assert_called_once_with({"leader": {}}, Path("output/transport"))
            local.assert_not_called()
            runner.create_transport("local-aip-stdio", {}, Path("config.json"), Path("output"))
            local.assert_called_once_with(Path("config.json"))

    async def test_target_preflight_or_source_failure_happens_before_platform_group(self):
        for failure in ("target", "source", "bindings"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target_path, _, target = profile(directory)
                config = root / "coordinator.json"; config.write_text("{}")
                args = runner.build_parser().parse_args(["--config", str(config), "--output", str(root / "out"),
                    "--transport", "wutong-amqps", "--backend", "docker", "--target-config", str(target_path), "--methods", "M0"])
                with patch("eval.run.ROOT", root), patch("eval.run.DockerTarget.from_file", return_value=target), \
                     patch("eval.run.freeze_sources", return_value=domain_proof()["application-agent"]["source_sha256"]), patch("eval.run.create_transport") as create, \
                     patch("eval.run.check_sources", side_effect=RuntimeError("changed") if failure == "source" else None), \
                     patch("eval.run.inject", AsyncMock(side_effect=ValueError("wrong project") if failure == "target" else None,
                        return_value={"target_proof": {"compose_sha256": {}, "domains": domain_proof()}})) as inject:
                    with self.assertRaises((ValueError, RuntimeError)):
                        await runner.run(args)
                    create.assert_not_called()
                    if failure == "source": inject.assert_not_called()

    def test_source_freeze_covers_sdk_policy_and_stops_on_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("eval/run.py", "incident/contracts.py", "domains/database/policy.yaml",
                "vendor/ACPs-community/acps-sdk/acps_sdk/aip/task.py", "requirements-lock.txt", "requirements-high-score.txt",
                "deploy/compose.yml", "deploy/agents.yml", "deploy/Dockerfile.agent", "business/order_app/Dockerfile"):
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("frozen")
            hidden = root / "domains/private/secret.yaml"; hidden.parent.mkdir(); hidden.write_text("excluded")
            with patch("eval.run.ROOT", root):
                hashes = runner.freeze_sources(root / "output")
                self.assertIn("domains/database/policy.yaml", hashes)
                self.assertIn("vendor/ACPs-community/acps-sdk/acps_sdk/aip/task.py", hashes)
                self.assertNotIn("domains/private/secret.yaml", hashes)
                runner.check_sources(hashes)
                (root / "domains/database/policy.yaml").write_text("changed")
                with self.assertRaises(RuntimeError):
                    runner.check_sources(hashes)

    async def test_same_methods_budgets_workload_and_approval_protocol_for_both_transports(self):
        real_sleep = asyncio.sleep
        async def fast_sleep(_):
            await real_sleep(0)
        cases = [(mode, scenario, act_status) for mode in ("local-aip-stdio", "wutong-amqps")
                 for scenario, act_status in (("F01", None), ("H00", None), ("H00", "ok"),
                    ("H00", "unknown"), ("H00", "rejected"), ("H00", "not_dispatched"))]
        for mode, scenario, act_status in cases:
            with self.subTest(mode=mode, scenario=scenario, act_status=act_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target_path, _, target = profile(directory)
                domains = domain_proof()
                config = root / "config.json"; config.write_text(json.dumps(platform_config(domains)))
                captures, observed = [], []
                class Hypothesis:
                    def __init__(self, **options):
                        self.__dict__.update(options); captures.append(("model", options))
                class Engine:
                    def __init__(self, transport, output, **options):
                        self.options = options; captures.append(("engine", options))
                    def new(self, symptom):
                        return {"id": "unit", "status": "running", "approvals": [], "tasks": [], "model_source": "rules",
                            "elapsed_seconds": .1, "tokens": 0, "diagnosed_causes": ["application_unavailable"], "token_usage_complete": True,
                            "model_calls": 0, "model_source_counts": {}, "model_requests": [], "error": ""}
                    async def run(self, state):
                        if act_status is not None:
                            state["tasks"].append({"tool": "ops.restart", "kind": "act", "status": act_status})
                        state["status"] = "completed"; return state
                    def save(self, state): pass
                class Observer:
                    def __init__(self, url, directory, **options):
                        observed.append((url, options)); self.task = None
                    async def start(self): return self
                    async def finish(self, **options):
                        return {"recovery_observed_seconds": 1, "recovery_confirmed_seconds": 31,
                            "recovery_confirmed": scenario != "H00", "fault_observed": scenario != "H00",
                            "healthy_control_confirmed": scenario == "H00", "control_observation_seconds": 30}
                transport = SimpleNamespace(mode=mode, tools=[probe.tool for probe in runner.PROBES]+list(runner.ACTIONS)+["incident.verification"],
                    start=AsyncMock(), close=AsyncMock(), issue_approval=Mock(), term=7,
                    selected={role: "unit-"+service for role, service in (("application", "application-agent"), ("verification", "verification-agent"), ("database", "database-agent"), ("ops", "ops-agent"))},
                    descriptions={"ops": {"resource_scope": {"compose_project": target.project, "compose_service": "app-v2",
                                                              "container_name": target.project+"-app-v2-1"}}})
                target_args = ["--backend", "docker", "--target-config", str(target_path)] if mode == "wutong-amqps" else []
                args = runner.build_parser().parse_args(["--config", str(config), "--output", str(root / "results"),
                    "--transport", mode, "--scenarios", scenario, "--methods", "M0,M1,M2", "--repeats", "1", "--enable-llm",
                    "--model-base-url", "http://model.invalid/v1", "--model", "offline-fixture", *target_args])
                with patch("eval.run.ROOT", root), patch("eval.run.freeze_sources", return_value=domains["application-agent"]["source_sha256"]), patch("eval.run.check_sources"), \
                     patch("eval.run.DockerTarget.from_file", return_value=target), \
                     patch("eval.run.create_transport", return_value=transport), patch("eval.run.inject", AsyncMock(return_value={"started_monotonic": 1, "target_proof": {"compose_sha256": {}, "domains": domains}})), \
                     patch("eval.run.HypothesisEngine", Hypothesis), patch("eval.run.IncidentCoordinator", Engine), \
                     patch("eval.run.ContinuousObserver", Observer), patch("eval.run.asyncio.sleep", fast_sleep), patch("builtins.print"):
                    self.assertEqual(await runner.run(args), int(scenario == "H00" and act_status is not None))
                models = [options for kind, options in captures if kind == "model"]
                engines = [options for kind, options in captures if kind == "engine"]
                self.assertEqual([row["enabled"] for row in models], [False, True, True])
                self.assertTrue(all(row["max_calls"] == 40 and row["token_budget"] == 65536 and row["max_output_tokens"] == 768 for row in models))
                self.assertTrue(all(row["task_budget"] == 40 and row["approval_issuer"] is transport.issue_approval for row in engines))
                self.assertIn("step_selector", engines[1]); self.assertNotIn("step_selector", engines[2])
                self.assertEqual([row[0] for row in observed], [target.order_url if target_args else "http://127.0.0.1:8088"]*3)
                self.assertTrue(all(row[1]["seed"] == 101 for row in observed))
                self.assertTrue(all(row[1]["healthy_control"] == (scenario == "H00") for row in observed))
                if scenario == "H00":
                    rows = json.loads((root / "results/results.json").read_text(encoding="utf-8"))
                    self.assertTrue(all(row["control_passed"] == (act_status is None) for row in rows))
                    self.assertTrue(all(row["modification_attempts"] == int(act_status is not None) for row in rows))
                    self.assertTrue(all(row["continuous_recovery_confirmed"] is False for row in rows))
                self.assertEqual(json.loads((root / "results/experiment.json").read_text(encoding="utf-8"))["continuous_workload"]["requests_per_second"], 1)
                transport.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
