import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from domains.onboarding.check import OnboardingPartner


class OnboardingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
        self.target = self.document["aic"]
        self.discover = AsyncMock(return_value=self.document)
        self.partner = OnboardingPartner("onboarding-fixture", discovery_url="https://unused.invalid",
                                         allowed_callers=["caller"], discover=self.discover)
        self.payload = {"incident_id": "check", "logical_task_id": "check-1", "kind": "observe",
                        "tool": "aip.onboarding.check", "args": {"target_aic": self.target}}

    async def test_approved_public_metadata_passes_official_schema(self):
        result = await self.partner.execute(self.payload, "caller")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["facts"][0]["value"]["passed"])

    async def test_wrong_protocol_and_inbox_return_specific_advice(self):
        self.document["protocolVersion"] = "00.00"
        self.document["endPoints"][0]["url"] = "https://example.invalid/"
        report = (await self.partner.execute(self.payload, "caller"))["facts"][0]["value"]
        self.assertFalse(report["passed"])
        self.assertFalse(report["protocol_version_valid"])
        self.assertFalse(report["inbox_endpoint_valid"])
        self.assertGreaterEqual(len(report["suggestions"]), 2)

    async def test_missing_identity_is_not_a_runtime_reachability_claim(self):
        self.discover.return_value = None
        report = (await self.partner.execute(self.payload, "caller"))["facts"][0]["value"]
        self.assertFalse(report["found"])
        self.assertFalse(report["active_target_probe"])

    async def test_unauthorized_and_active_probe_requests_never_contact_target(self):
        denied = await self.partner.execute(self.payload, "other")
        self.assertEqual(denied["status"], "rejected")
        self.payload["args"]["deep"] = True
        denied = await self.partner.execute(self.payload, "caller")
        self.assertEqual(denied["status"], "rejected")
        self.discover.assert_not_awaited()

    async def test_public_metadata_optin_accepts_external_aic_but_not_active_probes(self):
        self.partner.public_metadata_service = True
        external = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"
        result = await self.partner.execute(self.payload, external)
        self.assertTrue(result["facts"][0]["value"]["passed"])
        self.discover.reset_mock()
        self.payload["args"]["deep"] = True
        result = await self.partner.execute(self.payload, external)
        self.assertEqual(result["status"], "rejected")
        result = await self.partner.execute(self.payload, "invalid-aic")
        self.assertEqual(result["status"], "rejected")
        self.discover.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
