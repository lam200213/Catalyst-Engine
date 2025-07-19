# backend-services/scheduler-service/tests/test_scheduler.py
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import requests
from pymongo import errors

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.get_db_collection')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_screening_job_workflow_success(self, mock_requests_get, mock_requests_post, mock_get_db_collection):
        # --- Arrange: Mock a successful workflow where one ticker passes all stages ---
        mock_results_collection = MagicMock()
        mock_get_db_collection.return_value = mock_results_collection

        def get_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if 'ticker-service' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = ['PASS_TICKER', 'FAIL_VCP_TICKER', 'FAIL_TREND_TICKER']
            elif 'analyze/PASS_TICKER' in url:
                self.assertEqual(kwargs.get('params'), {'mode': 'fast'})
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"vcp_pass": True, "ticker": "PASS_TICKER"}
            elif 'analyze/FAIL_VCP_TICKER' in url:
                self.assertEqual(kwargs.get('params'), {'mode': 'fast'})
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"vcp_pass": False, "ticker": "FAIL_VCP_TICKER"}
            else:
                mock_resp.status_code = 404
                mock_resp.json.return_value = {"error": "URL not mocked"}
            return mock_resp

        mock_requests_get.side_effect = get_side_effect

        mock_requests_post.return_value = MagicMock(
            status_code=200,
            json=lambda: ['PASS_TICKER', 'FAIL_VCP_TICKER']
        )

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['message'], "Screening job completed successfully.")
        self.assertEqual(json_data['total_tickers_fetched'], 3)
        self.assertEqual(json_data['trend_screen_survivors'], 2)
        self.assertEqual(json_data['final_candidates_count'], 1)

        # Verify database call
        mock_results_collection.insert_many.assert_called_once()
        # Check that the argument passed to insert_many is a list with one dictionary
        args, _ = mock_results_collection.insert_many.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0]['ticker'], 'PASS_TICKER')


    @patch('app.results_collection')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_edge_case_no_tickers_found(self, mock_requests_get, mock_requests_post, mock_results_collection):
        # --- Arrange: Ticker service returns an empty list ---
        mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: [])

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['total_tickers_fetched'], 0)
        mock_requests_post.assert_not_called()
        mock_results_collection.insert_many.assert_not_called()

    @patch('app.results_collection')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_edge_case_no_trend_survivors(self, mock_requests_get, mock_requests_post, mock_results_collection):
        # --- Arrange: Screening service returns an empty list ---
        mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: ['TICKER_A'])
        mock_requests_post.return_value = MagicMock(status_code=200, json=lambda: [])

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['trend_screen_survivors'], 0)
        self.assertEqual(json_data['final_candidates_count'], 0)
        mock_results_collection.insert_many.assert_not_called()

    @patch('app.requests.get')
    def test_service_failure_ticker_service(self, mock_requests_get):
        # --- Arrange: Ticker service throws a connection error ---
        mock_requests_get.side_effect = requests.exceptions.RequestException("Ticker service down")

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 503)
        self.assertIn("Failed to connect to ticker-service", response.get_json()['error'])

    @patch('app.get_db_collection')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_database_failure(self, mock_requests_get, mock_requests_post, mock_get_db_collection):
        # --- Arrange: Mock a successful workflow up to the point of DB failure ---
        mock_collection = MagicMock()
        mock_collection.insert_many.side_effect = errors.PyMongoError("DB connection lost")
        mock_get_db_collection.return_value = mock_collection

        def get_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if 'ticker-service' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = ['DB_FAIL_TICKER']
            elif 'analyze/DB_FAIL_TICKER' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"vcp_pass": True, "ticker": "DB_FAIL_TICKER"}
            else:
                mock_resp.status_code = 404
            return mock_resp

        mock_requests_get.side_effect = get_side_effect
        mock_requests_post.return_value = MagicMock(
            status_code=200,
            json=lambda: ['DB_FAIL_TICKER']
        )

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to write to database", response.get_json()['error'])
        mock_collection.insert_many.assert_called_once()

    @patch('builtins.print')
    @patch('app.get_db_collection')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_funnel_logging_and_database_persistence(self, mock_requests_get, mock_requests_post, mock_get_db_collection, mock_print):
        # --- Arrange: Mock a successful workflow for logging and persistence checks ---
        mock_collection = MagicMock()
        mock_get_db_collection.return_value = mock_collection
        PASS_TICKER = 'LOG_PASS'

        def get_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if 'ticker-service' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = [PASS_TICKER, 'LOG_FAIL_VCP', 'LOG_FAIL_TREND']
            elif f'analyze/{PASS_TICKER}' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"vcp_pass": True, "ticker": PASS_TICKER}
            elif 'analyze/LOG_FAIL_VCP' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"vcp_pass": False, "ticker": "LOG_FAIL_VCP"}
            else:
                mock_resp.status_code = 404
            return mock_resp

        mock_requests_get.side_effect = get_side_effect
        mock_requests_post.return_value = MagicMock(status_code=200, json=lambda: [PASS_TICKER, 'LOG_FAIL_VCP'])

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)

        # Assert Database Persistence
        mock_collection.insert_many.assert_called_once()
        args, _ = mock_collection.insert_many.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertIn('job_id', args[0][0])
        self.assertIn('processed_at', args[0][0])
        self.assertEqual(args[0][0]['ticker'], PASS_TICKER)

        # Assert Funnel Logging
        log_calls = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("Fetched 3 total tickers.", "\n".join(log_calls))
        self.assertIn("Stage 1 (Trend Screen) passed: 2 tickers.", "\n".join(log_calls))
        self.assertIn("Stage 2 (VCP Screen) passed: 1 tickers.", "\n".join(log_calls))
        self.assertIn("Inserted 1 documents into the database.", "\n".join(log_calls))

if __name__ == '__main__':
    unittest.main()