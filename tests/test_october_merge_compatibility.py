"""Regression coverage for upstream/local integration boundaries."""
import re
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from config import proxy as proxy_cfg
from core import account_export
from core.chatgpt_plan import resolve_plan_check_route
from core.session import BrowserSession, close_browser_session
from webui.config_editor import EDITABLE_FIELDS


ROOT = Path(__file__).resolve().parents[1]


class OctoberMergeCompatibilityTests(unittest.TestCase):
    def test_configuration_fields_have_unique_keys(self):
        duplicates = [key for key, count in Counter(f["key"] for f in EDITABLE_FIELDS).items() if count > 1]
        self.assertEqual(duplicates, [])

    def test_token_copy_control_and_handler_are_not_duplicated(self):
        for name, control in (("index.html", "btnCopySelectedTokensV2"), ("index_legacy.html", "btnCopySelectedTokens")):
            with self.subTest(template=name):
                text = (ROOT / "webui/templates" / name).read_text(encoding="utf-8")
                self.assertEqual(text.count(f'id="{control}"'), 1)
                if name == "index.html":
                    binding = f"bind('{control}', copySelectedAccountTokens);"
                else:
                    binding = f"$('#{control}')?.addEventListener('click', copySelectedAccountTokens);"
                self.assertEqual(text.count(binding), 1)
                functions = Counter(re.findall(r"\bfunction\s+(\w+)\s*\(", text))
                self.assertEqual([key for key, count in functions.items() if count > 1], [])

    def test_explicit_dwell_override_survives_merge(self):
        with patch("core.account_export.time.sleep") as sleep:
            account_export.post_register_dwell("fixture@example.test", seconds_range="0,0")
        sleep.assert_not_called()

    def test_proxy_pool_preserves_local_auth_encoding_and_upstream_list_support(self):
        values = ["proxy.example.test:8080:user:p@ ss", "[::1]:8080"]
        self.assertEqual(proxy_cfg.normalize_proxy_list(values), [
            "http://user:p%40%20ss@proxy.example.test:8080", "http://[::1]:8080",
        ])

    def test_explicit_session_proxy_sets_target_and_transport(self):
        session = BrowserSession(proxy="proxy.example.test:8080:user:password", detect_exit_geo=False)
        try:
            expected = "http://user:password@proxy.example.test:8080"
            self.assertEqual(session.proxy_target, expected)
            self.assertEqual(session.session.proxies["https"], expected)
        finally:
            close_browser_session(session)

    def test_dedicated_plan_pool_normalizes_legacy_values(self):
        with patch.object(proxy_cfg, "PLAN_CHECK_PROXY_MODE", "proxy"), patch.object(
            proxy_cfg, "PLAN_CHECK_PROXY", ["proxy.example.test:8080:user:password"]
        ), patch.object(proxy_cfg, "PLAN_CHECK_UPSTREAM_PROXY", ""):
            route = resolve_plan_check_route()
        self.assertEqual(route["proxy"], "http://user:password@proxy.example.test:8080")
        self.assertEqual(route["proxy_used"], "http://***:***@proxy.example.test:8080")


if __name__ == "__main__":
    unittest.main()
