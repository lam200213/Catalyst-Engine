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

    # Test suite for the scheduler pipeline.
    @patch('app._store_results')
    @patch('app._run_leadership_screening')
    @patch('app._count_unique_industries')
    @patch('app._run_vcp_analysis')
    @patch('app._run_trend_screening')
    @patch('app._get_all_tickers')
    def test_full_pipeline_success(
        self,
        mock_get_tickers,
        mock_trend_screen,
        mock_vcp_analysis,
        mock_count_industries,
        mock_leadership_screen,
        mock_store_results
    ):
        """
        Test the successful execution of the entire screening pipeline from start to finish.
        Ensures data flows correctly between mocked stages and the final results are stored.
        """
        # --- Arrange: Mock the return values for each stage of the screening funnel ---
        mock_get_tickers.return_value = (['TICKER_A', 'TICKER_B', 'TICKER_C'], None)
        mock_trend_screen.return_value = (['TICKER_A', 'TICKER_B'], None)
        mock_vcp_analysis.return_value = [{'ticker': 'TICKER_A', 'vcp_pass': True}]
        mock_count_industries.return_value = 1
        mock_leadership_screen.return_value = [{'ticker': 'TICKER_A', 'vcp_pass': True, 'leadership_results': {'passes': True}}]
        mock_store_results.return_value = (True, None)

        # --- Act: Trigger the screening job via the API endpoint ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert: Verify the response and the interactions between pipeline stages ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['message'], "Screening job completed successfully.")
        self.assertEqual(json_data['total_tickers_fetched'], 3)
        self.assertEqual(json_data['trend_screen_survivors_count'], 2)
        self.assertEqual(json_data['vcp_survivors_count'], 1)
        self.assertEqual(json_data['final_candidates_count'], 1)
        self.assertIn(datetime.now(timezone.utc).strftime('%Y%m%d'), json_data['job_id'])

        # Verify that each stage was called with the output of the previous stage
        mock_get_tickers.assert_called_once()
        mock_trend_screen.assert_called_once_with(unittest.mock.ANY, ['TICKER_A', 'TICKER_B', 'TICKER_C'])
        mock_vcp_analysis.assert_called_once_with(unittest.mock.ANY, ['TICKER_A', 'TICKER_B'])
        mock_leadership_screen.assert_called_once_with(unittest.mock.ANY, [{'ticker': 'TICKER_A', 'vcp_pass': True}])
        
        # Verify the final results were stored correctly
        mock_store_results.assert_called_once()
        call_args = mock_store_results.call_args[0]
        self.assertEqual(call_args[1]['final_candidates_count'], 1) # summary_doc
        self.assertEqual(len(call_args[5]), 1) # final_candidates list
        self.assertEqual(call_args[5][0]['ticker'], 'TICKER_A')


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