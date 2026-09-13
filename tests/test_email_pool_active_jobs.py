# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db


class EmailPoolActiveJobTests(unittest.TestCase):
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
            "_DOMAIN_EMAIL_JSON": root / "domain.json",
            "_JOBS_JSON": root / "jobs.json",
            "_LEGACY_JOBS_JSON": root / "legacy-jobs.json",
            "_LOG_DIR": root / "logs",
        }
        for key in ("_ACCOUNTS_JSON", "_OUTLOOK_JSON", "_DOMAIN_EMAIL_JSON", "_JOBS_JSON"):
            paths[key].write_text("[]", encoding="utf-8")
        return td, paths

    def _patch_storage(self, paths):
        return patch.multiple(db, **paths)

    def _write_generic_pool(self, path: Path, rows: list[dict]) -> None:
        path.write_text(json.dumps(rows), encoding="utf-8")

    def _read_generic_pool(self, path: Path) -> list[dict]:
        return db.list_generic_api_email_pool(limit=500)

    def test_generic_claim_skips_email_already_used_by_active_job(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths):
                self._write_generic_pool(paths["_GENERIC_API_EMAIL_JSON"], [
                    {
                        "id": 1,
                        "email": "busy@example.com",
                        "code_url": "https://mail.example.test/busy",
                        "status": "available",
                        "used_at": None,
                    },
                    {
                        "id": 2,
                        "email": "next@example.com",
                        "code_url": "https://mail.example.test/next",
                        "status": "available",
                        "used_at": None,
                    },
                ])
                db.create_job(email_source="generic_api")
                db.update_job(1, status="running", email="busy@example.com")

                claimed = db.claim_next_generic_api_email()

                self.assertIsNotNone(claimed)
                self.assertEqual(claimed["email"], "next@example.com")
                rows = {row["email"]: row for row in self._read_generic_pool(paths["_GENERIC_API_EMAIL_JSON"])}
                self.assertEqual(rows["busy@example.com"]["status"], "available")
                self.assertEqual(rows["next@example.com"]["status"], "used")
        finally:
            td.cleanup()

    def test_release_allows_current_job_but_not_other_active_job(self):
        td, paths = self._storage()
        try:
            with self._patch_storage(paths):
                self._write_generic_pool(paths["_GENERIC_API_EMAIL_JSON"], [{
                    "id": 1,
                    "email": "same@example.com",
                    "code_url": "https://mail.example.test/same",
                    "status": "used",
                    "used_at": "2026-08-10T00:00:00",
                }])
                db.create_job(email_source="generic_api")
                db.update_job(1, status="running", email="same@example.com")

                self.assertTrue(db.release_unconsumed_generic_api_email("same@example.com", exclude_job_id=1))
                self.assertEqual(self._read_generic_pool(paths["_GENERIC_API_EMAIL_JSON"])[0]["status"], "available")

                db.update_job(1, status="failed")
                claimed = db.claim_next_generic_api_email()
                self.assertEqual(claimed["email"], "same@example.com")
                db.create_job(email_source="generic_api")
                db.update_job(2, status="running", email="same@example.com")

                self.assertFalse(db.release_unconsumed_generic_api_email("same@example.com", exclude_job_id=1))
                self.assertEqual(self._read_generic_pool(paths["_GENERIC_API_EMAIL_JSON"])[0]["status"], "used")
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
