"""Offline coordinator behavior; these fixtures are not live AMP evidence."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))

from incident.coordinator.engine import IncidentCoordinator
from incident.coordinator.hypothesis import HypothesisEngine
from incident.coordinator.planner import PlanNode


class FailedParticipantTransport:
    mode = "offline-participant-failure-test"
    tools = ["ops.containers", "incident.verification"]

    def __init__(self, *, confirmed=True, state="unreachable", verify_error=False, health_error=False):
        self.confirmed, self.state = confirmed, state
        self.verify_error, self.health_error = verify_error, health_error
        self.calls, self.health_calls = [], []

    async def call(self, payload):
        self.calls.append(deepcopy(payload))
        if payload["tool"] != "incident.verification":
            raise ConnectionError("offline fixture: operations channel closed")
        if self.verify_error:
            raise TimeoutError("offline fixture: verifier unavailable")
        return {"incident_id": payload["incident_id"], "logical_task_id": payload["logical_task_id"],
                "executor_aic": "local-test-verifier", "status": "ok", "facts": [
                    {"key": key, "value": value, "source": "offline-verifier-fixture"}
                    for key, value in {"business_recovered": True, "service_recovered": True,
                                       "order_observation": {"completed_workflows": 10,
                                                             "duration_seconds": 30, "unknown": 0}}.items()]}

    async def participant_health(self, payload, *, error):
        self.health_calls.append((deepcopy(payload), type(error).__name__))
        if self.health_error:
            raise ValueError("offline fixture: invalid evidence input")
        return {"aic": "local-test-ops", "confirmed": self.confirmed,
                "participant_state": self.state, "reason": "offline-fixture",
                "manual_required": True, "facts": [
                    {"key": "participant_unreachable", "value": self.confirmed,
                     "source": "offline-amp-assessment-fixture"}]}


class CoordinatorParticipantFailureTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, transport):
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory, hypothesis=HypothesisEngine(enabled=False))
            state = engine.new("巡检参与者没有返回")
            return await engine.run(state)

    async def test_business_health_does_not_close_confirmed_participant_failure(self):
        transport = FailedParticipantTransport()
        state = await self.run_case(transport)
        self.assertEqual(state["status"], "needs_attention")
        self.assertIn("participant_unavailable", state["diagnosed_causes"])
        self.assertTrue(state["result"]["business_recovered"])
        self.assertTrue(state["result"]["participant_failure_confirmed"])
        self.assertFalse(state["result"]["participant_recovered"])
        self.assertFalse(state["result"]["incident_resolved"])
        self.assertTrue(state["result"]["participant_manual_required"])
        self.assertEqual([row["kind"] for row in transport.calls], ["observe", "verify"])
        self.assertFalse(state["approvals"])
        self.assertEqual(state["tasks"][0]["error"], "ConnectionError")
        self.assertGreaterEqual(state["tasks"][0]["elapsed_ms"], 0)
        self.assertTrue(any(event["event"] == "participant_unreachable" for event in state["events"]))
        self.assertFalse(any(event["event"] == "original_request_unresolved" for event in state["events"]))
        self.assertEqual(state["model_calls"], 0)

    async def test_unknown_evidence_requires_review_without_diagnosing_agent_failure(self):
        state = await self.run_case(FailedParticipantTransport(confirmed=False, state="unknown"))
        self.assertEqual(state["status"], "needs_attention")
        self.assertNotIn("participant_unavailable", state["diagnosed_causes"])
        self.assertFalse(state["result"]["participant_failure_confirmed"])
        self.assertTrue(state["result"]["business_recovered"])
        self.assertFalse(state["result"]["incident_resolved"])

    async def test_inconsistent_confirmed_reachable_does_not_become_failure_cause(self):
        state = await self.run_case(FailedParticipantTransport(confirmed=True, state="reachable"))
        self.assertNotIn("participant_unavailable", state["diagnosed_causes"])
        self.assertFalse(state["result"]["participant_failure_confirmed"])

    async def test_verifier_failure_preserves_uncertain_business_and_manual_state(self):
        state = await self.run_case(FailedParticipantTransport(verify_error=True))
        self.assertEqual(state["status"], "needs_attention")
        self.assertNotIn("business_recovered", state["result"])
        self.assertFalse(state["result"]["incident_resolved"])
        self.assertTrue(any(event["event"] == "independent_verification_failed" for event in state["events"]))

    async def test_evidence_read_error_cannot_confirm_failure_or_mask_original_error(self):
        transport = FailedParticipantTransport(health_error=True)
        state = await self.run_case(transport)
        self.assertNotIn("participant_health", state)
        self.assertNotIn("participant_unavailable", state["diagnosed_causes"])
        self.assertIsNone(state["result"])
        self.assertIn("ConnectionError", state["error"])
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(any(event["event"] == "participant_health_check_failed" for event in state["events"]))

    async def test_unknown_action_is_not_replayed_or_classified_as_readonly_failure(self):
        transport = FailedParticipantTransport()
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory)
            state = engine.new("修改结果未知")
            # A low-risk fixture node avoids an approval wait; no action tool
            # actually runs in this fake transport.
            node = PlanNode(id="restart", tool="ops.restart", kind="act", resource="orders",
                            reason="offline test", args={"container": "app-v2"}, risk="low")
            with self.assertRaises(ConnectionError):
                await engine._call(state, node.tool, kind="act", args=node.args, node=node)
            self.assertEqual(state["tasks"][0]["status"], "unknown")
            self.assertFalse(transport.health_calls)
            self.assertEqual(len(transport.calls), 1)

    async def test_absent_verifier_does_not_invent_business_result(self):
        transport = FailedParticipantTransport()
        transport.tools = ["ops.containers"]
        state = await self.run_case(transport)
        self.assertEqual(state["status"], "needs_attention")
        self.assertTrue(state["result"]["participant_failure_confirmed"])
        self.assertNotIn("business_recovered", state["result"])
        self.assertEqual(len(transport.calls), 1)

    async def test_cancel_during_diagnosis_keeps_interruption_semantics(self):
        transport = FailedParticipantTransport()

        async def cancelled(*args, **kwargs):
            raise asyncio.CancelledError()

        transport.participant_health = cancelled
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory, hypothesis=HypothesisEngine(enabled=False))
            state = engine.new("offline cancellation")
            with self.assertRaises(asyncio.CancelledError):
                await engine.run(state)
            self.assertEqual(state["status"], "interrupted")
            self.assertIsNone(state["result"])
            self.assertFalse(state.get("participant_health"))

    async def test_cancel_during_independent_verification_preserves_unresolved_participant(self):
        transport = FailedParticipantTransport()
        original_call = transport.call
        verification_started = asyncio.Event()

        async def blocking_verification(payload):
            if payload["tool"] == "incident.verification":
                verification_started.set()
                await asyncio.Future()
            return await original_call(payload)

        transport.call = blocking_verification
        with tempfile.TemporaryDirectory() as directory:
            engine = IncidentCoordinator(transport, directory, hypothesis=HypothesisEngine(enabled=False))
            state = engine.new("offline cancel after participant failure")
            running = asyncio.create_task(engine.run(state))
            await asyncio.wait_for(verification_started.wait(), 5)
            running.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await running
            self.assertEqual(state["status"], "interrupted")
            self.assertTrue(state["result"]["participant_manual_required"])
            self.assertFalse(state["result"]["incident_resolved"])
            self.assertNotIn("business_recovered", state["result"])


if __name__ == "__main__":
    unittest.main()
