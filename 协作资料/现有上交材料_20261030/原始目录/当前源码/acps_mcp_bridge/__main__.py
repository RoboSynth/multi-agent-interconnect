"""Start a gateway, execute a local contract probe, or generate ACS from tools/list."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from . import ApprovalAuthority, Bridge, McpStdioClient, Policy, ServerConfig
from .acs_mapper import map_acs, validate_acs
from .audit import AmpAuditSink


async def run(args):
    from acps_sdk.aip.resumable import OperationLedger
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    def local_path(value):
        path = Path(value)
        return path if path.is_absolute() else config_path.parent / path
    # Called only inside the resource-domain process. The coordinator must not
    # import these environment files into its own process.
    for env_file in config.get("env_files", []):
        for line in local_path(env_file).read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name and not name.lstrip().startswith("#"):
                os.environ[name.strip()] = value.strip().strip('"').strip("'")
    approval = ApprovalAuthority(os.environ[config["approval_secret_env"]]) if config.get("approval_secret_env") else None
    policy = Policy.load(local_path(config["policy"]), allowed_callers=config["allowed_callers"],
                         approval_verifier=approval.verify if approval else None)
    ledger = OperationLedger(local_path(config["ledger_path"]), config.get("ledger_domain", policy.domain))
    secret_values = [os.environ[name] for server in config["servers"].values()
                     for name in server.get("env_names", []) if name in os.environ]
    platform = config.get("platform")
    audit = AmpAuditSink.from_certificate(local_path(config["audit_path"]), config["executor_aic"],
                 platform["cert"], platform["key"]) if platform else None
    from domains.ops.guard import labeled_container
    async with AsyncExitStack() as stack:
        clients = {}
        for name, server in config["servers"].items():
            clients[name] = await stack.enter_async_context(McpStdioClient(ServerConfig(**server)))
        bridge = await Bridge(policy, clients, ledger, config["executor_aic"], audit=audit,
                               resource_guard=labeled_container, secret_values=secret_values).initialize()
        if args.acs_base:
            document = map_acs(json.loads(Path(args.acs_base).read_text(encoding="utf-8-sig")), policy, bridge.inventory)
            check = validate_acs(document)
            if not check["sdk_schema_valid"] or not check["official_registry_schema_valid"]:
                raise ValueError("Generated ACS did not pass official offline schema validation")
            print(json.dumps(document, ensure_ascii=False, indent=2))
        elif args.payload:
            if not args.caller_aic:
                raise ValueError("Local task probes require --caller-aic")
            result = await bridge.execute(json.loads(Path(args.payload).read_text(encoding="utf-8-sig")), args.caller_aic)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "ok" else 1
        else:
            if not platform:
                raise ValueError("A real platform certificate/endpoint config is required to serve AIP")
            from .platform import serve_platform
            await serve_platform(bridge, platform)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--payload")
    parser.add_argument("--caller-aic")
    parser.add_argument("--acs-base")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
