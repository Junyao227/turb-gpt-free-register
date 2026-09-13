import os
import unittest
from unittest.mock import patch

import roxy_bulk_reset as bulk


class FakeRoxyClient:
    def __init__(self):
        self.token = "test-token"
        self.calls = []
        self.created = 0

    def request(self, method, path, payload=None, params=None):
        self.calls.append((method, path, payload, params))
        if path == "/browser/list":
            return {"code": 0, "data": [{"dirId": "old-1"}, {"id": "old-2"}]}
        if path == "/browser/create":
            self.created += 1
            return {"code": 0, "data": {"dirId": f"new-{self.created}"}}
        return {"code": 0, "data": {}}


class RoxyBulkResetTests(unittest.TestCase):
    def test_config_value_uses_environment_when_file_value_is_blank(self):
        with patch.dict(os.environ, {"ROXY_API_TOKEN": "environment-token"}, clear=False):
            self.assertEqual(
                bulk.config_value({"ROXY_API_TOKEN": ""}, "ROXY_API_TOKEN", "default-token"),
                "environment-token",
            )
        self.assertEqual(
            bulk.config_value({"ROXY_API_TOKEN": "file-token"}, "ROXY_API_TOKEN", "default-token"),
            "file-token",
        )

    def test_parse_proxy_accepts_supported_formats_without_exposing_credentials(self):
        http_proxy = bulk.parse_proxy("http://user:pass@jp.example.test:8080")
        socks_proxy = bulk.parse_proxy("socks5://user:pass@us.example.test:1080")
        four_part_proxy = bulk.parse_proxy("sg.example.test:3128:user:pass")

        self.assertEqual(http_proxy.roxy_proxy_info("")["proxyCategory"], "HTTP")
        self.assertEqual(socks_proxy.roxy_proxy_info("")["proxyCategory"], "SOCKS5")
        self.assertEqual(four_part_proxy.host, "sg.example.test")
        self.assertNotIn("user", four_part_proxy.masked)
        self.assertNotIn("pass", four_part_proxy.masked)

    def test_lifecycle_closes_deletes_creates_and_opens_one_profile_per_proxy(self):
        client = FakeRoxyClient()
        profiles = bulk.list_all_profiles(client, "/browser/list", "POST", "workspace-1", 100)
        delete_failures = bulk.close_and_delete_all(
            client,
            profiles,
            "workspace-1",
            "/browser/close",
            "/browser/delete",
            0,
        )
        created, create_failures = bulk.create_profiles(
            client,
            [
                bulk.parse_proxy("http://user:pass@jp.example.test:8080"),
                bulk.parse_proxy("socks5://user:pass@us.example.test:1080"),
            ],
            "workspace-1",
            "project-1",
            "/browser/create",
            "/browser/open",
            "macOS",
            "IPRust.io",
            True,
            "bulk-proxy",
        )

        self.assertEqual(delete_failures, [])
        self.assertEqual(create_failures, [])
        self.assertEqual([item["profile_id"] for item in created], ["new-1", "new-2"])
        self.assertEqual(
            [path for _, path, _, _ in client.calls],
            [
                "/browser/list",
                "/browser/close",
                "/browser/delete",
                "/browser/close",
                "/browser/delete",
                "/browser/create",
                "/browser/open",
                "/browser/create",
                "/browser/open",
            ],
        )
        first_create = client.calls[5][2]
        self.assertEqual(first_create["proxyInfo"]["host"], "jp.example.test")
        self.assertEqual(first_create["proxyInfo"]["proxyCategory"], "HTTP")


if __name__ == "__main__":
    unittest.main()
