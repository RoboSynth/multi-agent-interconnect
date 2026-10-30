"""Create shareable copies without changing the original verification files."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", required=True, type=Path, help="Original current-validation folder")
parser.add_argument("--repo", required=True, type=Path, help="Source checkout used by that verification")
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
args = parser.parse_args()
source, repo, output = args.source.resolve(), args.repo.resolve(), args.output.resolve()
if output == source or source in output.parents:
    raise SystemExit("The copy destination must be outside the source records")
records = output / "原始记录"
records.mkdir(parents=True, exist_ok=True)
counts = Counter()
secrets = set()
path_pairs = [(str(source), "${RECORDS}"), (str(repo), "${REPO}"),
              (str(Path.home()), "${USER_HOME}")]
path_pairs.sort(key=lambda item: len(item[0]), reverse=True)
sensitive_keys = {"proof", "signature", "sig", "hmac", "token", "password", "authorization", "approval_secret", "secret"}

def discover(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in sensitive_keys and isinstance(child, str) and child:
                secrets.add(child)
            discover(child)
    elif isinstance(value, list):
        for child in value:
            discover(child)
    elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            discover(json.loads(value))
        except (ValueError, RecursionError):
            pass

for path in source.rglob("*"):
    if path.suffix in (".json", ".jsonl"):
        text = path.read_text(encoding="utf-8")
        for value in ([text] if path.suffix == ".json" else text.splitlines()):
            try:
                discover(json.loads(value))
            except ValueError:
                pass
    elif path.suffix == ".env":
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                secrets.add(line.split("=", 1)[1])

def clean_text(text):
    for original, replacement in path_pairs:
        variants = {original, original.replace("\\", "/"), original.replace("\\", "\\\\")}
        for variant in sorted(variants, key=len, reverse=True):
            pattern = re.compile(re.escape(variant), re.IGNORECASE)
            matches = len(pattern.findall(text))
            if matches:
                counts["absolute_path_occurrences"] += matches
                text = pattern.sub(lambda match: replacement, text)
    for value in sorted(secrets, key=len, reverse=True):
        if value and value in text:
            counts["credential_or_proof_occurrences"] += text.count(value)
            text = text.replace(value, "[REDACTED_TEST_AUTH]")
    return text

def clean(value):
    if isinstance(value, dict):
        return {key: ("[REDACTED_AUTH]" if key.lower() in sensitive_keys and isinstance(child, str) and child else clean(child))
                for key, child in value.items()}
    if isinstance(value, list):
        return [clean(child) for child in value]
    if isinstance(value, bytes):
        try:
            return clean(value.decode("utf-8"))
        except UnicodeDecodeError:
            return {"binary_omitted": True, "length": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return json.dumps(clean(json.loads(value)), ensure_ascii=False, separators=(",", ":"))
            except (ValueError, RecursionError):
                pass
        return clean_text(value)
    return value

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = []
for path in sorted(source.rglob("*")):
    if not path.is_file() or "temporary" in path.relative_to(source).parts:
        continue
    relative = path.relative_to(source)
    entry = {"source_relative": relative.as_posix(), "source_sha256": digest(path)}
    destination = records / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix in (".sqlite", ".sqlite3"):
        destination = destination.with_suffix(destination.suffix + ".export.json")
        try:
            uri = "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as db:
                tables = db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                data = {}
                for name, sql in tables:
                    quoted = '"' + name.replace('"', '""') + '"'
                    cursor = db.execute("SELECT * FROM " + quoted)
                    columns = [description[0] for description in cursor.description]
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    data[name] = {"create_sql": sql, "rows": clean(rows)}
            document = {"kind": "read_only_logical_export", "source_relative": relative.as_posix(),
                        "immutable_read": True, "tables": data,
                        "note": "Logical records exported without changing the source DB; rollback journals were not replayed."}
        except sqlite3.Error as error:
            document = {"kind": "read_only_export_error", "source_relative": relative.as_posix(), "error": clean_text(str(error))}
        destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        entry["transformation"] = "SQLite read-only logical export and field redaction"
    elif path.name.endswith("-journal"):
        entry.update(transformation="not copied", reason="SQLite rollback journal is binary; original retained internally")
        manifest.append(entry)
        continue
    elif path.suffix == ".json":
        value = clean(json.loads(path.read_text(encoding="utf-8")))
        destination.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        entry["transformation"] = "JSON field redaction; records, results and timestamps preserved"
    elif path.suffix == ".jsonl":
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.dumps(clean(json.loads(line)), ensure_ascii=False, separators=(",", ":")) for line in lines]
        destination.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        entry.update(transformation="JSONL record-by-record redaction", records=len(rows))
    elif path.suffix in (".log", ".md", ".env", ".yaml", ".py"):
        if path.suffix == ".py":
            destination = destination.with_suffix(".py.reference.txt")
        destination.write_text(clean_text(path.read_text(encoding="utf-8")), encoding="utf-8")
        entry["transformation"] = "Text redaction only; Python copies are archival references"
    else:
        entry.update(transformation="not copied", reason="Unrecognised file type")
        manifest.append(entry)
        continue
    entry.update(output_relative=destination.relative_to(output).as_posix(), output_sha256=digest(destination))
    manifest.append(entry)

# Runnable versions use a discovered checkout or --repo; old runner records remain separate.
core = (source / "run_current_validation.py").read_text(encoding="utf-8")
start = core.index("OUT = Path(__file__).resolve().parent")
end = core.index("SDK = ROOT", start)
bootstrap = '''import argparse

_parser = argparse.ArgumentParser(description="Reproduce the current offline validation without changing source files")
_parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent / "当前源码")
_parser.add_argument("--output", type=Path, help="New result directory; defaults to a timestamped folder beside this script")
_parser.add_argument("--check", action="store_true", help="Check paths and print configuration without running tests")
_parser.add_argument("--diagnostic-only", action="store_true", help="For run_isolated_takeover.py: supply the missing healthy-channel fixture")
_parser.add_argument("--retry-before-modification", action="store_true", help="For run_isolated_takeover.py: run a fresh before-modification case")
_args = _parser.parse_args()
ROOT = _args.repo.resolve()
OUT = (_args.output.resolve() if _args.output else Path(__file__).resolve().parent / "新运行结果" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
if not (ROOT / "incident/wutong_transport.py").is_file() or not (ROOT / "tests/test_resume_transport.py").is_file():
    raise SystemExit("Source checkout not found: provide --repo <checkout>")
if OUT == ROOT or ROOT in OUT.parents:
    raise SystemExit("Keep output outside the source checkout")
if _args.check:
    print(json.dumps({"repo_found": True, "output_outside_repo": True, "default_layout": "测试记录 beside 当前源码"}, ensure_ascii=False))
    raise SystemExit(0)
OUT.mkdir(parents=True, exist_ok=False)
'''
core = core[:start] + bootstrap + core[end:]
core = core.replace('def git(*args):\n    return subprocess.check_output',
                    'def git(*args):\n    if not (ROOT / ".git").exists():\n        return "snapshot-without-git"\n    return subprocess.check_output')
(output / "run_current_validation.py").write_text(core, encoding="utf-8")
(output / "run_isolated_takeover.py").write_text((source / "run_isolated_takeover.py").read_text(encoding="utf-8"), encoding="utf-8")

for destination in output.rglob("*"):
    if not destination.is_file() or destination.name == Path(__file__).name:
        continue
    text = destination.read_text(encoding="utf-8")
    if re.search(r"(?i)\b[A-Z]:[\\/]", text):
        raise RuntimeError("Unredacted drive path in " + destination.relative_to(output).as_posix())
    if any(value and value in text for value in secrets):
        raise RuntimeError("Unredacted authentication material in " + destination.relative_to(output).as_posix())

report = {"created_utc": datetime.now(timezone.utc).isoformat(), "source_not_modified": True,
          "records_are_redacted_copies": True, "authentication_proofs_not_verifiable_after_redaction": True,
          "path_placeholders": {"${REPO}": "current source checkout", "${RECORDS}": "original validation directory", "${USER_HOME}": "runtime user home"},
          "redaction_counts": dict(counts), "credential_values_discovered": len(secrets), "files": manifest,
          "copied_files": sum("output_relative" in entry for entry in manifest),
          "omitted_files": sum("output_relative" not in entry for entry in manifest)}
(output / "脱敏副本清单.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: report[key] for key in ("copied_files", "omitted_files", "credential_values_discovered")}, ensure_ascii=False))
