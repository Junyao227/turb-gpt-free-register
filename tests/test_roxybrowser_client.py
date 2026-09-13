# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import Mock, patch

from config import roxybrowser as roxy_config
from core.roxybrowser_client import RoxyBrowserClient, _is_create_busy_error


ROXY_BUSY_MESSAGE = "\u6b63\u5728\u521b\u5efa\u4e2d\uff0c\u8bf7\u7a0d\u7b49\uff01"


def _response(payload: dict, status_code: int = 200):
    resp = Mock()
    resp.status_code = status_code
    resp.text = json.dumps(payload, ensure_ascii=False)
    resp.json.return_value = payload
    return resp


class RoxyBrowserClientCreateBusyTests(unittest.TestCase):
    def _patch_config(self):
        return patch.multiple(
            roxy_config,
            ROXY_CREATE_METHOD="POST",
            ROXY_CREATE_PATH="/browser/create",
            ROXY_WORKSPACE_ID="1",
            ROXY_PROJECT_ID="2",
            ROXY_PROFILE_CREATE_PAYLOAD={"name": "test-profile", "os": "macOS"},
            ROXY_RANDOM_PROFILE_NAME_ON_CREATE=False,
            ROXY_RANDOM_OS_ON_CREATE=False,
            ROXY_CREATE_USE_PROXY_POOL=False,
            ROXY_CREATE_BUSY_MAX_WAIT=10,
            ROXY_CREATE_BUSY_RETRY_DELAY=1,
        )

    def test_create_profile_retries_roxy_busy_response(self):
        client = RoxyBrowserClient(api_base="http://roxy.test", token="")
        client.http.request = Mock(side_effect=[
            _response({"code": 1, "msg": ROXY_BUSY_MESSAGE}),
            _response({"code": 1, "msg": ROXY_BUSY_MESSAGE}),
            _response({"code": 0, "data": {"dirId": "profile-123"}}),
        ])

        with self._patch_config(), patch("core.roxybrowser_client.time.sleep") as sleep:
            profile_id = client.create_profile()

        self.assertEqual(profile_id, "profile-123")
        self.assertEqual(client.http.request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_create_profile_does_not_retry_non_busy_failure(self):
        client = RoxyBrowserClient(api_base="http://roxy.test", token="")
        client.http.request = Mock(return_value=_response({"code": 1, "msg": "workspaceId is required"}))

        with self._patch_config(), patch("core.roxybrowser_client.time.sleep") as sleep:
            with self.assertRaises(RuntimeError):
                client.create_profile()

        self.assertEqual(client.http.request.call_count, 1)
        sleep.assert_not_called()

    def test_detects_real_roxy_chinese_busy_message(self):
        exc = RuntimeError(f"Roxy API \u8fd4\u56de\u5931\u8d25 POST /browser/create: {ROXY_BUSY_MESSAGE}")

        self.assertTrue(_is_create_busy_error(exc))


if __name__ == "__main__":
    unittest.main()
