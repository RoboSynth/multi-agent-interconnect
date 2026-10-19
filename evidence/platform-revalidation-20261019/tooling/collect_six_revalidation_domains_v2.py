"""Post-stop six-domain AMP copy only; default does not contact Docker or read logs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER_SHA = "da0e4b2b6fe265b6c6099a5299cc7469626b8aad34653defe0351f8399fc7c94"
PREPARED_SHA = "23552f95af1e86a33c6f4e3c923df471ab69edf7acad07f3acadfe4d85c353ac"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--terminal", type=Path)
    parser.add_argument("--terminal-sha")
    parser.add_argument("--output", type=Path, default=HERE / "runtime-amp-capture-v2")
    args = parser.parse_args()
    if not args.collect:
        print(json.dumps({"status": "PREPARED_NOT_COLLECTED", "Docker_calls": 0, "runtime_log_reads": 0,
                          "required": "--collect --terminal REAL_TERMINAL_JSON --terminal-sha EXACT_SHA; output must be new"}))
        return 0
    if not args.terminal or not args.terminal_sha:
        parser.error("Collection requires the real final terminal receipt and exact SHA")
    helper_path = HERE / "check_closed_revalidation_access_credentials_v2.py"
    prepared_path = HERE.parent / "plan-preparation/prepared-summary.json"
    if sha(helper_path) != HELPER_SHA or sha(prepared_path) != PREPARED_SHA:
        raise ValueError("Reviewed derived helper/prepared summary changed")
    spec = importlib.util.spec_from_file_location("revalidation_six_domain_collection", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    prepared = helper.read(prepared_path)
    helper.closure(args, prepared)
    output = helper.within(args.output.resolve(), HERE)
    output.mkdir(parents=True, exist_ok=False)
    try:
        manifest = helper.collect_domains(args, output, prepared)
        manifest_path = output / "private-domain-snapshot-manifest.json"
        result = {"status": "collected", "manifest": manifest_path.name,
                  "manifest_sha256": sha(manifest_path), "domain_count": len(manifest["domains"]),
                  "file_count": sum(len(row["files"]) for row in manifest["domains"]),
                  "source_helper_sha256": HELPER_SHA, "prepared_summary_sha256": PREPARED_SHA,
                  "terminal_sha256": args.terminal_sha, "collector_sha256": sha(Path(__file__)),
                  "inventory_imported": False, "analysis_executed": False,
                  "source_container_identity_unchanged": True, "containers_started_or_modified": 0}
        helper.save(output / "collection-result.json", result)
        print(json.dumps(result))
        return 0
    except Exception as error:
        helper.save(output / "collection-failure.json", {"status": "collection_failed", "error_class": type(error).__name__,
                    "inventory_imported": False, "analysis_executed": False, "source_helper_sha256": HELPER_SHA})
        print(json.dumps({"status": "collection_failed", "error_class": type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
