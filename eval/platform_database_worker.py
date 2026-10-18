"""E1-only formal database worker. Default checks files; --serve is explicit."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import ssl
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/srv")
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
# An E1 bundle adds only these two reviewed modules alongside the unchanged
# image packages. /srv remains the source of ordinary business/SDK behavior.
import acps_mcp_bridge
import incident
for package in (acps_mcp_bridge, incident):
    extra = str(ROOT / package.__name__)
    if extra not in package.__path__:
        package.__path__.insert(0, extra)

from acps_mcp_bridge import ApprovalAuthority, McpStdioClient, Policy, ServerConfig
from acps_mcp_bridge.experiment import DurableTrace, ExperimentBridge, ExperimentSpec, TracedSystemEmitter
from acps_mcp_bridge.platform import BridgeGroupRuntime
from acps_sdk.aip.resumable import OperationLedger
from incident.amp_setup import AmpRuntime
from incident.local_transport import environment_file
from incident.local_worker import CountedMcpClient


BUNDLE_SOURCES = {"source/eval/platform_database_worker.py", "source/acps_mcp_bridge/experiment.py", "source/incident/local_worker.py"}


def verify_bundle(path, expected_sha, experiment_id):
    path = Path(path).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("experiment bundle manifest SHA mismatch")
    manifest = json.loads(raw)
    if (manifest.get("schema_version") != "e1-worker-bundle/1" or manifest.get("experiment_id") != experiment_id
            or set(manifest.get("source_sha256", {})) != BUNDLE_SOURCES
            or set(manifest.get("experiment_sha256", {})) != {"primary.json", "backup.json"}):
        raise ValueError("experiment bundle scope mismatch")
    for name, digest in {**manifest["source_sha256"], **manifest["experiment_sha256"]}.items():
        target = path.parent / name
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("experiment bundle bytes changed")
    return manifest


def inspect_configuration(args):
    config_path, experiment_path = Path(args.config).resolve(), Path(args.experiment).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    experiment = ExperimentSpec.from_document(json.loads(experiment_path.read_text(encoding="utf-8-sig")),
        experiment_id=args.experiment_id, executor_aic=config["executor_aic"])
    if len(config.get("allowed_callers", [])) != 1 or not config.get("servers") or not config.get("platform"):
        raise ValueError("one formal coordinator and a resource-domain platform config are required")
    manifest = None
    if args.bundle_manifest or args.bundle_sha:
        if not args.bundle_manifest or not args.bundle_sha:
            raise ValueError("both bundle manifest and SHA required")
        manifest = verify_bundle(args.bundle_manifest, args.bundle_sha, args.experiment_id)
        bundle = Path(args.bundle_manifest).resolve().parent
        role_file = bundle / (experiment.worker_role + ".json")
        if experiment_path != role_file:
            raise ValueError("experiment config is outside its exact role bundle")
    if args.serve:
        if manifest is None:
            raise ValueError("serving requires a frozen E1 bundle manifest and SHA")
        import acps_mcp_bridge.experiment as hooks
        import incident.local_worker as counted
        actual = {"source/eval/platform_database_worker.py": Path(__file__).resolve(),
                  "source/acps_mcp_bridge/experiment.py": Path(hooks.__file__).resolve(),
                  "source/incident/local_worker.py": Path(counted.__file__).resolve()}
        if any(path != bundle / name for name, path in actual.items()):
            raise ValueError("actual E1 import paths differ from the frozen bundle")
    return config_path, config, experiment


async def serve(args, config_path, config, experiment):
    def local(value):
        path = Path(value)
        return path if path.is_absolute() else config_path.parent / path
    for filename in config.get("env_files", []):
        os.environ.update(environment_file(local(filename)))
    approval = ApprovalAuthority(os.environ[config["approval_secret_env"]]) if config.get("approval_secret_env") else None
    policy = Policy.load(local(config["policy"]), allowed_callers=config["allowed_callers"],
                         approval_verifier=approval.verify if approval else None)
    if policy.domain != "db":
        raise ValueError("E1 experiment worker is database-only")
    ledger = OperationLedger(local(config["ledger_path"]), config.get("ledger_domain", policy.domain))
    platform = config["platform"]
    amp = AmpRuntime(platform["amp_directory"], platform["name"], config["executor_aic"],
                     cert=platform["cert"], key=platform["key"])
    trace = DurableTrace(args.trace, experiment, config["executor_aic"])
    current = ContextVar("formal_e1_payload", default=None)
    counting_amp = SimpleNamespace(system=TracedSystemEmitter(amp.system, trace))
    context = ssl.create_default_context(cafile=platform["trust_bundle"])
    context.load_cert_chain(platform["cert"], platform["key"])
    from integration import wutong_smoke as transport
    endpoint = transport.parse_amqp_endpoint_url(platform["endpoint"], aic=config["executor_aic"])
    async with AsyncExitStack() as stack:
        clients = {}
        for name, server in config["servers"].items():
            raw = await stack.enter_async_context(McpStdioClient(ServerConfig(**server)))
            clients[name] = CountedMcpClient(raw, name, policy, counting_amp, current, transport="wutong-amqps")
        secrets = [os.environ[name] for server in config["servers"].values()
                   for name in server.get("env_names", []) if name in os.environ]
        bridge = await ExperimentBridge(policy, clients, ledger, config["executor_aic"], audit=amp.audit_event,
            experiment=experiment, current_payload=current, trace=trace, secret_values=secrets).initialize()
        runtime = BridgeGroupRuntime(bridge=bridge, amp=amp, leader_aic=config["executor_aic"],
            allowed_peer_aic=config["allowed_callers"][0], record=lambda *a, **k: None,
            ssl_context=context, identity_binding_enabled=True,
            rabbitmq_config={"host": endpoint.host, "port": endpoint.port, "vhost": endpoint.vhost,
                             "user": None, "password": None, "auth_service_url": platform["mq_auth_url"]})
        try:
            trace.append({"event": "experiment_worker_start", "incident_id": experiment.incident_id,
                          "worker_role": experiment.worker_role, "armed": experiment.armed,
                          "bundle_manifest_sha256": args.bundle_sha})
            await amp.start()
            await runtime.start_inbound()
            await asyncio.Event().wait()
        finally:
            try:
                await transport.close_runtime(runtime, 15, lambda *a, **k: None)
            finally:
                await amp.close()


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--config", required=True)
    value.add_argument("--experiment", required=True)
    value.add_argument("--experiment-id", required=True)
    value.add_argument("--trace", required=True)
    value.add_argument("--bundle-manifest")
    value.add_argument("--bundle-sha")
    value.add_argument("--serve", action="store_true")
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    config_path, config, experiment = inspect_configuration(args)
    if not args.serve:
        print(json.dumps(dict(status="E1_WORKER_FILES_VALIDATED_ONLY", experiment_id=experiment.experiment_id,
            worker_role=experiment.worker_role, armed=experiment.armed, resource_or_network_actions=0)))
        return 0
    asyncio.run(serve(args, config_path, config, experiment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
