# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from webui.app import _compact_account_for_list


ROOT = Path(__file__).resolve().parent.parent


class WebUiCodexAgentUiTests(unittest.TestCase):
    def test_compact_account_exports_codex_agent_error(self):
        row = {
            "id": 194,
            "email": "marina-2stealth@icloud.com",
            "codex_agent_status": "failed",
            "codex_agent_message": "正在生成 Codex Agent Token",
            "codex_agent_error": 'RuntimeError: Agent registration failed: 403 {"error":{"code":"agent_registry_not_enabled"}}',
            "codex_agent_runtime_id": None,
        }

        out = _compact_account_for_list(row)

        self.assertEqual(out["codex_agent_status"], "failed")
        self.assertEqual(out["codex_agent_message"], "正在生成 Codex Agent Token")
        self.assertEqual(out["codex_agent_error"], 'RuntimeError: Agent registration failed: 403 {"error":{"code":"agent_registry_not_enabled"}}')

    def test_modern_and_legacy_agent_cells_prioritize_codex_agent_error(self):
        modern = (ROOT / "webui" / "templates" / "index.html").read_text(encoding="utf-8")
        legacy = (ROOT / "webui" / "templates" / "index_legacy.html").read_text(encoding="utf-8")

        for html in (modern, legacy):
            self.assertIn("const detail = err || msg || r.codex_agent_runtime_id || '';", html)
            self.assertIn("function _agentErrorSummary(v)", html)
            self.assertIn("extract-link-error", html)
            self.assertIn("codex_agent_error", html)


if __name__ == "__main__":
    unittest.main()
