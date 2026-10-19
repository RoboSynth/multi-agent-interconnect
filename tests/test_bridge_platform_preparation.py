from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
import domains.setup_platform as platform_preparation
from domains.setup_platform import acs_base, declared_inventory, endpoint_template, native_skills
from acps_mcp_bridge import Policy
from acps_mcp_bridge.acs_mapper import map_acs, validate_acs

spec = importlib.util.spec_from_file_location("fluent_renderer", ROOT / "deploy/fluent-bit/render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class PlatformPreparationTests(unittest.TestCase):
    def test_pending_identity_acs_has_no_fabricated_aic_and_valid_official_schema(self):
        policy = Policy.load(ROOT / "domains/ops/policy.native.yaml")
        endpoint = endpoint_template("amqps://wt.ioa.pub:5671/acps?inbox=inbox_existing")
        draft = map_acs(acs_base("跨域入口运维智能体", None, endpoint), policy, declared_inventory(policy))
        self.assertEqual(draft["aic"], "")
        self.assertEqual(draft["provider"], {"name": "Incident Pilot"})
        self.assertEqual({s["id"] for s in draft["skills"]}, {"ops.observe", "ops.act"})
        self.assertTrue(validate_acs(draft)["official_registry_schema_valid"])

    def test_native_skill_ids_preserved_with_updated_ifc_contract(self):
        self.assertEqual(native_skills("application")[0]["id"], "incident.application")
        self.assertEqual(native_skills("verification")[0]["id"], "incident.verification")
        self.assertIn("ifc/1.0", native_skills("application")[0]["description"])

    def test_optional_onboarding_acs_declares_metadata_only_contract(self):
        draft = acs_base("互联接入检查智能体", None,
                         "amqps://wt.ioa.pub:5671/acps?inbox=inbox_{AIC}")
        draft["skills"] = native_skills("onboarding")
        self.assertEqual(draft["skills"][0]["id"], "aip.onboarding.check")
        self.assertIn("不探测目标运行端点", draft["skills"][0]["description"])
        self.assertTrue(validate_acs(draft)["official_registry_schema_valid"])

    def test_onboarding_preparation_is_opt_in_and_does_not_change_default_skills(self):
        # Temporary references only; no issued cert or platform request is involved.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime").mkdir()
            for domain in ("database", "ops"):
                config = {"policy": str(ROOT / "domains" / domain / "policy.yaml"),
                          "ledger_path": "fixture-ledger.sqlite", "audit_path": "fixture-audit.jsonl",
                          "env_files": []}
                (root / "runtime" / (domain + "-bridge.json")).write_text(json.dumps(config), encoding="utf-8")
            agents = {name: {"aic": "fixture-" + name, "cert": str(root / (name + "-cert.pem")),
                "key": str(root / (name + "-key.pem")),
                "endpoint": "amqps://fixture.invalid:5671/acps?inbox=inbox_fixture-" + name}
                for name in ("leader", "application", "database", "database_backup", "ops", "verification", "onboarding")}
            source = {"agents": agents, "trust_bundle": str(root / "trust.pem"),
                      "discovery_url": "https://fixture.invalid/adp", "mq_auth_url": "https://fixture.invalid/acl"}
            with patch.object(platform_preparation, "ROOT", root):
                report = platform_preparation.prepare(source, root / "optional")
                onboard = json.loads((root / "optional/onboarding.json").read_text(encoding="utf-8"))
                coordinator = json.loads((root / "optional/coordinator.json").read_text(encoding="utf-8"))
                self.assertIn("onboarding", report["identities"])
                self.assertEqual(coordinator["skills"]["onboarding"], "aip.onboarding.check")
                self.assertNotIn("env_file", onboard)
                self.assertNotIn("ledger_path", onboard)
                self.assertEqual(onboard["discovery_url"], source["discovery_url"])
                self.assertFalse(onboard["public_metadata_service"])
                platform_preparation.prepare(source, root / "public", public_onboarding=True)
                public = json.loads((root / "public/onboarding.json").read_text(encoding="utf-8"))
                self.assertTrue(public["public_metadata_service"])
                self.assertNotIn("env_file", public)
                source["agents"].pop("onboarding")
                platform_preparation.prepare(source, root / "default")
                default = json.loads((root / "default/coordinator.json").read_text(encoding="utf-8"))
                self.assertNotIn("onboarding", default["skills"])
                self.assertFalse((root / "default/onboarding.json").exists())
                with self.assertRaisesRegex(ValueError, "onboarding identity"):
                    platform_preparation.prepare(source, root / "missing", public_onboarding=True)
            self.assertNotIn("onboarding", platform_preparation.SKILLS)

    def test_onboarding_cannot_reuse_another_role_or_leader_aic(self):
        for other_role in ("application", "leader"):
            with self.subTest(other_role=other_role), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = {"agents": {"onboarding": {"aic": "fixture-shared"},
                                     other_role: {"aic": "fixture-shared"}}}
                with self.assertRaisesRegex(ValueError, "onboarding.*distinct"):
                    platform_preparation.prepare(source, root / "output")
                self.assertFalse((root / "output").exists())

    def test_kafka_requires_confirmed_endpoint_and_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                renderer.render(directory, directory, ROOT / "deploy/fluent-bit/parsers.conf", mode="kafka", kafka={"brokers": None})
            with self.assertRaises(ValueError):
                renderer.render(directory, directory, ROOT / "deploy/fluent-bit/parsers.conf", mode="kafka",
                    kafka={"brokers": "localhost:19092", "rdkafka": {"security.protocol": "sasl_ssl", "sasl.password": "plaintext-secret"}})


class PlatformAmpBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_emitters_reach_partner_and_handler_is_bound_before_join(self):
        from acps_mcp_bridge.platform import BridgeGroupRuntime
        from incident.amp_setup import AmpRuntime
        from acps_sdk.aip import TaskCommandType
        with tempfile.TemporaryDirectory() as directory:
            amp = AmpRuntime(directory, "bridge-test", "local-test")
            try:
                class Adapter:
                    def bind_partner(self, client):
                        async def handler(command, mentioned):
                            return {"status": "rejected"}
                        client.set_command_handler(handler)
                        return handler
                runtime = BridgeGroupRuntime(bridge=Adapter(), amp=amp, leader_aic="local-test", allowed_peer_aic="peer-test",
                    record=lambda *a, **k: None, rabbitmq_config={"host": "localhost", "port": 5671, "vhost": "/"})
                real_client = runtime._partner_client()
                self.assertIs(real_client._message_emitter, amp.message)
                self.assertIs(real_client._group_access.emitter, amp.access)
                class Partner:
                    group_id = None
                    is_joined = False
                    def set_command_handler(self, handler): self.handler = handler
                    def set_disconnect_handler(self, handler): self.disconnected = handler
                    async def join_group_from_invitation(self, invitation):
                        self.group_id = invitation.groupId
                        command = SimpleNamespace(groupId=self.group_id, sessionId="s", taskId="t", command=TaskCommandType.Start)
                        self.result = await self.handler(command, True)
                        self.is_joined = True
                        return True
                    async def close(self): pass
                partner = Partner()
                runtime._partner_client = lambda: partner
                runtime._invitation_policy = lambda invitation: None
                await runtime._accept_probe_invitation(SimpleNamespace(groupId="group-test"))
                self.assertEqual(partner.result["status"], "rejected")
                self.assertEqual(len(amp.sampler.samples), 1)
                self.assertEqual(amp.sampler.active, 0)
            finally:
                await amp.close()


if __name__ == "__main__":
    unittest.main()
