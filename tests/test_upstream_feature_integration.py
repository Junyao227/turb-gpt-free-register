# -*- coding: utf-8 -*-
import gzip
import json
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from core import account_export, db
from core.session import BrowserSession
from webui.app import create_app
from webui.config_editor import EDITABLE_FIELDS


ROOT = Path(__file__).resolve().parent.parent


class AutoPlanCheckTests(unittest.TestCase):
    def test_config_and_modern_ui_expose_the_auto_plan_check_switch(self):
        self.assertTrue(any(field["key"] == "AUTO_PLAN_CHECK_AFTER_REGISTER" for field in EDITABLE_FIELDS))
        html = (ROOT / "webui" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("renderRegistrationSettingsSection", html)
        self.assertIn("AUTO_PLAN_CHECK_AFTER_REGISTER", html)

    def test_disabled_auto_plan_check_does_not_enqueue_a_plan_request(self):
        with patch("core.db.insert_account", return_value=7), patch.object(
            account_export, "_append_batch_archive", return_value=Path("accounts/test")
        ), patch("core.plan_check_service.enqueue_account_plan_check") as enqueue:
            row_id = account_export.save_account_data(
                email="person@example.test",
                access_token="token",
                auto_plan_check=False,
            )

        self.assertEqual(row_id, 7)
        enqueue.assert_not_called()


class LivenessFingerprintTests(unittest.TestCase):
    def test_successful_liveness_check_persists_its_fingerprint_summary(self):
        rows = [{"id": 7, "email": "person@example.test", "access_token": "old"}]
        with patch.object(db, "_load_accounts", return_value=rows), patch.object(db, "_save_accounts") as save:
            self.assertTrue(db.update_account_liveness(7, {
                "ok": True,
                "status": "live",
                "device_id": "device-123",
                "proxy_used": "http://proxy.example.test:8080",
                "fingerprint": {"timezone_iana": "Asia/Shanghai"},
                "fingerprint_text": "device_id=device-123 tz=Asia/Shanghai(480)",
            }))

        row = rows[0]
        self.assertEqual(row["device_id"], "device-123")
        self.assertEqual(row["live_check_device_id"], "device-123")
        self.assertEqual(row["live_check_fingerprint"]["timezone_iana"], "Asia/Shanghai")
        self.assertIn("Asia/Shanghai", row["live_check_fingerprint_text"])
        save.assert_called_once_with(rows)

    def test_fingerprint_summary_is_compact_and_contains_core_profile_fields(self):
        session = BrowserSession.__new__(BrowserSession)
        session.device_id = "device-1234567890"
        session.proxy = "http://proxy.example.test:8080"
        session.browser_profile = {
            "user_agent": "Example Browser/1.0",
            "accept_language": "zh-CN,zh;q=0.9",
            "timezone_iana": "Asia/Shanghai",
            "timezone_offset_minutes": 480,
            "screen_width": 1440,
            "screen_height": 900,
            "device_pixel_ratio": 2,
            "hardware_concurrency": 8,
            "device_memory": 8,
        }
        session.exit_geo = {"country": "CN", "city": "Shanghai"}
        session.sentinel_sid = "sentinel"
        session.oai_session_id = "session"
        session.auth_session_logging_id = "auth"
        session.datadog_trace_id = "trace"
        session.datadog_parent_id = "parent"

        summary = session.fingerprint_summary()
        self.assertEqual(summary["timezone_iana"], "Asia/Shanghai")
        self.assertEqual(summary["screen_width"], 1440)
        self.assertIn("tz=Asia/Shanghai(480)", session.fingerprint_summary_text())


class JsonGzipTests(unittest.TestCase):
    def test_large_json_is_gzipped_only_when_client_allows_it(self):
        app = create_app(auth_code="test-gzip")

        @app.get("/api/test-large-json")
        def test_large_json():
            from flask import jsonify

            return jsonify({"payload": "x" * 4096})

        client = app.test_client()
        headers = {"X-Auth-Code": "test-gzip", "Accept-Encoding": "gzip"}
        compressed = client.get("/api/test-large-json", headers=headers)
        self.assertEqual(compressed.status_code, 200)
        self.assertEqual(compressed.headers.get("Content-Encoding"), "gzip")
        self.assertEqual(json.loads(gzip.decompress(compressed.data))["payload"], "x" * 4096)

        identity = client.get("/api/test-large-json", headers={"X-Auth-Code": "test-gzip", "Accept-Encoding": "identity"})
        self.assertEqual(identity.status_code, 200)
        self.assertIsNone(identity.headers.get("Content-Encoding"))


class CloudRegistrationIntegrationTests(unittest.TestCase):
    def test_cloud_registration_keeps_human_mode_and_stealth_as_optional_runtime_dependency(self):
        source = (ROOT / "core" / "browser_use_registration.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("def _human_fill_locator", source)
        self.assertIn("def _apply_cloud_browser_automation_mask", source)
        self.assertIn("SKYVERN_HUMAN_MODE", source)
        self.assertIn("playwright-stealth>=2.0.3", requirements)

    def test_stealth_configuration_does_not_override_or_warn_about_the_native_platform(self):
        from core.browser_use_registration import _build_playwright_stealth

        with warnings.catch_warnings(record=True) as caught:
            stealth = _build_playwright_stealth("skyvern", label="test")

        self.assertIsNotNone(stealth)
        self.assertFalse(any("navigator_platform" in str(item.message) for item in caught))


if __name__ == "__main__":
    unittest.main()
