"""Offline persisted model configuration and workbench wiring; no real HTTP."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from incident.coordinator.hypothesis import HypothesisEngine
from tools.configure_local_coordinator import configure, local_model_settings
from workbench_server import create_app


class WorkbenchModelConfigTests(unittest.TestCase):
    def test_check_is_read_only_and_first_write_defaults_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "not-created/coordinator.json"
            checked = configure(config, check=True)
            self.assertIs(checked["llm_enabled"], False)
            self.assertFalse(config.parent.exists())
            configured = configure(config)
            self.assertIs(configured["llm_enabled"], False)
            self.assertEqual(json.loads(config.read_bytes()), configured)

    def test_explicit_local_opt_in_and_ordinary_rerun_preserve_user_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "coordinator.json"
            initial = configure(config, enable_llm=True, model_base_url="http://localhost:9090/v1", model="local-choice",
                max_output_tokens=256, model_call_budget=7, model_token_budget=8192, model_timeout_seconds=12.5)
            initial.update(journal_path="chosen.sqlite", coordinator_aic="chosen-coordinator", custom={"keep": True}, workers=[])
            config.write_text(json.dumps(initial), encoding="utf-8")
            original_bytes = config.read_bytes()
            self.assertEqual(configure(config), initial)
            self.assertEqual(config.read_bytes(), original_bytes)
            disabled = configure(config, enable_llm=False)
            self.assertIs(disabled["llm_enabled"], False)
            self.assertEqual(disabled["llm_model"], "local-choice")
        with tempfile.TemporaryDirectory() as directory:
            settings = local_model_settings(configure(Path(directory) / "new.json", enable_llm=True))
            self.assertEqual((settings["base_url"], settings["model"]), ("http://127.0.0.1:8089/v1", "Qwen3-1.7B-Q8_0"))

    def test_cli_check_preserves_an_existing_enabled_model_without_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "coordinator.json"
            configure(config, enable_llm=True)
            before = config.read_bytes()
            result = subprocess.run([sys.executable, "-S", str(ROOT / "tools/configure_local_coordinator.py"),
                "--check", "--config", str(config)], capture_output=True, text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}, check=True)
            self.assertIs(json.loads(result.stdout)["llm_enabled"], True)
            self.assertEqual(config.read_bytes(), before)

    def test_invalid_local_settings_fail_before_writing(self):
        cases = [{"llm_base_url": "https://external.invalid/v1"}, {"llm_base_url": "http://user:password@localhost:8089/v1"},
            {"llm_base_url": "http://localhost:8089/v1?redirect=external"}, {"llm_base_url": ""}, {"llm_model": ""},
            {"llm_max_calls": 0}, {"llm_max_calls": True}, {"llm_token_budget": -1}, {"llm_max_output_tokens": "768"},
            {"llm_timeout_seconds": float("nan")}, {"llm_timeout_seconds": True}, {"llm_enabled": "true"}]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "coordinator.json"
            valid = configure(config, enable_llm=True)
            for change in cases:
                with self.subTest(change=change):
                    config.write_text(json.dumps({**valid, **change}), encoding="utf-8")
                    before = config.read_bytes()
                    with self.assertRaises(ValueError):
                        configure(config)
                    self.assertEqual(config.read_bytes(), before)
            for missing in ("llm_base_url", "llm_model"):
                broken = dict(valid)
                del broken[missing]
                config.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises(ValueError):
                    configure(config, check=True)

    def test_persisted_values_reach_injected_transport_workbench_and_raw_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "coordinator.json"
            values = configure(config, enable_llm=True, model_base_url="http://127.0.0.1:9090/v1", model="persisted-local",
                max_output_tokens=300, model_call_budget=9, model_token_budget=9000, model_timeout_seconds=17)
            # BOM and whitespace must be included in the loaded-byte fingerprint.
            raw = b"\xef\xbb\xbf" + json.dumps(values, indent=3).encode() + b"\n\n"
            config.write_bytes(raw)
            transport = SimpleNamespace(mode="fake_test_transport", participants=[], close=AsyncMock())
            with patch.dict("os.environ", {"INCIDENT_LLM_BASE_URL": "https://external.invalid/v1",
                    "INCIDENT_LLM_MODEL": "wrong-env-model", "INCIDENT_LLM_API_KEY": "offline-test-key"}), \
                    patch("incident.coordinator.hypothesis.httpx.AsyncClient", side_effect=AssertionError("unexpected HTTP")):
                app = create_app(config, Path(directory) / "output", transport)
                with TestClient(app) as client:
                    state = client.get("/api/state").json()
                    self.assertEqual(state["config_sha256"], hashlib.sha256(raw).hexdigest())
                    self.assertEqual(state["model"], "persisted-local")
                    self.assertEqual(state["model_config"], {"enabled": True, "base_url": "http://127.0.0.1:9090/v1",
                        "model": "persisted-local", "max_output_tokens": 300, "max_calls": 9,
                        "token_budget": 9000, "timeout_seconds": 17})
                    self.assertEqual(app.state.engine.hypothesis.api_key, "")
                    self.assertNotIn("offline-test-key", json.dumps(state))

    def test_invalid_enabled_workbench_refuses_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "coordinator.json"
            config.write_text(json.dumps({"llm_enabled": True}), encoding="utf-8")
            transport = SimpleNamespace(mode="fake_test_transport", participants=[], close=AsyncMock())
            with self.assertRaisesRegex(ValueError, "persisted llm_base_url"):
                with TestClient(create_app(config, Path(directory) / "output", transport)):
                    self.fail("Invalid enabled configuration started")

    def test_disabled_local_model_never_calls_http_and_missing_config_hash_is_null(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = SimpleNamespace(mode="fake_test_transport", participants=[], close=AsyncMock())
            with patch("incident.coordinator.hypothesis.httpx.AsyncClient", side_effect=AssertionError("unexpected HTTP")):
                app = create_app(Path(directory) / "missing.json", Path(directory) / "output", transport)
                with TestClient(app) as client:
                    state = client.get("/api/state").json()
                    self.assertIsNone(state["config_sha256"])
                    self.assertIs(state["model_config"]["enabled"], False)
                    self.assertEqual(state["model"], "rules")
                    asyncio.run(app.state.engine.hypothesis.generate("healthy", [], []))

    def test_remote_wutong_keeps_existing_environment_model_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "remote.json"
            config.write_text(json.dumps({"mode": "wutong-amqps", "llm_enabled": True,
                "llm_base_url": "ignored-config", "llm_max_calls": "ignored-existing-field"}), encoding="utf-8")
            transport = SimpleNamespace(mode="wutong-amqps", participants=[], close=AsyncMock())
            for endpoint, public in (("https://existing-remote.invalid/v1", "https://existing-remote.invalid/v1"),
                    ("https://user:offline-password@existing-remote.invalid/v1?key=offline-value", "[REDACTED]")):
                with self.subTest(endpoint=endpoint), patch.dict("os.environ", {"INCIDENT_LLM_BASE_URL": endpoint,
                        "INCIDENT_LLM_MODEL": "existing-remote-model", "INCIDENT_LLM_API_KEY": "existing-remote-key"}):
                    app = create_app(config, Path(directory) / "output", transport)
                    with TestClient(app) as client:
                        state = client.get("/api/state").json()
                        self.assertEqual(state["model"], "existing-remote-model")
                        self.assertEqual(state["model_config"]["base_url"], public)
                        self.assertEqual(app.state.engine.hypothesis.base_url, endpoint)
                        self.assertEqual(app.state.engine.hypothesis.api_key, "existing-remote-key")

    def test_explicit_empty_model_api_key_does_not_inherit_environment(self):
        with patch.dict("os.environ", {"INCIDENT_LLM_API_KEY": "offline-only-inherited-key"}):
            self.assertEqual(HypothesisEngine(api_key="").api_key, "")
            self.assertEqual(HypothesisEngine().api_key, "offline-only-inherited-key")


if __name__ == "__main__":
    unittest.main()
