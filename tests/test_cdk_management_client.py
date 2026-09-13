# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from config import codex
from core import cdk_management


class _Response:
    ok = True
    status_code = 200

    @staticmethod
    def json():
        return {
            "ok": True,
            "result": {
                "action": "created",
                "record_id": 7,
                "status": "draft",
                "has_cpa": True,
                "has_sub2api": False,
            },
        }


class CdkManagementClientTests(unittest.TestCase):
    def test_uploads_multipart_to_configured_management_origin(self):
        with (
            patch.object(codex, "CDK_MGMT_MANAGEMENT_URL", "https://cdk.example.test/deerchan"),
            patch.object(codex, "CDK_MGMT_MANAGEMENT_KEY", "test-management-key"),
            patch.object(codex, "CDK_MGMT_REQUEST_TIMEOUT", 12),
            patch.object(cdk_management.requests, "post", return_value=_Response()) as post,
        ):
            result = cdk_management.import_cpa_file(
                email="Mark@Example.com",
                content='{"email":"mark@example.com"}',
                filename="mark.json",
                source_filename="local-callback.json",
            )

        self.assertEqual(result["result"]["record_id"], 7)
        self.assertEqual(post.call_args.args[0], "https://cdk.example.test/api/management/import-cpa")
        self.assertEqual(post.call_args.kwargs["headers"]["X-Management-Key"], "test-management-key")
        self.assertEqual(post.call_args.kwargs["data"]["email"], "mark@example.com")
        self.assertEqual(post.call_args.kwargs["timeout"], 12)


if __name__ == "__main__":
    unittest.main()
