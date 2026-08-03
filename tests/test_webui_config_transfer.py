# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import patch

from webui import config_editor
from webui.app import create_app


class RuntimeConfigDocumentTests(unittest.TestCase):
    def test_export_document_contains_only_keys_and_values(self):
        fields = [
            {"key": "EXAMPLE_SECRET", "value": "token-value", "secret": True},
            {"key": "EXAMPLE_SWITCH", "value": False, "secret": False},
        ]
        with patch.object(config_editor, "get_config", return_value=fields):
            document = config_editor.build_runtime_config_export(exported_at="2026-08-03T00:00:00Z")

        self.assertEqual(document["format"], config_editor.RUNTIME_CONFIG_FORMAT)
        self.assertEqual(document["version"], config_editor.RUNTIME_CONFIG_VERSION)
        self.assertEqual(document["exported_at"], "2026-08-03T00:00:00Z")
        self.assertTrue(document["includes_secrets"])
        self.assertEqual(document["field_count"], 2)
        self.assertEqual(document["config"], {
            "EXAMPLE_SECRET": "token-value",
            "EXAMPLE_SWITCH": False,
        })

    def test_import_accepts_all_supported_value_types(self):
        examples = {
            "str": "value",
            "bool": True,
            "int": 3,
            "float": 1.5,
            "list_str_multiline": ["one", "two"],
        }
        values = {}
        expected = {}
        for vtype, value in examples.items():
            field = next(item for item in config_editor.EDITABLE_FIELDS if item["type"] == vtype)
            values[field["key"]] = value
            expected[field["key"]] = value
        values["FUTURE_CONFIG_KEY"] = "ignored"

        parsed = config_editor.parse_runtime_config_import({
            "format": config_editor.RUNTIME_CONFIG_FORMAT,
            "version": config_editor.RUNTIME_CONFIG_VERSION,
            "config": values,
        })

        self.assertEqual(parsed["updates"], expected)
        self.assertEqual(parsed["ignored"], ["FUTURE_CONFIG_KEY"])

    def test_import_rejects_wrong_format_version_and_type(self):
        bool_field = next(item for item in config_editor.EDITABLE_FIELDS if item["type"] == "bool")
        base = {
            "format": config_editor.RUNTIME_CONFIG_FORMAT,
            "version": config_editor.RUNTIME_CONFIG_VERSION,
            "config": {bool_field["key"]: True},
        }
        for document in (
            {**base, "format": "other"},
            {**base, "version": 999},
            {**base, "config": {bool_field["key"]: "true"}},
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                config_editor.parse_runtime_config_import(document)


class RuntimeConfigWebUiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app(auth_code="test-auth").test_client()
        self.client.environ_base["HTTP_X_AUTH_CODE"] = "test-auth"

    @patch("webui.app.config_editor.build_runtime_config_export")
    def test_export_endpoint_downloads_json(self, build_export):
        build_export.return_value = {
            "format": config_editor.RUNTIME_CONFIG_FORMAT,
            "version": 1,
            "config": {"ENABLE_CODEX_AUTO": True},
        }

        response = self.client.get("/api/config/export")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("attachment;", response.headers["Content-Disposition"])
        self.assertIn("runtime-config-", response.headers["Content-Disposition"])
        self.assertEqual(json.loads(response.data)["config"]["ENABLE_CODEX_AUTO"], True)
        self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")

    @patch("config.reload_all")
    @patch("webui.app.config_editor.update_config")
    def test_import_endpoint_updates_known_keys_and_reloads(self, update_config, reload_all):
        update_config.return_value = {
            "updated": ["ENABLE_CODEX_AUTO"],
            "ignored": [],
            "env_updated": ["ENABLE_CODEX_AUTO"],
        }
        response = self.client.post("/api/config/import", json={
            "format": config_editor.RUNTIME_CONFIG_FORMAT,
            "version": config_editor.RUNTIME_CONFIG_VERSION,
            "config": {"ENABLE_CODEX_AUTO": False, "FUTURE_CONFIG_KEY": "value"},
        })

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["imported"], 1)
        self.assertEqual(body["ignored"], ["FUTURE_CONFIG_KEY"])
        self.assertTrue(body["reloaded"])
        update_config.assert_called_once_with({"ENABLE_CODEX_AUTO": False})
        reload_all.assert_called_once_with()

    @patch("webui.app.config_editor.update_config")
    def test_import_endpoint_rejects_invalid_json_and_types(self, update_config):
        invalid_json = self.client.post(
            "/api/config/import", data="{", content_type="application/json"
        )
        invalid_type = self.client.post("/api/config/import", json={
            "format": config_editor.RUNTIME_CONFIG_FORMAT,
            "version": config_editor.RUNTIME_CONFIG_VERSION,
            "config": {"ENABLE_CODEX_AUTO": "false"},
        })

        self.assertEqual(invalid_json.status_code, 400)
        self.assertIn("有效的 JSON", invalid_json.get_json()["error"])
        self.assertEqual(invalid_type.status_code, 400)
        self.assertIn("必须是布尔值", invalid_type.get_json()["error"])
        update_config.assert_not_called()

    def test_both_ui_modes_render_config_transfer_controls(self):
        modern = self.client.get("/?ui=modern").get_data(as_text=True)
        legacy = self.client.get("/?ui=legacy").get_data(as_text=True)

        self.assertIn('id="btnExportRuntimeConfigV2"', modern)
        self.assertIn('id="btnImportRuntimeConfigV2"', modern)
        self.assertIn('id="runtimeConfigFileV2"', modern)
        self.assertIn('id="btnExportRuntimeConfig"', legacy)
        self.assertIn('id="btnImportRuntimeConfig"', legacy)
        self.assertIn('id="runtimeConfigFile"', legacy)


if __name__ == "__main__":
    unittest.main()
