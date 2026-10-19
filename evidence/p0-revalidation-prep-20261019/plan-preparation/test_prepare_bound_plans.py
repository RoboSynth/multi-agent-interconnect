"""Pure helper guards only; no project preparer, Docker, platform or config imports."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bound_plans", HERE / "prepare_bound_plans.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class PreparationGuards(unittest.TestCase):
    def image(self):
        return dict(actual_exit_code=0, process_terminal=True, inspect_exit_code=0,
                    image_reference=helper.IMAGE_REFERENCE, image_id="sha256:" + "a" * 64)

    def test_success_requires_real_integer_exits_and_terminal_inspection(self):
        self.assertEqual(helper.image_success(self.image()), "sha256:" + "a" * 64)
        for field, bad in (("actual_exit_code", 1), ("actual_exit_code", False),
                           ("inspect_exit_code", 1), ("inspect_exit_code", False),
                           ("process_terminal", False), ("process_terminal", 1)):
            value = self.image(); value[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                helper.image_success(value)

    def test_missing_or_wrong_image_binding_rejected(self):
        for field, bad in (("image_id", "sha256:short"), ("image_id", "sha256:" + "A" * 64),
                           ("image_reference", "incident-pilot-acceptance-20261019-agent:local")):
            value = self.image(); value[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                helper.image_success(value)
        with self.assertRaises(ValueError):
            helper.image_success({})

    def test_exact_twelve_unique_plans_and_four_condition_first_round(self):
        rows = helper.schedule()
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({row["key"] for row in rows}), 12)
        self.assertEqual([sum(row["case"] == c for row in rows) for c in ("E1-a", "E1-b", "E1-c", "F12/E5")], [3, 9, 0, 0])
        self.assertEqual([row["order"] for row in rows], list(range(1, 13)))
        self.assertTrue(all(row["repeat"] == 1 and row["first_round"] for row in rows[:4]))
        self.assertEqual(len({(r["case"], r["point"], r["method"]) for r in rows[:4]}), 4)
        self.assertTrue(all(not row["first_round"] for row in rows[4:]))
        self.assertEqual([row["repeat"] for row in rows[4:]], [2] * 4 + [3] * 4)

    def test_only_observation_recovery_and_three_after_applied_methods(self):
        rows = helper.schedule()
        observations = [row for row in rows if row["case"] == "E1-a"]
        self.assertEqual([row["repeat"] for row in observations], [1, 2, 3])
        self.assertTrue(all(row["point"] == "after_observation" and row["method"] is None for row in observations))
        for repeat in (1, 2, 3):
            handovers = [row for row in rows if row["case"] == "E1-b" and row["repeat"] == repeat]
            self.assertEqual([row["method"] for row in handovers], ["from_scratch", "full_history", "resume_package"])
            self.assertTrue(all(row["point"] == "after_applied" for row in handovers))

    def test_preexisting_plan_or_result_root_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory); private, results = root / "private", root / "results"
            helper.require_new(private, results)
            private.mkdir()
            with self.assertRaises(ValueError): helper.require_new(private, results)
            private.rmdir(); results.mkdir()
            with self.assertRaises(ValueError): helper.require_new(private, results)


if __name__ == "__main__":
    unittest.main()
