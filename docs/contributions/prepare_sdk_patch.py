"""Export SDK-only review evidence from the frozen v0.2 snapshot.

No source, baseline, credentials, live services or remote repository is changed.
git apply is exercised only against a temporary copy of baseline SDK sources.
An existing output directory is never overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.export_high_score_patch import BASELINE_NAME, SDK_PREFIX, canonical_json, sdk_patch, walk_source


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "baselines" / BASELINE_NAME)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/contributions/sdk-review-20261017")
    args = parser.parse_args()
    baseline, output = args.baseline.resolve(), args.output.resolve()
    metadata = json.loads((baseline / "BASELINE.json").read_text(encoding="utf-8"))
    patch, changes = sdk_patch(ROOT, baseline)
    if not changes or any(not Path(row["path"]).is_relative_to(SDK_PREFIX) for row in changes):
        raise ValueError("expected changes only inside the SDK prefix")
    output.mkdir(parents=True, exist_ok=False)
    patch_path = output / "acps-sdk-high-score.patch"
    patch_path.write_bytes(patch)
    commands = []
    with tempfile.TemporaryDirectory(prefix="incident-sdk-review-") as folder:
        copied = Path(folder)
        for relative in walk_source(baseline, SDK_PREFIX):
            destination = copied / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(baseline / relative, destination)
        def git(*arguments):
            result = subprocess.run(["git", "-C", str(copied), "-c", "core.autocrlf=false", "apply", *arguments, str(patch_path)],
                capture_output=True, text=True, encoding="utf-8", check=False)
            commands.append({"arguments": list(arguments), "exit_code": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                raise RuntimeError("SDK patch apply validation failed: "+result.stderr)
            return result.stdout
        diffstat = git("--stat")
        numstat = git("--numstat")
        git("--check")
        git()
        for row in changes:
            path = copied / row["path"]
            if row["change"] == "deleted":
                assert not path.exists()
            elif sha(path) != row["source_sha256"]:
                raise RuntimeError("Applied copy differs from reviewed source: "+row["path"])
    evidence_path = ROOT / "docs/contributions/evidence/summary.json"
    existing_patch = ROOT / "artifacts/high-score-source-20261017/acps-sdk-high-score.patch"
    manifest = {"format": "incident-sdk-review/1", "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {"snapshot": baseline.name, "sdk_commit": metadata["sdk_commit"],
                     "metadata_sha256": sha(baseline / "BASELINE.json"), "scope": "SDK source bytes only; no identity metadata copied"},
        "generator": {"entry": "docs/contributions/prepare_sdk_patch.py", "sha256": sha(Path(__file__)),
                      "function": "tools.export_high_score_patch.sdk_patch(root, baseline)",
                      "exporter_sha256": sha(ROOT / "tools/export_high_score_patch.py")},
        "patch": {"file": patch_path.name, "sha256": sha(patch_path), "bytes": len(patch), "changed_files": len(changes),
                  "added_files": sum(row["change"] == "added" for row in changes),
                  "modified_files": sum(row["change"] == "modified" for row in changes)},
        "changes": changes,
        "superseded_export": {"path": "artifacts/high-score-source-20261017/acps-sdk-high-score.patch",
                              "sha256": sha(existing_patch), "byte_identical": existing_patch.read_bytes() == patch},
        "validation": {"apply_check": True, "apply_in_temporary_copy": True, "applied_changed_source_hashes_match": True},
        "test_references": [{"path": relative, "sha256": sha(ROOT / relative), "passed_in_session": count}
            for relative, count in (("tests/test_task_ordering.py", 3),
                ("vendor/ACPs-community/acps-sdk/tests/resumable/test_resumable.py", 25))],
        "evidence_reference": {"path": "docs/contributions/evidence/summary.json", "sha256": sha(evidence_path)},
        "scope_limits": {"tests_rerun_for_export": False, "published": False, "remote_branch_created": False,
            "platform_E1a_E1b_run": False, "new_local_E1a_E1b_run": False,
            "pending": "explicit user authorization for the new local 18-case resource suite; formal ADP handover is separate"},
        "paths": {"project_root_apply": "git -c core.autocrlf=false apply --check acps-sdk-high-score.patch",
                  "upstream_repository_root_apply": "git -c core.autocrlf=false apply -p3 --check acps-sdk-high-score.patch",
                  "external_regression": "tests/test_task_ordering.py is outside SDK-only patch; move into upstream SDK tests before submission"}}
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    (output / "diffstat.txt").write_text(diffstat, encoding="utf-8")
    (output / "numstat.txt").write_text(numstat, encoding="utf-8")
    (output / "validation.json").write_bytes(canonical_json({"commands": commands,
        "resource_calls": 0, "model_calls": 0, "baseline_modified": False,
        "validation_copy": "temporary SDK source tree removed after successful hash verification"}))
    print(json.dumps({"output": str(output), **manifest["patch"], "apply_check": True}))


if __name__ == "__main__":
    main()
