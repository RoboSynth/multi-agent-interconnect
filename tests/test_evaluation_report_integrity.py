"""Exact recorded cells and separately reported H00 controls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scheduling_report import summarize
from eval.plot_results import plot


class EvaluationReportIntegrityTests(unittest.TestCase):
    def manifest(self, *, repeats=2, methods=None, scenarios=None):
        methods = methods or ["M0"]
        return {"scenarios": scenarios or ["F01"], "methods": methods, "repeats": repeats,
            "method_order": "rotate starting method by repeat within each scenario",
            "method_definition_ids": {method: method+"-definition" for method in methods},
            "held_out_instances": [{"repeat": index+1, "workload_seed": 101+index,
                "precondition_pool_rebuilds": index} for index in range(repeats)]}

    def rows(self, manifest):
        rows = []
        methods = manifest["methods"]
        for scenario in manifest["scenarios"]:
            for index in range(manifest["repeats"]):
                for method in methods[index % len(methods):]+methods[:index % len(methods)]:
                    rows.append({"scenario": scenario, "method": method, "repeat": index+1,
                        "method_definition_id": manifest["method_definition_ids"][method],
                        "workload_seed": 101+index, "precondition_pool_rebuilds": index,
                        "status": "completed", "continuous_recovery_confirmed": scenario != "H00",
                        "diagnosis_exact_match": scenario != "H00", "model_fallbacks": 0, "model_failures": 0,
                        "model_source": "rules", "unnecessary_high_privilege_calls": 0,
                        "probes": 2, "modifications": 0 if scenario == "H00" else 1,
                        "modification_attempts": 0 if scenario == "H00" else 1,
                        "control_passed": True if scenario == "H00" else None,
                        "control_observation_seconds": 30 if scenario == "H00" else None,
                        "seconds": 35, "recovery_observed_seconds": None if scenario == "H00" else 5,
                        "tokens": 0, "model_calls": 0, "approval_wait_seconds": 0,
                        "token_usage_complete": True})
        return rows

    def exports(self, manifest, rows):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")
            raw = json.dumps(rows).encode("utf-8")
            (root / "results.json").write_bytes(raw)
            report = summarize(root)
            figure = plot(root, root / "figures", formats=("svg",))
            svg = (root / "figures/scheduling-comparison.svg").read_text(encoding="utf-8")
            self.assertEqual((root / "results.json").read_bytes(), raw)
            self.assertEqual(report["matrix_integrity"], figure["matrix_integrity"])
            return report, figure, svg

    def test_duplicate_repeat_and_missing_key_cannot_claim_complete_despite_equal_group_count(self):
        manifest = self.manifest()
        rows = self.rows(manifest)
        rows[1] = copy.deepcopy(rows[0])
        report, figure, svg = self.exports(manifest, rows)
        for result in (report, figure):
            self.assertFalse(result["matrix_complete"])
            self.assertEqual(result["recorded_cells"], result["expected_cells"])
            self.assertEqual(result["matrix_integrity"]["duplicate_keys"], [["F01", "M0", 1]])
            self.assertEqual(result["matrix_integrity"]["missing_keys"], [["F01", "M0", 2]])
        self.assertIn("PARTIAL", svg)

    def test_unique_but_out_of_plan_repeat_cannot_replace_a_missing_repeat(self):
        manifest = self.manifest()
        rows = self.rows(manifest)
        rows[1]["repeat"] = 3
        report, _, _ = self.exports(manifest, rows)
        self.assertFalse(report["matrix_complete"])
        self.assertEqual(report["matrix_integrity"]["unexpected_keys"], [["F01", "M0", 3]])

    def test_recorded_definition_seed_and_rebuild_must_match_manifest_when_available(self):
        manifest = self.manifest(repeats=1)
        for field, wrong in (("method_definition_id", "wrong"), ("workload_seed", 999),
                             ("precondition_pool_rebuilds", 9)):
            with self.subTest(field=field):
                rows = self.rows(manifest)
                rows[0][field] = wrong
                report, _, _ = self.exports(manifest, rows)
                self.assertFalse(report["matrix_complete"])
                self.assertEqual(report["matrix_integrity"]["metadata_mismatches"][0]["field"], field)

    def test_rotated_order_is_checked_when_manifest_declares_it(self):
        manifest = self.manifest(methods=["M0", "M2"])
        rows = self.rows(manifest)
        report, _, _ = self.exports(manifest, rows)
        self.assertTrue(report["matrix_complete"])
        rows[2:] = reversed(rows[2:])
        report, _, _ = self.exports(manifest, rows)
        self.assertFalse(report["matrix_complete"])
        self.assertFalse(report["matrix_integrity"]["planned_order_matches"])
        self.assertEqual(report["matrix_integrity"]["missing_keys"], [])

    def test_h00_controls_are_separate_from_fault_panels_and_their_denominator(self):
        manifest = self.manifest(repeats=1, scenarios=["H00", "F01"])
        rows = self.rows(manifest)
        report, figure, svg = self.exports(manifest, rows)
        self.assertTrue(report["matrix_complete"])
        self.assertEqual(report["recovery_rate"], 1)
        self.assertEqual(figure["fault_recorded_cells"], 1)
        self.assertEqual(figure["fault_expected_cells"], 1)
        self.assertEqual(figure["healthy_control_recorded_cells"], 1)
        self.assertEqual(figure["healthy_control_passed"], 1)
        self.assertEqual([group["scenario"] for group in figure["groups"]], ["F01"])
        self.assertEqual(figure["healthy_control_groups"][0]["passed"], 1)
        self.assertIn("H00 healthy controls (separate): M0 1/1 passed", svg)
        self.assertNotIn("H00  M0", svg)

    def test_h00_with_an_action_attempt_is_not_labelled_a_pass(self):
        manifest = self.manifest(repeats=1, scenarios=["H00", "F01"])
        rows = self.rows(manifest)
        rows[0]["modification_attempts"] = 1
        _, figure, svg = self.exports(manifest, rows)
        self.assertEqual(figure["healthy_control_passed"], 0)
        self.assertIn("H00 healthy controls (separate): M0 0/1 passed", svg)

    def test_h00_source_freeze_is_preserved_even_when_excluded_from_fault_panels(self):
        manifest = self.manifest(repeats=1, scenarios=["H00", "F01"])
        rows = self.rows(manifest)
        rows[0]["source_version"] = "control-freeze"
        rows[1]["source_version"] = "fault-freeze"
        _, figure, svg = self.exports(manifest, rows)
        self.assertTrue(figure["matrix_complete"])
        self.assertTrue(figure["composite_source_versions"])
        self.assertEqual(figure["source_versions_by_scenario"],
            {"H00": ["control-freeze"], "F01": ["fault-freeze"]})
        self.assertEqual([group["scenario"] for group in figure["groups"]], ["F01"])
        self.assertIn("COMPOSITE", svg)
        self.assertIn("H00=control-freeze", svg)
        self.assertNotIn("Original failed F06", svg)

    def test_legacy_missing_metadata_is_explicitly_unchecked_not_a_full_validation_claim(self):
        manifest = self.manifest(repeats=1)
        rows = self.rows(manifest)
        for field in ("method_definition_ids", "held_out_instances", "method_order"):
            del manifest[field]
        report, _, _ = self.exports(manifest, rows)
        self.assertTrue(report["matrix_complete"])
        self.assertEqual(report["matrix_integrity"]["metadata_checks_per_field"],
            {"method_definition_id": 0, "workload_seed": 0, "precondition_pool_rebuilds": 0})
        self.assertFalse(report["matrix_integrity"]["planned_order_checked"])

    def test_h00_does_not_consume_fault_apply_binding_for_derived_confirmation(self):
        manifest = self.manifest(repeats=1, scenarios=["H00", "F01"])
        rows = self.rows(manifest)
        fault_apply = {"action": "apply", "returncode": 0, "scenario": "F01",
            "stdout": json.dumps({"started_monotonic": 100})}
        events = [{"at_monotonic": 100, "outcome": "unknown", "completed_workflows": 0}]
        events += [{"at_monotonic": 101+index, "outcome": "success",
            "completed_workflows": int((index+1) % 3 == 0)} for index in range(30)]
        for include_h00_apply in (False, True):
            with self.subTest(include_h00_apply=include_h00_apply), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")
                raw = json.dumps(rows).encode("utf-8")
                (root / "results.json").write_bytes(raw)
                processes = ([{"action": "apply", "returncode": 0, "scenario": "H00",
                    "stdout": json.dumps({"started_monotonic": 1})}] if include_h00_apply else []) + [fault_apply]
                (root / "private").mkdir()
                (root / "private/inject-process.jsonl").write_text(
                    "\n".join(json.dumps(process) for process in processes), encoding="utf-8")
                workload = root / "workloads/F01-M0-1"
                workload.mkdir(parents=True)
                (workload / "requests.jsonl").write_text(
                    "\n".join(json.dumps(event) for event in events), encoding="utf-8")
                report = summarize(root)
                derived = json.loads((root / "analysis-rows.json").read_text(encoding="utf-8"))
                self.assertIsNone(derived[0]["recovery_confirmed_earliest_seconds"])
                self.assertEqual(derived[1]["recovery_confirmed_earliest_seconds"], 31)
                self.assertEqual(report["groups"][0]["median_success_recovery_confirmed_earliest_seconds"], 31)
                self.assertEqual((root / "results.json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
