"""NEW7 six-domain healthy-only acceptance; default is offline JSON validation.

No participant, model, fault injector or resource-restore process is started.
The explicit --execute path opens the sole coordinator, queries only trusted
participants, checks a real 30-second business window, and closes its own group.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import uuid

ROLES = ("application", "database", "database-backup", "ops", "onboarding", "verification")
SKILLS = {"application": "incident.application", "database": "db.observe", "ops": "ops.observe",
          "verification": "incident.verification", "onboarding": "aip.onboarding.check"}
CLEANUP_FAILURES = {"dissolve_notify_failed", "group_acl_delete_failed", "queue_cleanup_failed", "exchange_cleanup_failed"}
RESOURCE_NAMES = {"DATABASE_URL", "DATABASE_URI", "PGADMINPASSWORD", "POSTGRES_PASSWORD", "ORDERS_DB_PASSWORD",
                  "BRIDGE_DB_PASSWORD", "APP_ADMIN_TOKEN", "OPS_SUPERVISOR_TOKEN", "DOCKER_HOST",
                  "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY", "INCIDENT_LLM_API_KEY"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def within(value, root):
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Configuration references must remain inside the selected checkout")
    return path


def has_resource_material(value):
    if isinstance(value, dict):
        return any(str(key).upper() in RESOURCE_NAMES or has_resource_material(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_resource_material(item) for item in value)
    return isinstance(value, str) and bool(re.search(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:postgres(?:ql)?|amqps?|https?)://[^\s/:@]+:[^\s/@]+@", value, re.I))


def prepare_inputs(root, config_path, deployment_path):
    root = Path(root).resolve()
    config_path, deployment_path = within(config_path, root), within(deployment_path, root)
    manifest, config = load(deployment_path), load(config_path)
    if (manifest.get("mode") != "seven" or manifest.get("wsl_distro") is not None
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", manifest.get("project", ""))):
        raise ValueError("Expected a native-Linux seven-identity deployment manifest")
    if within(manifest["coordinator_config"], root) != config_path:
        raise ValueError("Coordinator configuration differs from the deployment manifest")
    if config.get("mode") != "wutong-amqps" or config.get("skills") != SKILLS:
        raise ValueError("Expected the exact five NEW7 role skills")
    if config.get("llm_enabled", False) is not False:
        raise ValueError("Healthy acceptance does not enable a model")
    if has_resource_material(config):
        raise ValueError("Resource credentials do not belong in coordinator configuration")
    domain_root, domains, identities = config_path.parent.parent, {}, {"coordinator": config["leader"]["aic"]}
    for role in ROLES:
        bridge = role in {"database", "database-backup", "ops"}
        row = load(domain_root / role / ("bridge.json" if bridge else "config.json"))
        identity = row["platform"] if bridge else row
        domains[role + "-agent"] = identity
        identities[role] = identity["aic"]
    if len(set(identities.values())) != 7 or any(not isinstance(aic, str) or not aic for aic in identities.values()):
        raise ValueError("Expected exactly seven distinct NEW7 AICs")
    trusted = config.get("trusted_participant_aics", {})
    expected = {role: [identities[role]] for role in SKILLS}
    expected["database"].append(identities["database-backup"])
    if set(trusted) != set(expected) or any(set(trusted[role]) != set(aics) for role, aics in expected.items()):
        raise ValueError("Trusted participants differ from the six mounted domains")
    if config.get("initial_participant_aics", {}).get("database") != identities["database"]:
        raise ValueError("Initial database must be this deployment's primary identity")
    for row in [config["leader"], *domains.values()]:
        endpoint = urlsplit(row["endpoint"])
        if endpoint.scheme != "amqps" or not endpoint.hostname or endpoint.username or endpoint.password:
            raise ValueError("Identity Inbox endpoint must be credential-free AMQPS")
    sys.path.insert(0, str(root))
    from eval.targets import validate_platform_bindings
    validate_platform_bindings(config, domains, project=manifest["project"])
    # The healthy path never issues approvals; do not read that capability file.
    config = deepcopy(config)
    config.pop("approval_env_file", None)
    config["automatic_takeover"] = False
    return dict(root=root, config=config, domains=domains, identities=identities, project=manifest["project"],
                input_sha256={"coordinator_config": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                              "deployment_manifest": hashlib.sha256(deployment_path.read_bytes()).hexdigest()})


def check_environment(environment):
    forbidden = [name for name in environment if name.upper().startswith("PG") or name.upper() in RESOURCE_NAMES]
    if forbidden:
        raise ValueError("Remove resource/model credential and remote-Docker variables from this coordinator process")


def normal_tasks(identities):
    return [("application", "observe", "application.status", {}, 15000),
            ("database", "observe", "db.read_only_status", {}, 15000),
            ("database-backup", "observe", "db.read_only_status", {}, 15000),
            ("ops", "observe", "ops.route_status", {}, 15000),
            ("onboarding", "observe", "aip.onboarding.check", {"target_aic": identities["application"]}, 30000),
            ("verification", "verify", "incident.verification",
             {"original_request_key": None, "original_request_unknown": False}, 60000)]


def guard_payload(payload, target, identities):
    if target not in {identities[role] for role in ROLES}:
        raise ValueError("Healthy task target is outside this team's six domains")
    if set(payload) != {"schema_version", "incident_id", "logical_task_id", "kind", "tool", "args", "budget"}:
        raise ValueError("Healthy tasks cannot carry operation, fence or approval fields")
    expected = {("describe", "describe"): {}}
    expected.update({(kind, tool): args for _, kind, tool, args, _ in normal_tasks(identities)})
    if (payload["kind"], payload["tool"]) not in expected or payload["args"] != expected[(payload["kind"], payload["tool"])]:
        raise ValueError("Only the declared healthy describe, observation and verification tasks are allowed")


def checked_facts(role, product, identities):
    facts = {row["key"]: row["value"] for row in product.get("facts", [])}
    if role == "application" and facts.get("application_reachable") is not True:
        raise ValueError("Application is not reachable")
    if role in {"database", "database-backup"} and facts.get("read_only") is not False:
        raise ValueError("Database is not writable")
    if role == "ops" and facts.get("route_version") != "v2":
        raise ValueError("Public route is not v2")
    if role == "onboarding":
        report = facts.get("onboarding_report", {})
        if not (report.get("target_aic") == identities["application"] and report.get("passed") is True
                and report.get("active_target_probe") is False):
            raise ValueError("Public metadata check failed")
    if role == "verification":
        from deploy.verify import healthy_window
        observed = facts.get("order_observation", {})
        if (facts.get("business_recovered") is not True or facts.get("original_request_resolution") != "not_required"
                or not healthy_window(observed)):
            raise ValueError("Real 30-second / 10-workflow healthy window failed")
        return {key: observed[key] for key in ("duration_seconds", "requests", "success", "failed", "unknown",
                                              "completed_workflows", "unresolved_intents", "passed")} | {
                                                  "pending_intents": len(observed["state"]["pending"])}
    return None


class CleanupWarnings(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.events = []

    def emit(self, record):
        event = re.search(r"event=([A-Za-z0-9_]+)", record.getMessage())
        if event and event[1] in CLEANUP_FAILURES:
            self.events.append(dict(event=event[1], logger=record.name))


async def execute(prepared, output, *, transport_factory=None, discover=None):
    root, config, identities = prepared["root"], prepared["config"], prepared["identities"]
    sys.path[:0] = [str(root), str(root / "vendor/ACPs-community/acps-sdk")]
    if transport_factory is None:
        from incident.wutong_transport import WutongTransport
        transport_factory = WutongTransport
    if discover is None:
        from incident.selection import discover_candidates
        discover = discover_candidates
    from eval.targets import validate_platform_bindings
    output = within(output, root)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    private_output = root / "runtime/private" / ("cloud-health-" + uuid.uuid4().hex)
    report = dict(status="failed", task_phase_status="failed", close_status="not_started",
                  started_at=datetime.now(timezone.utc).isoformat(), identities=identities,
                  input_sha256=prepared["input_sha256"], confirmed_domains=[], completed_products=[],
                  model_calls=0, act_tasks=0, fault_injections=0, resource_credential_count=0,
                  private_runtime_directory=str(private_output.relative_to(root)))
    warnings = CleanupWarnings()
    logging.getLogger().addHandler(warnings)
    transport, owned = None, None
    try:
        transport = transport_factory(config, private_output)
        original_send = transport._send

        async def send(payload, target):
            guard_payload(payload, target, identities)
            product = await original_send(payload, target)
            report["completed_products"].append(dict(kind=payload["kind"], tool=payload["tool"],
                target_aic=target, logical_task_id=payload["logical_task_id"], status=product.get("status")))
            if product.get("status") != "ok":
                raise RuntimeError("Healthy participant product is not successful")
            return product

        async def own_candidates(role, skill):
            candidates = await discover(config["discovery_url"], skill, record=lambda *args, **kwargs: None)
            allowed = set(config["trusted_participant_aics"][role])
            return [row for row in candidates if row.get("aic") in allowed]

        transport._send, transport._discover_candidates = send, own_candidates
        await asyncio.wait_for(transport.start(), 240)
        owned = transport.session.session_id
        if set(transport.runtime.group_sessions) != {owned}:
            raise RuntimeError("Unexpected group ownership")
        expected_selected = {role: identities[role] for role in SKILLS}
        if transport.selected != expected_selected:
            raise RuntimeError("Selected domains differ from the cloud deployment")
        validate_platform_bindings(config, prepared["domains"], selected=transport.selected,
                                   descriptions=transport.descriptions, project=prepared["project"])
        candidates = await transport._discover_candidates("database", "db.observe")
        backup, description = await transport._select_participant("database",
            [row for row in candidates if row["aic"] == identities["database-backup"]],
            "db.read_only_status", initial=False)
        if backup["aic"] != identities["database-backup"] or description["executor_aic"] != backup["aic"]:
            raise RuntimeError("Backup description does not match its registered identity")
        if transport.selected != expected_selected:
            raise RuntimeError("Healthy backup check changed the selected primary")
        report["confirmed_domains"] = [dict(role=role, aic=identities[role]) for role in ROLES]
        incident_id = "cloud-healthy-" + uuid.uuid4().hex
        for role, kind, tool, arguments, budget in normal_tasks(identities):
            payload = dict(schema_version="ifc/1.0", incident_id=incident_id, logical_task_id="lt-" + uuid.uuid4().hex,
                           kind=kind, tool=tool, args=arguments, budget=dict(deadline_ms=budget))
            product = await (transport._send(payload, backup["aic"]) if role == "database-backup" else transport.call(payload))
            observed = checked_facts(role, product, identities)
            if observed is not None:
                report["healthy_business"] = observed
        if len(report["completed_products"]) != 12:
            raise RuntimeError("Expected six descriptions plus six normal tasks")
        if transport.journal.list_tasks(in_flight_only=True) or transport.runtime._pending_invitations:
            raise RuntimeError("Tasks or invitations remain in flight")
        report.update(task_phase_status="completed", journal_in_flight_before_close=0,
                      owned_group=dict(session_id=owned, group_id=transport.session.group_id,
                                       owner_aic=identities["coordinator"]))
    except Exception as error:
        report["error_class"] = type(error).__name__
    finally:
        if transport is not None:
            try:
                if owned is None and transport.session is not None:
                    owned = transport.session.session_id
                sessions = set(transport.runtime.group_sessions) if transport.runtime else set()
                inbound = getattr(transport.runtime, "_inbound_groups", {}) if transport.runtime else {}
                if sessions - ({owned} if owned else set()) or inbound:
                    raise RuntimeError("Unexpected group ownership; preserve runtime for inspection")
                await transport.close()
                runtime = transport.runtime
                state = getattr(getattr(transport.session, "leader_mq_client", None), "_state", None)
                checks = dict(no_group_sessions=not runtime or not runtime.group_sessions,
                    no_inbound_groups=not runtime or not runtime._inbound_groups,
                    inbox_consumer_cancelled=not runtime or runtime._inbox_consumer_tag is None,
                    connection_closed=not runtime or runtime._connection is None or runtime._connection.is_closed,
                    owned_group_disconnected=owned is None or str(getattr(state, "value", state)).casefold() == "disconnected",
                    no_sdk_cleanup_warning_events=not warnings.events)
                report["close_checks"] = checks
                report["close_status"] = "completed" if all(checks.values()) else "failed"
            except Exception as error:
                report.update(close_status="failed", close_error_class=type(error).__name__)
        logging.getLogger().removeHandler(warnings)
        report["cleanup_warning_events"] = warnings.events
        report["status"] = "completed" if report["task_phase_status"] == report["close_status"] == "completed" else "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["scope"] = "Normal six-domain AMQPS and H00 only; not recovery, takeover, uptime or platform ingestion"
        report["close_evidence_limit"] = "SDK returned, local state and captured cleanup warnings; no independent broker/ACL inventory"
        save(output / "results.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("/opt/incident-pilot"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lease-directory", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        prepared = prepare_inputs(args.project_root, args.config, args.deployment)
        if not args.execute:
            print(json.dumps(dict(status="offline_configuration_validated_not_executed", identities=prepared["identities"],
                                  expected_descriptions=6, expected_normal_tasks=6,
                                  network_attempted=False, processes_started=False)))
            return 0
        check_environment(os.environ)
        os.umask(0o077)
        from ops.aic_lease import AicLease, DEFAULT_DIRECTORY
        directory = args.lease_directory or DEFAULT_DIRECTORY
        with AicLease([prepared["identities"]["coordinator"]], purpose="cloud-healthy-coordinator", directory=directory) as lease:
            result = asyncio.run(execute(prepared, args.output))
            if result["close_status"] != "completed":
                lease.quarantine("Cloud healthy coordinator cleanup was not confirmed",
                                 evidence=dict(output=str(args.output), close_status=result["close_status"]))
        print(json.dumps({key: result[key] for key in ("status", "task_phase_status", "close_status")} | {"output": str(args.output)}))
        return 0 if result["status"] == "completed" else 1
    except Exception as error:
        # Exception text/provider payloads may contain sensitive material.
        print(json.dumps(dict(status="failed", error_class=type(error).__name__)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
