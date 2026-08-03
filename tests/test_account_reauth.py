# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import openai_protocol
from core import account_reauth, db, registration_service
from webui.app import create_app


class AccountReauthStorageTests(unittest.TestCase):
    def _storage(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        paths = {
            "_ACCOUNTS_JSON": root / "accounts.json",
            "_LEGACY_ACCOUNTS_JSON": root / "legacy-accounts.json",
            "_ACCOUNTS_TXT": root / "accounts.txt",
            "_TOKENS_TXT": root / "tokens.txt",
            "_VIEWER_HTML": root / "viewer.html",
            "_OUTLOOK_JSON": root / "outlook.json",
            "_OUTLOOK_TXT": root / "outlook.txt",
            "_GENERIC_API_EMAIL_JSON": root / "generic.json",
            "_GENERIC_API_EMAIL_TXT": root / "generic.txt",
            "_JOBS_JSON": root / "jobs.json",
            "_LEGACY_JOBS_JSON": root / "legacy-jobs.json",
        }
        accounts = [{
            "id": 1,
            "email": "account@example.com",
            "access_token": "old-token",
            "email_source": "generic_api",
            "plan_check_status": "failed",
            "plan_check_ok": False,
            "plan_check_error": "old token failed",
            "created_at": "2026-08-01T00:00:00",
        }]
        paths["_ACCOUNTS_JSON"].write_text(json.dumps(accounts), encoding="utf-8")
        paths["_GENERIC_API_EMAIL_JSON"].write_text(json.dumps([{
            "id": 1,
            "email": "account@example.com",
            "code_url": "https://mail.example.test/messages/account",
            "status": "used",
        }]), encoding="utf-8")
        paths["_OUTLOOK_JSON"].write_text("[]", encoding="utf-8")
        paths["_JOBS_JSON"].write_text("[]", encoding="utf-8")
        return td, paths

    def _patch_storage(self, paths):
        return patch.multiple(db, **paths)

    def test_success_updates_same_account_and_enqueues_plan_check(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths), patch(
                "core.account_reauth.run_account_reauth",
                return_value={
                    "email": "account@example.com",
                    "access_token": "new-token",
                    "session_info": {
                        "user": {"id": "user-1", "name": "Account User"},
                        "account": {"planType": "free"},
                        "expires": "2026-09-01T00:00:00",
                    },
                    "proxy_used": "http://proxy.test",
                },
            ), patch(
                "core.plan_check_service.enqueue_account_plan_check",
                return_value={"accepted": True, "status": "queued"},
            ) as enqueue:
                job, created = db.create_account_reauth_job(
                    1,
                    email="account@example.com",
                    email_source="generic_api",
                )
                self.assertTrue(created)
                registration_service._run_account_reauth_job(
                    job["id"], job["log_file"], "account@example.com", 1
                )

                account = db.get_account(1)
                self.assertEqual(account["id"], 1)
                self.assertEqual(account["access_token"], "new-token")
                self.assertEqual(account["user_id"], "user-1")
                self.assertEqual(account["plan_type"], "free")
                self.assertEqual(account["reauth_status"], "success")
                self.assertIsNone(account["plan_check_error"])
                self.assertEqual(len(db.list_accounts()), 1)
                enqueue.assert_called_once_with(
                    account_id=1,
                    email="account@example.com",
                    access_token="new-token",
                    trigger="reauth_auto",
                )
                self.assertEqual(db.get_job(job["id"])["status"], "success")
        finally:
            td.cleanup()

    def test_failure_keeps_old_token_and_redacts_otp(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths), patch(
                "core.account_reauth.run_account_reauth",
                side_effect=RuntimeError("OTP 123456 invalid; access_token=should-not-leak"),
            ):
                job, created = db.create_account_reauth_job(
                    1,
                    email="account@example.com",
                    email_source="generic_api",
                )
                self.assertTrue(created)
                registration_service._run_account_reauth_job(
                    job["id"], job["log_file"], "account@example.com", 1
                )

                account = db.get_account(1)
                self.assertEqual(account["access_token"], "old-token")
                self.assertEqual(account["reauth_status"], "failed")
                error = db.get_job(job["id"])["error_message"]
                self.assertIn("[已隐藏验证码]", error)
                self.assertNotIn("123456", error)
                self.assertNotIn("should-not-leak", error)
                log_text = Path(job["log_file"]).read_text(encoding="utf-8")
                self.assertNotIn("123456", log_text)
                self.assertNotIn("should-not-leak", log_text)
        finally:
            td.cleanup()

    def test_duplicate_submission_reuses_active_job(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths):
                first, created = db.create_account_reauth_job(
                    1,
                    email="account@example.com",
                    email_source="generic_api",
                )
                second, created_again = db.create_account_reauth_job(
                    1,
                    email="account@example.com",
                    email_source="generic_api",
                )
                self.assertTrue(created)
                self.assertFalse(created_again)
                self.assertEqual(first["id"], second["id"])
                self.assertEqual(len(db.list_jobs()), 1)
                self.assertEqual(db.get_account(1)["reauth_status"], "queued")
        finally:
            td.cleanup()

    def test_reauth_and_codex_jobs_are_mutually_exclusive(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths):
                paths["_JOBS_JSON"].write_text(json.dumps([{
                    "id": 7,
                    "job_type": "codex_retry",
                    "account_id": 1,
                    "status": "running",
                }]), encoding="utf-8")
                with self.assertRaises(ValueError):
                    db.create_account_reauth_job(
                        1,
                        email="account@example.com",
                        email_source="generic_api",
                    )

                paths["_JOBS_JSON"].write_text(json.dumps([{
                    "id": 8,
                    "job_type": "registration",
                    "root_job_id": 8,
                    "email": "account@example.com",
                    "email_source": "generic_api",
                    "status": "failed",
                    "account_id": 1,
                }]), encoding="utf-8")
                job, created = db.create_account_reauth_job(
                    1,
                    email="account@example.com",
                    email_source="generic_api",
                )
                self.assertTrue(created)
                with self.assertRaises(ValueError):
                    db.create_retry_job(
                        8,
                        job_type="codex_retry",
                        email_source="generic_api",
                        email="account@example.com",
                        account_id=1,
                    )
        finally:
            td.cleanup()


class AccountReauthFlowTests(unittest.TestCase):
    def test_generic_api_flow_uses_existing_mailbox_context(self):
        account = {
            "id": 1,
            "email": "account@example.com",
            "email_source": "generic_api",
            "access_token": "old-token",
        }
        generic_row = {
            "email": "account@example.com",
            "code_url": "https://mail.example.test/original-code-url",
        }
        session = unittest.mock.MagicMock()
        session.proxy = None
        session.get.return_value.raise_for_status.return_value = None
        otp_seen = {}

        def wait_from_original_context(email, *, after_ts):
            context = db.get_generic_api_email_by_email(email)
            otp_seen["code_url"] = context["code_url"]
            return "654321"

        with patch.object(db, "get_account_by_email", return_value=account), \
             patch.object(db, "get_generic_api_email_by_email", return_value=generic_row), \
             patch.object(openai_protocol, "CHATGPT_ANON_BOOTSTRAP_ENABLED", False), \
             patch.object(account_reauth, "BrowserSession", return_value=session), \
             patch.object(account_reauth, "network_preflight"), \
             patch.object(account_reauth, "get_providers"), \
             patch.object(account_reauth, "get_csrf_token", return_value="csrf"), \
             patch.object(account_reauth, "signin_openai", return_value="https://auth.openai.com/authorize"), \
             patch.object(account_reauth, "follow_authorize"), \
             patch.object(account_reauth, "validate_email_otp", return_value={
                 "page": {"type": "external_url"},
                 "external_url": "https://auth.openai.com/authorize/continue?state=opaque",
             }), \
             patch.object(account_reauth, "fetch_session", return_value={
                 "accessToken": "new-token",
                 "user": {"id": "user-1"},
                 "account": {"planType": "free"},
             }), \
             patch.object(account_reauth, "send_email_otp"), \
             patch("core.email_provider.wait_for_otp", side_effect=wait_from_original_context), \
             patch("core.email_provider.acquire_email") as acquire_email:
            result = account_reauth.run_account_reauth("account@example.com")

        self.assertEqual(result["email_source"], "generic_api")
        self.assertEqual(result["access_token"], "new-token")
        self.assertEqual(otp_seen["code_url"], generic_row["code_url"])
        acquire_email.assert_not_called()

    def test_reauth_api_returns_only_safe_job_fields(self):
        client = create_app(auth_code="test-auth").test_client()
        client.environ_base["HTTP_X_AUTH_CODE"] = "test-auth"
        result = {
            "ok": True,
            "message": "已创建重新登录任务",
            "job": {
                "id": 9,
                "job_type": "account_reauth",
                "status": "pending",
                "email": "account@example.com",
                "access_token": "must-not-return",
                "password": "must-not-return",
            },
        }
        with patch("webui.app.svc.submit_account_reauth", return_value=result):
            response = client.post("/api/accounts/1/reauth", json={})

        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertNotIn("access_token", json.dumps(payload))
        self.assertNotIn("password", json.dumps(payload))
        self.assertEqual(payload["job"]["id"], 9)


if __name__ == "__main__":
    unittest.main()
