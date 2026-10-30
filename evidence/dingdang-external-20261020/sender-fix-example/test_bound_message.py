import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
spec = importlib.util.spec_from_file_location("bound_message_example", HERE / "bound_message.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from acps_sdk.aip.aip_identity import AipIdentityError

SENDER = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
OTHER = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JU5"


class PublisherPatchTests(unittest.TestCase):
    def test_invitation_and_task_publish_standard_property(self):
        for kind in ("group-invitation", "task-command", "task-result", "group-mgmt-command"):
            with self.subTest(kind=kind):
                payload = {"type": kind, "senderId": SENDER, "groupId": "offline-example"}
                message = module.bound_message(payload, local_aic=SENDER)
                self.assertEqual(message.user_id, SENDER)
                self.assertEqual(json.loads(message.body), payload)
                self.assertEqual(message.content_type, "application/json")

    def test_trace_headers_preserved_but_not_used_as_identity(self):
        headers = {"traceparent": "existing-trace", "user_id": OTHER}
        message = module.bound_message({"senderId": SENDER}, local_aic=SENDER, headers=headers)
        self.assertEqual(message.headers, headers)
        self.assertEqual(message.user_id, SENDER)

    def test_sender_mismatch_is_rejected(self):
        with self.assertRaises(AipIdentityError):
            module.bound_message({"senderId": OTHER}, local_aic=SENDER)

    def test_missing_sender_is_rejected(self):
        with self.assertRaises(AipIdentityError):
            module.bound_message({"type": "group-invitation"}, local_aic=SENDER)


if __name__ == "__main__":
    unittest.main()
