"""Verify existing T63 evidence and build a narrowly scoped delivery patch.

No test, service, network, model or platform call is performed here.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent
GIT = Path(r"C:\Users\16080\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe")
BASE = "3760b21c8a1ed62e8119925da6f24ebd8b851d14"
SOURCE_FILES = ["eval/stability_bundle.py", "tests/test_stability_bundle.py", "docs/stability_report.md"]
TARGET = "evidence/t63-stability-report-20261019"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def git(directory, *args):
    result = subprocess.run([str(GIT), "-C", str(directory), *args], capture_output=True, check=True)
    return result.stdout


def main():
    baseline = load(ROOT / "source-baseline.json")
    assert baseline["source_commit"] == BASE
    for entry in baseline["files"]:
        rel = entry["path"]
        assert sha(ROOT / "baseline" / rel) == entry["sha256"]
        if rel != "docs/stability_report.md":
            assert sha(ROOT / "checkout" / rel) == entry["sha256"], rel

    # Reuse actual prior results; do not add repeated runs to the method count.
    def names(filename):
        text = (ROOT / "validation" / filename).read_text(encoding="utf-8-sig")
        assert text.rstrip().endswith("OK"), filename
        return set(re.findall(r"^(test_\S+) \(([^)]+)\) \.\.\. ok$", text, re.M))

    initial = names("attempt-2.log")
    final = names("attempt-4-bundle-final.log")
    legacy = {item for item in initial if not item[1].startswith("test_stability_bundle.")}
    assert len(initial) == 28 and len(legacy) == 20 and len(final) == 11
    tree = ast.parse((ROOT / "checkout/tests/test_stability_bundle.py").read_text(encoding="utf-8"))
    current_methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}
    assert current_methods == {item[0] for item in final}

    example = ROOT / "real-example-r3"
    bindings = load(example / "source-bindings.json")
    report = example / "report"
    summary = load(report / "summary.json")
    for entry in bindings["raw_source_files"]:
        assert sha(example / entry["projected_path"]) == entry["projected_sha256"]
    assert len(bindings["raw_source_files"]) == 9
    assert summary["amp"]["expected_aic_sampling_window"] == {
        "expected_agent_count": 7, "expected_slot_count": 840, "observed_slot_count": 840,
        "missing_slot_count": 0, "coverage_percent": 100.0, "unexpected_agents_excluded": True}
    assert summary["scheduler"]["counts"] == {"completed": 1}
    assert summary["scheduler"]["by_kind"][1]["evidence"] == "unknown_no_recorded_job"
    assert summary["coordinator"]["measured_count"] == 6
    assert summary["coordinator"]["median_ms"] == 1531.5
    assert summary["coordinator"]["p95_ms"] == 31875
    assert summary["amp"]["median_access_ms"] is None
    assert summary["amp"]["median_partner_processing_ms"] is None
    assert summary["amp"]["acceptance_window"]["duration_seconds"] == 1800
    assert sorted(row["sha256"] for row in summary["inputs"]) == sorted(row["projected_sha256"] for row in bindings["raw_source_files"])
    artifact_manifest = load(report / "artifact-manifest.json")
    assert len(artifact_manifest["files"]) == 7
    for entry in artifact_manifest["files"]:
        path = report / entry["path"]
        assert sha(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]
    with (report / "latency.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["median_ms"] for row in rows] == ["unknown", "unknown", "1531.5"]
    assert len(list(report.iterdir())) == 8

    # A disposable, local index supplies exact source bytes for git's patch.
    patch_tree = ROOT / "patch-build"
    patch_tree.mkdir(exist_ok=False)
    git(patch_tree, "init", "-q")
    git(patch_tree, "config", "core.autocrlf", "false")
    doc = patch_tree / "docs/stability_report.md"
    doc.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "baseline/docs/stability_report.md", doc)
    git(patch_tree, "add", "--", "docs/stability_report.md")
    for rel in SOURCE_FILES:
        target = patch_tree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "checkout" / rel, target)
    git(patch_tree, "add", "-N", "--", *SOURCE_FILES[:2])
    patch_path = ROOT / "t63-stability-bundle.patch"
    patch_path.write_bytes(git(patch_tree, "diff", "--binary", "--no-ext-diff", "--", *SOURCE_FILES))

    apply_tree = ROOT / "patch-application"
    apply_tree.mkdir(exist_ok=False)
    git(apply_tree, "init", "-q")
    git(apply_tree, "config", "core.autocrlf", "false")
    (apply_tree / "docs").mkdir()
    shutil.copyfile(ROOT / "baseline/docs/stability_report.md", apply_tree / "docs/stability_report.md")
    git(apply_tree, "apply", "--check", str(patch_path))
    git(apply_tree, "apply", str(patch_path))
    for rel in SOURCE_FILES:
        assert (apply_tree / rel).read_bytes() == (ROOT / "checkout" / rel).read_bytes(), rel

    evidence_files = [
        "README.md", "source-baseline.json", "t63-stability-bundle.patch", "finalize_delivery.py",
        "generate_real_example.py", "validation/attempt-1.json", "validation/attempt-2.log",
        "validation/attempt-3-scheduler.log", "validation/attempt-4-bundle-final.log",
        "validation/real-example-attempt-1.json", "validation/generate-real-example-attempt-1.py",
    ] + [path.relative_to(ROOT).as_posix() for path in sorted(example.rglob("*")) if path.is_file()]

    result = {
        "schema_version": 1, "source_commit": BASE, "status": "ready_for_integration_not_yet_applied",
        "code_review": "No further definite code defect found; native scheduler and coordinator elapsed semantics checked against frozen source.",
        "prior_tests_reused": {
            "legacy_method_count": 20, "legacy_evidence": "validation/attempt-2.log",
            "final_bundle_method_count": 11, "bundle_evidence": "validation/attempt-4-bundle-final.log",
            "unique_related_method_count": 31, "rerun_at_finalization": False},
        "artifact_checks": ["baseline hashes", "unchanged legacy source bytes", "final test method coverage against passed log", "nine projected input hashes", "input-to-summary hash binding", "seven report output hashes", "semantic real-example values", "CSV unknown values", "patch check/apply and three exact file bytes"],
        "patch_sha256": sha(patch_path),
        "visual_review": {"method": "actual local PNG opened with view_image", "path": "real-example-r3/report/stability-overview.png", "sha256": sha(report / "stability-overview.png"), "result": "Labels, unknown values, axes, bars and median/p95 legend readable; SVG is the same Figure's vector export."},
        "example_scope": {"window_seconds": 1800, "expected_heartbeat_slots": 840, "observed_heartbeat_slots": 840, "recorded_inspections": 1, "measured_tasks": 6, "task_median_ms": 1531.5, "task_nearest_rank_p95_ms": 31875},
        "preserved_failures": ["validation/attempt-1.json", "validation/real-example-attempt-1.json"],
        "limitations": ["Existing one-run 30-minute file analysis, no new runtime or fault experiment.", "AMP durations are unknown here and remain distinct from coordinator elapsed.", "No drill, uptime, 24-hour/7-day, Kafka/Monitor, signature verification or new-machine acceptance is established."]}
    dump(ROOT / "validation/result.json", result)
    evidence_files.append("validation/result.json")

    delivery = {"schema_version": 1, "source_commit": BASE,
                "source_files": [{"path": rel, "sha256": sha(ROOT / "checkout" / rel), "bytes": (ROOT / "checkout" / rel).stat().st_size} for rel in SOURCE_FILES],
                "evidence_files": [{"path": rel, "sha256": sha(ROOT / rel), "bytes": (ROOT / rel).stat().st_size} for rel in evidence_files],
                "self_and_publication_manifest": "Excluded from this hash list to avoid circular self-hashes; publication-files.json binds this delivery-manifest.json."}
    dump(ROOT / "delivery-manifest.json", delivery)
    evidence_files.append("delivery-manifest.json")
    entries = [{"source_relative": "checkout/"+rel, "target_relative": rel, "sha256": sha(ROOT / "checkout" / rel), "bytes": (ROOT / "checkout" / rel).stat().st_size} for rel in SOURCE_FILES]
    entries += [{"source_relative": rel, "target_relative": TARGET+"/"+rel, "sha256": sha(ROOT / rel), "bytes": (ROOT / rel).stat().st_size} for rel in evidence_files]
    dump(ROOT / "publication-files.json", {"schema_version": 1, "source_commit": BASE, "entries": entries,
        "manifest_target": TARGET+"/publication-files.json", "manifest_handling": "Copy this manifest itself in addition to entries; no recursive self-hash.",
        "excluded": ["baseline", "patch-build", "patch-application", "checkout source dependencies", "real-example", "real-example-r2", "validation/tmp", "validation/mpl-cache"],
        "publication_review": "Only explicit field projections and safe local validation metadata selected. Parent publication scan remains required."})
    print(json.dumps({"status": "ready_for_integration", "source_files": 3, "evidence_files": len(evidence_files)+1,
        "patch_sha256": sha(patch_path), "unique_related_methods": 31, "new_test_runs": 0, "publication_entries_plus_self": len(entries)+1}))


if __name__ == "__main__":
    main()
