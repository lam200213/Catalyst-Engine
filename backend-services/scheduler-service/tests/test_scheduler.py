# backend-services/scheduler-service/tests/test_scheduler.py
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import requests
from pymongo import errors
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    # Latest Add: Refactored to patch helper functions directly for clarity and stability.
    @patch('app._store_results')
    @patch('app._run_leadership_screening')
    @patch('app._count_unique_industries')
    @patch('app._run_vcp_analysis')
    @patch('app._run_trend_screening')
    @patch('app._get_all_tickers')
    def test_screening_job_workflow_success(self, mock_get_tickers, mock_trend_screen, mock_vcp_analysis, mock_count_industries, mock_leadership_screen, mock_store_results):
        # --- Arrange: Mock the return values of each stage in the pipeline ---
        mock_get_tickers.return_value = (['PASS_TICKER', 'FAIL_VCP', 'FAIL_TREND'], None)
        mock_trend_screen.return_value = (['PASS_TICKER', 'FAIL_VCP'], None)
        mock_vcp_analysis.return_value = [{'ticker': 'PASS_TICKER'}]
        mock_count_industries.return_value = 1
        mock_leadership_screen.return_value = [{'ticker': 'PASS_TICKER', 'leadership_results': {}}]
        mock_store_results.return_value = (True, None)

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['message'], "Screening job completed successfully.")
        self.assertEqual(json_data['total_tickers_fetched'], 3)
        self.assertEqual(json_data['trend_screen_survivors_count'], 2)
        self.assertEqual(json_data['vcp_survivors_count'], 1)
        self.assertEqual(json_data['final_candidates_count'], 1)
        self.assertIn(datetime.now(timezone.utc).strftime('%Y%m%d'), json_data['job_id'])

        # Verify the correct data was passed between functions
        mock_trend_screen.assert_called_once_with(unittest.mock.ANY, ['PASS_TICKER', 'FAIL_VCP', 'FAIL_TREND'])
        mock_vcp_analysis.assert_called_once_with(unittest.mock.ANY, ['PASS_TICKER', 'FAIL_VCP'])
        mock_leadership_screen.assert_called_once_with(unittest.mock.ANY, [{'ticker': 'PASS_TICKER'}])
        
        # Verify the final results were stored
        mock_store_results.assert_called_once()
        # Check the second argument of the call (candidates_doc)
        final_candidates_arg = mock_store_results.call_args[0][2]
        self.assertEqual(len(final_candidates_arg), 1)
        self.assertEqual(final_candidates_arg[0]['ticker'], 'PASS_TICKER')


    @patch('app._get_all_tickers')
    def test_service_failure_ticker_service(self, mock_get_tickers):
        # --- Arrange: Ticker service returns an error tuple ---
        mock_get_tickers.return_value = (None, ({"error": "Failed to connect"}, 503))

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 503)
        self.assertIn("Failed to connect", response.get_json()['error'])


    @patch('app._store_results')
    @patch('app._run_leadership_screening', return_value=[])
    @patch('app._run_vcp_analysis', return_value=[])
    @patch('app._run_trend_screening', return_value=([], None))
    @patch('app._get_all_tickers')
    def test_database_failure_on_store(self, mock_get_tickers, *args):
        # --- Arrange: Mock a DB failure during the final step ---
        mock_get_tickers.return_value = (['DB_FAIL_TICKER'], None)
        # The first patched arg is _store_results
        mock_store_results = args[-1]
        mock_store_results.return_value = (False, ({"error": "DB connection lost"}, 500))
        
        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 500)
        self.assertIn("DB connection lost", response.get_json()['error'])
        mock_store_results.assert_called_once()


if __name__ == '__main__':
    unittest.main()