"""Read public first-party Dingdang assets for documented MQ service addresses.

No login, cookies, credentials, writes, guessed paths, or broad scans.
"""
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import hashlib
import json
import re
import httpx

OUT = Path(__file__).resolve().parent
ORIGIN = "https://wt.ioa.pub"
records = []

def fetch(label, url):
    assert urlsplit(url).hostname == "wt.ioa.pub"
    entry = {"url": url, "authentication": "none", "method": "GET"}
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url)
        entry.update(status=r.status_code, final_url=str(r.url), content_type=r.headers.get("content-type"), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
        (OUT / (label + ".response.txt")).write_bytes(r.content)
        entry["response_file"] = label + ".response.txt"
        text = r.text
    except Exception as exc:
        entry.update(error_type=type(exc).__name__, error=str(exc))
        text = ""
    records.append(entry)
    (OUT / "exchanges.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return text

saved_index = OUT / "dingdang-public-index.response.txt"
html = saved_index.read_text(encoding="utf-8") if saved_index.exists() else fetch("dingdang-public-index", ORIGIN + "/dingdang/")
scripts = re.findall(r'<script[^>]+src=[\"\']([^\"\']+)', html)
summary = {"scope": "First-party public Dingdang index and named JavaScript assets only; main app inspected after three helper assets", "endpoint_configs": []}
for idx, src in enumerate([s for s in scripts if s.startswith("app.js")]):
    url = urljoin(ORIGIN + "/dingdang/", src)
    if urlsplit(url).hostname != "wt.ioa.pub":
        continue
    body = fetch("dingdang-main-app-" + str(idx), url)
    # Narrow endpoint-only extraction. Do not inspect credentials or user data.
    patterns = [r'(?:VITE_MQ_AUTH_URL|auth_service_url|group_api_url|MQ_AUTH_URL|mqAuthUrl|authServiceUrl)\s*[:=]\s*[\"\']([^\"\']+)', r'https://[^\s\"\'<>`]+(?:mq-auth|mq_auth|group-api|mq/group)[^\s\"\'<>`]*']
    for pattern in patterns:
        for match in re.finditer(pattern, body):
            summary["endpoint_configs"].append({"asset": url, "value": match.group(1) if match.lastindex else match.group(0)})
(OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"requests": records, "summary": summary}, ensure_ascii=True, indent=2))
