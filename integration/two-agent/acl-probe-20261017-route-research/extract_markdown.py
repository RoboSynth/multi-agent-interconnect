from pathlib import Path
import json
import re

out = Path(__file__).resolve().parent
for file in sorted(out.glob("flux-group-document-*.response.txt")):
    raw = file.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    document, _ = decoder.raw_decode(raw.split("export default", 1)[1].lstrip())
    md = file.with_suffix(".md")
    md.write_text(document, encoding="utf-8")
    print(md.name)
    for line_number, line in enumerate(document.splitlines(), 1):
        if re.search(r"https?://|mq.auth|mq_auth|group_api|url|URL|base_url|Group API|9007", line):
            print(str(line_number) + ": " + line)
