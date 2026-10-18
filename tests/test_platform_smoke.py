from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval.platform_smoke import observation_arguments, run

TARGET_AIC = "1.2.156.3088.1.BUPT.8N4WSS.GHBD0W.7K98MJ.0WS5"


class PlatformSmokeArgumentsTests(unittest.IsolatedAsyncioTestCase):
    async def exercise_close(self, *, call_error=None, close_error=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            (config / "coordinator.json").write_text(json.dumps({
                "skills": {"application": "incident.application"}, "automatic_takeover": True}), encoding="utf-8")
            output = root / "run"
            observation = {"status": "ok", "facts": [{"key": "application_reachable", "value": True}]}
            transport = SimpleNamespace(start=AsyncMock(), call=AsyncMock(return_value=observation, side_effect=call_error),
                close=AsyncMock(side_effect=close_error), participants=[{"role": "application"}],
                tools=["application.status"])
            args = SimpleNamespace(observe_tool="application.status", observe_application=False,
                observe_target_aic=None, output=output, roles="application", config_dir=config,
                external_workers=True)
            with patch("eval.platform_smoke.WutongTransport", return_value=transport) as factory:
                actual_exit = await run(args)
                self.assertIs(factory.call_args.args[0]["automatic_takeover"], False)
            transport.close.assert_awaited_once()
            return actual_exit, json.loads((output / "results.json").read_text(encoding="utf-8")), observation

    async def test_successful_observation_and_normal_close_return_zero(self):
        actual_exit, result, observation = await self.exercise_close()
        self.assertEqual(actual_exit, 0)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["task_phase_status"], "completed")
        self.assertEqual(result["close_status"], "completed")
        self.assertEqual(result["observation"], observation)

    async def test_close_error_fails_run_but_preserves_successful_observation(self):
        actual_exit, result, observation = await self.exercise_close(close_error=OSError("close failed"))
        self.assertEqual(actual_exit, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["task_phase_status"], "completed")
        self.assertEqual(result["observation"], observation)
        self.assertEqual(result["close_error_class"], "OSError")
        self.assertEqual(result["close_status"], "failed")
        self.assertNotIn("error_class", result)

    async def test_primary_error_is_retained_when_close_also_fails(self):
        actual_exit, result, _ = await self.exercise_close(call_error=ValueError("observation failed"),
            close_error=OSError("close failed"))
        self.assertEqual(actual_exit, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["task_phase_status"], "failed")
        self.assertEqual(result["error_class"], "ValueError")
        self.assertEqual(result["close_error_class"], "OSError")
        self.assertNotIn("observation", result)

    def test_onboarding_has_explicit_public_target(self):
        self.assertEqual(observation_arguments("aip.onboarding.check", TARGET_AIC), {"target_aic": TARGET_AIC})
        self.assertEqual(observation_arguments("application.status"), {})
        self.assertEqual(observation_arguments(None), {})
        with self.assertRaises(ValueError):
            observation_arguments("application.status", TARGET_AIC)

    async def test_invalid_onboarding_target_cannot_create_group_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            for target in (None, "", "not-an-aic"):
                args = SimpleNamespace(observe_tool="aip.onboarding.check", observe_application=False,
                    observe_target_aic=target, output=output)
                with self.subTest(target=target), patch("eval.platform_smoke.WutongTransport") as transport:
                    with self.assertRaises(ValueError):
                        await run(args)
                    transport.assert_not_called()
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
