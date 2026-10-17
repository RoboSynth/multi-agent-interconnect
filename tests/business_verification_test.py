"""Verification boundary regression; does not connect to or modify the target."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.partners import VerificationPartner


class VerificationFreshWorkflows(unittest.IsolatedAsyncioTestCase):
    async def test_two_verification_tasks_use_disjoint_order_namespaces(self):
        summary = {"passed": True, "completed_workflows": 10, "duration_seconds": 30}
        with patch("business.load.OrderObserver") as observer:
            observer.return_value.observe = AsyncMock(return_value=summary)
            partner = VerificationPartner("verifier", allowed_callers=["coordinator"])
            for logical_task_id in ("verify-first", "verify-after-second-repair"):
                result = await partner.execute({"schema_version": "ifc/1.0", "incident_id": "inc-repeat",
                    "logical_task_id": logical_task_id, "kind": "verify", "tool": "incident.verification", "args": {}}, "coordinator")
                recovered = next(f["value"] for f in result["facts"] if f["key"] == "business_recovered")
                self.assertTrue(recovered)
            namespaces = [call.kwargs["run_id"] for call in observer.call_args_list]
            first_keys = {f"load-{namespaces[0]}-{i:06d}" for i in range(10)}
            second_keys = {f"load-{namespaces[1]}-{i:06d}" for i in range(10)}
            self.assertTrue(first_keys.isdisjoint(second_keys))
            for call in observer.return_value.observe.call_args_list:
                self.assertEqual(call.kwargs, {"duration": 30, "min_complete": 10})


if __name__ == "__main__":
    unittest.main()
