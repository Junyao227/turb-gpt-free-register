# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch

from config import proxy as proxy_config
from config import roxybrowser as roxy_config
from core.chatgpt_plan import resolve_plan_check_route
from core.cloakbrowser_driver import _normalize_proxy as normalize_cloak_proxy
from core.roxybrowser_client import RoxyBrowserClient, _proxy_url_to_roxy_info
from webui.app import _compact_account_for_list


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

    def test_mask_proxy_url_hides_credentials(self):
        self.assertEqual(
            proxy_config.mask_proxy_url("proxy.example:1000:user:pass"),
            "http://***:***@proxy.example:1000",
        )

    def test_proxy_display_label_identifies_kookeey_country(self):
        self.assertEqual(
            proxy_config.proxy_display_label(
                "http://account:credential-KR-session-marker@gate.kookeey.info:1000"
            ),
            "kookeey-kr",
        )

    def test_proxy_display_label_identifies_bunnyproxy_country_from_host(self):
        self.assertEqual(
            proxy_config.proxy_display_label(
                "http://account:secret@proxy.us.bunnyproxy.com:18080"
            ),
            "bunnyproxy-us",
        )

    def test_proxy_display_label_identifies_known_provider_without_country(self):
        self.assertEqual(
            proxy_config.proxy_display_label(
                "http://account:secret@gateway.bunnyproxy.com:18080"
            ),
            "bunnyproxy",
        )

    def test_proxy_display_label_identifies_cliproxy_country_from_host(self):
        self.assertEqual(
            proxy_config.proxy_display_label(
                "http://account:secret@us.cliproxy.io:3010"
            ),
            "cliproxy-us",
        )

    def test_proxy_display_label_identifies_1024proxy_country_from_host(self):
        self.assertEqual(
            proxy_config.proxy_display_label(
                "http://account:secret@us.1024proxy.io:3000"
            ),
            "1024proxy-us",
        )

    def test_proxy_display_label_identifies_ipipbright_country_from_username(self):
        value = "sp.ipipbright.net:1000:fixture_area-US_life-15_session-abc:secret"

        self.assertEqual(
            proxy_config.normalize_proxy_url(value),
            "http://fixture_area-US_life-15_session-abc:secret@sp.ipipbright.net:1000",
        )
        self.assertEqual(proxy_config.proxy_display_label(value), "ipipbright-us")

    def test_proxy_display_label_uses_safe_fallback_for_unknown_provider(self):
        self.assertEqual(
            proxy_config.proxy_display_label("http://account:secret@proxy.example:1000"),
            "http://***:***@proxy.example:1000",
        )

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

    def test_roxy_open_result_retains_selected_proxy(self):
        roxy = RoxyBrowserClient(api_base="http://roxy.test", token="")
        roxy.request = Mock(side_effect=[
            {"data": {"dirId": "123"}},
            {"webdriver": "http://127.0.0.1:9515"},
        ])
        selected = "http://user:pass@proxy.example:1000"

        with (
            patch.object(roxy_config, "ROXY_PROFILE_ID", ""),
            patch.object(roxy_config, "ROXY_ONE_PROFILE_PER_ACCOUNT", True),
            patch.object(roxy_config, "ROXY_WORKSPACE_ID", "1"),
            patch.object(roxy_config, "ROXY_PROFILE_CREATE_PAYLOAD", {}),
            patch.object(roxy_config, "ROXY_CREATE_USE_PROXY_POOL", True),
            patch.object(roxy_config, "ROXY_OPEN_PATH", "/browser/open"),
            patch.object(roxy_config, "ROXY_OPEN_METHOD", "POST"),
            patch.object(roxy_config, "ROXY_OPEN_EXTRA_PARAMS", {}),
            patch.object(proxy_config, "pick_proxy", return_value=selected),
        ):
            opened = roxy.open_profile()

        self.assertEqual(opened.proxy_used, selected)
        create_body = roxy.request.call_args_list[0].kwargs["json_body"]
        self.assertEqual(create_body["proxyInfo"]["host"], "proxy.example")

    def test_account_list_masks_proxy_credentials(self):
        compact = _compact_account_for_list({
            "id": 1,
            "email": "account@example.com",
            "proxy_used": "http://user:secret-US-session-marker@gate.kookeey.info:1000",
        })

        self.assertEqual(compact["proxy_used"], "kookeey-us")

    def test_account_list_labels_bunnyproxy_proxy(self):
        compact = _compact_account_for_list({
            "id": 2,
            "email": "bunny@example.com",
            "proxy_used": "http://user:secret@proxy.us.bunnyproxy.com:18080",
        })

        self.assertEqual(compact["proxy_used"], "bunnyproxy-us")

    def test_account_list_labels_cliproxy_proxy(self):
        compact = _compact_account_for_list({
            "id": 3,
            "email": "cliproxy@example.com",
            "proxy_used": "http://user:secret@us.cliproxy.io:3010",
        })

        self.assertEqual(compact["proxy_used"], "cliproxy-us")

    def test_account_list_labels_ipipbright_proxy(self):
        compact = _compact_account_for_list({
            "id": 4,
            "email": "ipipbright@example.com",
            "proxy_used": "sp.ipipbright.net:1000:fixture_area-US_life-15_session-abc:secret",
        })

        self.assertEqual(compact["proxy_used"], "ipipbright-us")


if __name__ == "__main__":
    unittest.main()
