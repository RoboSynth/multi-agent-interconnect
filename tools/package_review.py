"""Export allowlisted code/evidence with anonymous copies and auditable hashes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import posixpath
import re
import struct
import subprocess
import unicodedata
from urllib.parse import unquote, quote
import zipfile
import zlib


USER_PATH = re.compile(
    r"""(?i)(?:[a-z]:[\\/]+Users[\\/]+[^\s\\/"'<>:{}\[\]()]+"""
    r"""|/home/[^\s\\/"'<>:{}\[\]()]+)"""
)
PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}"
)
TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", "private", "runtime", "artifacts"}
EXCLUDED_SUFFIXES = {".pem", ".key", ".crt", ".p12", ".pfx", ".sqlite", ".sqlite3", ".pyc"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_decode(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def search_text(text):
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), text)
    return unicodedata.normalize("NFKC", html.unescape(unquote(text))).casefold()


def png_text(data):
    """Read PNG text metadata, rejecting unsupported embedded EXIF."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset, parts = 8, []
    while offset < len(data):
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + size]
        if len(body) != size or offset + size + 12 > len(data):
            raise ValueError("truncated PNG")
        if kind == b"tEXt":
            parts.append(body.decode("latin-1"))
        elif kind == b"zTXt":
            keyword, value = body.split(b"\0", 1)
            parts.append(keyword.decode("latin-1") + zlib.decompress(value[1:]).decode("latin-1"))
        elif kind == b"iTXt":
            keyword, value = body.split(b"\0", 1)
            flag, method = value[:2]
            language, translated, value = value[2:].split(b"\0", 2)
            if flag:
                value = zlib.decompress(value)
            parts.append(keyword.decode("latin-1") + translated.decode("utf-8") + value.decode("utf-8"))
        elif kind == b"eXIf":
            raise ValueError("PNG EXIF needs explicit review")
        offset += size + 12
        if kind == b"IEND":
            break
    return "\n".join(parts)


def scan_text(text, policy):
    expanded = search_text(text)
    compact = re.sub(r"\s+", "", expanded)
    findings = set()
    for entry in policy["terms"]:
        term = re.sub(r"\s+", "", search_text(entry["value"]))
        matched = (re.search(r"\b" + re.escape(term) + r"\b", expanded)
                   if entry.get("whole_word") else
                   term in expanded if re.fullmatch(r"[a-z0-9_-]+", term) else term in compact)
        if term and matched:
            findings.add(entry["category"])
    if USER_PATH.search(text) or USER_PATH.search(expanded):
        findings.add("local_user_path")
    for entry in policy.get("path_prefixes", []):
        canonical = re.sub(r"[\\/]+", "/", expanded)
        if entry.casefold().replace("\\", "/") in canonical:
            findings.add("local_user_path")
    if PRIVATE_KEY.search(text) or TOKEN.search(text):
        findings.add("credential")
    return sorted(findings)


def neutral_providers(value):
    if isinstance(value, dict):
        provider = value.get("provider")
        if isinstance(provider, dict) and isinstance(provider.get("name"), str):
            provider["name"] = "Incident Pilot Project"
        for item in value.values():
            neutral_providers(item)
    elif isinstance(value, list):
        for item in value:
            neutral_providers(item)


def measured_scalars(value):
    """Identity replacement must never change JSON numbers or booleans."""
    if isinstance(value, dict):
        return [item for child in value.values() for item in measured_scalars(child)]
    if isinstance(value, list):
        return [item for child in value for item in measured_scalars(child)]
    return [(type(value).__name__, value)] if isinstance(value, (int, float, bool)) else []


def sanitize_text(text, policy):
    counts = Counter()
    for entry in policy["terms"]:
        if entry["category"] == "github_account":
            pattern = r"https?://(?:www\.)?github\.com/" + re.escape(entry["value"]) + r"(?=/|[\"'\s)]|$)"
            text, count = re.subn(pattern, "https://example.invalid/project-source", text, flags=re.I)
            counts["github_account"] += count
    for entry in sorted(policy["terms"], key=lambda e: len(e["value"]), reverse=True):
        term = entry["value"]
        variants = {term, json.dumps(term, ensure_ascii=True)[1:-1], quote(term, safe=""),
                    "".join("\\u%04x" % ord(c) for c in term)}
        for variant in sorted(variants, key=len, reverse=True):
            pattern = re.escape(variant)
            if entry.get("whole_word") and variant == term:
                pattern = r"\b" + pattern + r"\b"
            text, count = re.subn(pattern, lambda _: entry["replacement"], text, flags=re.I)
            counts[entry["category"]] += count
    text, count = USER_PATH.subn("X:/workspace", text)
    counts["local_user_path"] += count
    for prefix in policy.get("path_prefixes", []):
        # Match plain, JSON-escaped and slash paths; preserve the rest of the file.
        for variant in {prefix, json.dumps(prefix, ensure_ascii=True)[1:-1], quote(prefix, safe="")}:
            pattern = r"[\\/]+".join(re.escape(p) for p in re.split(r"[\\/]+", variant))
            text, count = re.subn(pattern, "X:/workspace", text, flags=re.I)
            counts["local_user_path"] += count
    return text, counts


def repair_links(packages):
    """Keep links inside the two archives; label omitted historical references."""
    prefixes = {"code": "review-code", "evidence": "review-evidence"}
    for kind, files in packages.items():
        other = "evidence" if kind == "code" else "code"
        for name, data in list(files.items()):
            if not name.endswith(".md"):
                continue
            def replace(match):
                label, target = match[1], match[2]
                if target.startswith("https://example.invalid/project-source"):
                    return label + "（团队来源链接已匿名化）"
                if "://" in target or target.startswith("#"):
                    return match[0]
                path, separator, fragment = target.partition("#")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(path)))
                if resolved in files or any(n.startswith(resolved.rstrip("/") + "/") for n in files):
                    return match[0]
                if resolved in packages[other] or any(n.startswith(resolved.rstrip("/") + "/") for n in packages[other]):
                    relative = posixpath.relpath(prefixes[other] + "/" + resolved,
                                                prefixes[kind] + "/" + posixpath.dirname(name))
                    return "[" + label + "](" + relative + separator + fragment + ")"
                return label + "（历史引用，未随本包分发）"
            files[name] = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", replace,
                                 data.decode("utf-8")).encode("utf-8")


def transform(name, data, policy):
    if name.lower().endswith(".png"):
        # Pixels are immutable; their exact bytes require separate visual sign-off.
        metadata = png_text(data)
        findings = scan_text(metadata, policy)
        if findings:
            raise ValueError("PNG metadata contains identity information: " + name)
        return data, Counter(), "png_metadata_and_visual_review"
    try:
        text = text_decode(data)
        mode = "full_text"
    except UnicodeDecodeError:
        if not name.endswith((".txt", ".log")):
            raise
        text = data.decode("gb18030")
        mode = "full_text_legacy_windows_codepage"
    text = text.replace("\x00", "")
    original_numbers = None
    if name.endswith(".json"):
        try:
            original_numbers = measured_scalars(json.loads(text))
        except ValueError:
            pass
    text, counts = sanitize_text(text, policy)
    if name.endswith(".json"):
        try:
            value = json.loads(text)
        except ValueError:
            # Some historical command captures use JSON suffixes for plain text.
            value = None
        if value is not None:
            neutral_providers(value)
            if original_numbers is not None and measured_scalars(value) != original_numbers:
                raise ValueError("anonymous copy changed measured values: " + name)
            text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    findings = scan_text(text, policy)
    if findings:
        raise ValueError("identity scan failed: " + name + " categories=" + ",".join(findings))
    return text.encode("utf-8"), counts, mode


def safe_name(name):
    p = Path(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name:
        raise ValueError("unsafe package path")
    if any(part in EXCLUDED_PARTS for part in p.parts) or p.suffix.lower() in EXCLUDED_SUFFIXES:
        raise ValueError("runtime or private file cannot be packaged: " + name)
    return name


def build(repo, config, policy, acceptance, extra_records, output, visual_hashes):
    repo, output = repo.resolve(), output.resolve()
    if output.exists():
        raise ValueError("use a new output directory; preserve previous packages")
    subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD"], check=True)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    tracked = {p.decode() for p in subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z"]).split(b"\0") if p}
    code_names = config["code_files"]
    if any(n not in tracked for n in code_names):
        raise ValueError("all code paths must be tracked")
    evidence_names = sorted(n for n in tracked if any(
        n.startswith("evidence/" + batch + "/") for batch in config["evidence_batches"]))
    if any(n.split("/")[0] in {"docs", "research", "deliverables", "baselines"} for n in evidence_names):
        raise ValueError("process material entered evidence allowlist")
    output.mkdir(parents=True)
    inventory, counts, image_reviews = [], Counter(), []
    packages = {"code": {}, "evidence": {}}

    def add(kind, name, data, origin):
        safe_name(name)
        if name.lower().endswith(".png"):
            if sha(data) not in visual_hashes:
                raise ValueError("PNG has no exact-byte visual review: " + name)
            image_reviews.append({"file": name, "sha256": sha(data), "result": "no_visible_identity"})
        delivered, changes, mode = transform(name, data, policy)
        if name in packages[kind]:
            raise ValueError("duplicate package destination")
        packages[kind][name] = delivered
        counts.update(changes)
        inventory.append({
            "package": kind, "file": name, "source": origin,
            "source_sha256": sha(data), "delivered_sha256": sha(delivered),
            "changed": data != delivered, "scan_mode": mode,
        })

    for name in code_names:
        add("code", name, (repo / name).read_bytes(), "git:" + commit)
    for name in evidence_names:
        add("evidence", name, (repo / name).read_bytes(), "git:" + commit)
    for name in config["acceptance_files"]:
        add("evidence", "acceptance/" + name, (acceptance / name).read_bytes(), "prior-review-acceptance")
    for path in extra_records:
        add("evidence", "acceptance/current/" + path.name, path.read_bytes(), "current-main-validation")

    # A self-contained index replaces references to excluded process documents.
    intro = (
        "# Anonymous evidence\n\n"
        "Only the allowlisted cloud deployment, four-case cloud revalidation, local60-r3, "
        "public onboarding, upstream contribution records and review acceptance are included.\n\n"
        "These files are anonymous derivatives. Numerical outcomes and failures are preserved. "
        "Original hashes refer to pre-redaction files; delivered hashes are listed separately. "
        "Old paths, external team links and old source hashes are historical provenance, "
        "not a claim that this anonymous copy has the original bytes.\n\n"
        "The 60-cell interruption and continuation remain distinct. "
        "See evidence/p5-local60-r3-20261020/README.md and results.csv.\n\n"
        "Cloud status and upstream PR states are timestamped snapshots, not live status.\n"
    )
    packages["evidence"]["README.md"] = intro.encode()
    repair_links(packages)
    for item in inventory:
        delivered = packages[item["package"]][item["file"]]
        item["delivered_sha256"] = sha(delivered)
        item["changed"] = item["source_sha256"] != item["delivered_sha256"]
    report = {
        "schema": "anonymous-review-delivery/1",
        "source_commit": commit,
        "selected_evidence_batches": config["evidence_batches"],
        "excluded_evidence_roots": ["research", "docs", "deliverables", "baselines"],
        "scan": {
            "categories": sorted({e["category"] for e in policy["terms"]} | {"local_user_path", "credential"}),
            "term_count": len(policy["terms"]),
            "term_fingerprints": [sha(e["value"].encode()) for e in policy["terms"]],
            "term_sources": policy.get("term_sources", []),
            "teacher_roster_supplied": policy.get("teacher_roster_supplied", False),
            "changes_by_category": dict(counts),
            "remaining_hits": 0, "errors": 0,
            "text_scan": "UTF-8/UTF-16 text, decoded Unicode escapes, URL/HTML entities, filenames and ZIP comments",
            "image_reviews": image_reviews,
            "third_party_license_notices_preserved": True,
            "json_numbers_and_booleans_preserved": True,
            "scope": "Discovered/provided identity terms and generic user paths; not a proof of names absent from the inventory.",
        },
        "inventory": inventory,
    }
    # Include the same anonymous provenance inventory in the evidence archive.
    packages["evidence"]["package-manifest.json"] = json.dumps(
        report, ensure_ascii=False, indent=2).encode("utf-8")
    archives = []
    for kind, filename in (("code", "review-code.zip"), ("evidence", "review-evidence.zip")):
        destination = output / filename
        prefix = "review-" + kind
        tree = output / prefix
        for name, data in packages[kind].items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(packages[kind].items()):
                archive.writestr(prefix + "/" + name, data)
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC verification failed")
            for member in archive.infolist():
                text = png_text(archive.read(member)) if member.filename.endswith(".png") else text_decode(archive.read(member))
                findings = scan_text(member.filename + "\n" + member.comment.decode("utf-8") + "\n" + text, policy)
                if findings:
                    raise ValueError("final ZIP scan failed: " + member.filename)
        archives.append({"file": filename, "files": len(packages[kind]),
                         "bytes": destination.stat().st_size, "sha256": sha(destination.read_bytes())})
    report["archives"] = archives
    manifest = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    if scan_text(manifest.decode(), policy):
        raise ValueError("manifest leaks identity information")
    (output / "delivery-manifest.json").write_bytes(manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--extra-record", type=Path, action="append", default=[])
    parser.add_argument("--visual-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.repo, json.loads(args.config.read_text(encoding="utf-8")),
                   json.loads(args.policy.read_text(encoding="utf-8")), args.acceptance,
                   args.extra_record, args.output,
                   json.loads(args.visual_review.read_text(encoding="utf-8"))["sha256"])
    print(json.dumps({"archives": report["archives"], "remaining_hits": report["scan"]["remaining_hits"]}))


if __name__ == "__main__":
    main()
