# -*- coding: utf-8 -*-
import time
import unittest
import os
from unittest.mock import patch

from config import codex as codex_config
from core import sms_provider
from webui import config_editor


class _Response:
    status_code = 200

    def __init__(self, text):
        self.text = text


class _Http:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, params=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        return _Response(self.responses.pop(0))

    def close(self):
        self.closed = True


class HandlerSmsProviderTests(unittest.TestCase):
    def setUp(self):
        sms_provider._ACQUIRED_AT.clear()

    def tearDown(self):
        sms_provider._ACQUIRED_AT.clear()

    def test_webui_exposes_provider_specific_handler_fields(self):
        fields = {field["key"]: field for field in config_editor.EDITABLE_FIELDS}

        for key in (
            "GRIZZLY_SMS_API_BASE",
            "GRIZZLY_SMS_API_KEY",
            "SMSBOWER_API_BASE",
            "SMSBOWER_API_KEY",
            "SMSBOWER_COUNTRY",
            "SMSBOWER_SERVICE",
            "SMSBOWER_MAX_PRICE",
            "SMS_POLL_INTERVAL",
            "SMS_REQUEST_TIMEOUT",
        ):
            self.assertIn(key, fields)
        self.assertTrue(fields["GRIZZLY_SMS_API_KEY"].get("secret"))
        self.assertTrue(fields["SMSBOWER_API_KEY"].get("secret"))

    def test_smsbower_reuses_handler_protocol(self):
        http = _Http([
            "ACCESS_NUMBER:act-1:56900000000",
            "STATUS_OK:123456",
            "ACCESS_READY",
        ])
        with (
            patch.dict(os.environ, {
                "SMSBOWER_API_BASE": "1",
                "SMSBOWER_API_KEY": "1",
                "SMSBOWER_SERVICE": "1",
                "SMSBOWER_COUNTRY": "1",
                "SMSBOWER_MAX_PRICE": "1",
            }),
            patch.object(codex_config, "SMS_PROVIDER", "smsbower"),
            patch.object(codex_config, "SMSBOWER_API_BASE", "https://smsbower.example/handler_api.php"),
            patch.object(codex_config, "SMSBOWER_API_KEY", "secret"),
            patch.object(codex_config, "SMSBOWER_SERVICE", "dr"),
            patch.object(codex_config, "SMSBOWER_COUNTRY", "151"),
            patch.object(codex_config, "SMSBOWER_MAX_PRICE", "0.07"),
        ):
            activation_id, phone = sms_provider.acquire_number(http=http)
            code = sms_provider.wait_for_sms_code(
                activation_id,
                http=http,
                max_wait=1,
                poll_interval=0,
            )
            status = sms_provider.set_status(activation_id, 1, http=http)

        self.assertEqual((activation_id, phone), ("act-1", "56900000000"))
        self.assertEqual(code, "123456")
        self.assertEqual(status, "ACCESS_READY")
        self.assertEqual(
            [call["params"]["action"] for call in http.calls],
            ["getNumber", "getStatus", "setStatus"],
        )
        self.assertEqual(http.calls[0]["params"]["service"], "dr")
        self.assertEqual(http.calls[0]["params"]["country"], "151")
        self.assertEqual(http.calls[0]["params"]["maxPrice"], "0.07")
        self.assertEqual(http.calls[0]["params"]["api_key"], "secret")

    def test_smsbower_cancel_skips_grizzly_wait(self):
        http = _Http(["ACCESS_CANCEL"])
        sms_provider._ACQUIRED_AT["act-2"] = time.time()

        with (
            patch.dict(os.environ, {"SMSBOWER_API_BASE": "1", "SMSBOWER_API_KEY": "1"}),
            patch.object(codex_config, "SMS_PROVIDER", "smsbower"),
            patch.object(codex_config, "SMSBOWER_API_BASE", "https://smsbower.example/handler_api.php"),
            patch.object(codex_config, "SMSBOWER_API_KEY", "secret"),
            patch("core.sms_provider.time.sleep") as sleep_mock,
        ):
            sms_provider._do_cancel_sync("act-2", lambda: http)

        sleep_mock.assert_not_called()
        self.assertEqual(http.calls[0]["params"]["action"], "setStatus")
        self.assertEqual(http.calls[0]["params"]["status"], "8")
        self.assertNotIn("act-2", sms_provider._ACQUIRED_AT)

    def test_split_settings_do_not_leak_smsbower_key_into_grizzly(self):
        configured = {"SMSBOWER_API_KEY": "set", "SMS_API_KEY": "legacy"}
        with (
            patch("core.sms_provider.os.getenv", side_effect=lambda key: configured.get(key)),
            patch.object(codex_config, "SMS_PROVIDER", "grizzly"),
            patch.object(codex_config, "GRIZZLY_SMS_API_KEY", ""),
            patch.object(codex_config, "SMS_API_KEY", "smsbower-secret"),
        ):
            settings = sms_provider._handler_settings()

        self.assertEqual(settings["api_key"], "")


if __name__ == "__main__":
    unittest.main()
