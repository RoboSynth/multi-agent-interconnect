"""Read existing Git objects; write only an explicit new artifact directory.

No fetch, index, commit, credential helper, import of SDK, or runtime tests.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

CANONICAL = "3760b21c8a1ed62e8119925da6f24ebd8b851d14"
IMPLEMENTATION = "3985c1330209f075c124669cc9d31f0e75448140"
BASE = "94077d10b336bfdb9a7d68e4859390bf44a67a27"
PR13 = "09fe13bd699f4a9df279507ed23861f6f817babe"
PR14 = "72a994bfb8cd5cc832beb0204a4715a2c090f983"
VENDOR = "vendor/ACPs-community/"
SDK = "acps-sdk/"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def oid(kind, data):
    return hashlib.sha1(kind.encode() + b" " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_tree(repo, ref, prefix=""):
    result = {}
    args = ("ls-tree", "-r", "-z", ref, "--", prefix) if prefix else ("ls-tree", "-r", "-z", ref)
    for entry in git(repo, *args).split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        path = path.decode("utf-8")
        if kind != "blob":
            raise ValueError((path, kind))
        result[path[len(prefix):]] = {"mode": mode, "oid": blob}
    return result


def blobs(repo, entries):
    unique = sorted({row["oid"] for row in entries.values()})
    request = ("\n".join(unique) + "\n").encode()
    raw = subprocess.check_output(["git", "-C", str(repo), "cat-file", "--batch"], input=request)
    offset = 0
    result = {}
    for expected in unique:
        end = raw.index(b"\n", offset)
        actual, kind, count = raw[offset:end].decode().split()
        size = int(count)
        assert actual == expected and kind == "blob"
        data = raw[end + 1:end + 1 + size]
        assert raw[end + 1 + size:end + 2 + size] == b"\n"
        offset = end + 2 + size
        result[expected] = data
    assert offset == len(raw)
    return {path: result[row["oid"]] for path, row in entries.items()}


def lf(data):
    return data.replace(b"\r\n", b"\n")


def tree_oid(entries):
    root = {}
    for path, entry in entries.items():
        parent = root
        parts = path.split("/")
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
        assert parts[-1] not in parent
        parent[parts[-1]] = (entry["mode"], entry["oid"])

    def visit(node):
        items = []
        for name, value in node.items():
            if isinstance(value, dict):
                mode, obj = "40000", visit(value)
                sortkey = name.encode() + b"/"
            else:
                mode, obj = value
                sortkey = name.encode()
            items.append((sortkey, mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(obj)))
        data = b"".join(row[1] for row in sorted(items))
        return oid("tree", data)

    return visit(root)


def stats(data):
    return dict(sha256=sha(data), lf_sha256=sha(lf(data)), bytes=len(data), crlf=data.count(b"\r\n"),
                git_blob_oid=oid("blob", data))


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_patch(path, before, after, before_meta, after_meta):
    chunks = []
    changed = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        changed.append(name)
        chunks.append(f"diff --git a/{name} b/{name}\n".encode())
        if old is None:
            chunks.append(f"new file mode {after_meta[name]['mode']}\n".encode())
        if new is None:
            chunks.append(f"deleted file mode {before_meta[name]['mode']}\n".encode())
        old_oid = "0" * 40 if old is None else oid("blob", old)
        new_oid = "0" * 40 if new is None else oid("blob", new)
        chunks.append(f"index {old_oid}..{new_oid}\n".encode())
        a_name = b"/dev/null" if old is None else ("a/" + name).encode()
        b_name = b"/dev/null" if new is None else ("b/" + name).encode()
        for line in difflib.diff_bytes(difflib.unified_diff, (old or b"").splitlines(keepends=True),
                                      (new or b"").splitlines(keepends=True), fromfile=a_name, tofile=b_name):
            chunks.append(line)
            if not line.endswith(b"\n"):
                chunks.append(b"\n\\ No newline at end of file\n")
    path.write_bytes(b"".join(chunks))
    return dict(path=path.name, sha256=sha(path.read_bytes()), bytes=path.stat().st_size,
                changed_files=len(changed), paths=changed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", type=Path, required=True)
    ap.add_argument("--implementation-repo", type=Path, required=True)
    ap.add_argument("--fork13", type=Path, required=True)
    ap.add_argument("--fork14", type=Path, required=True)
    ap.add_argument("--tested-manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(exist_ok=False)
    before_status = git(args.canonical, "status", "--porcelain=v1", "--untracked-files=all")
    assert git(args.canonical, "rev-parse", "HEAD").decode().strip() == CANONICAL
    assert before_status == b"", "Canonical must be clean"
    sources = {}
    for label, repo, ref, prefix in (
        ("official-implementation", args.implementation_repo, IMPLEMENTATION, SDK),
        ("official-pr-base", args.fork13, BASE, SDK),
        ("pr13", args.fork13, PR13, SDK),
        ("pr14", args.fork14, PR14, SDK),
        ("canonical", args.canonical, CANONICAL, VENDOR + SDK),
    ):
        entries = read_tree(repo, ref, prefix)
        data = blobs(repo, entries)
        assert tree_oid(entries) == git(repo, "rev-parse", ref + ":" + prefix.rstrip("/")).decode().strip()
        sources[label] = dict(entries=entries, data=data, ref=ref, prefix=prefix)
    base = sources["official-pr-base"]
    old = sources["official-implementation"]
    pr13, pr14, current = (sources[k] for k in ("pr13", "pr14", "canonical"))
    assert base["data"] == old["data"], "Official baseline SDK differs"
    tested = json.loads(args.tested_manifest.read_text(encoding="utf-8"))["source_sha256"]
    assert set(tested) == {SDK + p for p in current["data"]}
    worktree = {}
    for path, data in current["data"].items():
        raw = (args.canonical / VENDOR / SDK / path).read_bytes()
        assert data == raw and sha(raw) == tested[SDK + path], path
        worktree[path] = raw
    composite = dict(pr13["data"])
    composite_meta = dict(pr13["entries"])
    pr14_selected = ("acps_sdk/amp/message_emitter.py", "tests/amp/test_message_emitter_concurrency.py")
    for path in pr14_selected:
        composite[path] = pr14["data"][path]
        composite_meta[path] = pr14["entries"][path]
    assert pr13["data"]["tests/amp/test_amp_metrics_emitter.py"] == pr14["data"]["tests/amp/test_amp_metrics_emitter.py"]
    normalized = {p: lf(b) for p, b in current["data"].items()}
    normalized_meta = {p: {"mode": current["entries"][p]["mode"], "oid": oid("blob", b)}
                       for p, b in normalized.items()}
    inventory, delta = [], []
    for path in sorted(current["data"].keys() | composite.keys()):
        raw = current["data"].get(path)
        row = dict(path=SDK + path, sources={})
        for label, source in sources.items():
            data = source["data"].get(path)
            row["sources"][label] = stats(data) if data is not None else None
        row["composite"] = stats(composite[path]) if path in composite else None
        row["same_as_composite_lf"] = raw is not None and path in composite and lf(raw) == lf(composite[path])
        row["normalized_candidate"] = stats(normalized[path]) if raw is not None else None
        if not row["same_as_composite_lf"]:
            delta.append(row)
        inventory.append(row)

    def prefix(mapping):
        return {SDK + p: value for p, value in mapping.items()}

    patches = []
    for label, source_data, source_meta in (("official", base["data"], base["entries"]),
                                            ("pr13", pr13["data"], pr13["entries"]),
                                            ("pr13-plus-pr14", composite, composite_meta)):
        for target_label, target_data, target_meta in (("lf-minimal", normalized, normalized_meta),
                                                      ("raw-exact", current["data"], current["entries"])):
            patches.append(write_patch(args.output / f"{label}-to-{target_label}.patch",
                                       prefix(source_data), prefix(target_data), prefix(source_meta), prefix(target_meta)))
    full_base = read_tree(args.fork13, BASE)
    assert tree_oid(full_base) == git(args.fork13, "rev-parse", BASE + "^{tree}").decode().strip()
    full_base_without_sdk = {p: e for p, e in full_base.items() if not p.startswith(SDK)}
    candidates = {}
    for label, metadata in (("lf-minimal", normalized_meta), ("raw-exact", current["entries"])):
        whole = dict(full_base_without_sdk)
        whole.update(prefix(metadata))
        candidates[label] = dict(sdk_tree_oid=tree_oid(metadata), whole_repository_tree_oid=tree_oid(whole),
                                 sdk_files=len(metadata), root_files=len(whole),
                                 actual_commit_oid=None, commit_created=False, public_branch_created=False)
    official_license = git(args.fork13, "show", BASE + ":LICENSE")
    sdk_license = base["data"]["LICENSE"]
    assert lf(official_license) == lf(sdk_license) == lf(current["data"]["LICENSE"])
    licenses = dict(spdx_id="MulanPSL-2.0", official_root=stats(official_license),
                    official_sdk=stats(sdk_license), current_vendor_sdk=stats(current["data"]["LICENSE"]),
                    normalized_candidate_sdk=stats(normalized["LICENSE"]),
                    pyproject_license_line='license = "MulanPSL-2.0"',
                    repository_global_license_selected=False)
    write_json(args.output / "inventory.json", dict(schema_version="sdk-final-binding-inventory/1",
        canonical=CANONICAL, official_implementation=IMPLEMENTATION, official_pr_base=BASE,
        pr13=PR13, pr14=PR14, per_file=inventory))
    write_json(args.output / "delta-after-two-prs.json", dict(files=len(delta), per_file=delta))
    write_json(args.output / "candidate-bindings.json", dict(schema_version="sdk-candidate-bindings/1",
        canonical=CANONICAL, candidates=candidates, patches=patches,
        exact_tested_raw_sdk_tree_oid=tree_oid(current["entries"]),
        tested_manifest_sha256=sha(args.tested_manifest.read_bytes()),
        inventory_sha256=sha((args.output / "inventory.json").read_bytes()),
        original_bytes_equal_to_tested=True,
        original_file_bytes_equal_to_canonical_git=True,
        normalized_candidate_was_runtime_tested=False,
        normalization="CRLF -> LF only; raw-exact retains all source bytes", licenses=licenses))
    assert git(args.canonical, "status", "--porcelain=v1", "--untracked-files=all") == before_status
    assert git(args.canonical, "rev-parse", "HEAD").decode().strip() == CANONICAL
    write_json(args.output / "read-only-verification.json", dict(status="READ_ONLY_COMPARISON_COMPLETE",
        canonical_clean_before_after=True, files_matched_tested_manifest=len(current["data"]),
        official_implementation_sdk_equals_pr_base=True,
        composite_files=len(composite), semantic_delta_files=len(delta),
        sdk_runtime_or_collection_calls=0, git_index_writes=0, git_object_writes=0,
        network_calls=0, official_licenses_preserved=True,
        candidates=candidates,
        semantic_delta_paths=[row["path"] for row in delta]))
    print(json.dumps(dict(status="READ_ONLY_COMPARISON_COMPLETE", sdk_files=len(current["data"]),
                         composite_files=len(composite), semantic_delta_files=len(delta), candidates=candidates), ensure_ascii=False))


if __name__ == "__main__":
    main()
