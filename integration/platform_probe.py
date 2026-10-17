"""Read-only Wutong public onboarding probe using the pinned official SDK.

No account tokens/passwords are read. No registration, review submission, group
creation, task invocation or certificate issuance is performed. POST requests
only query the public ADP discovery endpoint. Broker TLS checks use addresses
actually returned by public ACS records, never a guessed port range.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import socket
import ssl
import sys
import time
from urllib.parse import parse_qs, urljoin, urlparse
import uuid

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vendor" / "ACPs-community" / "acps-sdk"))
from acps_sdk.acs import AgentCapabilitySpec  # noqa: E402
from acps_sdk.adp import (  # noqa: E402
    DiscoveryFilter,
    DiscoveryRequest,
    DiscoveryResponse,
    validate_discovery_request,
)

ORIGIN = "https://wt.ioa.pub"
BASES = {
    "registry": ORIGIN + "/registry-server",
    "ca": ORIGIN + "/ca-server",
    "discovery": ORIGIN + "/discovery",
}
TZ = timezone(timedelta(hours=8))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Probe:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        # Use the existing proxy environment; never change desktop routing.
        self.http = httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=True)
        self.exchanges: list[dict] = []

    def request(self, label: str, method: str, url: str, payload: dict | None = None, save_body: bool = True):
        if urlparse(url).hostname != "wt.ioa.pub":
            raise ValueError("Probe only contacts the explicit official origin")
        request = {"method": method, "url": url, "json": payload, "authentication": "none"}
        write_json(self.directory / f"{label}.request.json", request)
        began = time.monotonic()
        entry = {"label": label, **request}
        try:
            response = self.http.request(method, url, json=payload)
            entry.update(
                status=response.status_code,
                content_type=response.headers.get("content-type"),
                bytes=len(response.content),
                sha256=digest(response.content),
                elapsed_seconds=round(time.monotonic() - began, 3),
                final_url=str(response.url),
            )
            if save_body:
                suffix = ".response.json" if "json" in response.headers.get("content-type", "") else ".response.txt"
                name = label + suffix
                (self.directory / name).write_bytes(response.content)
                entry["body_file"] = name
            self.exchanges.append(entry)
            write_json(self.directory / f"{label}.metadata.json", entry)
            return response
        except Exception as exc:
            entry.update(error_type=type(exc).__name__, error=str(exc), elapsed_seconds=round(time.monotonic() - began, 3))
            self.exchanges.append(entry)
            write_json(self.directory / f"{label}.metadata.json", entry)
            return None


def public_agent_summary(aic: str, acs: dict) -> dict:
    endpoints = acs.get("endPoints", [])
    identity_warnings = []
    for endpoint in endpoints:
        if endpoint.get("transport") == "AMQP":
            inbox = parse_qs(urlparse(endpoint.get("url", "")).query).get("inbox", [])
            if inbox != ["inbox_" + aic]:
                identity_warnings.append("Published AMQP inbox AIC differs from the ACS map identity")
    try:
        AgentCapabilitySpec.from_dict(acs)
        sdk_acs_ok = True
        sdk_acs_error = None
    except Exception as exc:
        sdk_acs_ok = False
        sdk_acs_error = str(exc)
    return {
        "aic": aic,
        "name": acs.get("name"),
        "protocolVersion": acs.get("protocolVersion"),
        "endPoints": endpoints,
        "capabilities": acs.get("capabilities"),
        "skillIds": [skill.get("id") for skill in acs.get("skills", [])],
        "identity_warnings": identity_warnings,
        "pinned_sdk_acs_model_valid": sdk_acs_ok,
        "pinned_sdk_acs_model_error": sdk_acs_error,
    }


def tls_without_client_cert(host: str, port: int, trust_pem: str | None) -> dict:
    record = {"host": host, "port": port, "client_certificate_supplied": False, "task_or_auth_request_sent": False}
    for label, cadata in [("system_ca", None), ("platform_public_trust_bundle", trust_pem)]:
        if label == "platform_public_trust_bundle" and not cadata:
            continue
        result = {"trust": label, "server_hostname_verification": True}
        began = time.monotonic()
        try:
            context = ssl.create_default_context(cadata=cadata)
            with socket.create_connection((host, port), timeout=8) as plain:
                with context.wrap_socket(plain, server_hostname=host) as secure:
                    result.update(tls_handshake_completed=True, tls_version=secure.version(), cipher=secure.cipher())
                    peer = secure.getpeercert()
                    result["peer_certificate"] = {key: peer.get(key) for key in ["subject", "issuer", "notBefore", "notAfter", "subjectAltName"]}
                    # Normal AMQP protocol preface only; no SASL credentials,
                    # queue creation, exchange publication or task messages.
                    secure.settimeout(3)
                    secure.sendall(b"AMQP\x00\x00\x09\x01")
                    result["amqp_protocol_preface_sent"] = True
                    result["received_prefix_hex"] = secure.recv(16).hex()
        except Exception as exc:
            result.update(error_type=type(exc).__name__, error=str(exc))
            result["client_certificate_required_observed"] = "certificate required" in str(exc).lower() or "certificate_required" in str(exc).lower()
            result["sandbox_socket_denied_observed"] = isinstance(exc, PermissionError)
        result["elapsed_seconds"] = round(time.monotonic() - began, 3)
        record[label] = result
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-tls", action="store_true")
    args = parser.parse_args()
    started = datetime.now(TZ)
    directory = args.output_dir or Path(__file__).resolve().parent / "artifacts" / ("platform-probe-" + started.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    probe = Probe(directory)
    result = {
        "observed_at": started.isoformat(timespec="seconds"),
        "source_commit": "3985c1330209f075c124669cc9d31f0e75448140",
        "authorization_material_read": False,
        "platform_writes_performed": False,
        "project_agent_aic_or_certificate_obtained": False,
        "scope": "public documents, public OpenAPI, public ADP queries and published-broker TLS preface only",
    }
    schemas = {}
    for service, base in BASES.items():
        response = probe.request(service + "-openapi", "GET", base + "/openapi.json")
        if response is not None and response.status_code == 200 and "json" in response.headers.get("content-type", ""):
            schemas[service] = response.json()
    result["public_api_versions"] = {name: schema.get("info") for name, schema in schemas.items()}
    docs = probe.request("official-docs", "GET", ORIGIN + "/docs.html")
    if docs is not None:
        document = docs.content.decode("utf-8", errors="replace")
        blocks = [html.unescape(re.sub("<[^>]+>", "", block)) for block in re.findall(r"<pre[^>]*>(.*?)</pre>", document, flags=re.S)]
        result["docs_configuration_excerpts"] = [block for block in blocks if any(term in block for term in ["registry-server", "ca-server", "[discovery]", "19092", "amqps", "rabbitmq", "mq-auth"])]

    page = probe.request("registry-public-html", "GET", ORIGIN + "/registry/")
    configs: dict[str, list[str]] = {}
    if page is not None:
        scripts = re.findall(r"<script[^>]*src=[\"']([^\"']+)", page.text)
        for index, source in enumerate(scripts[:2]):
            url = urljoin(ORIGIN, source)
            if not url.startswith(ORIGIN + "/registry/static/"):
                continue
            response = probe.request(f"registry-public-script-{index}", "GET", url, save_body=False)
            if response is None:
                continue
            # Only inspect this whitelist of public deployment configuration;
            # never search for credentials, tokens or logged-in account data.
            pattern = r"(VITE_(?:RABBITMQ_HOST|RABBITMQ_PORT|MQ_AUTH_URL|DISCOVERY_SERVER_URL|DISCOVERY_URL|SUPPORT_DISCOVER))\s*:\s*\"([^\"]*)\""
            for key, value in re.findall(pattern, response.text):
                configs.setdefault(key, [])
                if value not in configs[key]:
                    configs[key].append(value)
    result["public_frontend_configuration"] = configs

    discovery_schema = schemas.get("discovery", {})
    live_paths = discovery_schema.get("paths", {})
    discover_path = next((path for path in live_paths if path.endswith("/discover") and "post" in live_paths[path]), None)
    result["actual_discovery_path"] = discover_path
    result["sdk_demo_base_url_requirement"] = "Demo DiscoveryClient appends /discover; use an ADP-prefixed base URL. CLI appends /acps-adp-v2 itself, so CLI base stays /discovery."
    live_model = discovery_schema.get("components", {}).get("schemas", {}).get("DiscoveryRequest", {})
    live_fields = set(live_model.get("properties", {}))
    pinned_fields = {field.alias or name for name, field in DiscoveryRequest.model_fields.items()}
    result["live_request_fields_absent_from_pinned_sdk"] = sorted(live_fields - pinned_fields)
    capabilities_path = next((path for path in live_paths if path.endswith("/capabilities")), None)
    if capabilities_path:
        response = probe.request("discovery-capabilities", "GET", BASES["discovery"] + capabilities_path)
        if response is not None and response.status_code == 200:
            result["live_discovery_capabilities"] = response.json()
    probe.request("discovery-health", "GET", BASES["discovery"] + "/health")

    query_results = {}
    broker_candidates = set()
    if discover_path:
        filters = {
            "public-active": [{"field": "active", "op": "eq", "value": True}],
            "amqp-active": [{"field": "active", "op": "eq", "value": True}, {"field": "endPoints.transport", "op": "eq", "value": "AMQP"}],
            "our-application-skill": [{"field": "active", "op": "eq", "value": True}, {"field": "skills.id", "op": "eq", "value": "incident.application.inspect"}],
        }
        for label, conditions in filters.items():
            request = DiscoveryRequest(type="filtered", limit=5, filter=DiscoveryFilter.model_validate({"logic": "and", "conditions": conditions}))
            validate_discovery_request(request)
            payload = request.to_dict()
            response = probe.request("adp-" + label, "POST", BASES["discovery"] + discover_path, payload)
            entry = {"request_built_and_validated_by_official_sdk": True}
            if response is not None:
                entry["status"] = response.status_code
                try:
                    raw = response.json()
                    parsed = DiscoveryResponse.from_dict(raw)
                    entry.update(response_parsed_by_official_sdk=True, protocol_error=parsed.is_error())
                    if parsed.is_error():
                        entry["error"] = raw.get("error")
                    acs_map = (raw.get("result") or {}).get("acsMap", {})
                    entry["agent_count"] = len(acs_map)
                    entry["agents"] = [public_agent_summary(aic, acs) for aic, acs in acs_map.items()]
                    for agent in entry["agents"]:
                        if agent["identity_warnings"]:
                            continue
                        for endpoint in agent["endPoints"]:
                            parsed_url = urlparse(endpoint.get("url", ""))
                            if endpoint.get("transport") == "AMQP" and parsed_url.scheme == "amqps" and parsed_url.hostname == "wt.ioa.pub" and parsed_url.port:
                                broker_candidates.add((parsed_url.hostname, parsed_url.port, parsed_url.path.lstrip("/")))
                except Exception as exc:
                    entry.update(response_parsed_by_official_sdk=False, parsing_error=str(exc))
            query_results[label] = entry
    result["adp_queries"] = query_results
    result["broker_candidates_from_consistent_public_acs"] = [dict(host=host, port=port, vhost=vhost) for host, port, vhost in sorted(broker_candidates)]

    ca_schema = schemas.get("ca", {})
    ca_paths = ca_schema.get("paths", {})
    trust_pem = None
    trust_path = "/acps-atr-v2/ca/trust-bundle"
    if trust_path in ca_paths:
        response = probe.request("ca-public-trust-bundle", "GET", BASES["ca"] + trust_path)
        if response is not None and response.status_code == 200 and b"BEGIN CERTIFICATE" in response.content:
            trust_pem = response.content.decode("ascii")
    directory_path = "/acps-atr-v2/acme/directory"
    if directory_path in ca_paths:
        response = probe.request("ca-acme-directory", "GET", BASES["ca"] + directory_path)
        if response is not None and response.status_code == 200:
            result["acme_directory"] = response.json()

    # Two bounded service-name path checks, not a port scan. Public source has
    # /health within mq-auth-server, but no confirmed production proxy prefix.
    # HTML homepage fallbacks must not be mistaken for working Group APIs.
    group_checks = []
    for suffix in ["/health", "/openapi.json"]:
        response = probe.request("mq-auth-prefix-" + suffix.rsplit("/", 1)[-1].replace(".", "-"), "GET", ORIGIN + "/mq-auth-server" + suffix)
        if response is not None:
            group_checks.append({"url": str(response.url), "status": response.status_code, "content_type": response.headers.get("content-type"), "sha256": digest(response.content), "json_api_observed": "json" in response.headers.get("content-type", "")})
    result["group_api_prefix_checks"] = group_checks
    result["group_api_public_url_confirmed"] = False
    result["group_api_search_scope"] = "official docs, registry root JS public configuration, service OpenAPI, pinned nginx templates, two same-origin mq-auth-server paths"
    if not args.skip_tls:
        result["published_broker_tls_without_client_certificate"] = [tls_without_client_cert(host, port, trust_pem) for host, port, _ in sorted(broker_candidates)]
    else:
        result["published_broker_tls_without_client_certificate"] = "not run (--skip-tls)"
    result["http_exchanges"] = probe.exchanges
    write_json(directory / "RESULTS.json", result)
    report = [
        "# 梧桐公共接入探针", "", f"实测时间：{result['observed_at']}", "",
        "本次没有读取账户令牌/密码，没有登记、审核、申请证书、创建群组或调用其他参赛者的智能体。", "",
        f"真实发现路由：`{BASES['discovery'] + (discover_path or '')}`。", "",
        "|查询|HTTP|官方 SDK 解析|公开 ACS 数|", "|---|---:|---|---:|",
    ]
    for name, entry in query_results.items():
        report.append(f"|{name}|{entry.get('status')}|{entry.get('response_parsed_by_official_sdk')}|{entry.get('agent_count', 0)}|")
    report += ["", "保存的原始请求和公开响应与 RESULTS.json 同目录。公开发现成功与本项目已经入网是两件事；本项目目前仍需实际审批身份和证书。", "", "AMQP 地址仅从公开 ACS 获取，排除 Inbox 与 AIC 不一致的记录作为连接依据。前端 localhost 配置和 HTML 主页兜底不能当成公网 Group API。", "", "证书门槛、TLS 实测、SDK 与线上模型差异均详见 RESULTS.json。"]
    (directory / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    probe.http.close()
    print(json.dumps({"artifact_dir": str(directory.resolve()), "actual_discovery_path": discover_path, "query_counts": {name: entry.get('agent_count') for name, entry in query_results.items()}, "broker_candidates": result["broker_candidates_from_consistent_public_acs"], "group_api_url_confirmed": False, "tls": result["published_broker_tls_without_client_certificate"]}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
