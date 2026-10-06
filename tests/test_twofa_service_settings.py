# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from core import twofa_service


class TwofaServiceSettingsTests(unittest.TestCase):
    def test_executor_has_capacity_for_live_worker_settings(self):
        settings = twofa_service.queue_settings()

        self.assertGreaterEqual(settings["workers"], 1)
        self.assertLessEqual(settings["workers"], 16)
        self.assertGreaterEqual(settings["queue_limit"], settings["workers"])
        self.assertGreaterEqual(twofa_service._EXECUTOR._max_workers, settings["workers"])

    def test_apply_settings_updates_live_limits_without_replacing_executor(self):
        executor = twofa_service._EXECUTOR
        original = twofa_service.queue_settings()
        try:
            with patch.object(twofa_service._twofa_cfg, "TWOFA_WORKERS", 7), patch.object(
                twofa_service._twofa_cfg, "TWOFA_QUEUE_LIMIT", 3
            ):
                updated = twofa_service.apply_settings()
                self.assertEqual(updated["workers"], 7)
                self.assertEqual(updated["queue_limit"], 7)
                self.assertIs(twofa_service._EXECUTOR, executor)
        finally:
            twofa_service.apply_settings()
        self.assertEqual(twofa_service.queue_settings()["workers"], original["workers"])

    def test_integer_settings_are_bounded(self):
        original = getattr(twofa_service._twofa_cfg, "TWOFA_WORKERS", None)
        try:
            twofa_service._twofa_cfg.TWOFA_WORKERS = 999
            self.assertEqual(twofa_service._int_setting("TWOFA_WORKERS", 4, 1, 16), 16)
            twofa_service._twofa_cfg.TWOFA_WORKERS = -5
            self.assertEqual(twofa_service._int_setting("TWOFA_WORKERS", 4, 1, 16), 1)
        finally:
            twofa_service._twofa_cfg.TWOFA_WORKERS = original


if __name__ == "__main__":
    unittest.main()
