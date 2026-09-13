# -*- coding: utf-8 -*-
import unittest
from pathlib import Path

from webui import config_editor


ROOT = Path(__file__).resolve().parent.parent


class CdkManagementUiTests(unittest.TestCase):
    def test_config_fields_are_available_and_keep_key_in_env(self):
        fields = {field["key"]: field for field in config_editor.EDITABLE_FIELDS}
        self.assertEqual(fields["CDK_MGMT_MANAGEMENT_URL"]["file"], "codex.py")
        self.assertTrue(fields["CDK_MGMT_MANAGEMENT_KEY"]["secret"])
        self.assertEqual(fields["CDK_MGMT_MANAGEMENT_KEY"]["storage"], "env")
        self.assertEqual(fields["CDK_MGMT_REQUEST_TIMEOUT"]["type"], "int")

    def test_modern_ui_has_bulk_cdk_management_upload_entry(self):
        html = (ROOT / "webui" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="btnCodexUploadBulkCdkV2"', html)
        self.assertIn("上传到CDK管理", html)
        self.assertIn("/api/codex/upload-bulk-to-cdk-management", html)
        self.assertIn("CDK管理端", html)
        self.assertIn("bind('btnCodexUploadBulkCdkV2', codexUploadBulkToCdkManagement);", html)

    def test_secret_config_fields_have_a_visibility_toggle(self):
        html = (ROOT / "webui" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("config-secret-toggle", html)
        self.assertIn("data-secret-visibility-toggle", html)
        self.assertIn("显示密钥", html)
        self.assertIn("input.type = visible ? 'text' : 'password';", html)


if __name__ == "__main__":
    unittest.main()
