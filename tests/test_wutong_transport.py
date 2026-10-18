import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from incident.wutong_transport import WutongTransport


class WutongTakeoverTests(unittest.IsolatedAsyncioTestCase):
    def transport(self, directory, name="run"):
        config = {"leader": {"aic": "coordinator", "cert": "unused", "key": "unused"},
                  "term_journal_path": str(Path(directory) / "terms.sqlite"),
                  "discovery_url": "https://unused.invalid/discover", "skills": {"database": "db.observe"}}
        with patch("incident.wutong_transport.AmpRuntime"):
            transport = WutongTransport(config, Path(directory) / name)
        transport.selected = {"database": "primary"}
        transport.descriptions = {"database": {"resource_scope": {"database": "orders"}}}
        transport.session = SimpleNamespace(session_id="group-session")
        transport.runtime = SimpleNamespace(force_remove_partner=AsyncMock())
        transport._describe = AsyncMock(return_value={"executor_aic": "backup",
            "resource_scope": {"database": "orders"}, "tools": ["db.restore_writes"]})
        return transport

    def payload(self, transport):
        return {"schema_version": "ifc/1.0", "incident_id": "incident", "logical_task_id": "logical",
                "kind": "act", "tool": "db.restore_writes", "args": {}, "operation_id": "operation",
                "fence": {"coordinator_term": transport.term, "takeover_version": 0}}

    async def exercise(self, state, status="ok", *, initial_primary=False):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            if initial_primary:
                transport.config["initial_participant_aics"] = {"database": "primary"}
                transport.config["trusted_participant_aics"] = {"database": ["primary", "backup"]}
            control = {"status": status, "logical_task_id": "logical", "operation": {"state": state,
                "active_fence": {"coordinator_term": transport.term, "takeover_version": 1}}, "facts": []}
            transport._send = AsyncMock(side_effect=[TimeoutError(), control,
                {"status": "ok", "facts": [], "operation": {"state": "applied"}}])
            with patch("incident.wutong_transport.discover_candidates", AsyncMock(return_value=[{"aic": "primary"}, {"aic": "backup"}])):
                result = await transport.call(self.payload(transport))
            calls = transport._send.call_args_list
            return result, calls, transport

    async def test_coordinator_term_persists_across_output_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.transport(directory, "first")
            second = self.transport(directory, "second")
            self.assertGreater(second.term, first.term)

    async def test_applied_operation_is_reconciled_without_second_modification(self):
        result, calls, transport = await self.exercise("skipped_already_applied")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[0]["kind"], "resume")
        self.assertEqual(calls[1].args[0]["operation_id"], "operation")
        self.assertEqual(transport.selected["database"], "backup")
        transport.runtime.force_remove_partner.assert_awaited_once()

    async def test_unknown_effect_is_not_retried(self):
        result, calls, _ = await self.exercise("unknown", "unknown")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(calls), 2)

    async def test_received_operation_reuses_identity_with_confirmed_fence(self):
        result, calls, transport = await self.exercise("received", initial_primary=True)
        self.assertEqual(result["status"], "ok")
        retry = calls[2].args[0]
        self.assertEqual(retry["logical_task_id"], "logical")
        self.assertEqual(retry["operation_id"], "operation")
        self.assertEqual(retry["fence"]["takeover_version"], 1)
        self.assertEqual(transport.selected["database"], "backup")

    async def test_same_skill_on_different_resource_cannot_take_over(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport._describe.return_value["resource_scope"] = {"database": "other"}
            transport._send = AsyncMock(side_effect=TimeoutError())
            with patch("incident.wutong_transport.discover_candidates", AsyncMock(return_value=[{"aic": "backup"}])):
                with self.assertRaises(TimeoutError) as failed:
                    await transport.call(self.payload(transport))
            self.assertIsInstance(failed.exception.__cause__, RuntimeError)
            self.assertEqual(transport._send.await_count, 1)
            transport.runtime.force_remove_partner.assert_not_awaited()

    async def test_handover_does_not_refresh_old_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.evidence["incident"] = [
                {"key": "old", "observed_at": "2020-01-01T00:00:00+00:00"},
                {"key": "unknown"},
                {"key": "fresh", "observed_at": datetime.now(timezone.utc).isoformat()}]
            refs = transport._handover_evidence("incident")
            now = datetime.now(timezone.utc).timestamp()
            self.assertLess(refs[0]["expires_at"], now)
            self.assertEqual(refs[1]["expires_at"], 0)
            self.assertGreater(refs[2]["expires_at"], now)

    async def test_trusted_role_aics_are_filtered_before_any_invitation(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.config["trusted_participant_aics"] = {"database": ["primary"]}
            transport.runtime.invite_partner = AsyncMock()
            transport._describe = WutongTransport._describe.__get__(transport, WutongTransport)
            transport._send = AsyncMock(return_value={"status": "ok", "executor_aic": "primary",
                "description": {"resources": ["orders"], "tools": ["db.read_only_status"]}})
            chosen, _ = await transport._select_participant("database",
                [{"aic": "new-unapproved"}, {"aic": "primary"}], "db.read_only_status")
            self.assertEqual(chosen["aic"], "primary")
            transport.runtime.invite_partner.assert_awaited_once()
            self.assertEqual(transport.runtime.invite_partner.call_args.args[1].aic, "primary")
            transport.config["trusted_participant_aics"]["database"] = []
            with self.assertRaises(RuntimeError):
                await transport._select_participant("database", [{"aic": "primary"}], "db.read_only_status")
            self.assertEqual(transport.runtime.invite_partner.await_count, 1)

    async def test_candidate_deadline_records_the_invitation_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.config["participant_describe_timeout_seconds"] = 0.01
            async def never_joins(*args, **kwargs):
                await asyncio.Future()
            transport.runtime.invite_partner = AsyncMock(side_effect=never_joins)
            transport._describe = WutongTransport._describe.__get__(transport, WutongTransport)
            transport._send = AsyncMock()
            with self.assertRaises(RuntimeError):
                await transport._select_participant("database", [{"aic": "primary"}], "db.read_only_status")
            transport._send.assert_not_awaited()
            events = [json.loads(row) for row in (transport.output / "events.jsonl").read_text().splitlines()]
            failed = next(row for row in events if row["event"] == "capability_confirmation_failed")
            self.assertEqual(failed["phase"], "invite")
            self.assertEqual(failed["error_class"], "CancelledError")
            self.assertTrue(any(row["event"] == "participant_not_confirmed"
                and row["error_class"] == "TimeoutError" for row in events))

    async def test_initial_primary_does_not_depend_on_aic_sort_order(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.config["initial_participant_aics"] = {"database": "z-primary"}
            transport.config["trusted_participant_aics"] = {"database": ["a-backup", "z-primary"]}
            transport.runtime.invite_partner = AsyncMock()
            transport._describe = WutongTransport._describe.__get__(transport, WutongTransport)
            transport._send = AsyncMock(return_value={"status": "ok", "executor_aic": "z-primary",
                "description": {"resources": ["orders"], "tools": ["db.read_only_status"]}})
            chosen, _ = await transport._select_participant("database",
                [{"aic": "a-backup"}, {"aic": "z-primary"}], "db.read_only_status", initial=True)
            self.assertEqual(chosen["aic"], "z-primary")
            transport.runtime.invite_partner.assert_awaited_once()
            self.assertEqual(transport.runtime.invite_partner.call_args.args[1].aic, "z-primary")

    async def test_missing_or_untrusted_initial_primary_never_invites_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.config["initial_participant_aics"] = {"database": "z-primary"}
            transport.config["trusted_participant_aics"] = {"database": ["a-backup"]}
            for candidates in ([{"aic": "a-backup"}], [{"aic": "a-backup"}, {"aic": "z-primary"}]):
                with self.assertRaises(RuntimeError):
                    await transport._select_participant("database", candidates, "db.read_only_status", initial=True)
            transport._describe.assert_not_awaited()
            for value in ("", " z-primary", None, ["z-primary"]):
                transport.config["initial_participant_aics"]["database"] = value
                with self.subTest(value=value), self.assertRaises(ValueError):
                    await transport._select_participant("database", [{"aic": "z-primary"}],
                        "db.read_only_status", initial=True)
            transport._describe.assert_not_awaited()

    async def test_onboarding_is_selected_for_public_metadata_resource_only(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.config["trusted_participant_aics"] = {"onboarding": ["onboarding"]}
            transport._describe = AsyncMock(return_value={"executor_aic": "onboarding",
                "resources": ["public-acs"], "tools": ["aip.onboarding.check"]})
            chosen, _ = await transport._select_participant("onboarding",
                [{"aic": "onboarding"}], "aip.onboarding.check", initial=True)
            self.assertEqual(chosen["aic"], "onboarding")
            transport._describe.return_value["resources"] = ["orders"]
            with self.assertRaises(RuntimeError):
                await transport._select_participant("onboarding",
                    [{"aic": "onboarding"}], "aip.onboarding.check", initial=True)

    async def test_onboarding_observation_routes_to_confirmed_onboarding_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport(directory)
            transport.selected["onboarding"] = "onboarding"
            transport._send = AsyncMock(return_value={"status": "ok", "facts": []})
            payload = {"schema_version": "ifc/1.0", "incident_id": "onboarding-check",
                "logical_task_id": "metadata-check", "kind": "observe", "tool": "aip.onboarding.check",
                "args": {"target_aic": "target"}}
            result = await transport.call(payload)
            self.assertEqual(result["status"], "ok")
            transport._send.assert_awaited_once_with(payload, "onboarding")


if __name__ == "__main__":
    unittest.main()
