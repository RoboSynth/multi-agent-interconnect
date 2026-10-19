"""Project local evidence paths while retaining original and published byte bindings.

Run against the preserved artifact batch. No raw databases or private inputs are
copied. This script only publishes the explicit evidence selection below.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--map", action="append", default=[], metavar="LABEL=PATH")
    args = parser.parse_args()
    batch, checkout, canonical = (p.resolve() for p in (args.batch, args.checkout, args.canonical))
    output = checkout / "evidence/current-source-validation-20261019"
    output.mkdir(parents=True, exist_ok=True)
    base = "613ecbfc6e7500a30264bfec3c702d17152f0b6a"
    roots = [("project", checkout), ("batch", batch), ("canonical", canonical)]
    roots.extend((label, Path(value)) for label, value in (item.split("=", 1) for item in args.map))
    replacements = {}
    for label, path in roots:
        raw = str(path)
        variants = {raw, path.as_posix()}
        if path.drive:
            variants.add("/mnt/" + path.drive[0].lower() + path.as_posix()[2:])
        # Retain the original console mojibake as a bounded path-only projection.
        variants.update(v.encode("gbk", errors="replace").decode("utf-8", errors="replace") for v in list(variants))
        for variant in variants:
            encoded = {variant, json.dumps(variant, ensure_ascii=True)[1:-1]}
            for _ in range(3):
                encoded.update(v.replace(chr(92), chr(92) * 2) for v in list(encoded))
            for value in encoded:
                replacements[value] = "[" + label + "]"
    replacements = sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True)

    def project(text, destination):
        # Review links to the old canonical stay pinned to the actual reviewed base.
        for root, fixed in ((canonical, True), (checkout, False)):
            prefix = root.as_posix() + "/"
            pattern = re.compile(r"<" + re.escape(prefix) + r"([^>]+)>")

            def link(match):
                value = match.group(1)
                line = re.search(r":(\d+)$", value)
                suffix = "#L" + line.group(1) if line else ""
                path = value[:line.start()] if line else value
                if fixed:
                    target = "https://github.com/RoboSynth/multi-agent-interconnect/blob/" + base + "/" + quote(path, safe="/")
                else:
                    target = Path(os.path.relpath(checkout / path, destination.parent)).as_posix()
                    target = quote(target, safe="/.")
                return "<" + target + suffix + ">"

            text = pattern.sub(link, text)
        for original, replacement in replacements:
            text = text.replace(original, replacement)
        # Forward slashes in the projected path suffix also avoid UNC-looking
        # escaped separators in JSON/log representations. Other text is intact.
        labels = "|".join(re.escape("[" + label + "]") for label, _ in roots)
        text = re.sub(r"(?:" + labels + r")([^\s\"'<>]*)",
                      lambda match: re.sub(re.escape(chr(92)) + r"+(?=[A-Za-z_.-])", "/", match.group()), text)
        return text

    names = {"root-validation-summary.json", "root-validation-summary-r1.json", "profile-prepared.json",
             "compose-check-provenance.json", "deployment-validation/summary.json", "scanner-provenance.txt",
             "image-build/result.json", "image-build/build.stdout.log", "app-image-build/result.json",
             "app-image-build/build.stdout.log", "image-attestation/summary.json", "image-attestation/closure.json",
             "image-attestation/failure-diagnostic.json", "image-attestation-final/summary.json",
             "image-attestation-final/stdout.json", "image-attestation-final/expected.json"}
    for folder in ("review", "recovery-evidence", "native-down-evidence", "report-evidence"):
        for path in (batch / folder).rglob("*"):
            if path.is_file() and path.suffix in {".json", ".md", ".log", ".txt"}:
                names.add(path.relative_to(batch).as_posix())
    bindings = []
    for name in sorted(names):
        source, target = batch / name, output / name
        raw = source.read_bytes()
        original_text = raw.decode("utf-8-sig")
        if source.suffix == ".json":
            def walk(value):
                if isinstance(value, str):
                    return project(value, target)
                if isinstance(value, list):
                    return [walk(item) for item in value]
                if isinstance(value, dict):
                    return {key: walk(item) for key, item in value.items()}
                return value
            original_object = json.loads(original_text)
            projected = walk(original_object)
            published = (json.dumps(projected, ensure_ascii=False, indent=2) + "\n").encode("utf-8") if projected != original_object else raw
        else:
            published = project(original_text, target).encode("utf-8")
        # Preserve untouched original bytes, including BOM and newline choices.
        if published == raw.removeprefix(b"\xef\xbb\xbf"):
            published = raw
        if source.suffix == ".json":
            json.loads(published)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(published)
        bindings.append({"source_relative_to_batch": name, "published_path": name,
                         "original_bytes": len(raw), "original_sha256": sha(raw),
                         "published_bytes": len(published), "published_sha256": sha(published),
                         "path_projection_applied": published != raw})
    receipt = {"schema_version": "access-durability-publication/1", "base_commit": base,
               "selection": "explicit source validation, build, probe, recovery, shutdown and report JSON Markdown and logs; excludes databases, private TLS and binary stderr",
               "transform": "bounded local path projection and review-link conversion only; original sources remain unchanged",
               "hash_semantics": "summary-embedded SHA values bind original artifact bytes; bindings below map them to projected publication bytes",
               "publisher_sha256": sha(Path(__file__).read_bytes()),
               "files": bindings, "source_files_modified": False}
    (output / "publication-bindings.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tooling = output / "tooling"
    tooling.mkdir(exist_ok=True)
    (tooling / "publish_evidence.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"published_files": len(bindings), "projected_files": sum(b["path_projection_applied"] for b in bindings)}))


if __name__ == "__main__":
    main()
