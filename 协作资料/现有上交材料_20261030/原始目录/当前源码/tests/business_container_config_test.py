"""Initialization only: no network, database, or platform resource is mutated."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/ACPs-community/acps-sdk"))
from incident.partners import ApplicationPartner


class ContainerDomainConfigTests(unittest.TestCase):
    def test_fixed_compose_name_requires_explicit_domain_configuration(self):
        with self.assertRaises(ValueError):
            ApplicationPartner("test", object(), base_url="http://app-v2:8000")
        partner = ApplicationPartner("test", object(), base_url="http://app-v2:8000/", allowed_hosts=["app-v2"])
        self.assertEqual(partner.base_url, "http://app-v2:8000")
        ApplicationPartner("test", object(), base_url="http://127.0.0.1:8082")

    def test_arbitrary_hosts_and_embedded_credentials_remain_rejected(self):
        for url, hosts in (("http://example.com", ["example.com"]),
                           ("http://app-v2.evil:8000", ["app-v2"]),
                           ("http://token@app-v2:8000", ["app-v2"]),
                           ("http://app-v2:8000/admin", ["app-v2"])):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ApplicationPartner("test", object(), base_url=url, allowed_hosts=hosts)


if __name__ == "__main__":
    unittest.main()
