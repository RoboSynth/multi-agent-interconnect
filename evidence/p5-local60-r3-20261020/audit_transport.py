"""Audit recorded worker products without calling workers or changing results."""
from collections import Counter
import hashlib
import json
import sys


def audit_transport(run, artifacts, rows):
    sys.path.insert(0, str(run / "source"))
    from incident.contracts import TaskProduct
    from pydantic import ValidationError

    method_by_id = {row["incident_id"]: row["method"] for row in rows}
    invalid, verification, product_errors = [], [], []
    product_count = 0
    source = run / "transport/messages.jsonl"
    with source.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            record = json.loads(raw)
            message = record.get("message", {})
            if (record.get("direction") != "receive"
                    or message.get("status", {}).get("state") != "awaiting-completion"):
                continue
            products = message.get("products", [])
            if len(products) != 1 or len(products[0].get("dataItems", [])) != 1:
                invalid.append({"line": number, "reason": "unexpected_product_envelope"})
                continue
            product = products[0]["dataItems"][0].get("data")
            product_count += 1
            try:
                TaskProduct.model_validate(product)
            except ValidationError as error:
                invalid.append({"line": number, "errors": error.errors(include_input=False, include_url=False)})
                continue
            if product.get("reason") == "ValidationError":
                product_errors.append({"line": number, "incident_id": product["incident_id"]})
            if products[0].get("name") == "incident.verification":
                facts = {fact["key"]: fact["value"] for fact in product["facts"]}
                verification.append({
                    "line": number, "raw_line_sha256": hashlib.sha256(raw).hexdigest(),
                    "incident_id": product["incident_id"], "task_id": message["taskId"],
                    "method": method_by_id.get(product["incident_id"]),
                    "business_recovered": facts.get("business_recovered"),
                    "carried_fact_present": "carried_symptom_intents" in facts,
                    "completed_workflows": facts.get("order_observation", {}).get("completed_workflows"),
                })
    channel_errors = [
        {key: row[key] for key in ("scenario", "method", "repeat", "incident_id", "error")}
        for row in rows if any(marker in row.get("error", "").lower() for marker in (
            "channel failed", "worker is unavailable", "no ready domain worker",
            "local_channel", "worker exited", "field required", "broken pipe",
        ))
    ]
    preflight = json.loads((artifacts / "preflight.json").read_text(encoding="utf-8"))
    check = preflight.get("local_aip_actual_roundtrip", {})
    final = {fact["key"]: fact["value"] for fact in check.get("verification_product", {}).get("facts", [])}
    following = {fact["key"]: fact["value"] for fact in check.get("following_product", {}).get("facts", [])}
    preflight_passed = (preflight.get("status") == "PASSED"
                       and final.get("business_recovered") is True
                       and "carried_symptom_intents" not in final
                       and following.get("symptom_check_passed") is True)
    usable = (preflight_passed and product_count > 0 and bool(verification)
              and not invalid and not product_errors and not channel_errors)
    return {
        "status": "PASSED" if usable else "FAILED", "comparison_usable": usable,
        "scope": "Recorded product schema checks and channel-error markers; algorithm failures remain in the comparison",
        "preflight_final_and_following_task_passed": preflight_passed,
        "raw_messages_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "received_products_checked": product_count, "invalid_products": invalid,
        "worker_validation_errors": product_errors, "channel_error_rows": channel_errors,
        "final_verification_products_by_method": dict(Counter(row["method"] for row in verification)),
        "final_verification_products": verification,
    }
