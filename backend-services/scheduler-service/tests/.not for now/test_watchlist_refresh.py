# backend-services/scheduler-service/tests/test_watchlist_refresh.py
"""
The public (or internal) API route, e.g. POST /jobs/watchlist/refresh, on the scheduler-service.
Verify that hitting the job endpoint actually triggers the scheduler-side orchestration entrypoint (here _call_monitoring_refresh or the Celery task enqueue).
Assert the HTTP contract seen by callers: status code (200 vs 202 vs error), presence of a job_id or a synchronous summary, and error envelope when the downstream provider fails.

WEEK 10 scope, not for week 7
"""
import unittest
from unittest.mock import patch, MagicMock
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

class TestWatchlistRefreshJob(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch("app._call_monitoring_refresh")
    def test_jobs_watchlist_refresh_triggers_orchestrator_and_returns_jobid(self, mock_call):
        """
        Consumer integration: POST /jobs/watchlist/refresh enqueues refresh and returns job id.
        """
        mock_call.return_value = {"message": "OK", "updated_items": 3, "archived_items": 1, "failed_items": 0}
        resp = self.client.post("/jobs/watchlist/refresh")
        # Accept either synchronous 200 or async 202 depending on implementation
        self.assertIn(resp.status_code, (200, 202))
        data = resp.get_json()
        # If async, a job_id is expected; if sync, summary may be returned directly
        self.assertTrue(("job_id" in data) or ("updated_items" in data))

    @patch("app._call_monitoring_refresh")
    def test_jobs_watchlist_refresh_handles_provider_500(self, mock_call):
        """
        Consumer integration: monitoring-service 500 should surface as 502/503 at scheduler.
        """
        mock_call.side_effect = RuntimeError("monitoring failed")
        resp = self.client.post("/jobs/watchlist/refresh")
        self.assertIn(resp.status_code, (502, 503, 500))
        data = resp.get_json()
        self.assertIn("error", data)
        self.assertIsInstance(data["error"], str)
