"""Offline validation of captured products; never contacts running workers."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
FROZEN = BATCH / "matrix/source"
sys.path.insert(0, str(FROZEN))
from incident.contracts import TaskProduct
from pydantic import ValidationError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(data):
    try:
        TaskProduct.model_validate(data)
        return {"valid": True}
    except ValidationError as error:
        return {"valid": False, "errors": error.errors(include_url=False, include_input=False)}


def main():
    messages_path = BATCH / "matrix/transport/messages.jsonl"
    snapshot = messages_path.read_bytes()
    rows = []
    for line_number, raw in enumerate(snapshot.splitlines(keepends=True), 1):
        if not raw.endswith(b"\n"):
            continue  # The writer may still be appending the final record.
        record = json.loads(raw)
        message = record.get("message", {})
        if (record.get("direction") != "receive" or record.get("worker_aic") != "local-verification"
                or message.get("status", {}).get("state") != "awaiting-completion"):
            continue
        products = message.get("products", [])
        if len(products) != 1 or products[0].get("name") != "incident.verification":
            continue
        product = products[0]["dataItems"][0]["data"]
        outcome = validate(product)
        row = {"line_number": line_number, "raw_line_sha256": digest(raw),
               "timestamp": record["timestamp"], "incident_id": product["incident_id"],
               "logical_task_id": product["logical_task_id"], "task_id": message["taskId"], **outcome}
        rows.append(row)
        if not outcome["valid"] and not (HERE / "first-invalid-message.json").exists():
            (HERE / "first-invalid-message.json").write_bytes(raw)
            restored = deepcopy(product)
            target = next(f for f in restored["facts"] if f["key"] == "carried_symptom_intents")
            target["value"] = None
            accepted = TaskProduct.model_validate(restored)
            serialized = accepted.model_dump(exclude_none=True)
            row["restoring_explicit_none_before_worker_dump"] = validate(restored)
            row["worker_dump_exclude_none_removes_value"] = "value" not in next(
                f for f in serialized["facts"] if f["key"] == "carried_symptom_intents")
            row["validation_after_worker_dump"] = validate(serialized)
            proposal = deepcopy(product)
            proposal["facts"] = [f for f in proposal["facts"] if f["key"] != "carried_symptom_intents"]
            row["proposed_omit_absent_fact_validation"] = validate(proposal)

    results_bytes = (BATCH / "matrix/results.jsonl").read_bytes()
    results = [json.loads(raw) for raw in results_bytes.splitlines(keepends=True) if raw.endswith(b"\n")]
    first_bad = next((r for r in rows if not r["valid"]), None)
    first_bad_index = next((i for i, r in enumerate(results)
                            if first_bad and r.get("incident_id") == first_bad["incident_id"]), None)
    after = [] if first_bad_index is None else [
        {k: r.get(k) for k in ("scenario", "method", "repeat", "incident_id", "status", "error")}
        for r in results[first_bad_index:]]
    report = {"captured_at": datetime.now(timezone.utc).isoformat(),
              "scope": "read-only snapshot of a running batch; no worker calls or algorithm changes",
              "messages_snapshot_bytes": len(snapshot), "messages_snapshot_sha256": digest(snapshot),
              "results_snapshot_bytes": len(results_bytes), "results_snapshot_sha256": digest(results_bytes),
              "frozen_contracts_sha256": digest((FROZEN / "incident/contracts.py").read_bytes()),
              "verification_products_observed": rows, "terminal_cells_observed": len(results),
              "first_invalid_cell_and_subsequent_observed_cells": after}
    (HERE / "validation-reproduction.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"captured_verification_products": len(rows),
                      "first_invalid": first_bad, "terminal_cells_observed": len(results),
                      "post_first_invalid_cells": len(after)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
