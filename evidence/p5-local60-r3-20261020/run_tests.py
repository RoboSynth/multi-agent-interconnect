"""Run the verification contract and its affected local regression suites."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
BATCH = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "vendor/ACPs-community/acps-sdk")]
PATTERNS = [
    "test_carried_symptom_intents.py", "business_verification_test.py",
    "test_receipt_resolution.py", "test_public_order_version.py",
    "test_observer_key_bounds.py", "test_p5_incident_scheduling.py",
    "test_coordinator.py", "test_platform_worker.py",
]


def main():
    suite = unittest.TestSuite()
    for pattern in PATTERNS:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern))
    with (BATCH / "tests/affected-tests.txt").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    receipt = {
        "observed_at": datetime.now(timezone.utc).isoformat(), "patterns": PATTERNS,
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "status": "PASSED" if result.wasSuccessful() else "FAILED",
    }
    (BATCH / "tests/summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
