"""Prepare one application Partner ACS using confirmed platform endpoint data.

Writes only a local candidate. It does not register, submit, or contact anything.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from validate_acs import validate_document

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mq-endpoint", required=True, help="Confirmed amqps://broker:port/vhost?inbox=inbox_{AIC}")
    parser.add_argument("--provider-file", type=Path, help="Real provider JSON; omitting leaves {} and fails the observed live platform non-empty-provider rule")
    parser.add_argument("--output", type=Path, default=HERE / "acs" / "application.registration.json")
    parser.add_argument("--require-official-schema", action="store_true")
    args = parser.parse_args()
    document = json.loads((HERE / "acs" / "application.draft.json").read_text(encoding="utf-8"))
    document["lastModifiedTime"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    document["provider"] = json.loads(args.provider_file.read_text(encoding="utf-8-sig")) if args.provider_file else {}
    if not isinstance(document["provider"], dict):
        parser.error("provider-file must contain a provider object")
    if "{AIC}" not in args.mq_endpoint:
        parser.error("Initial registration endpoint must preserve the official {AIC} placeholder")
    document["endPoints"] = [{"url": args.mq_endpoint, "transport": "AMQP", "security": [{"mtls": []}]}]
    document["capabilities"]["messageQueue"] = ["amqp:0.9.1"]
    document["securitySchemes"]["mtls"]["description"] = "使用平台认可的 AIC clientAuth 证书通过 AMQPS EXTERNAL 认证，接收 Inbox 邀请并参与 AIP 群组。"
    result = validate_document(document, submission=True)
    # This builder prepares an inbound Partner for this pilot, so enforce its
    # public Inbox runtime policy explicitly, separately from Registry rules.
    if result["errors"] or result["live_admission_blockers"] or result["local_runtime_policy_blockers"]:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1
    if args.require_official_schema and result["official_registry_schema_valid"] is None:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2
    if args.output.exists():
        parser.error("output already exists; use a new path to preserve earlier registration material")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "state": "local_registration_candidate_only", "validation": result}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
