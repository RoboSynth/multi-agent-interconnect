import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.schedule import Scheduler


class RotationTests(unittest.IsolatedAsyncioTestCase):
    def config(self, directory):
        return dict(directory=directory, workbench_url="http://127.0.0.1:8877", fault_backend="docker",
                    target_config="runtime/private/my-seven/target.json", drill_scenarios=["F01", "F02", "F06", "F07"],
                    drill_seed=17, drill_auto_approvals=[])

    async def test_apply_and_restore_keep_same_scenario_and_persist_rotation(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(temporary)
            scheduler = Scheduler(config, enable_fault_drills=True)
            observed = []
            async def inject(action):
                observed.append((action, scheduler.state["active"]["scenario"]))
            scheduler.inject = inject
            scheduler.request = AsyncMock(side_effect=[dict(connected=True, mode="wutong-amqps", resource_credential_count=0, incidents=[], incident=None),
                                                      dict(id="incident"), dict(status="completed", elapsed_seconds=1)])
            await scheduler.run_job("drill")
            self.assertEqual(observed, [("apply", scheduler.drills[0]), ("restore", scheduler.drills[0])])
            restarted = Scheduler(config, enable_fault_drills=True)
            self.assertEqual(restarted.drills, scheduler.drills)
            self.assertEqual(restarted.state["next_drill_index"], 1)
            self.assertIsNone(restarted.state["active"])

    async def test_failed_restore_retains_exact_pending_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            scheduler = Scheduler(self.config(temporary), enable_fault_drills=True)
            scheduler.inject = AsyncMock(side_effect=[None, RuntimeError("restore failed")])
            scheduler.request = AsyncMock(side_effect=[dict(connected=True, mode="wutong-amqps", resource_credential_count=0, incidents=[], incident=None),
                                                      dict(id="incident"), dict(status="completed", elapsed_seconds=1)])
            with self.assertRaises(RuntimeError):
                await scheduler.run_job("drill")
            state = json.loads(scheduler.path.read_bytes())
            self.assertEqual(state["active"]["scenario"], scheduler.drills[0])
            self.assertTrue(state["active"]["finished"])
            self.assertNotIn("next_drill_index", state)
            events = [json.loads(line) for line in (Path(temporary) / "events.jsonl").read_text().splitlines()]
            self.assertFalse(any(row["event"] == "job_finished" for row in events))
            failed = next(row for row in events if row["event"] == "job_failed")
            self.assertEqual(failed["run_id"], state["active"]["id"])
            self.assertEqual(failed["phase"], "restore")

    async def test_rotating_docker_uses_bound_target_and_current_scenario(self):
        with tempfile.TemporaryDirectory() as temporary:
            scheduler = Scheduler(self.config(temporary), enable_fault_drills=True)
            scheduler.state["active"] = dict(kind="drill", scenario="F07")
            process = AsyncMock()
            process.communicate.return_value = (b"", b"")
            process.returncode = 0
            with patch("ops.schedule.asyncio.create_subprocess_exec", return_value=process) as spawn:
                await scheduler.inject("restore")
            argv = spawn.call_args.args
            self.assertIn("F07", argv)
            self.assertIn("--target-config", argv)
            scheduler.config.pop("target_config")
            with self.assertRaises(ValueError):
                await scheduler.inject("apply")


if __name__ == "__main__":
    unittest.main()
