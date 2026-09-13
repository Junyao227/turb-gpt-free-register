# -*- coding: utf-8 -*-
import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from core import generic_api_mail_client as client


class GenericApiTimestampedFeedTests(unittest.TestCase):
    def test_timestamped_feed_returns_newest_fresh_openai_otp(self):
        response = Mock(status_code=200)
        response.text = json.dumps({
            "status": "success",
            "data": [
                {
                    "saved_at": "2026-08-05 09:21:42",
                    "from": "OpenAI <noreply@openai.com>",
                    "subject": "New sign-in to your OpenAI account",
                    "body": "No verification code is required.",
                },
                {
                    "saved_at": "2026-08-05 09:21:41",
                    "from": "ChatGPT <noreply@openai.com>",
                    "subject": "Your temporary ChatGPT login code",
                    "body": "Your verification code is 654321.",
                },
                {
                    "saved_at": "2026-08-05 09:05:55",
                    "from": "ChatGPT <noreply@openai.com>",
                    "subject": "Your temporary ChatGPT login code",
                    "body": "Your verification code is 111111.",
                },
            ],
        })
        session = Mock()
        session.get.return_value = response
        after_ts = datetime(2026, 8, 5, 9, 21, 40).timestamp()

        with patch.object(
            client,
            "get_account_context",
            return_value=client.GenericApiEmailAccount("fresh@example.com", "https://mail.example.test/feed"),
        ), patch("core.generic_api_mail_client.requests.Session", return_value=session):
            code = client.fetch_latest_otp(
                "fresh@example.com",
                after_ts=after_ts,
                max_wait=1,
                poll_interval=1,
                settle_seconds=0,
            )

        self.assertEqual(code, "654321")
        session.get.assert_called_once()

    def test_timestamped_feed_does_not_fall_back_to_an_old_otp(self):
        handled, code = client._fetch_timestamped_feed_otp(
            json.dumps({
                "status": "success",
                "data": [{
                    "saved_at": "2026-08-05 09:05:55",
                    "from": "ChatGPT <noreply@openai.com>",
                    "subject": "Your temporary ChatGPT login code",
                    "body": "Your verification code is 111111.",
                }],
            }),
            after_ts=datetime(2026, 8, 5, 9, 21, 40).timestamp(),
        )

        self.assertTrue(handled)
        self.assertIsNone(code)

    def test_untimestamped_response_keeps_legacy_fallback(self):
        handled, code = client._fetch_timestamped_feed_otp(
            json.dumps({"status": "success", "data": [{"body": "code 123456"}]}),
            after_ts=datetime(2026, 8, 5, 9, 21, 40).timestamp(),
        )

        self.assertFalse(handled)
        self.assertIsNone(code)


if __name__ == "__main__":
    unittest.main()
