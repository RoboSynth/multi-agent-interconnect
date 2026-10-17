"""Read only official public Flux modules to find MQ endpoint configuration."""
from pathlib import Path
import hashlib
import json
import re
import httpx

out = Path(__file__).resolve().parent
urls = ["https://wt.ioa.pub/flux/src/docs/content/acps/aip-group.md?import&raw", "https://wt.ioa.pub/flux/src/docs/content/api-reference/acps/group-acl.md?import&raw", "https://wt.ioa.pub/flux/src/docs/content/api-reference/acps/infrastructure.md?import&raw"]
results = []
for index, url in enumerate(urls):
    entry = {"method": "GET", "url": url, "authentication": "none"}
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        entry.update(status=r.status_code, content_type=r.headers.get("content-type"), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest())
        path = out / f"flux-group-document-{index}.response.txt"
        path.write_bytes(r.content)
        entry["response_file"] = path.name
        # Only public import paths and endpoint address candidates are surfaced.
        entry["imports"] = re.findall(r'(?:from|import)\s*[\"\']([^\"\']+)[\"\']', r.text)
        entry["mq_url_candidates"] = re.findall(r'https://[^\s\"\'<>`]+(?:mq-auth|mq_auth|group-api)[^\s\"\'<>`]*', r.text)
    except Exception as exc:
        entry.update(error_type=type(exc).__name__, error=str(exc))
    results.append(entry)
(out / "FLUX-GROUP-RESULTS.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=True, indent=2))
