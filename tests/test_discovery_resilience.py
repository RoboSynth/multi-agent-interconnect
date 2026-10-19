"""Read-only discovery retries are bounded and do not hide final failures."""
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
from incident.selection import discover_candidates


class DiscoveryRetryTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, sequence):
        requests, events = [], []
        def handle(request):
            requests.append(request)
            value = sequence[len(requests)-1]
            if isinstance(value, type) and issubclass(value, Exception):
                raise value("synthetic", request=request)
            return httpx.Response(value, json={"result": {"acsMap": {}, "agents": []}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with patch("incident.selection.asyncio.sleep", new_callable=AsyncMock) as sleep:
                try:
                    result = await discover_candidates("https://discovery.invalid", "db.observe", client=client,
                        record=lambda event, **data: events.append({"event": event, **data}))
                    return requests, events, sleep, result, None
                except Exception as error:
                    return requests, events, sleep, None, error

    async def test_two_connect_timeouts_then_success(self):
        requests, events, sleep, result, error = await self.exercise([httpx.ConnectTimeout, httpx.ConnectTimeout, 200])
        self.assertIsNone(error)
        self.assertEqual(result, [])
        self.assertEqual(len(requests), 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual([event["event"] for event in events],
                         ["official_discovery_retry", "official_discovery_retry", "official_discovery"])

    async def test_server_failure_retries_but_client_error_does_not(self):
        for sequence, attempts in (([502, 503, 200], 3), ([403], 1)):
            requests, _, sleep, result, error = await self.exercise(sequence)
            self.assertEqual(len(requests), attempts)
            self.assertEqual(sleep.await_count, attempts - 1)
            self.assertIsInstance(error, httpx.HTTPStatusError) if attempts == 1 else self.assertEqual(result, [])

    async def test_exhausted_discovery_preserves_transport_error(self):
        requests, events, sleep, _, error = await self.exercise([httpx.ConnectError] * 4)
        self.assertEqual(len(requests), 4)
        self.assertEqual(sleep.await_count, 3)
        self.assertIsInstance(error, httpx.ConnectError)
        self.assertFalse(any(event["event"] == "official_discovery" for event in events))

    async def test_owned_client_disables_ambient_proxy_and_has_phase_timeouts(self):
        original = httpx.AsyncClient
        options = []
        def factory(**kwargs):
            options.append(kwargs)
            return original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json={"result": {"acsMap": {}, "agents": []}})))
        with patch("incident.selection.httpx.AsyncClient", side_effect=factory):
            self.assertEqual(await discover_candidates("https://discovery.invalid", "db.observe"), [])
        self.assertIs(options[0]["trust_env"], False)
        self.assertEqual((options[0]["timeout"].connect, options[0]["timeout"].read), (5, 10))
