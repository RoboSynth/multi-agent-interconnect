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
    findings, scanned, parse_findings, read_findings = [], [], [], []
    seen, json_records = set(), 0
    for value in paths:
        path = Path(value)
        if not path.exists():
            read_findings.append({"file": str(path), "error_type": "FileNotFoundError"})
            continue
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if not file.is_file() or file.suffix.lower() not in {".json", ".jsonl", ".env", ".log", ".txt", ".yaml"}:
                continue
            resolved = file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                content = file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as error:
                read_findings.append({"file": str(file), "error_type": type(error).__name__})
                continue
            scanned.append(str(file))
            if file.suffix.lower() == ".json":
                try:
                    json.loads(content)
                    json_records += 1
                except ValueError as error:
                    parse_findings.append({"file": str(file), "line": getattr(error, "lineno", 1),
                                           "error_type": type(error).__name__})
            for number, line in enumerate(content.splitlines(), 1):
                if file.suffix.lower() == ".jsonl" and line.strip():
                    try:
                        json.loads(line)
                        json_records += 1
                    except ValueError as error:
                        parse_findings.append({"file": str(file), "line": number,
                                               "error_type": type(error).__name__})
                categories = {name for name, pattern in PATTERNS.items() if pattern.search(line)}
                if any(secret and secret in line for secret in known_secrets):
                    categories.add("known_resource_secret")
                for category in sorted(categories):
                    findings.append({"file": str(file), "line": number, "category": category})
    return {"scanned_files": len(scanned), "files": scanned, "hits": len(findings), "findings": findings,
            "json_records": json_records, "parse_errors": len(parse_findings), "parse_findings": parse_findings,
            "read_errors": len(read_findings), "read_findings": read_findings,
            "machine_checks_passed": bool(scanned) and not findings and not parse_findings and not read_findings,
            "scope": "Only supplied paths, credential patterns and provided known secrets; JSON/JSONL parsed. Not a proof that arbitrary sensitive text is absent."}


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
    raise SystemExit(0 if result["machine_checks_passed"] else 1)
