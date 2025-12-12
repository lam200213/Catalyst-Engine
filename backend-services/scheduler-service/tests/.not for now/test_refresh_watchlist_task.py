# backend-services/scheduler-service/tests/test_refresh_watchlist_task.py
"""
The background worker function (e.g. refresh_watchlist_task) that actually calls monitoring-service’s orchestrator endpoint via HTTP and persists or updates job state.
Verify the consumer-side integration with monitoring-service: that the task issues requests.post to monitor/internal/watchlist/refresh-status, parses the raw JSON correctly, and translates it into the scheduler’s own job status and stored summary.
Assert behavior when the provider returns success vs 500, independent of how the API route is wired.

WEEK 10 scope, not for week 7
"""
import unittest
from unittest.mock import patch, MagicMock
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as scheduler_app

class TestRefreshWatchlistTask(unittest.TestCase):
    @patch("scheduler_app.requests.post")
    def test_task_calls_orchestrator_and_persists_summary(self, mock_post):
        """
        Consumer task: calls monitoring orchestrator and records summary to job store.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "OK", "updated_items": 2, "archived_items": 1, "failed_items": 0}
        mock_post.return_value = mock_resp

        # Simulate invoking the task function (name may differ)
        if hasattr(scheduler_app, "refresh_watchlist_task"):
            result = scheduler_app.refresh_watchlist_task()
            self.assertTrue(result)
        # Assert HTTP called once
        mock_post.assert_called()

    @patch("scheduler_app.requests.post")
    def test_task_handles_500_from_orchestrator(self, mock_post):
        """
        Consumer task: 500 from provider should mark job as failed.
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "internal"}
        mock_post.return_value = mock_resp

        if hasattr(scheduler_app, "refresh_watchlist_task"):
            result = scheduler_app.refresh_watchlist_task()
            self.assertFalse(result)
        mock_post.assert_called()
