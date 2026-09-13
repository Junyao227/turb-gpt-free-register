# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from core import pay153_client
from webui.app import create_app


class Pay153WebUiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app(auth_code="test-auth").test_client()
        self.client.environ_base["HTTP_X_AUTH_CODE"] = "test-auth"

    @patch("webui.app.pay153_client.health", return_value={"ok": True, "time": 1})
    def test_health_proxy(self, health):
        response = self.client.get("/api/pay153/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        health.assert_called_once_with()

    @patch("webui.app.pay153_client.create_job", return_value={"job": {"id": "job-1"}})
    def test_create_job_proxy(self, create_job):
        payload = {"ba_token": "BA-ABCDEFGH1234", "phone": "+5511999999999", "country": "BR"}
        response = self.client.post("/api/pay153/jobs", json=payload)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["job"]["id"], "job-1")
        create_job.assert_called_once_with(payload)

    @patch("webui.app.pay153_client.get_job", return_value={"id": "job-1", "status": "awaiting_otp"})
    def test_get_job_proxy_with_log_offset(self, get_job):
        response = self.client.get("/api/pay153/jobs/job-1?log_offset=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "awaiting_otp")
        get_job.assert_called_once_with("job-1", log_offset=7)

    def test_get_job_rejects_invalid_log_offset(self):
        response = self.client.get("/api/pay153/jobs/job-1?log_offset=abc")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    @patch("webui.app.pay153_client.submit_otp", return_value={"job": {"id": "job-1"}})
    def test_submit_otp_proxy(self, submit_otp):
        response = self.client.post("/api/pay153/jobs/job-1/otp", json={"value": "123456"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        submit_otp.assert_called_once_with("job-1", "123456")

    @patch("webui.app.pay153_client.cancel_job", return_value={"job": {"id": "job-1", "status": "cancelled"}})
    def test_cancel_job_proxy(self, cancel_job):
        response = self.client.post("/api/pay153/jobs/job-1/cancel", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["job"]["status"], "cancelled")
        cancel_job.assert_called_once_with("job-1")

    @patch("webui.app.pay153_client.health", side_effect=pay153_client.Pay153ConfigError("disabled"))
    def test_config_error_returns_400(self, health):
        response = self.client.get("/api/pay153/health")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "disabled")
        health.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
