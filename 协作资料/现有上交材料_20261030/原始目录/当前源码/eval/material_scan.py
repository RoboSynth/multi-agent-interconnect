"""Bounded anonymity checks for explicitly selected PDF and text materials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata

from eval.secret_scan import PATTERNS as SECRET_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {**SECRET_PATTERNS,
    "school_marker": re.compile(r"大学|学院|university|college", re.I),
    "registered_namespace": re.compile(r"BUPT", re.I),
    "developer_user_path": re.compile(r"(?:[A-Z]:[/\\]Users[/\\]|/home/[^/\s]+/)", re.I),
    "email_address": re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I),
}
TEXT_TYPES = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".csv"}


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def text_parts(path, poppler_dir=None):
    if path.suffix.lower() in TEXT_TYPES:
        return {"text": path.read_text(encoding="utf-8-sig")}
    if path.suffix.lower() != ".pdf":
        raise ValueError("unsupported material type; requires separate review")
    parts = {}
    for name, arguments, section in (
        ("pdftotext", ["-enc", "UTF-8", str(path), "-"], "pdf_text"),
        ("pdfinfo", ["-enc", "UTF-8", "-rawdates", str(path)], "pdf_properties"),
        ("pdfinfo", ["-meta", str(path)], "pdf_xmp"),
    ):
        executable = (str(Path(poppler_dir)/(name + (".exe" if os.name == "nt" else "")))
                      if poppler_dir else shutil.which(name))
        if not executable:
            raise FileNotFoundError("Poppler executable unavailable")
        result = subprocess.run([executable, *arguments], check=True, capture_output=True, timeout=30)
        parts[section] = result.stdout.decode("utf-8")
    if not parts["pdf_text"].strip():
        raise ValueError("PDF has no extractable text; visual/OCR review required")
    return parts


def scan(paths, *, forbidden_terms=(), poppler_dir=None):
    files, findings, errors = [], [], []
    for index, value in enumerate(paths, 1):
        path = Path(value).resolve()
        try:
            label = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
            data = path.read_bytes()
            parts = text_parts(path, poppler_dir)
            files.append({"input": index, "file": label, "sha256": hashlib.sha256(data).hexdigest(),
                          "bytes": len(data), "sections": list(parts), "visual_review_required": path.suffix.lower() == ".pdf"})
            for section, text in parts.items():
                compact = normalize(text)
                categories = {name for name, pattern in PATTERNS.items() if pattern.search(text) or pattern.search(compact)}
                categories.update("forbidden_term_"+str(i) for i, term in enumerate(forbidden_terms, 1)
                                  if normalize(term) and normalize(term) in compact)
                findings.extend({"input": index, "file": label, "section": section, "category": name}
                                for name in sorted(categories))
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as error:
            # Do not echo source contents or external tool error text.
            errors.append({"input": index, "file": path.name, "error_type": type(error).__name__})
    return {"schema_version": "material-text-anonymity/1.0", "files": files, "scanned_files": len(files),
            "findings": findings, "hits": len(findings), "errors": errors,
            "machine_checks_passed": bool(files) and not findings and not errors,
            "final_submission_anonymity_proven": False,
            "scope": "Only supplied files, extracted PDF text/properties/XMP and bounded patterns/terms. No pixel/logo/OCR, attachments, video, or unavailable final material review.",
            "required_manual_review": "Inspect final rendered PDF pages and images; supply actual school/teacher/provider terms before final checks."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--forbid-term", action="append", default=[])
    parser.add_argument("--poppler-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = scan(args.paths, forbidden_terms=args.forbid_term, poppler_dir=args.poppler_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"scanned_files": result["scanned_files"], "hits": result["hits"],
                      "errors": len(result["errors"]), "machine_checks_passed": result["machine_checks_passed"]}))
    return 2 if result["errors"] else (0 if result["machine_checks_passed"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
