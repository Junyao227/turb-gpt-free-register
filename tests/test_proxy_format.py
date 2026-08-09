# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from config import proxy as proxy_config
from core.chatgpt_plan import resolve_plan_check_route
from core.cloakbrowser_driver import _normalize_proxy as normalize_cloak_proxy
from core.roxybrowser_client import _proxy_url_to_roxy_info


class ProxyFormatTests(unittest.TestCase):
    def test_standard_url_is_unchanged(self):
        value = "https://user:pass@proxy.example:8443"
        self.assertEqual(proxy_config.normalize_proxy_url(value), value)

    def test_four_part_url_with_scheme_is_normalized(self):
        self.assertEqual(
            proxy_config.normalize_proxy_url("http://proxy.example:1000:user-name:pass-word"),
            "http://user-name:pass-word@proxy.example:1000",
        )

    def test_four_part_url_without_scheme_is_normalized(self):
        self.assertEqual(
            proxy_config.normalize_proxy_url("proxy.example:1000:user-name:pass-word"),
            "http://user-name:pass-word@proxy.example:1000",
        )

    def test_standard_auth_without_scheme_gets_default_scheme(self):
        self.assertEqual(
            proxy_config.normalize_proxy_url("user:pass@proxy.example:1000"),
            "http://user:pass@proxy.example:1000",
        )

    def test_colons_in_four_part_password_are_encoded(self):
        self.assertEqual(
            proxy_config.normalize_proxy_url("proxy.example:1000:user:pass:with:colons"),
            "http://user:pass%3Awith%3Acolons@proxy.example:1000",
        )

    def test_bracketed_ipv6_host_port_is_not_treated_as_four_part(self):
        self.assertEqual(
            proxy_config.normalize_proxy_url("[::1]:8080"),
            "http://[::1]:8080",
        )

    def test_pick_proxy_normalizes_selected_value(self):
        with (
            patch.object(proxy_config, "PROXY_POOL", ["proxy.example:1000:user:pass"]),
            patch("config.proxy.random.choice", return_value="proxy.example:1000:user:pass"),
        ):
            selected = proxy_config.pick_proxy()

        self.assertEqual(selected, "http://user:pass@proxy.example:1000")

    def test_roxy_info_accepts_four_part_value(self):
        info = _proxy_url_to_roxy_info("proxy.example:1000:user:pass:extra")

        self.assertEqual(info["protocol"], "HTTP")
        self.assertEqual(info["host"], "proxy.example")
        self.assertEqual(info["port"], "1000")
        self.assertEqual(info["proxyUserName"], "user")
        self.assertEqual(info["proxyPassword"], "pass:extra")

    def test_cloak_accepts_four_part_value_and_maps_socks5h(self):
        self.assertEqual(
            normalize_cloak_proxy("socks5h://proxy.example:1000:user:pass"),
            "socks5://user:pass@proxy.example:1000",
        )

    def test_plan_check_explicit_proxy_accepts_four_part_value(self):
        route = resolve_plan_check_route("proxy.example:1000:user:pass")

        self.assertEqual(route["proxy"], "http://user:pass@proxy.example:1000")
        self.assertEqual(route["network_route"], "proxy")
        self.assertEqual(route["proxy_used"], "http://***:***@proxy.example:1000")


if __name__ == "__main__":
    unittest.main()
