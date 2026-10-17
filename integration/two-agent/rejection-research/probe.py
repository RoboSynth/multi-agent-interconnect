"""Read-only admission-rejection research; public documents and assets only."""
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import hashlib
import json
import re
import httpx

out = Path(__file__).resolve().parent
records = []
client = httpx.Client(timeout=20, follow_redirects=True)

def fetch(label, url):
    assert urlsplit(url).hostname == "wt.ioa.pub"
    entry = {"url": url, "method": "GET", "authentication": "none"}
    try:
        r = client.get(url)
        entry.update(status=r.status_code, final_url=str(r.url), content_type=r.headers.get("content-type"), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
        path = out / (label + ".response.txt")
        path.write_bytes(r.content)
        entry["response_file"] = path.name
        body = r.text
    except Exception as exc:
        entry.update(error_type=type(exc).__name__, error=str(exc))
        body = ""
    records.append(entry)
    (out / "EXCHANGES.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return body

doc = fetch("wit-trusted-registration", "https://wt.ioa.pub/flux/src/docs/content/acps/identity-and-trusted-registration.md?import&raw")
if doc.startswith("export default"):
    md, _ = json.JSONDecoder().raw_decode(doc.split("export default", 1)[1].lstrip())
    (out / "wit-trusted-registration.md").write_text(md, encoding="utf-8")

index = fetch("registry-public-index", "https://wt.ioa.pub/registry/")
scripts = re.findall(r'<script[^>]+src=[\"\']([^\"\']+)', index)
summary = {"admission_rule_literal_found": False, "provider_ui_excerpts": []}
for i, src in enumerate(scripts[:2]):
    url = urljoin("https://wt.ioa.pub", src)
    if not url.startswith("https://wt.ioa.pub/registry/static/"):
        continue
    body = fetch("registry-public-main-" + str(i), url)
    summary["admission_rule_literal_found"] |= "registry-admission-2.0-static-format-llm-whole-acs" in body
    # Surface only narrow human-facing explanatory UI strings near provider.
    patterns = [r"[^\"\'<>]{0,70}(?:provider|Provider)[^\"\'<>]{0,140}", r"[^\"\'<>]{0,70}(?:实名|组织认证|认证资料|审核资料)[^\"\'<>]{0,140}"]
    snippets = []
    for pattern in patterns:
        for m in re.finditer(pattern, body):
            s = m.group(0)
            if re.search(r"[\u4e00-\u9fff]", s) and s not in snippets:
                snippets.append(s)
    summary["provider_ui_excerpts"].append({"asset": url, "snippets": snippets[:50]})
(out / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"requests": records, "summary": summary}, ensure_ascii=True, indent=2))
