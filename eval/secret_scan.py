"""Scan coordinator configuration and task captures without printing secrets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential_url": re.compile(r"(?:postgres(?:ql)?|amqps?|https?)://[^\s/:@]+:[^\s/@]+@", re.I),
    "resource_secret": re.compile(r'''(?:["']?(?:PGPASSWORD|PGADMINPASSWORD|DATABASE_URL|APP_ADMIN_TOKEN|DOCKER_CERT_PATH)["']?)\s*[:=]\s*["']?(?!\[REDACTED\])[^\s"'{}\[\],]+''', re.I),
}


def scan(paths, known_secrets=()):
    findings, scanned = [], []
    for value in paths:
        path = Path(value)
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if not file.is_file() or file.suffix.lower() not in {".json", ".jsonl", ".env", ".log", ".txt", ".yaml"}:
                continue
            content = file.read_text(encoding="utf-8-sig", errors="replace")
            scanned.append(str(file))
            for number, line in enumerate(content.splitlines(), 1):
                categories = {name for name, pattern in PATTERNS.items() if pattern.search(line)}
                if any(secret and secret in line for secret in known_secrets):
                    categories.add("known_resource_secret")
                for category in sorted(categories):
                    findings.append({"file": str(file), "line": number, "category": category})
    return {"scanned_files": len(scanned), "files": scanned, "hits": len(findings), "findings": findings,
            "scope": "Only the supplied coordinator configuration and capture paths were scanned."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--known-secret-env", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    secrets = []
    for path in args.known_secret_env:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if any(word in key for word in ("PASSWORD", "TOKEN", "SECRET", "DATABASE_URL", "DATABASE_URI", "DSN")):
                    secrets.append(value)
    result = scan(args.paths, secrets)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if result["hits"] else 0)
