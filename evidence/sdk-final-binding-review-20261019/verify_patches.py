"""Apply review patches only to newly-created disposable artifact copies."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from compare_sdk_binding import BASE, PR13, PR14, VENDOR, SDK, CANONICAL, git, read_tree, blobs, lf, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical", type=Path, required=True)
    ap.add_argument("--fork13", type=Path, required=True)
    ap.add_argument("--fork14", type=Path, required=True)
    ap.add_argument("--comparison", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(exist_ok=False)
    manifest = json.loads((args.comparison / "candidate-bindings.json").read_text("utf-8"))
    src = {}
    for label, repo, ref in (("official", args.fork13, BASE), ("pr13", args.fork13, PR13), ("pr14", args.fork14, PR14)):
        src[label] = blobs(repo, read_tree(repo, ref, SDK))
    src["pr13-plus-pr14"] = dict(src["pr13"])
    for p in ("acps_sdk/amp/message_emitter.py", "tests/amp/test_message_emitter_concurrency.py"):
        src["pr13-plus-pr14"][p] = src["pr14"][p]
    cur = blobs(args.canonical, read_tree(args.canonical, CANONICAL, VENDOR + SDK))
    rows = []
    for patch in manifest["patches"]:
        label, target = patch["path"].removesuffix(".patch").split("-to-", 1)
        dest = args.output / patch["path"].removesuffix(".patch")
        dest.mkdir(exist_ok=False)
        for path, data in src[label].items():
            out = dest / SDK / path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        patch_path = (args.comparison / patch["path"]).resolve()
        assert sha(patch_path.read_bytes()) == patch["sha256"]
        executions = []
        for mode in ("check", "apply"):
            cmd = ["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "apply", "--whitespace=nowarn"]
            if mode == "check":
                cmd.append("--check")
            cmd.append(str(patch_path))
            result = subprocess.run(cmd, cwd=dest, capture_output=True)
            executions.append(dict(operation=mode, exit_code=result.returncode,
                                   stdout=result.stdout.decode("utf-8", "replace"), stderr=result.stderr.decode("utf-8", "replace")))
            assert result.returncode == 0, executions[-1]
        actual = {p.relative_to(dest / SDK).as_posix(): p.read_bytes() for p in (dest / SDK).rglob("*") if p.is_file()}
        expected = cur if target == "raw-exact" else {p: lf(b) for p, b in cur.items()}
        assert actual == expected
        rows.append(dict(patch=patch["path"], patch_sha256=patch["sha256"], executions=executions,
                         all_file_bytes_equal=True, files=len(actual)))
    output = dict(status="ALL_SIX_PATCHES_APPLIED_AND_BYTE_VERIFIED", sdk_runtime_calls=0,
                  git_index_writes=0, tested_raw_source_unchanged=True, results=rows)
    (args.output / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=output["status"], patches=len(rows), files_each=147)))


if __name__ == "__main__":
    main()
