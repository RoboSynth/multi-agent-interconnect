"""Validate against the pinned SDK and, when installed, Registry JSON Schema.

This is an offline check. It never logs in, registers an agent, generates a key,
or contacts the platform. Pinned official structure, observed live admission rules,
SDK compatibility, and this pilot's Inbox runtime policy are reported separately.
The known live rules are incomplete; a pass does not prove platform approval,
issued identity/certificates, or runtime reachability.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "ACPs-community"
sys.path.insert(0, str(VENDOR / "acps-sdk"))

from acps_sdk.acs import AgentCapabilitySpec  # noqa: E402

SCHEMA_PATH = VENDOR / "registry-server" / "app" / "agent" / "acsSchema.json"
LIVE_ADMISSION_RULE = "registry-admission-2.0-static-format-llm-whole-acs"


def observed_live_admission(document: dict, endpoints: list) -> list[str]:
    """Replay two observed rejection conditions, not the unknown full policy.

    An absolute URL is only a basic endpoint candidate, not proof that the live
    server will consider it valid, owned, deployed, or semantically acceptable.
    """
    blockers = []
    provider = document.get("provider")
    if not isinstance(provider, dict) or not provider:
        blockers.append("ACS provider must be a non-empty object")

    def absolute_url(value, schemes):
        if not isinstance(value, str):
            return False
        try:
            parsed = urlparse(value)
            return parsed.scheme in schemes and bool(parsed.hostname)
        except ValueError:
            return False

    candidate = any(isinstance(endpoint, dict) and absolute_url(
        endpoint.get("url"), {"http", "https", "grpc", "grpcs", "amqp", "amqps"}) for endpoint in endpoints)
    web_app = absolute_url(document.get("webAppUrl"), {"http", "https"})
    if not candidate and not web_app:
        blockers.append("At least one valid Endpoint or webAppUrl is required")
    return blockers


def validate_document(document: dict, submission: bool = False) -> dict:
    sdk_errors: list[str] = []
    official_errors: list[str] = []
    runtime_blockers: list[str] = []
    warnings: list[str] = []
    try:
        AgentCapabilitySpec.from_dict(document)
        sdk_ok = True
    except Exception as exc:
        sdk_ok = False
        sdk_errors.append(f"Pinned SDK compatibility: {exc}")

    official_schema_ok: bool | None = None
    if importlib.util.find_spec("jsonschema"):
        from jsonschema import Draft202012Validator

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        # Match registry-server/app/utils/acs.py: jsonschema validation without
        # an optional FormatChecker. Extra local policies must not become rules.
        validator = Draft202012Validator(schema)
        schema_errors = list(validator.iter_errors(document))
        official_schema_ok = not schema_errors
        official_errors.extend(f"Registry schema {error.json_path}: {error.message}" for error in schema_errors)
    else:
        warnings.append("jsonschema is not installed: full Registry JSON Schema validation was NOT run.")

    # Registry has endpoint security checks in addition to its JSON Schema.
    schemes = document.get("securitySchemes") or {}
    mtls_names = {name for name, spec in schemes.items()
                  if isinstance(spec, dict) and spec.get("type") == "mutualTLS"} if isinstance(schemes, dict) else set()
    endpoints = document.get("endPoints") or []
    if not isinstance(endpoints, list):
        endpoints = []  # The official JSON Schema reports this type error.
    transport_schemes = {
        "AMQP": {"amqp", "amqps"}, "GRPC": {"grpc", "grpcs", "http", "https"},
        "HTTP_JSON": {"http", "https"}, "JSONRPC": {"http", "https"}, "REST": {"http", "https"},
    }
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict):
            continue  # The official JSON Schema reports this type error.
        url = endpoint.get("url", "")
        parsed = urlparse(url if isinstance(url, str) else "")
        if not parsed.scheme or not parsed.netloc:
            official_errors.append(f"endPoints[{index}]: Registry requires an absolute endpoint URL")
        allowed_schemes = transport_schemes.get(str(endpoint.get("transport", "")).upper())
        if allowed_schemes and parsed.scheme not in allowed_schemes:
            official_errors.append(f"endPoints[{index}]: Registry requires URL scheme to match transport")
        security = endpoint.get("security") or []
        if not isinstance(security, list) or not any(isinstance(requirement, dict) and set(requirement) & mtls_names for requirement in security):
            official_errors.append(f"endPoints[{index}]: Registry requires mutualTLS security")
        if endpoint.get("transport") == "AMQP":
            if parsed.scheme != "amqps":
                runtime_blockers.append(f"endPoints[{index}]: this pilot's public MQ runtime policy requires amqps")
            inbox = parse_qs(parsed.query).get("inbox", [])
            expected = "inbox_" + (document.get("aic") or "{AIC}")
            if inbox != [expected]:
                runtime_blockers.append(f"endPoints[{index}]: this pilot's Inbox runtime requires inbox={expected}")
            if parsed.username or parsed.password:
                runtime_blockers.append(f"endPoints[{index}]: this pilot does not publish broker credentials in ACS")
            host = parsed.hostname or ""
            if host in {"localhost", "", "0.0.0.0"} or host.endswith((".example.com", ".invalid", ".localhost")):
                runtime_blockers.append(f"endPoints[{index}]: local/placeholder broker is not ready for this pilot's public platform run")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address and not address.is_global:
                runtime_blockers.append(f"endPoints[{index}]: private/loopback IP is not a verified public broker for this pilot")

    if document.get("protocolVersion") != "02.02":
        runtime_blockers.append("this pilot's pinned runtime supports protocolVersion 02.02")
    if not document.get("provider"):
        warnings.append("provider is empty: allowed by the pinned official schema but rejected by the observed live platform admission rule")
    if not endpoints:
        warnings.append("no inbound endpoint is declared: allowed by the pinned official schema; the observed live platform additionally requires an Endpoint or webAppUrl")
    if not document.get("skills"):
        warnings.append("no published skill: allowed by the official schema, but no business capability is advertised")

    errors = official_errors + sdk_errors
    official_structure_ok = None if official_schema_ok is None else not official_errors
    live_blockers = observed_live_admission(document, endpoints)

    return {
        "sdk_schema_valid": sdk_ok,
        "official_registry_schema_valid": official_schema_ok,
        "official_endpoint_checks_valid": not any(error.startswith("endPoints[") for error in official_errors),
        "official_submission_structure_valid": official_structure_ok,
        "official_submission_structure_errors": official_errors,
        "sdk_compatibility_errors": sdk_errors,
        "errors": errors,
        "live_admission_blockers": live_blockers,
        "live_admission_known_conditions_satisfied": not live_blockers,
        "live_admission_rule_id": LIVE_ADMISSION_RULE,
        "live_admission_rule_source": {
            "kind": "observed platform rejection comments, not pinned schema",
            "platform": "https://wt.ioa.pub/registry/",
            "observations": ["integration/two-agent/leader.rejection-observation.json",
                             "integration/two-agent/partner.rejection-observation.json"],
            "policy_complete": False,
            "scope": "non-empty provider and basic Endpoint/webAppUrl presence only; complete live format, semantic, identity, ownership, and service-validity rules are unknown",
        },
        # Compatibility keys combine the known submission gates, not runtime.
        "submission_blockers": official_errors + live_blockers,
        "submission_fields_complete": official_structure_ok is True and not live_blockers,
        "compatibility_key_scope": "submission_blockers/submission_fields_complete cover pinned official structure plus two observed live admission conditions only; not the full live policy, account authorization, approval, identity, or runtime readiness",
        "local_runtime_policy_blockers": runtime_blockers,
        "local_runtime_policy_satisfied": sdk_ok and not runtime_blockers,
        "local_runtime_policy_scope": "this pilot's pinned SDK and public AMQPS Inbox route; not Registry submission requirements or proof of a live service",
        "inbound_service_declared": bool(endpoints),
        "warnings": warnings,
        "offline_structure_valid": not errors,
        "runtime_reachability_tested": False,
        "platform_registration_tested": False,
        "submission_mode": submission,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acs_file", type=Path)
    parser.add_argument("--submission", action="store_true", help="Fail on pinned official structure errors or known observed live admission blockers; full live rules remain unknown")
    parser.add_argument("--require-official-schema", action="store_true", help="Fail if jsonschema is unavailable")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("output already exists; choose a new path to preserve prior evidence")
    document = json.loads(args.acs_file.read_text(encoding="utf-8-sig"))
    result = validate_document(document, args.submission)
    result["file"] = str(args.acs_file.resolve())
    encoded = json.dumps(result, ensure_ascii=True, indent=2)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    blocking_errors = result["submission_blockers"] if args.submission else result["errors"]
    if blocking_errors:
        return 1
    if args.require_official_schema and result["official_registry_schema_valid"] is None:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
