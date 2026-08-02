# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class JobRetryUiTests(unittest.TestCase):
    def test_row_retry_uses_click_without_pointerdown_deduplication(self):
        for template_name in ("index.html", "index_legacy.html"):
            html = (ROOT / "webui" / "templates" / template_name).read_text(encoding="utf-8")
            self.assertNotIn("pointerHandled", html, template_name)
            self.assertNotIn("addEventListener('pointerdown'", html, template_name)
            self.assertIn("const retryBtn = e.target.closest('[data-retry-job]')", html, template_name)
            self.assertIn("retryJob(parseInt(retryBtn.dataset.retryJob, 10), retryBtn)", html, template_name)


if __name__ == "__main__":
    unittest.main()
