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
    @patch('app._run_vcp_analysis')
    @patch('app._run_trend_screening')
    @patch('app._get_all_tickers')
    def test_full_pipeline_success(
        self,
        mock_get_tickers,
        mock_trend_screen,
        mock_vcp_analysis,
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
        mock_leadership_screen.return_value = ([{'ticker': 'TICKER_A', 'vcp_pass': True, 'leadership_results': {'passes': True}}], 1)
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
        self.assertEqual(json_data['unique_industries_count'], 1)
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
    @patch('app._run_leadership_screening', return_value=([], 0))
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

    @patch('app._store_results', return_value=(True, None))
    @patch('app._run_leadership_screening', return_value=([], 0))
    @patch('app._run_vcp_analysis', return_value=[])
    @patch('app._run_trend_screening')
    @patch('app.get_db_collections')
    @patch('app._get_all_tickers')
    def test_pipeline_filters_delisted_tickers_before_screening(
        self,
        mock_get_tickers,
        mock_get_db,
        mock_trend_screen,
        *other_mocks
    ):
        """
        Goal: Verify the core pre-filtering logic in the orchestration pipeline.
        """
        # --- Arrange ---
        # 1. Mock the full list of tickers
        mock_get_tickers.return_value = (['AAPL', 'GOOG', 'ATVI'], None)

        # 2. Mock the DB collection for delisted tickers
        mock_ticker_status_coll = MagicMock()
        mock_ticker_status_coll.find.return_value = [{'ticker': 'ATVI'}]
        # get_db_collections returns a tuple, we only care about the last one (ticker_status)
        mock_get_db.return_value = (None, None, None, None, None, mock_ticker_status_coll)

        # 3. Mock the trend screening function to act as a spy
        mock_trend_screen.return_value = (['AAPL', 'GOOG'], None)

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        # Assert that the trend screening stage was called with the FILTERED list
        mock_trend_screen.assert_called_once()
        call_args, _ = mock_trend_screen.call_args
        # The list might be in a different order, so compare content ignoring order
        self.assertCountEqual(call_args[1], ['AAPL', 'GOOG'])

    @patch('app._store_results', return_value=(True, None))
    @patch('app._run_leadership_screening', return_value=([], 0))
    @patch('app._run_vcp_analysis', return_value=[])
    @patch('app._run_trend_screening')
    @patch('app.get_db_collections')
    @patch('app._get_all_tickers')
    def test_pipeline_proceeds_with_unfiltered_list_on_db_error(
        self,
        mock_get_tickers,
        mock_get_db,
        mock_trend_screen,
        *other_mocks
    ):
        """
        Goal: Ensure the pipeline doesn't fail if the ticker_status collection can't be queried.
        """
        # --- Arrange ---
        # 1. Mock the full list of tickers
        full_ticker_list = ['AAPL', 'GOOG', 'ATVI']
        mock_get_tickers.return_value = (full_ticker_list, None)

        # 2. Mock the DB collection to raise an error
        mock_ticker_status_coll = MagicMock()
        mock_ticker_status_coll.find.side_effect = errors.PyMongoError("Connection failed")
        mock_get_db.return_value = (None, None, None, None, None, mock_ticker_status_coll)

        # 3. Mock the trend screening function
        mock_trend_screen.return_value = ([], None) # Return value doesn't matter much here

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        # Assert that the trend screening stage was called with the COMPLETE, UNFILTERED list
        mock_trend_screen.assert_called_once()
        call_args, _ = mock_trend_screen.call_args
        self.assertCountEqual(call_args[1], full_ticker_list)

if __name__ == '__main__':
    unittest.main()