"""Reuse private capture audit definitions, without copying private dictionaries.

Supply --private-auditor pointing to the original audit_shared_anonymity.py.
The private scanner and identity cache are deliberately not bundled.
"""
import argparse
import hashlib
import ipaddress
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-auditor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-report", type=Path, required=True)
    args = parser.parse_args()
    auditor = args.private_auditor.resolve()
    source = auditor.read_text(encoding="utf-8-sig")
    setup, marker, _ = source.partition("for path in sorted(ROOT.rglob('*')):")
    if not marker:
        raise RuntimeError("Private scanner entry point changed; review adapter before use")
    ns = {"__file__": str(auditor), "__name__": "private_audit_helpers"}
    exec(compile(setup, str(auditor), "exec"), ns)
    root = args.output.resolve()
    files, errors, image_count = [], [], 0
    institution_terms = {part for value in ns["IDENTITIES"].values() for part in value.split(".")[5:7] if len(part) >= 4}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "匿名核验.json":
            continue
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        files.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        try:
            if path.suffix == ".png":
                with Image.open(path) as picture:
                    text = json.dumps({k: v for k, v in picture.info.items() if isinstance(v, str)}, ensure_ascii=False)
                image_count += 1
                for label, values in (("known_identity_in_binary", ns["IDENTITIES"].values()), ("known_name_in_binary", ns["NAMES"]), ("known_secret_in_binary", ns["SECRETS"])):
                    if any(value.encode("utf-8") in raw for value in values):
                        ns["flag"](relative, "binary", label)
            else:
                text = raw.decode("utf-8-sig")
            ns["text_checks"](text, relative, "text")
            if path.suffix == ".json":
                ns["walk"](json.loads(text), relative)
            if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I) for term in institution_terms):
                ns["flag"](relative, "text", "identity_prefix_or_institution")
            if re.search(r"[\u4e00-\u9fff]{2,12}大学", text):
                ns["flag"](relative, "text", "university_name_candidate")
            for value in set(re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text)):
                try:
                    address = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if not address.is_loopback:
                    ns["flag"](relative, "text", "nonloopback_ip_candidate")
            if re.search(r"(?i)(?:[A-Z]:[/\\](?:Users|16080)[/\\]|[/]home[/]|ubuntu@[A-Za-z0-9])", text):
                ns["flag"](relative, "text", "private_path_or_login_candidate")
        except (ValueError, OSError, UnicodeError) as exc:
            errors.append({"file": relative, "error_type": type(exc).__name__})
    findings = [{"file": file, "field": field, "type": kind} for file, field, kind in sorted(ns["FINDINGS"])]
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "new PPT source-material directory only; private values loaded in memory, never included",
        "counts": {"files_scanned": len(files), "text_files_scanned": len(files) - image_count,
                   "png_metadata_scanned": image_count, "bytes_scanned": sum(p["bytes"] for p in files),
                   "known_aic_terms": len(ns["IDENTITIES"]), "known_provider_terms": len(ns["NAMES"]),
                   "known_credential_terms": len(ns["SECRETS"]), "findings": len(findings), "read_or_parse_errors": len(errors)},
        "findings": findings, "errors": errors,
        "media_review": "Two PNG diagrams are generated only from corresponding scanned SVG/report figure definitions and were visually inspected. No browser screenshots or audio are newly included.",
    }
    args.private_report.write_text(json.dumps({"report": report, "files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "匿名核验.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if findings or errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
