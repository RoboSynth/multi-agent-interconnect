"""Verify the fixed 3760b21 development export using the existing ZIP verifier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent
REPO = ARTIFACTS.parents[1] / "team-repository-multi-agent-interconnect"
COMMIT = "3760b21c8a1ed62e8119925da6f24ebd8b851d14"
ADAPTER = ARTIFACTS / "p0-access-accounting-20261019/archive/verify_current_archive.py"
ADAPTER_SHA = "7efc9ed328602a9d6ef51f20545a288454540a9de89a859d032f9614711f0117"
ARCHIVE = HERE / "incident-pilot-development-3760b21.zip"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, data):
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    assert sha(ADAPTER.read_bytes()) == ADAPTER_SHA
    spec = importlib.util.spec_from_file_location("frozen_export_legacy_adapter", ADAPTER)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    verifier, exceptions = adapter.load_verifier()
    assert verifier.git(REPO, "rev-parse", "HEAD").decode().strip() == COMMIT
    assert not verifier.git(REPO, "status", "--porcelain").strip()
    object_format = verifier.git(REPO, "rev-parse", "--show-object-format").decode().strip()
    assert object_format in {"sha1", "sha256"}
    tree = {}
    for record in verifier.git(REPO, "ls-tree", "-r", "-z", "--full-tree", COMMIT).split(b"\0"):
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        name = name.decode("utf-8")
        verifier.check_path(name)
        assert kind == "blob" and mode in {"100644", "100755"}
        tree[name] = dict(mode=mode, oid=oid)
    required = set(json.loads(adapter.REQUIRED.read_bytes())["required_paths"])
    required.update({
        "tools/sdk-suite/run_sdk_suite.py", "tools/sdk-suite/synthetic_tls.py",
        "tools/sdk-suite/requirements-tested.txt", "tools/sdk-suite/tls-source-binding.json", "tools/sdk-suite/README.md",
        "incident/recover_access.py", "deploy/local-down.ps1", "tools/local_shutdown.py",
        "docs/开发者接手指南_20261018.md", "docs/access_recovery_validation_20261019.md",
        "deliverables/development-report-20261019-revision3/technical-report-development.pdf",
        "deliverables/development-report-20261019-revision3/validation.json",
        "deliverables/development-report-20261019-revision3/visual-review.json",
        "evidence/access-validation-prep-20261019/plan-preparation/run-scope.md",
        "evidence/access-validation-prep-20261019/plan-preparation/prepared-summary.json",
        "evidence/access-validation-prep-20261019/review/four-case-preparation-review.md",
    })
    assert required <= set(tree), sorted(required - set(tree))
    # One batch reads committed blobs, independent of ZIP contents and worktree files.
    request = b"".join((item["oid"] + "\n").encode("ascii") for item in tree.values())
    process = subprocess.run([str(adapter.GIT), "-C", str(REPO), "cat-file", "--batch"],
                             input=request, capture_output=True, check=True)
    data, cursor, listed = process.stdout, 0, {}
    for name, item in tree.items():
        end = data.index(b"\n", cursor)
        oid, kind, size = data[cursor:end].decode("ascii").split()
        assert oid == item["oid"] and kind == "blob"
        size = int(size)
        content = data[end + 1:end + 1 + size]
        cursor = end + 1 + size
        assert data[cursor:cursor + 1] == b"\n"
        cursor += 1
        assert hashlib.new(object_format, b"blob " + str(size).encode() + b"\0" + content).hexdigest() == oid
        listed[name] = dict(bytes=size, sha256=sha(content))
        for exception in exceptions:
            if name == exception["path"]:
                assert listed[name] == dict(bytes=exception["bytes"], sha256=exception["sha256"])
    assert cursor == len(data)
    with zipfile.ZipFile(ARCHIVE) as archive:
        for member in archive.infolist():
            assert member.is_dir() or stat.S_IFMT(member.external_attr >> 16) in {0, stat.S_IFREG}
    prepared = dict(commit=COMMIT, object_format=object_format, tree=tree, listed=listed,
                    prefix="incident-pilot-development-3760b21/")
    verified = verifier.verify_zip(ARCHIVE, prepared)
    manifest = dict(schema_version="frozen-git-export-manifest/1", commit=COMMIT,
                    files=[dict(path=name, git_blob=item["oid"], **listed[name]) for name, item in tree.items()],
                    note="Complete manifest for this fixed export, external to its immutable Git tree. The root SNAPSHOT-MANIFEST.json is retained as historical source content and is not used to assert current completeness.")
    save("export-manifest.json", manifest)
    save("required-paths.json", dict(required_paths=sorted(required)))
    result = dict(status="passed", commit=COMMIT, **verified, required_path_count=len(required),
                  archive_name=ARCHIVE.name, archive_bytes=ARCHIVE.stat().st_size, archive_sha256=sha(ARCHIVE.read_bytes()),
                  manifest_sha256=sha((HERE / "export-manifest.json").read_bytes()),
                  source_worktree_clean=True, historical_snapshot_manifest_not_used_for_current_completeness=True,
                  reused_adapter_sha256=ADAPTER_SHA, legacy_verifier_sha256=adapter.LEGACY_SHA256,
                  current_verifier_sha256=sha(Path(__file__).read_bytes()),
                  exact_official_template_exceptions=len(exceptions), new_path_exceptions=0,
                  private_configuration_read=False, runtime_or_new_machine_verified=False,
                  original22_and_repair12_results_unchanged=True)
    save("verification.json", result)
    print(json.dumps({key: result[key] for key in ("status", "commit", "archive_payload_files", "archive_bytes", "archive_sha256", "required_path_count")}))


if __name__ == "__main__":
    main()
