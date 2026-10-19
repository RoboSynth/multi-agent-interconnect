from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.onboarding_client import configuration, main

AIC = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"


class OnboardingClientTests(unittest.TestCase):
    def test_default_prepares_request_without_opening_config_or_transport(self):
        stream = io.StringIO()
        with patch("tools.onboarding_client.execute") as execute, redirect_stdout(stream):
            self.assertEqual(main(["--target-aic", AIC]), 0)
        execute.assert_not_called()
        report = json.loads(stream.getvalue())
        self.assertEqual(report["status"], "PREPARED_NOT_SENT")
        self.assertFalse(report["payload"]["args"]["deep"])

    def test_config_copies_only_own_identity_and_public_protocol_locations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = dict(leader=dict(aic=AIC, endpoint="amqps://broker.invalid:5671/acps", cert="own.pem", key="own.key"),
                trust_bundle="ca.pem", discovery_url="https://discovery.invalid", mq_auth_url="https://acl.invalid",
                approval_env_file="must-not-read.env", database_password="must-not-copy")
            path = root / "caller.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            result = configuration(path, root / "run", AIC)
            self.assertNotIn("approval_env_file", result)
            self.assertNotIn("database_password", result)
            self.assertEqual(result["leader"]["key"], str(root / "own.key"))
            self.assertEqual(result["skills"], {"onboarding": "aip.onboarding.check"})
            self.assertFalse(result["automatic_takeover"])


if __name__ == "__main__":
    unittest.main()
