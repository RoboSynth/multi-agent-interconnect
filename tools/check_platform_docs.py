"""Fetch the two public platform documents once, without cookies or login."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.request import Request, urlopen

URLS = {"docs": "https://wt.ioa.pub/docs.html", "amp": "https://wt.ioa.pub/amp"}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden-1)
    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    previous = json.loads(args.previous.read_bytes()) if args.previous else {}
    rows = {}
    for name, url in URLS.items():
        row = dict(url=url, observed_at_utc=datetime.now(timezone.utc).isoformat())
        try:
            with urlopen(Request(url, headers={"User-Agent": "incident-pilot-public-doc-check/1"}), timeout=20) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("public document exceeds read limit")
                row.update(http_status=response.status, final_url=response.url,
                           sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
                decoded = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            (args.output / (name + ".html")).write_bytes(raw)
            visible = VisibleText()
            visible.feed(decoded)
            lines = visible.parts
            (args.output / (name + ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")
            row["relevant_lines"] = [line for line in lines if any(word in line.lower() for word in
                ("kafka", "19092", "tls", "monitor", "访问量", "调用次数", "排行"))]
            old = previous.get("documents", {}).get(name, {}).get("sha256")
            row["content_changed"] = row["sha256"] != old if old else None
            row["status"] = "read"
        except Exception as error:
            row.update(status="unavailable", error_class=type(error).__name__)
        rows[name] = row
    result = dict(schema_version="public-platform-doc-check/1", login_used=False, messages_sent=0, documents=rows)
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: value for key, value in row.items() if key != "relevant_lines"} for name, row in rows.items()}))
    return 0 if all(row["status"] == "read" for row in rows.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
