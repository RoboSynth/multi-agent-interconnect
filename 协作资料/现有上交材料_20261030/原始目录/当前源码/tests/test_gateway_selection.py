import asyncio
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from incident.selection import select_participant


class GatewaySelectionTests(unittest.TestCase):
    def test_named_gateway_scope_matches_orders_but_not_other_metadata(self):
        async def describe(acs):
            return {"executor_aic": acs["aic"], "resource_scope": {"database": "orders", "user": "orders_app"},
                    "tools": [{"name": "db.read_only_status"}]}
        chosen, _ = asyncio.run(select_participant([{"aic": "database-domain"}], resource="orders",
                              tool="db.read_only_status", describe=describe))
        self.assertEqual(chosen["aic"], "database-domain")
        with self.assertRaises(RuntimeError):
            asyncio.run(select_participant([{"aic": "database-domain"}], resource="orders_app",
                        tool="db.read_only_status", describe=describe))
