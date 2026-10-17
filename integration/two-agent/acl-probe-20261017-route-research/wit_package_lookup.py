"""Fetch explicitly documented public WIT installation sources only."""
from pathlib import Path
import hashlib
import json
import re
import httpx

out = Path(__file__).resolve().parent
urls = [
    "https://wt.ioa.pub/flux/src/docs/content/index.md?import&raw",
    "https://wt.ioa.pub/flux/src/docs/components/DocsHeader.vue",
]
records = []
for index, url in enumerate(urls):
    entry = {"url": url, "method": "GET", "authentication": "none"}
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        entry.update(status=r.status_code, final_url=str(r.url), content_type=r.headers.get("content-type"), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
        path = out / f"wit-release-link-source-{index}.response.txt"
        path.write_bytes(r.content)
        entry["response_file"] = path.name
        raw = r.text
        if raw.startswith("export default"):
            md, _ = json.JSONDecoder().raw_decode(raw.split("export default", 1)[1].lstrip())
            path.with_suffix(".md").write_text(md, encoding="utf-8")
            entry["source_locators"] = [{"line": i, "text": line} for i, line in enumerate(md.splitlines(), 1) if re.search(r"https?://|pip install|uv add|git clone|ioa_pub", line)]
    except Exception as exc:
        entry.update(error_type=type(exc).__name__, error=str(exc))
    records.append(entry)
(out / "WIT-RELEASE-LINK-SOURCES.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(records, ensure_ascii=True, indent=2))
