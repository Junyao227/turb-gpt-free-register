from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from core import extract_link_service as service


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def read(self) -> bytes:
        return self._body


class ExtractLinkServiceTests(unittest.TestCase):
    def test_grabpay_link_type_is_accepted(self):
        self.assertEqual(service._link_type("grabpay"), "grabpay")

    def test_gopay_link_type_is_accepted(self):
        self.assertEqual(service._link_type("gopay"), "gopay")

    def test_twint_link_type_is_accepted(self):
        self.assertEqual(service._link_type("twint"), "twint")

    def test_gcash_link_type_is_accepted(self):
        self.assertEqual(service._link_type("gcash"), "gcash")

    def test_paypal_link_type_is_accepted(self):
        self.assertEqual(service._link_type("paypal"), "paypal")

    def test_create_job_posts_only_token_and_link_type(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _Response(b'{"ok": true, "job_id": "job-1"}')

        with patch.object(service, "_api_base", return_value="http://127.0.0.1:8787"), patch.object(
            service, "_session", return_value=None
        ), patch.object(service, "urlopen", side_effect=fake_urlopen):
            result = service._create_extract_job(token="access-token", link_type="pix")

        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(captured["url"], "http://127.0.0.1:8787/api/extract")
        self.assertEqual(captured["payload"], {"token": "access-token", "link_type": "pix"})

    def test_sse_subscription_has_no_query_parameters(self):
        body = b"event: log\ndata: {\"message\": \"working\"}\n\nevent: done\ndata: {\"ok\": true}\n\n"
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return io.BytesIO(body)

        with patch.object(service, "_api_base", return_value="http://127.0.0.1:8787"), patch.object(
            service, "_session", return_value=None
        ), patch.object(service, "urlopen", side_effect=fake_urlopen):
            events = list(service._iter_sse_events(job_id="job-1"))

        self.assertEqual(captured["url"], "http://127.0.0.1:8787/api/jobs/job-1/events")
        self.assertEqual(events, [("log", {"message": "working"}), ("done", {"ok": True})])


if __name__ == "__main__":
    unittest.main()
