"""Publish this batch's compact ledger and unchanged failed incidents after cleanup."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import runpy
import shutil
from report import ARTIFACTS, BATCH, ROOT, RUN, OUTPUT, confirmed, load, save, sha, validate_inputs


def concise_fact(fact):
    value = fact.get("value")
    if fact.get("key") in {"order_observation", "symptom_observation"} and isinstance(value, dict):
        value = {k: v for k, v in value.items() if k not in {"events", "state"}}
    return {**fact, "value": value}


def known_secrets():
    values = []
    paths = [ROOT / "deploy/.env", *sorted((ROOT / "runtime/private").glob("*.env"))]
    for path in paths:
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and re.search("PASSWORD|TOKEN|SECRET|DATABASE_URL|DATABASE_URI|DSN", key, re.I):
                    value = value.strip().strip("\"'")
                    if value:
                        values.append(value)
    return values


def scan_payload(paths):
    scanner = runpy.run_path(str(BATCH / "binding/source/eval/secret_scan.py"))
    secrets = known_secrets()
    findings, parsed, checked, binary = [], 0, [], []
    for path in paths:
        if path.suffix.lower() == ".png":
            binary.append(str(path.relative_to(OUTPUT)))
            continue
        body = path.read_text(encoding="utf-8-sig")
        checked.append(str(path.relative_to(OUTPUT)))
        if path.suffix.lower() == ".json":
            json.loads(body)
            parsed += 1
        for number, line in enumerate(body.splitlines(), 1):
            categories = {key for key, pattern in scanner["PATTERNS"].items() if pattern.search(line)}
            if any(secret in line for secret in secrets):
                categories.add("known_resource_secret")
            findings.extend({"file": str(path.relative_to(OUTPUT)), "line": number, "category": c} for c in sorted(categories))
    receipt = {"status": "PASSED" if not findings else "FAILED", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Explicit publication files; frozen credential patterns and current local resource secret values; all JSON parsed",
        "text_files_scanned": len(checked), "files": checked, "binary_files_not_text_scanned": binary,
        "known_secret_values_checked": len(secrets), "json_records_parsed": parsed,
        "hits": len(findings), "findings": findings, "machine_checks_passed": not findings}
    save(OUTPUT / "publication-scan.json", receipt)
    if findings:
        raise ValueError("Publication scan failed; inspect category-only publication-scan.json")


def main():
    rows, experiment = validate_inputs()
    integrity = load(OUTPUT / "integrity-verification.json")
    if integrity["status"] != "VERIFIED" or integrity["results_sha256"] != sha(RUN / "results.json"):
        raise ValueError("Run the offline integrity verifier after the final report and cleanup")
    if load(ARTIFACTS / "cleanup-result.json")["status"] != "STOPPED":
        raise ValueError("Publication requires confirmed cleanup")
    if (OUTPUT / "failed-incidents").exists():
        expected = {r["incident_id"] + ".json" for r in rows if not confirmed(r)}
        actual = {p.name for p in (OUTPUT / "failed-incidents").iterdir() if p.is_file()}
        if actual - expected:
            raise ValueError("Stale failed incidents in publication; preserve and investigate")
    ledger = []
    for row in rows:
        raw = RUN / "incidents" / (row["incident_id"] + ".json")
        state = load(raw)
        tasks = []
        for task in state.get("tasks", []):
            product = task.get("product") or {}
            tasks.append({**{k: v for k, v in task.items() if k not in {"product", "args"}},
                "operation": product.get("operation"), "facts": [concise_fact(f) for f in product.get("facts", [])],
                "product_status": product.get("status")})
        ledger.append({"scenario": row["scenario"], "method": row["method"], "repeat": row["repeat"],
            "incident_id": row["incident_id"], "status": state["status"], "error": state.get("error"),
            "facts": [concise_fact(f) for f in state["facts"]], "diagnosed_causes": state.get("diagnosed_causes"),
            "hypotheses": state.get("hypotheses"), "planning_history": state.get("planning_history"), "tasks": tasks,
            "model_requests": [{k: v for k, v in q.items() if k not in {"context", "schema"}} for q in state.get("model_requests", [])],
            "raw_incident_sha256": sha(raw)})
        if not confirmed(row):
            target = OUTPUT / "failed-incidents" / raw.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw, target)
            if sha(target) != sha(raw):
                raise ValueError("Raw failed incident copy mismatch")
    save(OUTPUT / "incident-ledger.json", ledger)
    shutil.copy2(RUN / "experiment.json", OUTPUT / "experiment.json")
    receipts = {BATCH / name for name in ["execution-intent.json", "execution-result.json"]}
    receipts.update(ARTIFACTS / name for name in ["final-h00.json", "cleanup-result.json"])
    for source in receipts:
        shutil.copy2(source, OUTPUT / source.name)
    names = {p.name for p in receipts}
    payload = [p for p in sorted(OUTPUT.rglob("*")) if p.is_file()
               and p.name not in {"artifact-manifest.json", "publication-scan.json"}]
    # Local matrix/source/config/private material is never a publication input.
    if any(p.suffix.lower() in {".sqlite", ".db", ".env", ".pem", ".gguf"} for p in payload):
        raise ValueError("Unexpected private resource file in publication")
    scan_payload(payload)
    payload.append(OUTPUT / "publication-scan.json")
    for source in payload:
        target = BATCH / source.relative_to(OUTPUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == source.resolve():
            raise ValueError("Source and publication destination coincide")
        if target.exists() and target.name in names and sha(target) != sha(source):
            raise ValueError("Immutable execution receipt differs from selected publication")
        if target.exists() and sha(target) == sha(source):
            continue
        shutil.copy2(source, target)
    manifest = {"recorded_at": datetime.now(timezone.utc).isoformat(),
        "scope": "60 terminal cells, compact ledger, all unchanged failed incidents and verification receipts",
        "raw_artifact_directory": str(RUN), "source_fingerprint_count": len(experiment["source_sha256"]),
        "all_failure_rows_retained": True, "failed_incident_files": sum(not confirmed(r) for r in rows),
        "compact_ledger_omits": ["model input contexts and schemas", "task args", "per-order observation events and state"],
        "raw_failed_incidents": "Byte-for-byte original incidents retained, including planning_history and tasks",
        "publication_helpers": {name: sha(BATCH / name) for name in [
            "run.py", "report.py", "plot_report.py", "verify_evidence.py", "package_evidence.py"]},
        "files": {str(p.relative_to(OUTPUT)): {"bytes": p.stat().st_size, "sha256": sha(p)} for p in payload}}
    save(BATCH / "artifact-manifest.json", manifest)
    print(json.dumps({"status": "PACKAGED", "terminal_cells": 60, "files": len(payload) + 1,
                      "raw_failed_incidents": manifest["failed_incident_files"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
