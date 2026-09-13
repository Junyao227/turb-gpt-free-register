# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from unittest.mock import patch

from core import registration_service as service

ROOT = Path(__file__).resolve().parent.parent


class JobRetryUiTests(unittest.TestCase):
    def test_row_retry_uses_click_without_pointerdown_deduplication(self):
        for template_name in ("index.html", "index_legacy.html"):
            html = (ROOT / "webui" / "templates" / template_name).read_text(encoding="utf-8")
            self.assertNotIn("pointerHandled", html, template_name)
            self.assertNotIn("addEventListener('pointerdown'", html, template_name)
            self.assertIn("const retryBtn = e.target.closest('[data-retry-job]')", html, template_name)
            self.assertIn("retryJob(parseInt(retryBtn.dataset.retryJob, 10), retryBtn)", html, template_name)

    def test_job_polling_guards_against_overlapping_requests(self):
        for template_name in ("index.html", "index_legacy.html"):
            html = (ROOT / "webui" / "templates" / template_name).read_text(encoding="utf-8")
            self.assertIn("let jobsLoading = false;", html, template_name)
            self.assertIn("if (jobsLoading) return;", html, template_name)
            self.assertIn("let summaryLoading = false;", html, template_name)
            refresh_body = html.split("async function refreshJobs()", 1)[1].split("let modalScrollY", 1)[0]
            self.assertNotIn("loadSummary();", refresh_body, template_name)


class JobRetryInfoBatchTests(unittest.TestCase):
    def test_batch_retry_info_uses_indexes_instead_of_per_row_db_reads(self):
        jobs = [
            {"id": 1, "status": "failed", "email": "root@example.com"},
            {"id": 2, "status": "success", "root_job_id": 1, "email": "root@example.com"},
            {"id": 3, "status": "failed", "account_id": 10, "email": "account@example.com"},
            {"id": 4, "status": "cancelled", "email": "fresh@example.com"},
            {"id": 5, "status": "running", "email": "active@example.com"},
        ]
        accounts = [
            {"id": 10, "email": "account@example.com", "codex_status": "failed"},
            {"id": 11, "email": "fresh@example.com", "codex_status": "success"},
        ]

        with patch.object(service.db, "list_accounts", return_value=accounts) as list_accounts, \
             patch.object(service.db, "get_successful_retry_for_job", side_effect=AssertionError("per-row job lookup")), \
             patch.object(service.db, "get_account", side_effect=AssertionError("per-row account lookup")), \
             patch.object(service.db, "get_account_by_email", side_effect=AssertionError("per-row email lookup")):
            info = service.get_retry_info_map(jobs, all_jobs=jobs)

        self.assertEqual(info[1]["successful_retry_job_id"], 2)
        self.assertFalse(info[1]["retryable"])
        self.assertEqual(info[3]["retry_action"], "codex")
        self.assertEqual(info[3]["display_status"], "partial_success")
        self.assertFalse(info[4]["retryable"])
        self.assertEqual(info[4]["retry_reason"], "账号和 Codex 授权均已完成")
        self.assertFalse(info[5]["retryable"])
        list_accounts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
