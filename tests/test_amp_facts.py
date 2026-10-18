"""Participant failure inference must never convert telemetry absence to death."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.coordinator.amp_facts import AmpFactStore, ManagementStatusEvidence, TaskEvidence


def heartbeat(aic="ops", stamp=10, identifier="hb"):
    return {"schema_version": "1.0", "log_type": "heartbeat", "log_id": identifier, "aic": aic,
            "timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(), "body": {"uptimeSeconds": 1}}


def access(aic="ops", stamp=95, status=200, *, callee=None, identifier="access"):
    return {**heartbeat(aic, stamp, identifier), "log_type": "access", "body": {
        "durationMs": 2, "callee": {"aic": aic if callee is None else callee}, "response": {"statusCode": status}}}


class AmpFactsTests(unittest.TestCase):
    def assessment(self, store=None, *, status="deadline_expired", task=None, management=None, now=100):
        store = store or AmpFactStore()
        return store.assess("ops", now=now,
            task=task or TaskEvidence("ops", status, 91, deadline=90),
            management=management or ManagementStatusEvidence("ops", "timeout", 92, 95))

    def test_three_signals_confirm_exact_participant_without_claiming_business_failure(self):
        store = AmpFactStore()
        store.ingest([heartbeat()], now=100)
        for status in ("deadline_expired", "channel_lost"):
            with self.subTest(status=status):
                result = self.assessment(store, status=status)
                self.assertTrue(result["confirmed"])
                self.assertEqual(result["participant_state"], "unreachable")
                self.assertEqual(result["task_status"], status)
                self.assertEqual(result["aic"], "ops")
                self.assertEqual(result["business_state"], "unknown")
                self.assertTrue(result["manual_required"])
                json.dumps(result, allow_nan=False)

    def test_no_record_or_another_aic_cannot_mean_expired(self):
        for rows in ([], [heartbeat("ops-backup")], [heartbeat("prefix-ops")]):
            with self.subTest(rows=rows):
                store = AmpFactStore()
                store.ingest(rows, now=100)
                self.assertFalse(self.assessment(store)["confirmed"])
                self.assertEqual(self.assessment(store)["evidence"]["heartbeat_state"], "unknown")

    def test_one_missing_signal_never_confirms(self):
        store = AmpFactStore()
        store.ingest([heartbeat()], now=100)
        for task, management in ((None, None), (TaskEvidence("ops", "unknown", 91), ManagementStatusEvidence("ops", "timeout", 92, 95)),
            (TaskEvidence("ops", "channel_lost", 91), None)):
            with self.subTest(task=task, management=management):
                self.assertFalse(store.assess("ops", task=task, management=management, now=100)["confirmed"])

    def test_recent_heartbeat_success_or_business_error_blocks_unreachable(self):
        for row in (heartbeat(stamp=99, identifier="fresh"), access(), access(status=500)):
            with self.subTest(row=row):
                store = AmpFactStore()
                store.ingest([heartbeat(), row], now=100)
                result = self.assessment(store)
                self.assertFalse(result["confirmed"])
                self.assertEqual(result["participant_state"], "reachable")
                self.assertEqual(result["business_state"], "unknown")

    def test_sender_publish_access_does_not_prove_target_replied(self):
        store = AmpFactStore()
        store.ingest([heartbeat(), access("leader", callee="ops", status=202)], now=100)
        self.assertTrue(self.assessment(store)["confirmed"])

    def test_success_before_later_failure_is_retained_without_claiming_current_reachability(self):
        for status in ("channel_lost", "deadline_expired"):
            with self.subTest(status=status):
                store = AmpFactStore()
                store.ingest([heartbeat(stamp=90), access(stamp=90)], now=100)
                initial = self.assessment(store, status=status)
                self.assertEqual(initial["participant_state"], "unknown")
                self.assertFalse(initial["confirmed"])
                self.assertEqual(initial["evidence"]["access_state"], "success")
                self.assertEqual(initial["evidence"]["access_age_seconds"], 10)
                self.assertFalse(initial["evidence"]["access_after_task_failure"])
                self.assertFalse(initial["evidence"]["heartbeat_after_task_failure"])
                # Access is still fresh at 46 seconds, but predates the failure.
                # HB45 truly expired; task/query evidence is still within60.
                later = self.assessment(store, status=status, now=136)
                self.assertTrue(later["confirmed"])
                self.assertEqual(later["evidence"]["access_state"], "success")
                self.assertEqual(later["evidence"]["heartbeat_state"], "expired")

    def test_response_at_or_after_failure_prevents_confirmation(self):
        for stamp in (91, 99):
            for row in (heartbeat(stamp=stamp, identifier="post"), access(stamp=stamp)):
                with self.subTest(stamp=stamp, kind=row["log_type"]):
                    store = AmpFactStore()
                    store.ingest([heartbeat(), row], now=100)
                    result = self.assessment(store, status="channel_lost")
                    self.assertEqual(result["participant_state"], "reachable")
                    self.assertFalse(result["confirmed"])
                    self.assertTrue(result["evidence"][row["log_type"] + "_after_task_failure"])

    def test_management_reply_overrides_failure_and_outcomes_stay_distinct(self):
        store = AmpFactStore()
        store.ingest([heartbeat()], now=100)
        for outcome in ("reply", "timeout", "no_reply", "unknown", "published"):
            with self.subTest(outcome=outcome):
                result = self.assessment(store, management=ManagementStatusEvidence("ops", outcome, 92, 95))
                self.assertEqual(result["confirmed"], outcome in {"timeout", "no_reply"})
                self.assertEqual(result["evidence"]["management_outcome"], outcome if outcome != "published" else "unknown")
                if outcome == "reply":
                    self.assertEqual(result["participant_state"], "reachable")

    def test_management_must_be_after_failure_current_and_for_exact_aic(self):
        store = AmpFactStore()
        store.ingest([heartbeat()], now=100)
        cases = [ManagementStatusEvidence("other", "timeout", 92, 95),
                 ManagementStatusEvidence("ops", "timeout", 89, 95),
                 ManagementStatusEvidence("ops", "timeout", 96, 95),
                 ManagementStatusEvidence("ops", "timeout", 92, 101),
                 ManagementStatusEvidence("ops", "timeout", 1, 2)]
        for evidence in cases:
            with self.subTest(evidence=evidence):
                self.assertFalse(self.assessment(store, management=evidence)["confirmed"])

    def test_task_deadline_channel_loss_and_unknown_times_are_not_conflated(self):
        store = AmpFactStore()
        store.ingest([heartbeat()], now=100)
        for task in (TaskEvidence("other", "channel_lost", 91), TaskEvidence("ops", "deadline_expired", 91),
                     TaskEvidence("ops", "deadline_expired", 91, 92), TaskEvidence("ops", "channel_lost", 101),
                     TaskEvidence("ops", "channel_lost", float("nan")), TaskEvidence("ops", "channel_lost", 1),
                     TaskEvidence("ops", "deadline_expired", True, 0)):
            with self.subTest(task=task):
                self.assertFalse(self.assessment(store, task=task)["confirmed"])
        self.assertTrue(self.assessment(store, task=TaskEvidence("ops", "channel_lost", 91))["confirmed"])

    def test_future_invalid_duplicate_and_out_of_order_records_do_not_refresh_evidence(self):
        store = AmpFactStore()
        invalid = heartbeat(identifier="reused")
        invalid["timestamp"] = "2026-01-01T00:00:00"
        future = heartbeat(stamp=101, identifier="reused")
        stats = store.ingest([invalid, future, heartbeat(identifier="reused"), heartbeat(stamp=99, identifier="reused")], now=100)
        self.assertEqual((stats["invalid"], stats["future"], stats["accepted"], stats["duplicates"]), (1, 1, 1, 1))
        self.assertTrue(self.assessment(store)["confirmed"])
        store.ingest([heartbeat(stamp=90, identifier="new"), heartbeat(stamp=1, identifier="older")], now=100)
        self.assertEqual(self.assessment(store)["evidence"]["heartbeat_age_seconds"], 10)
        future_only = AmpFactStore()
        future_only.ingest([future], now=100)
        self.assertFalse(self.assessment(future_only)["confirmed"])

    def test_missing_corrupt_files_are_diagnostics_only_and_bodies_do_not_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "amp.jsonl"
            row = heartbeat()
            row["body"]["private_value"] = "do-not-copy-body"
            path.write_text("not json\n" + json.dumps(row) + "\n", encoding="utf-8")
            store = AmpFactStore()
            stats = store.load_jsonl([path, Path(folder) / "absent"], now=100)
            self.assertEqual((stats["invalid"], stats["unreadable_files"], stats["accepted"]), (1, 1, 1))
            self.assertNotIn("do-not-copy-body", json.dumps(self.assessment(store)))
            empty = AmpFactStore()
            empty.load_jsonl(Path(folder) / "absent", now=100)
            self.assertEqual(self.assessment(empty)["participant_state"], "unknown")

    def test_ttl_boundary_and_ageing_do_not_renew_source_observed_at(self):
        store = AmpFactStore(heartbeat_ttl_seconds=90)
        store.ingest([heartbeat()], now=100)
        self.assertEqual(self.assessment(store)["evidence"]["heartbeat_state"], "fresh")
        result = self.assessment(store, now=101)
        self.assertTrue(result["confirmed"])
        fact = next(row for row in result["facts"] if row["key"] == "participant_heartbeat_status")
        self.assertEqual(fact["observed_at"], datetime.fromtimestamp(10, timezone.utc).isoformat())
        self.assertFalse(self.assessment(store, now=200)["confirmed"])

    def test_real_official_emitters_are_consumed_without_native_transport_or_resources(self):
        from acps_sdk.amp import AccessEmitter, HeartbeatEmitter
        from acps_sdk.amp.models import AccessBody, AccessParticipant, AccessResponse
        with tempfile.TemporaryDirectory() as folder:
            hb, log = Path(folder) / "hb.jsonl", Path(folder) / "access.jsonl"
            HeartbeatEmitter(hb, "ops").emit_sync()
            AccessEmitter(log, "ops").emit_sync(AccessBody(callee=AccessParticipant(aic="ops"), response=AccessResponse(status_code=200)))
            store = AmpFactStore()
            import time
            now = time.time()
            self.assertEqual(store.load_jsonl([hb, log], now=now)["accepted"], 2)
            result = store.assess("ops", now=now)
            self.assertEqual(result["participant_state"], "reachable")
            self.assertEqual(result["evidence"]["access_state"], "success")

    def test_invalid_settings_reject_and_storage_is_bounded(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AmpFactStore(heartbeat_ttl_seconds=value)
        store = AmpFactStore(capacity=2)
        store.ingest([heartbeat(identifier=str(n)) for n in range(4)], now=100)
        self.assertEqual(len(store._records), 2)
        with self.assertRaises(ValueError):
            store.assess("ops", now=True)
        with self.assertRaises(ValueError):
            store.assess("", now=100)


if __name__ == "__main__":
    unittest.main()
