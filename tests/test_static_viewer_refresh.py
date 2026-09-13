# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from core import db


class StaticViewerRefreshTests(unittest.TestCase):
    def setUp(self):
        self._timer = db._VIEWER_REFRESH_TIMER
        self._reason = db._VIEWER_REFRESH_REASON
        db._VIEWER_REFRESH_TIMER = None
        db._VIEWER_REFRESH_REASON = ""

    def tearDown(self):
        timer = db._VIEWER_REFRESH_TIMER
        if timer is not None:
            timer.cancel()
        db._VIEWER_REFRESH_TIMER = self._timer
        db._VIEWER_REFRESH_REASON = self._reason

    def test_account_save_schedules_static_viewer_instead_of_rendering(self):
        with patch.object(db, "_save_collection"), \
             patch.object(db, "_sync_accounts_txt"), \
             patch.object(db, "_sync_tokens_txt"), \
             patch.object(db, "_schedule_static_viewer_refresh") as schedule, \
             patch.object(db, "_render_static_viewer") as render:
            db._save_accounts([{"id": 1, "email": "test@example.com"}])

        schedule.assert_called_once_with("save_accounts")
        render.assert_not_called()

    def test_schedule_coalesces_multiple_pending_refreshes(self):
        first_timer = MagicMock()
        second_timer = MagicMock()
        with patch.object(db.threading, "Timer", side_effect=[first_timer, second_timer]) as timer_factory:
            db._schedule_static_viewer_refresh("save_accounts")
            db._schedule_static_viewer_refresh("save_outlook")

        self.assertEqual(timer_factory.call_count, 2)
        first_timer.cancel.assert_called_once()
        second_timer.start.assert_called_once()
        self.assertEqual(db._VIEWER_REFRESH_REASON, "save_outlook")

    def test_manual_refresh_cancels_pending_background_refresh(self):
        pending_timer = MagicMock()
        db._VIEWER_REFRESH_TIMER = pending_timer
        db._VIEWER_REFRESH_REASON = "save_accounts"
        with patch.object(db, "_load_outlook", return_value=[]) as load_outlook, \
             patch.object(db, "_load_accounts", return_value=[]) as load_accounts, \
             patch.object(db, "_sync_outlook_txt"), \
             patch.object(db, "_sync_accounts_txt"), \
             patch.object(db, "_sync_tokens_txt"), \
             patch.object(db, "_render_static_viewer", return_value=db._VIEWER_HTML) as render:
            result = db.refresh_static_viewer()

        pending_timer.cancel.assert_called_once()
        load_outlook.assert_called_once()
        load_accounts.assert_called_once()
        render.assert_called_once_with(outlook_rows=[], account_rows=[])
        self.assertEqual(result, db._VIEWER_HTML)


if __name__ == "__main__":
    unittest.main()
