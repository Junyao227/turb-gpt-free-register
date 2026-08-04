# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db
from core import chatgpt_token_lifecycle as lifecycle
from webui.app import create_app


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class ChatGPTTokenLifecycleTests(unittest.TestCase):
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
        for key in ("_ACCOUNTS_JSON", "_OUTLOOK_JSON", "_GENERIC_API_EMAIL_JSON", "_JOBS_JSON"):
            paths[key].write_text("[]", encoding="utf-8")
        return td, paths

    def _insert_refreshable_account(self):
        return db.insert_account(
            email="account@example.com",
            access_token="access-old",
            extra={
                "chatgpt_oauth_tokens": {
                    "access_token": "access-old",
                    "refresh_token": "refresh-old",
                    "id_token": "id-old",
                    "oauth_context": {
                        "client_id": "client-chatgpt",
                        "redirect_uri": "http://localhost:1455/callback",
                        "token_url": "https://token.example.test/oauth/token",
                    },
                }
            },
        )

    def test_session_only_token_is_explicitly_unavailable(self):
        tokens = lifecycle.normalize_tokens(
            None,
            fallback_access_token="session-access-only",
            session_expires_at="2026-09-01T00:00:00Z",
        )
        self.assertEqual(tokens["status"], lifecycle.STATUS_UNAVAILABLE)
        self.assertEqual(tokens["refresh_token"], "")
        self.assertFalse(lifecycle.summarize_tokens(tokens)["can_refresh_chatgpt_token"])

    def test_refresh_rotates_refresh_token_and_updates_account_atomically(self):
        td, paths = self._storage()
        try:
            with patch.multiple(db, **paths):
                account_id = self._insert_refreshable_account()
                result = lifecycle.refresh_account(
                    account_id,
                    post=lambda *args: _Response(200, {
                        "access_token": "access-new",
                        "refresh_token": "refresh-new",
                        "id_token": "id-new",
                        "expires_in": 3600,
                    }),
                )
                self.assertEqual(result["status"], "refreshed")
                account = db.get_account(account_id)
                saved = db.get_chatgpt_oauth_tokens(account_id)
                self.assertEqual(account["access_token"], "access-new")
                self.assertEqual(saved["refresh_token"], "refresh-new")
                self.assertEqual(saved["id_token"], "id-new")
                self.assertEqual(saved["status"], lifecycle.STATUS_ACTIVE)
                self.assertTrue(saved["last_refreshed_at"])
                self.assertTrue(saved["expires_at"])
        finally:
            td.cleanup()

    def test_refresh_without_rotation_preserves_existing_refresh_token(self):
        td, paths = self._storage()
        try:
            with patch.multiple(db, **paths):
                account_id = self._insert_refreshable_account()
                result = lifecycle.refresh_account(
                    account_id,
                    post=lambda *args: _Response(200, {"access_token": "access-new", "expires_in": 1200}),
                )
                self.assertEqual(result["status"], "refreshed")
                saved = db.get_chatgpt_oauth_tokens(account_id)
                self.assertEqual(saved["refresh_token"], "refresh-old")
                self.assertEqual(saved["access_token"], "access-new")
        finally:
            td.cleanup()

    def test_refresh_failure_keeps_credentials_and_writes_redacted_status(self):
        td, paths = self._storage()
        try:
            with patch.multiple(db, **paths):
                account_id = self._insert_refreshable_account()
                result = lifecycle.refresh_account(
                    account_id,
                    post=lambda *args: _Response(400, {"error": "invalid_grant", "refresh_token": "must-not-leak"}),
                )
                self.assertEqual(result["status"], "failed")
                self.assertNotIn("must-not-leak", result["error"])
                saved = db.get_chatgpt_oauth_tokens(account_id)
                self.assertEqual(saved["refresh_token"], "refresh-old")
                self.assertEqual(saved["status"], lifecycle.STATUS_FAILED)
                self.assertNotIn("refresh-old", saved["last_error"])
        finally:
            td.cleanup()

    def test_mailbox_refresh_token_is_not_a_chatgpt_refresh_token(self):
        td, paths = self._storage()
        try:
            paths["_ACCOUNTS_JSON"].write_text(json.dumps([{
                "id": 1,
                "email": "account@example.com",
                "access_token": "access-old",
                "refresh_token": "outlook-refresh-only",
            }]), encoding="utf-8")
            with patch.multiple(db, **paths):
                result = lifecycle.refresh_account(1, post=lambda *args: self.fail("unexpected network refresh"))
                self.assertEqual(result["status"], "skipped")
                saved = db.get_chatgpt_oauth_tokens(1)
                self.assertEqual(saved["refresh_token"], "")
                self.assertEqual(db.get_account(1)["refresh_token"], "outlook-refresh-only")
        finally:
            td.cleanup()

    def test_account_list_and_refresh_apis_are_token_safe(self):
        td, paths = self._storage()
        try:
            with patch.multiple(db, **paths):
                account_id = self._insert_refreshable_account()
                app = create_app(auth_code="test-auth")
                client = app.test_client()
                client.environ_base["HTTP_X_AUTH_CODE"] = "test-auth"

                listing = client.get("/api/accounts?paged=1&page=1&page_size=10")
                listing_text = json.dumps(listing.get_json())
                self.assertEqual(listing.status_code, 200)
                self.assertNotIn("refresh-old", listing_text)
                self.assertNotIn("access-old", listing_text)
                self.assertTrue(listing.get_json()["items"][0]["can_refresh_chatgpt_token"])

                with patch("core.chatgpt_token_lifecycle.refresh_account", return_value={
                    "account_id": account_id,
                    "status": "refreshed",
                    "error": "",
                }):
                    response = client.post(f"/api/accounts/{account_id}/refresh-token", json={})
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload["status"], "refreshed")
                self.assertNotIn("refresh-old", json.dumps(payload))
                self.assertNotIn("access-old", json.dumps(payload))

                with patch("core.chatgpt_token_lifecycle.refresh_accounts", return_value={
                    "requested_count": 1,
                    "refreshed_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "results": [{"account_id": account_id, "status": "refreshed", "error": ""}],
                }):
                    bulk = client.post("/api/accounts/refresh-token-bulk", json={"account_ids": [account_id]})
                self.assertEqual(bulk.status_code, 200)
                self.assertEqual(bulk.get_json()["refreshed_count"], 1)
                self.assertNotIn("access-old", json.dumps(bulk.get_json()))
                self.assertNotIn("refresh-old", json.dumps(bulk.get_json()))
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
