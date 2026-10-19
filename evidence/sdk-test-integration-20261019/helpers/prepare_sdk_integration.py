"""Bind three existing PR test blobs and prepare one current complete SDK copy."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE / "checkout"
ARTIFACTS = HERE.parent
VENDOR = ROOT / "vendor/ACPs-community"
SDK = VENDOR / "acps-sdk"
OUT = HERE / "sdk-integration-evidence"
GIT = Path(sys.base_prefix).parent / "native/git/cmd/git.exe"
SOURCES = (
    ("resumable", "09fe13bd699f4a9df279507ed23861f6f817babe", "acps-sdk/tests/aip/test_task_ordering.py", "cd8573acaac6a0b754039dc63b619aaf1496997f4332cd331f0725012c674411"),
    ("message-emitter", "72a994bfb8cd5cc832beb0204a4715a2c090f983", "acps-sdk/tests/amp/test_message_emitter_concurrency.py", "12c4eb6a6879da7932cc29eb1b3b4a32d4dffe6f030549f83d87348f92806136"),
    ("resumable", "09fe13bd699f4a9df279507ed23861f6f817babe", "acps-sdk/tests/amp/test_amp_metrics_emitter.py", "559812c1ed5bc2bad5c381e3a0a64c38664f75a8216d7136bb49666d20265e09"),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write(name, value):
    with (OUT / name).open("xb") as stream:
        stream.write(encoded(value))


def git(repo, *args):
    return subprocess.run([str(GIT), "--no-optional-locks", "-C", str(repo), *args],
                          capture_output=True, check=True, timeout=120).stdout


def main():
    assert git(ROOT, "rev-parse", "HEAD").decode().strip() == "613ecbfc6e7500a30264bfec3c702d17152f0b6a"
    OUT.mkdir(exist_ok=False)
    names = [p for p in git(ROOT, "ls-files", "-z", "--", "vendor/ACPs-community/acps-sdk/").decode().split("\0") if p]
    original = {p: (ROOT / p).read_bytes() for p in names}
    runtime_before = {p: sha(data) for p, data in original.items() if "/acps_sdk/" in p}
    integration = []
    for label, commit, path, expected in SOURCES:
        source = ARTIFACTS / f"upstream-public-submission-20261018/branch-{label}"
        assert git(source, "rev-parse", "HEAD").decode().strip() == commit
        data = git(source, "show", commit + ":" + path)
        assert sha(data) == expected and (source / path).read_bytes() == data
        blob = git(source, "rev-parse", commit + ":" + path).decode().strip()
        target = VENDOR / path
        before = target.read_bytes() if target.exists() else None
        if path.endswith("test_amp_metrics_emitter.py"):
            assert before is not None and sha(before) == "30fd9af5a358388adb43b0dd8044f6317dfe482dab37762e7b692d8ce7c0542f"
        else:
            assert before is None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        integration.append(dict(path="vendor/ACPs-community/" + path, source_commit=commit,
            source_branch=label, git_blob_oid=blob, source_sha256=sha(data), installed_sha256=sha(target.read_bytes()),
            previous_sha256=sha(before) if before is not None else None, bytes=len(data)))
    runtime_after = {p: sha((ROOT / p).read_bytes()) for p in runtime_before}
    assert runtime_before == runtime_after
    all_names = sorted(set(names) | {"vendor/ACPs-community/" + path for _, _, path, _ in SOURCES})
    manifest = {p.removeprefix("vendor/ACPs-community/"): sha((ROOT / p).read_bytes()) for p in all_names}
    tree = OUT / "suite-copy"
    for relative, expected in manifest.items():
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(VENDOR / relative, target)
        assert sha(target.read_bytes()) == expected
    tls_helper = ARTIFACTS / "upstream-full-suite-20261018/prepare_suite_trees.py"
    spec = importlib.util.spec_from_file_location("sdk_original_tls_preparer", tls_helper)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    tls_files, public_tls = module.make_tls()
    for relative, data in tls_files.items():
        target = tree / relative
        assert not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    locked = ARTIFACTS / "upstream-full-suite-20261018/locked-dependencies"
    locked_audit = ARTIFACTS / "upstream-full-suite-20261018/locked-dependency-audit.json"
    audit = json.loads(locked_audit.read_bytes())
    assert audit["status"] == "ISOLATED_LOCKED_DEPENDENCY_GRAPH_VALIDATED" and not audit["problems"]
    write("source-manifest.json", dict(schema_version="current-sdk-test-integration/1", source_base="613ecbfc6e7500a30264bfec3c702d17152f0b6a",
        source_sha256=manifest, sdk_files=len(manifest), runtime_sha256=runtime_before,
        installed_test_blobs=integration, runtime_unchanged=True, sdk_tests_executed=False))
    write("public-tls.json", public_tls)
    write("preparation.json", dict(status="CURRENT_SDK_COMPLETE_SUITE_PREPARED_NOT_EXECUTED",
        root=str(ROOT), suite_tree=str(tree), isolated_dependencies=str(locked),
        preparation_script_sha256=sha(Path(__file__).read_bytes()), tls_generator_sha256=sha(tls_helper.read_bytes()),
        locked_dependency_audit_sha256=sha(locked_audit.read_bytes()),
        dependency_versions=audit["installed_distributions"],
        source_manifest_sha256=sha((OUT / "source-manifest.json").read_bytes()),
        public_tls_sha256=sha((OUT / "public-tls.json").read_bytes()),
        synthetic_fixture_sha256={p:sha(data) for p,data in tls_files.items()},
        private_keys_local_only=True, registered_platform_credentials_used=False,
        completed_at_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(status="CURRENT_SDK_COMPLETE_SUITE_PREPARED_NOT_EXECUTED", sdk_files=len(manifest),
                         test_files_integrated=len(integration), runtime_unchanged=True)))


if __name__ == "__main__":
    main()
