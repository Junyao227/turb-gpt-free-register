# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
AUDIT_ROOT = ROOT / "kuozhan" / "gpt-account-audit"
sys.path.insert(0, str(AUDIT_ROOT))

from audit.app import (  # noqa: E402
    effective_proxy,
    normalize_proxy_config,
    normalize_proxy_pool,
    normalize_proxy_url,
    proxy_for_account,
)
from audit import probes  # noqa: E402


class _FakeSession:
    def close(self):
        pass


class GptAccountAuditProxyFormatTests(unittest.TestCase):
    def test_normalizes_1024proxy_four_part_format(self):
        raw = "us.1024proxy.io:3000:fixture-region-DE-sid-abc-t-10:secret"

        self.assertEqual(
            normalize_proxy_url(raw),
            "http://fixture-region-DE-sid-abc-t-10:secret@us.1024proxy.io:3000",
        )

    def test_preserves_existing_proxy_url(self):
        value = "http://user:pass@proxy.example.test:8080"

        self.assertEqual(normalize_proxy_url(value), value)

    def test_adds_http_scheme_to_userinfo_proxy_without_scheme(self):
        self.assertEqual(
            normalize_proxy_url("user:pass@proxy.example.test:8080"),
            "http://user:pass@proxy.example.test:8080",
        )

    def test_encodes_colons_in_four_part_password(self):
        self.assertEqual(
            normalize_proxy_url("proxy.example.test:8080:user:pass:extra"),
            "http://user:pass%3Aextra@proxy.example.test:8080",
        )

    def test_effective_residential_proxy_uses_normalized_value(self):
        proxy = effective_proxy({
            "proxy_mode": "residential",
            "residential_proxy": "proxy.example.test:8080:user:pass",
            "use_parent": False,
        })

        self.assertEqual(proxy, "http://user:pass@proxy.example.test:8080")

    def test_normalizes_residential_proxy_pool_to_one_proxy_per_line(self):
        cfg = normalize_proxy_config({
            "proxy_mode": "residential",
            "residential_proxy": "\n".join([
                "proxy-a.example.test:8080:user-a:pass-a",
                "http://user-b:pass-b@proxy-b.example.test:8081",
                "proxy-a.example.test:8080:user-a:pass-a",
            ]),
        })

        self.assertEqual(
            cfg["residential_proxy"],
            "\n".join([
                "http://user-a:pass-a@proxy-a.example.test:8080",
                "http://user-b:pass-b@proxy-b.example.test:8081",
            ]),
        )
        self.assertEqual(
            normalize_proxy_pool(cfg["residential_proxy"]),
            [
                "http://user-a:pass-a@proxy-a.example.test:8080",
                "http://user-b:pass-b@proxy-b.example.test:8081",
            ],
        )

    def test_residential_pool_rotates_by_account_index(self):
        cfg = {
            "proxy_mode": "residential",
            "residential_proxy": "\n".join([
                "proxy-a.example.test:8080:user-a:pass-a",
                "proxy-b.example.test:8081:user-b:pass-b",
            ]),
            "use_parent": False,
        }

        self.assertEqual(proxy_for_account(cfg, 0), "http://user-a:pass-a@proxy-a.example.test:8080")
        self.assertEqual(proxy_for_account(cfg, 1), "http://user-b:pass-b@proxy-b.example.test:8081")
        self.assertEqual(proxy_for_account(cfg, 2), "http://user-a:pass-a@proxy-a.example.test:8080")

    def test_ui_saves_current_input_before_testing_proxy(self):
        html = (AUDIT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("host:port:user:pass", html)
        self.assertIn("住宅代理池（一行一个）", html)
        self.assertIn("function collectConfigBody()", html)
        self.assertIn("applyConfig(r.config, r.proxy, r.proxy_pool_count);", html)
        self.assertIn("await saveConfig({ quiet: true, throwOnError: true });", html)

    def test_import_clears_result_filters_that_hide_pending_accounts(self):
        html = (AUDIT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('document.getElementById("filterPm").value = "";', html)
        self.assertIn('document.getElementById("filterTrial").value = "";', html)
        self.assertIn('document.getElementById("filterKind").value = "";', html)
        self.assertIn("刚导入的待检查账号会被该筛选隐藏", html)

    def test_ui_shows_accounts_check_and_coupon_trial_sources(self):
        html = (AUDIT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("function trialDetails(a)", html)
        self.assertIn("套餐口径=eligible", html)
        self.assertIn("coupon=", html)
        self.assertIn("风控/待复查", html)


class GptAccountAuditTrialSourceTests(unittest.TestCase):
    def test_accounts_check_trial_signal_overrides_coupon_not_eligible(self):
        with patch.object(probes, "_session", return_value=_FakeSession()), \
             patch.object(probes, "probe_plan_trial", return_value={
                 "ok": True,
                 "http": 200,
                 "plan_trial_eligible": True,
                 "plan_trial_campaign_id": "campaign-fixture",
                 "current_plan_type": "free",
             }), \
             patch.object(probes, "probe_trial", return_value={
                 "ok": True,
                 "http": 200,
                 "state": "not_eligible",
                 "eligible": False,
             }), \
             patch.object(probes, "probe_checkout_kind", return_value={
                 "ok": True,
                 "http": 200,
                 "checkout_kind": "cs_live",
                 "payment_method_types": ["paypal"],
             }), \
             patch.object(probes, "probe_offers", return_value=[]):
            result = probes.probe_account("header.payload.signature")

        self.assertTrue(result["trial_eligible"])
        self.assertEqual(result["trial_source"], "accounts_check")
        self.assertEqual(result["trial_state"], "not_eligible")
        self.assertEqual(result["status"], "done")
        self.assertIn("plus-1-month-free", result["trial_offers"])

    def test_trial_http_403_with_checkout_success_is_warning_not_failure(self):
        with patch.object(probes, "_session", return_value=_FakeSession()), \
             patch.object(probes, "probe_plan_trial", return_value={
                 "ok": False,
                 "http": 403,
                 "plan_trial_eligible": None,
             }), \
             patch.object(probes, "probe_trial", return_value={
                 "ok": False,
                 "http": 403,
                 "state": "",
                 "eligible": False,
             }), \
             patch.object(probes, "probe_checkout_kind", return_value={
                 "ok": True,
                 "http": 200,
                 "checkout_kind": "cs_live",
                 "payment_method_types": [],
             }), \
             patch.object(probes, "probe_offers", return_value=[]):
            result = probes.probe_account("header.payload.signature")

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["error"], "")
        self.assertIn("trial HTTP 403", result["warning"])


if __name__ == "__main__":
    unittest.main()
