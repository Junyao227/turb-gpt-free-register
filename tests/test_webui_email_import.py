# -*- coding: utf-8 -*-
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class EmailImportUiTests(unittest.TestCase):
    def test_email_pool_import_is_the_default_in_both_uis(self):
        cases = (
            ("index.html", "importAsRegisteredV2", "registeredEl ? !!registeredEl.checked : false"),
            ("index_legacy.html", "importAsRegistered", "$('#importAsRegistered')?.checked ?? false"),
        )
        for template_name, checkbox_id, default_expression in cases:
            html = (ROOT / "webui" / "templates" / template_name).read_text(encoding="utf-8")
            checkbox = re.search(
                rf'<input\s+id="{checkbox_id}"[^>]*>',
                html,
                flags=re.IGNORECASE,
            )
            self.assertIsNotNone(checkbox, template_name)
            self.assertNotRegex(checkbox.group(0), r"\bchecked\b", template_name)
            self.assertIn(default_expression, html, template_name)


if __name__ == "__main__":
    unittest.main()
