"""Prepare an IFC metadata check; --execute explicitly runs the caller's own AIP identity."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aic import validate_aic_format


def payload(target_aic):
    if not validate_aic_format(target_aic)[0]:
        raise ValueError("target_aic must be a registered AIC")
    identifier = "onboarding-" + uuid.uuid4().hex
    return dict(schema_version="ifc/1.0", incident_id=identifier, logical_task_id=identifier + ":check",
                kind="observe", tool="aip.onboarding.check", args=dict(target_aic=target_aic, deep=False),
                budget=dict(deadline_ms=30000))


def configuration(path, output, service_aic):
    if not validate_aic_format(service_aic)[0]:
        raise ValueError("service_aic must be the discovered onboarding identity")
    source = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    # Copy only the caller's identity and public protocol locations.
    leader = {key: source["leader"][key] for key in ("aic", "endpoint", "cert", "key")}
    for key in ("cert", "key"):
        value = Path(leader[key])
        leader[key] = str(value if value.is_absolute() else Path(path).resolve().parent / value)
    trust = Path(source["trust_bundle"])
    return dict(leader=leader, trust_bundle=str(trust if trust.is_absolute() else Path(path).resolve().parent / trust),
        discovery_url=source["discovery_url"], mq_auth_url=source["mq_auth_url"],
        skills={"onboarding": "aip.onboarding.check"}, trusted_participant_aics={"onboarding": [service_aic]},
        initial_participant_aics={"onboarding": service_aic}, automatic_takeover=False,
        term_journal_path=str(Path(output).resolve() / "terms.sqlite"), term_namespace="onboarding-only")


async def execute(config, request, output):
    from incident.wutong_transport import WutongTransport
    transport = WutongTransport(config, output)
    try:
        await transport.start()
        return await transport.call(request)
    finally:
        await transport.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-aic", required=True)
    parser.add_argument("--service-aic")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    request = payload(args.target_aic)
    if not args.execute:
        print(json.dumps(dict(status="PREPARED_NOT_SENT", payload=request), ensure_ascii=False, indent=2))
        return 0
    if not args.config or not args.service_aic or not args.output:
        parser.error("execution requires --config, --service-aic and a new --output")
    if args.output.exists():
        parser.error("keep prior logs; use a new output directory")
    config = configuration(args.config, args.output, args.service_aic)
    from eval.platform_resume_experiment import coordinator_lock
    with coordinator_lock(config["leader"]["aic"]):
        result = asyncio.run(execute(config, request, args.output))
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
