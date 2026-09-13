# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from unittest.mock import patch

from core import db
from webui.app import create_app


ROOT = Path(__file__).resolve().parent.parent


class AccountCodexFilterTests(unittest.TestCase):
    def test_matches_codex_status_and_deactivated_liveness(self):
        success = {"codex_status": "success"}
        failed = {"codex_status": "failed"}
        deactivated_by_liveness = {"codex_status": "failed", "live_check_status": "deactivated"}
        deactivated_by_codex = {"codex_status": "deactivated"}

        self.assertTrue(db._matches_codex_status_filter(success, "success"))
        self.assertFalse(db._matches_codex_status_filter(success, "failed"))
        self.assertTrue(db._matches_codex_status_filter(failed, "failed"))
        self.assertTrue(db._matches_codex_status_filter(deactivated_by_liveness, "deactivated"))
        self.assertTrue(db._matches_codex_status_filter(deactivated_by_codex, "deactivated"))
        self.assertFalse(db._matches_codex_status_filter(failed, "deactivated"))
        self.assertTrue(db._matches_codex_status_filter(success, ""))

    def test_account_apis_pass_codex_status_filter_to_database(self):
        app = create_app(auth_code="test-account-filter")
        client = app.test_client()
        auth_headers = {"X-Auth-Code": "test-account-filter"}

        with patch.object(db, "list_accounts_page", return_value={"items": [], "total": 0}) as list_page:
            response = client.get("/api/accounts?paged=1&codex_status=deactivated", headers=auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_page.call_args.kwargs["codex_filter"], "deactivated")

        with patch.object(db, "list_account_plan_check_statuses", return_value={"items": [], "total": 0}) as list_status:
            response = client.get("/api/accounts/plan-check-status?codex_status=failed", headers=auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_status.call_args.kwargs["codex_filter"], "failed")

    def test_both_account_pages_send_the_filter_and_copy_selected_tokens(self):
        for template_name, filter_id in (
            ("index.html", "codexStatusFilterV2"),
            ("index_legacy.html", "codexStatusFilter"),
        ):
            source = (ROOT / "webui" / "templates" / template_name).read_text(encoding="utf-8")
            self.assertIn(filter_id, source, template_name)
            self.assertIn("codex_status=${encodeURIComponent(codex)}", source, template_name)
            self.assertIn("copySelectedAccountTokens", source, template_name)


if __name__ == "__main__":
    unittest.main()
