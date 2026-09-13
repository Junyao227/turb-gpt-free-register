# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from core import pay153_client
from webui import config_editor


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def _settings(overrides=None):
    values = {
        "PAY153_ENABLED": True,
        "PAY153_API_BASE": "http://127.0.0.1:8080",
        "PAY153_REQUEST_TIMEOUT": 30,
        "PAY153_DEFAULT_COUNTRY": "BR",
        "PAY153_DEFAULT_BUYER_MODE": "identity_elevation",
        "PAY153_DEFAULT_AGREEMENT_ONLY": False,
    }
    values.update(overrides or {})
    return lambda name, default=None: values.get(name, default)


class Pay153ClientTests(unittest.TestCase):
    def setUp(self):
        pay153_client.reset_session()

    def tearDown(self):
        pay153_client.reset_session()

    def test_config_editor_exposes_pay153_group(self):
        fields = {item["key"]: item for item in config_editor.EDITABLE_FIELDS}

        self.assertEqual(fields["PAY153_API_BASE"]["group"], "协议支付")
        self.assertEqual(fields["PAY153_ENABLED"]["type"], "bool")
        self.assertEqual(fields["PAY153_DEFAULT_AGREEMENT_ONLY"]["type"], "bool")

    def test_normalize_api_base_accepts_root_mount_and_api(self):
        self.assertEqual(
            pay153_client.normalize_api_base("http://127.0.0.1:8080"),
            "http://127.0.0.1:8080/api",
        )
        self.assertEqual(
            pay153_client.normalize_api_base("http://127.0.0.1:8080/paypal-pay"),
            "http://127.0.0.1:8080/paypal-pay/api",
        )
        self.assertEqual(
            pay153_client.normalize_api_base("http://127.0.0.1:8080/paypal-pay/api"),
            "http://127.0.0.1:8080/paypal-pay/api",
        )

    def test_create_job_posts_defaults_to_pay153(self):
        fake = _FakeSession([_FakeResponse(201, {"job": {"id": "job-1"}})])
        with patch.object(pay153_client, "_runtime_setting", side_effect=_settings()), patch(
            "core.pay153_client.requests.Session", return_value=fake
        ):
            result = pay153_client.create_job({"ba_token": "BA-ABCDEFGH1234", "phone": "+5511999999999"})

        self.assertEqual(result["job"]["id"], "job-1")
        self.assertEqual(len(fake.calls), 1)
        call = fake.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "http://127.0.0.1:8080/api/jobs")
        self.assertEqual(call["json"]["country"], "BR")
        self.assertEqual(call["json"]["buyer_mode"], "identity_elevation")
        self.assertIs(call["json"]["agreement_only"], False)
        self.assertEqual(call["json"]["ba_token"], "BA-ABCDEFGH1234")

    def test_session_cookie_jar_is_reused_between_requests(self):
        fake = _FakeSession([
            _FakeResponse(201, {"job": {"id": "job-1"}}),
            _FakeResponse(200, {"id": "job-1", "status": "running"}),
        ])
        with patch.object(pay153_client, "_runtime_setting", side_effect=_settings()), patch(
            "core.pay153_client.requests.Session", return_value=fake
        ) as session_factory:
            pay153_client.create_job({"paypal_url": "https://paypal.test/approve?ba_token=BA-ABCDEFGH1234", "phone": "+5511999999999"})
            job = pay153_client.get_job("job-1", log_offset=3)

        self.assertEqual(job["status"], "running")
        session_factory.assert_called_once_with()
        self.assertEqual(fake.calls[1]["url"], "http://127.0.0.1:8080/api/jobs/job-1")
        self.assertEqual(fake.calls[1]["params"], {"log_offset": 3})

    def test_disabled_integration_raises_config_error(self):
        with patch.object(pay153_client, "_runtime_setting", side_effect=_settings({"PAY153_ENABLED": False})):
            with self.assertRaises(pay153_client.Pay153ConfigError):
                pay153_client.health()

    def test_upstream_error_is_redacted(self):
        fake = _FakeSession([
            _FakeResponse(400, {"error": "bad BA-ABCDEFGH1234567890 via http://user:pass@proxy.example.test:8080"}),
        ])
        with patch.object(pay153_client, "_runtime_setting", side_effect=_settings()), patch(
            "core.pay153_client.requests.Session", return_value=fake
        ):
            with self.assertRaises(pay153_client.Pay153Error) as caught:
                pay153_client.health()

        message = str(caught.exception)
        self.assertIn("BA-***", message)
        self.assertIn("http://***:***@proxy.example.test:8080", message)
        self.assertNotIn("BA-ABCDEFGH1234567890", message)
        self.assertNotIn("user:pass", message)


if __name__ == "__main__":
    unittest.main()
