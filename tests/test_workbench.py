"""Local API behavior, approval typing and renderer entry points."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from workbench_server import create_app


class WorkbenchTests(unittest.TestCase):
    def test_original_intent_input_is_strict_and_reaches_incident_state(self):
        cases = [({}, False), ({"original_request_unknown": True}, True),
                 ({"original_request_key": "request-one"}, True)]
        for fields, expected_unknown in cases:
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as directory:
                transport = SimpleNamespace(mode="fake_test_transport", participants=[], close=AsyncMock())
                with patch("workbench_server.IncidentCoordinator.run", new=AsyncMock()):
                    with TestClient(create_app(Path(directory)/"absent.json", Path(directory)/"output", transport)) as client:
                        response = client.post("/api/incidents", json={"symptom": "订单异常", **fields})
                        self.assertEqual(response.status_code, 202)
                        saved = client.get("/api/incidents/"+response.json()["id"]).json()
                        self.assertIs(saved["original_request_unknown"], expected_unknown)
                        self.assertEqual(saved["original_request_key"], fields.get("original_request_key"))
                        page = client.get("/").text
                        self.assertIn('id="original-unknown" type="checkbox"', page)
                        self.assertIn("存在结果未知的原请求", page)
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory)/"absent.json", Path(directory)/"output")) as client:
                for value in ("false", "true", 0, 1, None):
                    response = client.post("/api/incidents", json={"symptom": "订单异常", "original_request_unknown": value})
                    self.assertEqual(response.status_code, 422)

    def test_unconfigured_workbench_explains_missing_participants(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory)/"absent.json", Path(directory)/"output")
            with TestClient(app) as client:
                self.assertFalse(client.get("/api/state").json()["connected"])
                response = client.post("/api/incidents", json={"symptom": "订单失败"})
                self.assertEqual(response.status_code, 503)
                self.assertIn("参与者尚未连接", response.json()["detail"])
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/assets/workbench.js").status_code, 200)

    def test_approval_rejects_string_false_and_foreign_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory)/"absent.json", Path(directory)/"output")) as client:
                response = client.post("/api/approvals/missing", json={"approved": "false"})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(client.post("/api/approvals/missing", json={"approved": False}).status_code, 404)
                response = client.post("/api/incidents", json={"symptom": "test"}, headers={"Origin": "https://foreign.example"})
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
