import asyncio
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from incident.selection import select_participant


class ParticipantSelectionTests(unittest.IsolatedAsyncioTestCase):
    def description(self, aic):
        return {"executor_aic": aic, "resources": ["orders"], "tools": ["db.read_only_status"]}

    async def test_allowlist_filters_before_describe_and_empty_denies_all(self):
        calls = []
        async def describe(acs):
            calls.append(acs["aic"])
            return self.description(acs["aic"])
        candidates = [{"aic": "new-agent"}, {"aic": "old-agent"}]
        chosen, _ = await select_participant(candidates, resource="orders", tool="db.read_only_status",
            describe=describe, trusted_aics={"old-agent"})
        self.assertEqual(chosen["aic"], "old-agent")
        self.assertEqual(calls, ["old-agent"])
        calls.clear()
        with self.assertRaises(RuntimeError):
            await select_participant(candidates, resource="orders", tool="db.read_only_status",
                describe=describe, trusted_aics=set())
        self.assertEqual(calls, [])

    async def test_unresponsive_candidate_times_out_then_available_candidate_is_confirmed(self):
        cancelled, calls, events = set(), [], []
        async def describe(acs):
            aic = acs["aic"]
            calls.append(aic)
            if aic == "a-unresponsive":
                try:
                    await asyncio.Future()
                finally:
                    cancelled.add(aic)
            return self.description(aic)
        chosen, _ = await select_participant(
            [{"aic": "a-unresponsive"}, {"aic": "b-available"}],
            resource="orders", tool="db.read_only_status", describe=describe,
            describe_timeout_seconds=0.01, record=lambda event, **data: events.append((event, data)))
        self.assertEqual(chosen["aic"], "b-available")
        self.assertEqual(calls, ["a-unresponsive", "b-available"])
        self.assertEqual(cancelled, {"a-unresponsive"})
        self.assertEqual(events[0][0], "participant_not_confirmed")
        self.assertEqual(events[0][1]["error_class"], "TimeoutError")

    async def test_none_retains_candidate_scope_and_existing_sorted_winner(self):
        calls = []
        async def describe(acs):
            calls.append(acs["aic"])
            return self.description(acs["aic"])
        chosen, _ = await select_participant([{"aic": "z-agent"}, {"aic": "a-agent"}],
            resource="orders", tool="db.read_only_status", describe=describe, trusted_aics=None)
        self.assertEqual(chosen["aic"], "a-agent")
        self.assertEqual(calls, ["a-agent", "z-agent"])

    async def test_allowlist_is_exact_and_invalid_deadlines_fail_before_describe(self):
        calls = []
        async def describe(acs):
            calls.append(acs["aic"])
            return self.description(acs["aic"])
        with self.assertRaises(RuntimeError):
            await select_participant([{"aic": "old-agent"}], resource="orders",
                tool="db.read_only_status", describe=describe, trusted_aics={"OLD-AGENT"})
        for timeout in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                await select_participant([{"aic": "old-agent"}], resource="orders",
                    tool="db.read_only_status", describe=describe, describe_timeout_seconds=timeout)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
