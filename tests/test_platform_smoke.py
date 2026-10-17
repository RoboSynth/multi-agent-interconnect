from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from eval.platform_smoke import observation_arguments, run

TARGET_AIC = "1.2.156.3088.1.BUPT.8N4WSS.GHBD0W.7K98MJ.0WS5"


class PlatformSmokeArgumentsTests(unittest.IsolatedAsyncioTestCase):
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
