"""Read-only passive checks for the two exact recorded group names; no deletes."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
import time
from urllib.parse import urlparse
import urllib.request

import close_owned_group as cleanup
import httpx
from aiormq.exceptions import ChannelNotFoundEntity
from acps_sdk.aip.aip_group_leader import GroupLeaderMqClient
from acps_sdk.aip.aip_group_runtime import (
    build_group_exchange_name, build_group_queue_name, parse_amqp_endpoint_url,
)

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "readonly-probe-1"


async def main():
    OUTPUT.mkdir(exist_ok=False)
    scope, plan, config = cleanup.scope()
    report = {"schema_version": "owned-group-readonly-probe/1", "started_at": cleanup.now(),
        "source_scope_sha256": cleanup.sha(HERE / "prepared-v2.json"),
        "effects": ["connect and close original certificate transport", "AMQP passive existence checks",
                    "two read-only health GETs to the original ACL endpoint with per-client proxy behavior"],
        "new_resources": 0, "consumers": 0, "published_messages": 0, "delete_requests": 0,
        "group_creation_status_unchanged": True, "mq_resources": [], "health": []}
    cleanup.save(OUTPUT / "result.json", report)
    os.environ.clear()
    os.environ.update(cleanup.CLEAN_ENV)
    context = ssl.create_default_context(cafile=config["trust_bundle"])
    context.load_cert_chain(config["leader"]["cert"], config["leader"]["key"])
    endpoint = parse_amqp_endpoint_url(config["leader"]["endpoint"], aic=cleanup.AIC)
    mq = GroupLeaderMqClient(leader_aic=cleanup.AIC, rabbitmq_host=endpoint.host,
        rabbitmq_port=endpoint.port, rabbitmq_vhost=endpoint.vhost,
        rabbitmq_user=None, rabbitmq_password=None, ssl_context=context, identity_binding_enabled=True)
    try:
        with cleanup.e1.coordinator_lock(cleanup.AIC):
            report["preflight"] = cleanup.runtime_preflight(plan, OUTPUT)
            await asyncio.wait_for(mq.connect(), 20)
            report["amqps_connected"] = True
            for group in (cleanup.GROUP, "group-" + cleanup.UNKNOWN_SESSION):
                for kind, name in (("exchange", build_group_exchange_name(cleanup.AIC, group)),
                        ("leader_queue", build_group_queue_name(cleanup.AIC, group, cleanup.AIC))):
                    row = {"group_id": group, "kind": kind, "name": name, "passive": True, "exists": None}
                    channel = await mq._connection.channel()
                    try:
                        if kind == "exchange":
                            await asyncio.wait_for(channel.get_exchange(name, ensure=True), 8)
                        else:
                            await asyncio.wait_for(channel.get_queue(name, ensure=True), 8)
                        row["exists"] = True
                    except ChannelNotFoundEntity:
                        row.update(exists=False, error_class="ChannelNotFoundEntity", broker_not_found=True)
                    except Exception as error:
                        row["error_class"] = type(error).__name__
                    finally:
                        if not channel.is_closed:
                            await channel.close()
                        report["mq_resources"].append(row)
                        cleanup.save(OUTPUT / "result.json", report)
            report["effective_proxy_metadata"] = [
                {"type": kind, "scheme": urlparse(url).scheme,
                 "loopback": urlparse(url).hostname in {"localhost", "127.0.0.1", "::1"}, "port": urlparse(url).port}
                for kind, url in urllib.request.getproxies().items() if kind != "no"]
            report["acl_endpoint_sha256"] = hashlib.sha256(config["mq_auth_url"].encode()).hexdigest()
            # Both clients use the exact same certificate and endpoint. This is
            # process-local diagnosis; the system proxy configuration is untouched.
            for trust_env in (True, False):
                started = time.monotonic()
                row = {"request": "GET /health", "trust_env": trust_env}
                try:
                    async with httpx.AsyncClient(verify=context, timeout=6, trust_env=trust_env) as client:
                        response = await client.get(config["mq_auth_url"].rstrip("/") + "/health")
                        row["http_status"] = response.status_code
                except Exception as error:
                    row["error_chain"] = []
                    while error is not None:
                        item = {"class": type(error).__name__}
                        for attr in ("errno", "winerror"):
                            if isinstance(getattr(error, attr, None), int):
                                item[attr] = getattr(error, attr)
                        row["error_chain"].append(item)
                        error = error.__cause__
                row["duration_seconds"] = round(time.monotonic() - started, 3)
                report["health"].append(row)
                cleanup.save(OUTPUT / "result.json", report)
            cleanup.require(cleanup.scope()[0] == scope, "Original failure inputs changed")
            report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error_class=type(error).__name__)
        raise
    finally:
        if mq._connection and not mq._connection.is_closed:
            await asyncio.wait_for(mq._connection.close(), 10)
        report["connection_closed"] = mq._connection is None or mq._connection.is_closed
        report["completed_at"] = cleanup.now()
        cleanup.save(OUTPUT / "result.json", report)
        print(json.dumps({"status": report.get("status"), "connection_closed": report["connection_closed"],
                          "completed_at": report["completed_at"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
