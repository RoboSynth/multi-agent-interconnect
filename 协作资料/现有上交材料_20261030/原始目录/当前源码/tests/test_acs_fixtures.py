"""Published ACS test inputs must stay synthetic and unusable as live profiles."""
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from acps_sdk.aic import validate_aic_format
from integration.validate_acs import validate_document


class SyntheticAcsFixtureTests(unittest.TestCase):
    def test_schema_valid_fixtures_remain_unregistered_and_without_credentials(self):
        identities = set()
        for filename in ("database.submission.acs.json", "application.approved.acs.json"):
            with self.subTest(filename=filename):
                document = json.loads((ROOT / "integration/incident" / filename).read_text(encoding="utf-8"))
                report = validate_document(document)
                self.assertTrue(report["sdk_schema_valid"], report)
                self.assertIs(report["official_registry_schema_valid"], True, report)
                self.assertTrue(validate_aic_format(document["aic"])[0])
                self.assertNotIn(document["aic"], identities)
                identities.add(document["aic"])
                self.assertFalse(document["active"])
                self.assertTrue(document["entityMeta"]["synthetic"])
                self.assertTrue(document["entityMeta"]["notRegistered"])
                self.assertFalse(report["local_runtime_policy_satisfied"])
                self.assertFalse(report["runtime_reachability_tested"])
                self.assertFalse(report["platform_registration_tested"])
                for endpoint in document["endPoints"]:
                    url = urlparse(endpoint["url"])
                    self.assertEqual(url.hostname, "fixture.invalid")
                    self.assertIsNone(url.username)
                    self.assertIsNone(url.password)
                    self.assertEqual(parse_qs(url.query)["inbox"], ["inbox_" + document["aic"]])
                def check_keys(value):
                    if isinstance(value, dict):
                        self.assertFalse(set(value) & {"cert", "key", "password", "token", "keyId", "macKey", "client_secret"})
                        for item in value.values():
                            check_keys(item)
                    elif isinstance(value, list):
                        for item in value:
                            check_keys(item)
                check_keys(document)


if __name__ == "__main__":
    unittest.main()
