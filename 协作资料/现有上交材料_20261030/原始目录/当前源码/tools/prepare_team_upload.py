"""Inventory useful team-repository sources and sanitized CLOSED evidence; no Git writes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("business", "incident", "acps_mcp_bridge", "acps-mcp-bridge", "domains", "deploy", "eval", "tests", "tools", "ops", "demo-ui", "docs")
DENIED_DIRS = {"private", "runtime", "artifacts", "output", "results", "__pycache__", ".git", ".cache", ".playwright-cli",
               "node_modules", "dist", "build", ".pytest_cache", "certs", "certificates", "credentials", "secrets"}
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".js", ".css", ".html", ".sql", ".json", ".svg",
                   ".ini", ".cfg", ".conf", ".sh", ".ps1", ".rst", ".typed", ".lock"}
SPECIAL_NAMES = {"LICENSE", "LICENSE.md", "MANIFEST.in", "Dockerfile", "Dockerfile.agent", "Dockerfile.docker-mcp", ".gitignore", ".dockerignore"}
CLOSED_RESULTS = (
    "eval/results/local/business-verification-summary.json", "eval/results/local/business-native-acceptance.json",
    "eval/results/local/business-native-acceptance-route-fix.json", "eval/results/local/business-native-acceptance-wmi-failure.json",
    "eval/results/local/ui-f10-complete.json", "eval/results/local/F15-native-20261017-initial/results.json",
    "eval/results/local/scheduling-native-20261017/results.json", "eval/results/local/scheduling-native-20261017/access-reconciliation.json",
    "eval/results/local/local-amp-report.json", "eval/results/local/docker-h00-20261017.json",
    "eval/results/local/native-environment-restoration-v2.json", "eval/results/local/workbench-launch-environment-isolation-v2.json",
    "eval/results/local/F12-container-20261017-initial.json", "eval/results/local/E1c-container-20261017-initial/results.json",
    "eval/results/local/E1c-container-20261017-retry/results.json", "eval/results/local/E1c-container-20261017-retry/credential-scan.json",
    "eval/results/platform/application-verification-20261017-initial/results.json",
    "eval/results/platform/container-old-contract-20261017/tls.json", "eval/results/platform/container-old-contract-20261017/start.json",
    "eval/results/platform/container-postgres-mcp-20261017-initial/results.json",
    "output/database-bridge-20261017T085554Z/results.json", "output/database-blocker-bridge-20261017T091119Z/results.json",
    "output/native-ops-bridge-20261017T085959Z/results.json", "output/docker-mcp-bridge-20261017T094625Z/results.json",
)
SECRET_FIELD = re.compile(r"(?:password|secret|eab|private[_-]?key|api[_-]?key|(?:^|[_-])token$|(?:access|refresh|id)[_-]?token$|^DATABASE_(?:URI|URL)$)", re.I)
CREDENTIAL_URL = re.compile(r"(?:postgres(?:ql)?|amqps?|https?)://[^\s/:@]+:[^\s/@]+@", re.I)
PEM_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blocked(path):
    return any(part.lower() in DENIED_DIRS or part.lower().startswith(".venv") for part in path.parts)


def selected(path):
    name = path.name.lower()
    if name == "native-runtime.json" or name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS | {".pdf"} or path.name in SPECIAL_NAMES


def walk(directory):
    if not directory.is_dir():
        return
    for parent, directories, files in os.walk(directory, followlinks=False):
        parent = Path(parent)
        directories[:] = sorted(name for name in directories if not blocked(Path(name)) and not (parent / name).is_symlink()
                                and not bool(getattr((parent / name).lstat(), "st_file_attributes", 0) & 0x400))
        for name in sorted(files):
            path = parent / name
            if selected(path) and not path.is_symlink() and not bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
                yield path


def known_values():
    values = set()
    for directory in (ROOT / "runtime/private", ROOT / "runtime/container-domains/application", ROOT / "runtime/container-domains/database",
                      ROOT / "runtime/container-domains/ops"):
        if directory.is_dir():
            for file in directory.glob("*.env"):
                for line in file.read_text(encoding="utf-8-sig").splitlines():
                    key, separator, value = line.partition("=")
                    if separator and SECRET_FIELD.search(key) and len(value) >= 12:
                        values.add(value.strip().strip('"').strip("'"))
    return sorted(values, key=len, reverse=True)


def findings(content, secrets):
    output = []
    for number, line in enumerate(content.splitlines(), 1):
        if any(value and value in line for value in secrets):
            output.append({"line": number, "category": "known_live_secret", "blocking": True})
        if CREDENTIAL_URL.search(line):
            output.append({"line": number, "category": "credential_url_or_example", "blocking": False})
    if PEM_KEY.search(content):
        output.append({"line": None, "category": "inline_private_key_or_fixture", "blocking": True})
    return output


def sanitize(value, secrets, changed, path="$", parent_key=None):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            location = path + "." + key
            if SECRET_FIELD.search(key) and isinstance(item, str) and item:
                result[key] = "[REDACTED]"
                changed.append(location)
            elif parent_key == "provider" and key == "name":
                result[key] = "[TEAM]"
                changed.append(location)
            else:
                result[key] = sanitize(item, secrets, changed, location, key)
        return result
    if isinstance(value, list):
        return [sanitize(item, secrets, changed, path + "[" + str(i) + "]", parent_key) for i, item in enumerate(value)]
    if isinstance(value, str):
        result = value.replace(str(ROOT), "<workspace>").replace(ROOT.as_posix(), "<workspace>")
        for secret in secrets:
            result = result.replace(secret, "[REDACTED]")
        if result != value:
            changed.append(path)
        return result
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-closed-result", action="append", default=[])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    secrets = known_values()
    candidates, seen = [], set()
    def add(path, target, category):
        if path in seen:
            return
        seen.add(path)
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise RuntimeError("Candidate changed while reading: " + str(path.relative_to(ROOT)))
        checks = findings(data.decode("utf-8-sig", errors="replace"), secrets) if path.suffix.lower() != ".pdf" else []
        candidates.append({"source": str(path), "target": target, "category": category, "bytes": len(data), "sha256": digest(data),
            "decision": "quarantine" if any(row["blocking"] for row in checks) else "review_examples" if checks else "candidate",
            "content_scan": "binary PDF not text-scanned" if path.suffix.lower() == ".pdf" else "known live values and credential patterns",
            "findings": checks})
    for directory in SOURCE_DIRS:
        for path in walk(ROOT / directory):
            add(path, path.relative_to(ROOT).as_posix(), "current_source")
    for path in sorted(ROOT.iterdir()):
        if path.is_file() and (path.suffix == ".py" or path.name in SPECIAL_NAMES or path.name.startswith("requirements") and path.suffix == ".txt"):
            add(path, path.name, "current_root_and_baseline_entry")
    for path in walk(ROOT / "integration"):
        if path.suffix.lower() in {".py", ".md"} or path.name == "discovery-application.request.json":
            add(path, path.relative_to(ROOT).as_posix(), "public_platform_source")
    for relative in ("vendor/ACPs-community/acps-sdk",):
        for path in walk(ROOT / relative):
            add(path, path.relative_to(ROOT).as_posix(), "required_official_sdk_modified_source")
    for relative in ("vendor/ACPs-community/LICENSE", "vendor/ACPs-community/README.md", "vendor/ACPs-community/registry-server/app/agent/acsSchema.json"):
        add(ROOT / relative, relative, "official_license_or_schema")
    baseline = ROOT / "baselines/incident-v0.2.0-20261017T045307Z"
    for relative in ("run_pilot.py", "services.py", "README.md", "BASELINE.json", "FILES.json", "environment.json", "requirements-lock.txt"):
        add(baseline / relative, (baseline / relative).relative_to(ROOT).as_posix(), "filtered_baseline_reproduction")
    for directory in ("integration", "archive", "vendor/ACPs-community/acps-sdk"):
        for path in walk(baseline / directory):
            if directory != "integration" or path.suffix.lower() in {".py", ".md"}:
                add(path, path.relative_to(ROOT).as_posix(), "filtered_baseline_reproduction")
    for directory, target, category in ((ROOT.parent / "参赛资料_2026AIC_AI开源", "research/competition", "relevant_rules_and_research"),
            (ROOT.parent / "参赛资料_2026AIC_其他赛道_20261016", "research/other-tracks", "optional_other_track_research"),
            (ROOT.parent / "error-assistant/docs", "research/error-assistant", "optional_prior_direction_docs")):
        for path in walk(directory):
            actual_category = "current_interconnect_official_rules" if "智能体互联" in path.name else category
            add(path, target + "/" + path.relative_to(directory).as_posix(), actual_category)
    for relative in (*CLOSED_RESULTS, *args.include_closed_result):
        path = ROOT / relative
        if not path.is_file():
            continue
        if "model-fairness-formal-20261017" in str(path):
            raise ValueError("The active 45-run matrix is excluded until root declares it frozen")
        data = path.read_bytes()
        record = json.loads(data)
        changes = []
        clean = sanitize(record, secrets, changes)
        encoded = (json.dumps(clean, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        destination = output / "sanitized-evidence" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(encoded)
        checks = findings(encoded.decode(), secrets)
        candidates.append({"source": str(destination), "original_source": str(path), "original_sha256": digest(data),
            "target": "evidence/" + relative, "category": "closed_result_sanitized_copy", "bytes": len(encoded), "sha256": digest(encoded),
            "decision": "quarantine" if any(row["blocking"] for row in checks) else "review_examples" if checks else "candidate",
            "redacted_json_paths": sorted(set(changes)), "findings": checks})
    baseline_files = [{"path": row["target"].split("/", 2)[-1], "bytes": row["bytes"], "sha256": row["sha256"]}
                      for row in candidates if row["category"] == "filtered_baseline_reproduction"]
    baseline_manifest = output / "baseline-source-manifest.json"
    baseline_manifest.write_text(json.dumps({"source_snapshot": baseline.name, "filtered_source_only": True,
        "raw_archive_excluded": True, "omitted": "runtime databases, private configuration, certificates and generated outputs",
        "files": sorted(baseline_files, key=lambda row: row["path"])}, ensure_ascii=False, indent=2), encoding="utf-8")
    add(baseline_manifest, "baselines/" + baseline.name + "/TEAM-SOURCE-MANIFEST.json", "filtered_baseline_manifest")
    candidates.sort(key=lambda row: row["target"])
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "git_actions_performed": False,
        "root": str(ROOT), "source_baseline_modified": False, "candidates": candidates,
        "excluded": ["all private/runtime/database/certificate/key/env/venv/cache/model/binary/archive paths",
                     "raw baseline ZIP contains two orders.sqlite files; original archive remains local",
                     "active eval/results/local/model-fairness-formal-20261017 tree",
                     "workspace cache/output/tmp and stray browser console snippets"],
        "notes": ["Candidate means reviewable, not uploaded or staged.", "Sanitized evidence is a derived copy; original hashes are retained.",
                  "Signed raw AMP records are not rewritten or included here.", "Public PDFs are inventoried but not text-scanned."]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    scan = {"candidate_files": len(candidates), "candidate_bytes": sum(row["bytes"] for row in candidates),
        "quarantined_files": [row["target"] for row in candidates if row["decision"] == "quarantine"],
        "example_review_files": [row["target"] for row in candidates if row["decision"] == "review_examples"],
        "known_value_count": len(secrets), "scope": "Only explicitly selected sources and closed-result copies; no cache/runtime traversal."}
    (output / "candidate-scan.json").write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**{key: value for key, value in scan.items() if key not in {"quarantined_files", "example_review_files"}},
        "quarantined_files": len(scan["quarantined_files"]), "example_review_files": len(scan["example_review_files"]), "output": str(output)}))


if __name__ == "__main__":
    main()
