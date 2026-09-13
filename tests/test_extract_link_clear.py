# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db


class ExtractLinkClearTests(unittest.TestCase):
    def test_clear_account_extract_removes_finished_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts_path = root / "accounts.json"
            accounts_path.write_text(
                json.dumps(
                    [
                        {
                            "id": 1,
                            "email": "a@test.com",
                            "extract_link_status": "failed",
                            "extract_link_ok": False,
                            "extract_link_error": "network exploded",
                            "extract_link_message": "network exploded",
                            "extract_link_job_id": "job-1",
                            "extract_link_long_url": "https://example.test/pay",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(db, "_ACCOUNTS_JSON", accounts_path), patch.object(
                db, "_LEGACY_ACCOUNTS_JSON", root / "legacy_accounts.json"
            ), patch.object(db, "_ACCOUNTS_TXT", root / "accounts.txt"), patch.object(
                db, "_TOKENS_TXT", root / "tokens.txt"
            ), patch.object(db, "_VIEWER_HTML", root / "viewer.html"):
                self.assertEqual(db.clear_account_extract(1), "cleared")
                account = db.get_account(1)

        self.assertIsNotNone(account)
        self.assertNotIn("extract_link_status", account)
        self.assertNotIn("extract_link_error", account)
        self.assertNotIn("extract_link_job_id", account)
        self.assertNotIn("extract_link_long_url", account)

    def test_clear_account_extract_rejects_running_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts_path = root / "accounts.json"
            accounts_path.write_text(
                '[{"id":1,"email":"a@test.com","extract_link_status":"running","extract_link_error":"working"}]',
                encoding="utf-8",
            )
            with patch.object(db, "_ACCOUNTS_JSON", accounts_path), patch.object(
                db, "_LEGACY_ACCOUNTS_JSON", root / "legacy_accounts.json"
            ), patch.object(db, "_ACCOUNTS_TXT", root / "accounts.txt"), patch.object(
                db, "_TOKENS_TXT", root / "tokens.txt"
            ), patch.object(db, "_VIEWER_HTML", root / "viewer.html"):
                self.assertEqual(db.clear_account_extract(1), "busy")
                self.assertEqual(db.get_account(1)["extract_link_status"], "running")

    def test_clear_accounts_extract_clears_finished_and_skips_busy_missing_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts_path = root / "accounts.json"
            accounts_path.write_text(
                json.dumps(
                    [
                        {
                            "id": 1,
                            "email": "failed@test.com",
                            "extract_link_status": "failed",
                            "extract_link_error": "network exploded",
                        },
                        {
                            "id": 2,
                            "email": "success@test.com",
                            "extract_link_status": "success",
                            "extract_link_long_url": "https://example.test/pay",
                        },
                        {
                            "id": 3,
                            "email": "running@test.com",
                            "extract_link_status": "running",
                            "extract_link_error": "working",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(db, "_ACCOUNTS_JSON", accounts_path), patch.object(
                db, "_LEGACY_ACCOUNTS_JSON", root / "legacy_accounts.json"
            ), patch.object(db, "_ACCOUNTS_TXT", root / "accounts.txt"), patch.object(
                db, "_TOKENS_TXT", root / "tokens.txt"
            ), patch.object(db, "_VIEWER_HTML", root / "viewer.html"):
                cleared, skipped = db.clear_accounts_extract([1, 2, 3, 404, "bad", 1])
                account_1 = db.get_account(1)
                account_2 = db.get_account(2)
                account_3 = db.get_account(3)

        self.assertEqual([item["id"] for item in cleared], [1, 2])
        self.assertEqual({str(item["id"]) for item in skipped}, {"3", "404", "bad"})
        self.assertNotIn("extract_link_status", account_1)
        self.assertNotIn("extract_link_error", account_1)
        self.assertNotIn("extract_link_status", account_2)
        self.assertNotIn("extract_link_long_url", account_2)
        self.assertEqual(account_3["extract_link_status"], "running")
        self.assertEqual(account_3["extract_link_error"], "working")


if __name__ == "__main__":
    unittest.main()
