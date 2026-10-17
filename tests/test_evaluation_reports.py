"""Historical observation-only M1 must not silently become full-tool evidence."""
import json
from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.scheduling_report import summarize

if find_spec("matplotlib"):
    from eval.plot_results import plot
else:
    plot = None


class EvaluationReportTests(unittest.TestCase):
    def cohort(self, root, definitions):
        manifest = {"scenarios": ["F01"], "methods": ["M1"], "repeats": len(definitions)}
        rows = []
        for index, definition in enumerate(definitions):
            row = {"scenario": "F01", "method": "M1", "repeat": index + 1,
                "status": "completed", "continuous_recovery_confirmed": True,
                "diagnosis_exact_match": True, "model_fallbacks": 0, "model_failures": 0,
                "model_source": "llm", "unnecessary_high_privilege_calls": 0,
                "probes": 2, "modifications": 1, "seconds": 35, "recovery_observed_seconds": 5,
                "tokens": 100, "model_calls": 4, "approval_wait_seconds": .1,
                "token_usage_complete": True}
            if definition:
                row["method_definition_id"] = definition
            rows.append(row)
        (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")
        (root / "results.json").write_text(json.dumps(rows), encoding="utf-8")

    def test_historical_scope_stays_observation_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cohort(root, [None])
            result = summarize(root)
            self.assertEqual(result["M1_method_definition_ids"], ["observation-only-v1"])
            self.assertIn("Historical M1", (root / "report.md").read_text(encoding="utf-8"))

    @unittest.skipIf(plot is None, "figure checks require requirements-report.txt")
    def test_full_tool_scope_reaches_report_and_exported_figure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cohort(root, ["free-tools-v1"])
            report = summarize(root)
            figure = plot(root, root / "figures", formats=("svg",))
            self.assertEqual(report["M1_method_definition_ids"], figure["M1_method_definition_ids"])
            self.assertIn("guarded actions and verification", (root / "report.md").read_text(encoding="utf-8"))
            self.assertIn("selects observations, actions and verification",
                          (root / "figures/scheduling-comparison.svg").read_text(encoding="utf-8"))

    def test_mixed_method_definitions_cannot_be_aggregated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.cohort(root, [None, "free-tools-v1"])
            exports = [summarize]
            if plot:
                exports.append(lambda path: plot(path, path / "figures", formats=("svg",)))
            for export in exports:
                with self.subTest(export=export), self.assertRaisesRegex(ValueError, "definitions differ"):
                    export(root)
            self.assertFalse((root / "summary.json").exists())
            self.assertFalse((root / "figures").exists())


if __name__ == "__main__":
    unittest.main()
