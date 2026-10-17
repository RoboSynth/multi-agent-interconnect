"""Export a reviewable SDK patch and a deterministic source overlay.

Default operation is a read-only inventory. Pass --export only after the source
freeze. The baseline is always read-only; running services/private state are
never copied. The overlay requires the named baseline's SDK and integration
helpers, then applies the included SDK patch.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE_NAME = "incident-v0.2.0-20261017T045307Z"
SDK_PREFIX = Path("vendor/ACPs-community/acps-sdk")
SOURCE_DIRECTORIES = ("business", "incident", "acps_mcp_bridge", "acps-mcp-bridge", "domains", "deploy", "eval", "tests", "ops")
ROOT_FILES = ("workbench_server.py", "requirements-high-score.txt", "requirements-lock.txt", "README.md", ".gitignore", ".dockerignore")
UI_FILES = ("demo-ui/workbench.html", "demo-ui/workbench.js", "demo-ui/workbench.css")
TOOL_FILES = ("tools/download_native_runtime.py", "tools/prepare_native_database.py", "tools/configure_local_coordinator.py",
              "tools/start_workbench.ps1", "tools/export_high_score_patch.py", "tools/local_model.py",
              "tools/edge-wutong.ps1", "tools/edge-register-form.ps1", "tools/edge-submit-new-agent.ps1")
DOC_FILES = ("docs/高分方案_需求架构创新与任务_20261017.md", "docs/本地开发验收.md", "docs/开发进度_高分方案.md",
             "docs/P0完成审计_20261017.md", "docs/新版平台接入准备.md", "docs/platform_worker.md")
PUBLIC_DEPENDENCIES = ("integration/validate_acs.py", "vendor/ACPs-community/registry-server/app/agent/acsSchema.json")
SOURCE_SUFFIXES = {".py", ".ps1", ".sh", ".sql", ".yaml", ".yml", ".toml", ".json", ".md", ".txt",
                   ".html", ".css", ".js", ".ts", ".ini", ".cfg", ".conf", ".rst", ".typed"}
DENIED_DIRECTORIES = {"private", "runtime", "artifacts", "results", "output", "baselines", "__pycache__", ".git",
                      ".agents", ".codex", ".cache", ".pytest_cache", "node_modules", "dist", "build",
                      "certs", "certificates", "credentials", "secrets"}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def forbidden(relative):
    parts = tuple(part.lower() for part in Path(relative).parts)
    if any(part in DENIED_DIRECTORIES or part.startswith(".venv") or part.endswith(".egg-info") for part in parts):
        return True
    name = parts[-1] if parts else ""
    # Include no live environment files, including .env templates. Required
    # variable names remain documented; credentials are generated at deployment.
    return name == "native-runtime.json" or name == ".env" or name.startswith(".env.") or name.endswith(".env")


def source_name(path):
    return path.suffix.lower() in SOURCE_SUFFIXES or path.name in {"Dockerfile", "Dockerfile.agent", "Dockerfile.docker-mcp", "LICENSE", "LICENSE.md", "MANIFEST.in", ".gitignore", ".dockerignore"}


def reparse_point(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def walk_source(base, relative):
    directory = base / relative
    if not directory.is_dir() or reparse_point(directory):
        return
    for parent, names, files in os.walk(directory, followlinks=False):
        parent = Path(parent)
        names[:] = sorted(name for name in names if not forbidden((parent / name).relative_to(base)) and not reparse_point(parent / name))
        for name in sorted(files):
            path = parent / name
            rel = path.relative_to(base)
            if not forbidden(rel) and source_name(path) and not reparse_point(path):
                yield rel


def source_paths(root):
    paths = set()
    for directory in SOURCE_DIRECTORIES:
        paths.update(walk_source(root, Path(directory)))
    for name in (*ROOT_FILES, *UI_FILES, *TOOL_FILES, *DOC_FILES, *PUBLIC_DEPENDENCIES):
        path = root / name
        if path.is_file() and not forbidden(Path(name)) and not reparse_point(path):
            paths.add(Path(name))
    return sorted(paths, key=lambda path: path.as_posix())


def read_source(path):
    before = path.stat()
    content = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Source changed while reading: {path.name}; freeze changes and retry")
    if b"\0" in content:
        raise ValueError(f"Unexpected binary file in source allowlist: {path.name}")
    content.decode("utf-8-sig")
    return content


def sdk_patch(root, baseline):
    before_paths = set(walk_source(baseline, SDK_PREFIX))
    after_paths = set(walk_source(root, SDK_PREFIX))
    chunks, changes = [], []
    for relative in sorted(before_paths | after_paths, key=lambda path: path.as_posix()):
        before = read_source(baseline / relative) if relative in before_paths else b""
        after = read_source(root / relative) if relative in after_paths else b""
        if before == after:
            continue
        name = relative.as_posix()
        added, deleted = relative not in before_paths, relative not in after_paths
        chunks.append(f"diff --git a/{name} b/{name}\n".encode())
        if added:
            chunks.append(b"new file mode 100644\n")
        if deleted:
            chunks.append(b"deleted file mode 100644\n")
        for line in difflib.diff_bytes(difflib.unified_diff, before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=b"/dev/null" if added else ("a/" + name).encode(),
                tofile=b"/dev/null" if deleted else ("b/" + name).encode(), lineterm=b"\n"):
            if line.endswith(b"\n"):
                chunks.append(line)
            else:
                chunks.append(line + b"\n\\ No newline at end of file\n")
        changes.append({"path": name, "change": "added" if added else "deleted" if deleted else "modified",
                        "baseline_sha256": None if added else digest(before), "source_sha256": None if deleted else digest(after),
                        "baseline_bytes": len(before), "source_bytes": len(after)})
    return b"".join(chunks), changes


def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def deterministic_zip(entries):
    """Stored entries avoid zlib-version differences; no wall-clock metadata."""
    import io
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Archive member is not a safe relative path")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, entries[name])
    return output.getvalue()


def prepare_export(root, baseline):
    if not (baseline / SDK_PREFIX).is_dir():
        raise ValueError("Baseline is missing the pinned SDK snapshot")
    patch, changes = sdk_patch(root, baseline)
    entries, inventory, added, changed = {}, [], [], []
    for relative in source_paths(root):
        name = relative.as_posix()
        content = read_source(root / relative)
        entries[name] = content
        before = baseline / relative
        before_content = read_source(before) if before.is_file() else None
        state = "added" if before_content is None else "unchanged" if before_content == content else "modified"
        inventory.append({"path": name, "bytes": len(content), "sha256": digest(content), "change_from_snapshot": state})
        if state == "added":
            added.append(name)
        elif state == "modified":
            changed.append(name)
    manifest = {"format": "incident-pilot-source-overlay/1", "baseline": baseline.name,
        "sdk_comparison": "Exact UTF-8 source bytes against the read-only baseline snapshot",
        "sdk_patch_sha256": digest(patch), "sdk_changes": changes, "source_files": inventory,
        "new_files": added, "modified_files": changed,
        "zip_reproducibility": "Sorted entries; fixed 1980 UTC timestamp and 0644 mode; ZIP_STORED; no timestamps or absolute paths in manifest",
        "exclusions": {"directories": sorted(DENIED_DIRECTORIES), "environment_files": "All .env/.env.*/*.env files are excluded",
                       "other": [".venv*", "reparse points/symlinks", "certificates/private keys", "compiled/binary archives", "legacy UI"]}}
    entries["patches/acps-sdk-high-score.patch"] = patch
    entries["EXPORT.json"] = canonical_json(manifest)
    entries["EXPORT-README.txt"] = (
        "Incident Pilot high-score source overlay\n\n"
        f"Baseline: {baseline.name}\n"
        "Extract this archive over a COPY of the named baseline/project. Keep the saved baseline unchanged.\n"
        "Apply patches/acps-sdk-high-score.patch from the project root with git -c core.autocrlf=false apply --check, then git -c core.autocrlf=false apply.\n"
        "The baseline provides the pinned SDK, existing integration/wutong_smoke.py and related baseline helpers.\n"
        "Only the source allowlist is included. This is not a credentials/data/runtime/evidence backup.\n"
        "Create resource-domain environment files locally; follow docs/本地开发验收.md and deploy/README.md.\n"
        "For Docker create deploy/.env locally with POSTGRES_PASSWORD, ORDERS_DB_PASSWORD, APP_ADMIN_TOKEN; even .env.example is excluded.\n"
        "Official runtimes, Python environments, certificates, private state and historical results are deliberately excluded.\n"
        "No deployment or platform verification is implied by a successful export.\n"
        "Identical selected source bytes and baseline bytes produce byte-identical ZIP and manifest.\n"
    ).encode("utf-8")
    return entries, patch, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/high-score-source-export")
    parser.add_argument("--export", action="store_true", help="Write immutable export artifacts after the source freeze")
    args = parser.parse_args()
    root = args.root.resolve()
    baseline = (args.baseline or root / "baselines" / BASELINE_NAME).resolve()
    entries, patch, manifest = prepare_export(root, baseline)
    summary = {"mode": "export" if args.export else "inventory_only", "baseline": baseline.name,
               "source_files": len(manifest["source_files"]), "sdk_changed_files": len(manifest["sdk_changes"]),
               "new_source_files": len(manifest["new_files"]), "sdk_patch_bytes": len(patch)}
    if not args.export:
        print(json.dumps(summary))
        return
    output = args.output.resolve()
    if output == baseline or output.is_relative_to(baseline) or output == root:
        raise ValueError("Export output must not replace the baseline or project root")
    output.mkdir(parents=True, exist_ok=False)
    zip_bytes = deterministic_zip(entries)
    files = {"acps-sdk-high-score.patch": patch, "source-manifest.json": canonical_json(manifest),
             "new-source-files.txt": ("\n".join(manifest["new_files"]) + "\n").encode("utf-8"),
             "high-score-source-overlay.zip": zip_bytes}
    for name, content in files.items():
        (output / name).write_bytes(content)
    summary.update(output=str(output), zip_bytes=len(zip_bytes), zip_sha256=digest(zip_bytes))
    (output / "EXPORT-RESULT.json").write_bytes(canonical_json(summary))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
