# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TokenCopyUiTests(unittest.TestCase):
    def test_modern_ui_has_separate_selected_and_current_page_token_copy(self):
        html = (ROOT / "webui" / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="btnCopySelectedTokensV2"', html)
        self.assertIn("复制选中Token", html)
        self.assertIn("'btnRefreshSelectedChatGPTTokensV2', 'btnCopySelectedTokensV2'", html)
        self.assertIn("bind('btnCopySelectedTokensV2', copySelectedAccountTokens);", html)

        self.assertIn('id="btnCopyAllTokensV2"', html)
        self.assertIn("复制本页Token", html)
        self.assertIn("bind('btnCopyAllTokensV2', copyCurrentPageTokens);", html)

    def test_legacy_ui_has_separate_selected_and_current_page_token_copy(self):
        html = (ROOT / "webui" / "templates" / "index_legacy.html").read_text(encoding="utf-8")

        self.assertIn('id="btnCopySelectedTokens"', html)
        self.assertIn("复制选中Token", html)
        self.assertIn("copySelectedTokensBtn.disabled = ACCOUNT_SELECTED.size === 0", html)
        self.assertIn("$('#btnCopySelectedTokens')?.addEventListener('click', copySelectedAccountTokens);", html)

        self.assertIn('id="copyAllTokens"', html)
        self.assertIn("复制本页Token", html)
        self.assertIn("$('#copyAllTokens').addEventListener('click'", html)


if __name__ == "__main__":
    unittest.main()
