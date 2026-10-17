"""Read only explicitly named official deployment and client documentation."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import httpx

out = Path(__file__).resolve().parent
urls = {
    "official-compare-to-pinned": "https://api.github.com/repos/AIP-PUB/ACPs-community/compare/3985c1330209f075c124669cc9d31f0e75448140...94077d10b336bfdb9a7d68e4859390bf44a67a27",
    "live-ca-acme-directory": "https://wt.ioa.pub/ca-server/acps-atr-v2/acme/directory",
    "live-registry-openapi": "https://wt.ioa.pub/registry-server/openapi.json",
}

def fetch(item):
    label, url = item
    entry = {"url": url, "method": "GET", "authentication": "none"}
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        entry.update(status=r.status_code, final_url=str(r.url), content_type=r.headers.get("content-type"), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
        path = out / (label + ".response.txt")
        path.write_bytes(r.content)
        entry["response_file"] = path.name
        if label == "github-main-commit" and r.status_code == 200:
            body = r.json()
            entry["commit"] = {"sha": body.get("sha"), "message": body.get("commit", {}).get("message"), "date": body.get("commit", {}).get("committer", {}).get("date")}
    except Exception as exc:
        entry.update(error_type=type(exc).__name__, error=str(exc))
    return entry

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    records = list(pool.map(fetch, urls.items()))
(out / "CURRENT-CLIENT-EXCHANGES.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(records, ensure_ascii=True, indent=2))
