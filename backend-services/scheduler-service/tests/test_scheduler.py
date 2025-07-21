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

    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_screening_job_workflow_success(self, mock_requests_get, mock_requests_post, mock_get_db_collections):
        # --- Arrange: Mock a successful workflow where one ticker passes all stages ---
        mock_results_collection = MagicMock()
        mock_jobs_collection = MagicMock()
        mock_get_db_collections.return_value = (mock_results_collection, mock_jobs_collection)

        def get_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            #  Corrected endpoint check for ticker-service
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
        self.assertEqual(json_data['trend_screen_survivors_count'], 2)
        self.assertEqual(json_data['final_candidates_count'], 1)
        self.assertIn(datetime.now(timezone.utc).strftime('%Y%m%d'), json_data['job_id'])

        # Verify database call
        mock_results_collection.insert_many.assert_called_once()
        args, _ = mock_results_collection.insert_many.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0]['ticker'], 'PASS_TICKER')

        mock_jobs_collection.insert_one.assert_called_once()
        summary_doc = mock_jobs_collection.insert_one.call_args[0][0]
        self.assertIn('job_id', summary_doc)
        self.assertEqual(summary_doc['final_candidates_count'], 1)


    #  Corrected patching for this test
    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_edge_case_no_tickers_found(self, mock_requests_get, mock_requests_post, mock_get_db_collections):
        # --- Arrange: Ticker service returns an empty list ---
        mock_get_db_collections.return_value = (MagicMock(), MagicMock())
        mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: [])

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['total_tickers_fetched'], 0)
        mock_requests_post.assert_not_called()
        #  Check that insert_many was not called on the results collection mock
        mock_get_db_collections.return_value[0].insert_many.assert_not_called()

    #  Corrected patching for this test
    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_edge_case_no_trend_survivors(self, mock_requests_get, mock_requests_post, mock_get_db_collections):
        # --- Arrange: Screening service returns an empty list ---
        mock_get_db_collections.return_value = (MagicMock(), MagicMock())
        mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: ['TICKER_A'])
        mock_requests_post.return_value = MagicMock(status_code=200, json=lambda: [])

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        #  Corrected assertion key
        self.assertEqual(json_data['trend_screen_survivors_count'], 0)
        self.assertEqual(json_data['final_candidates_count'], 0)
        mock_get_db_collections.return_value[0].insert_many.assert_not_called()

    @patch('app.requests.get')
    def test_service_failure_ticker_service(self, mock_requests_get):
        # --- Arrange: Ticker service throws a connection error ---
        mock_requests_get.side_effect = requests.exceptions.RequestException("Ticker service down")

        # --- Act ---
        response = self.app.post('/jobs/screening/start')

        # --- Assert ---
        self.assertEqual(response.status_code, 503)
        self.assertIn("Failed to connect to ticker-service", response.get_json()['error'])

    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_database_failure(self, mock_requests_get, mock_requests_post, mock_get_db_collections):
        # --- Arrange: Mock a DB failure ---
        mock_results_collection = MagicMock()
        mock_jobs_collection = MagicMock()
        mock_results_collection.insert_many.side_effect = errors.PyMongoError("DB connection lost")
        mock_get_db_collections.return_value = (mock_results_collection, mock_jobs_collection)
      
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
        mock_results_collection.insert_many.assert_called_once()
        mock_jobs_collection.insert_one.assert_not_called()

    #  Corrected patching for this test
    @patch('builtins.print')
    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_funnel_logging_and_database_persistence(self, mock_requests_get, mock_requests_post, mock_get_db_collections, mock_print):
        # --- Arrange: Mock a successful workflow for logging and persistence checks ---
        mock_results_collection, mock_jobs_collection = MagicMock(), MagicMock()
        mock_get_db_collections.return_value = (mock_results_collection, mock_jobs_collection)
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

        mock_results_collection.insert_many.assert_called_once()
        args, _ = mock_results_collection.insert_many.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertIn('job_id', args[0][0])
        self.assertIn('processed_at', args[0][0])
        self.assertEqual(args[0][0]['ticker'], PASS_TICKER)

        log_calls = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Fetched 3 total tickers." in call for call in log_calls))
        self.assertTrue(any("Stage 1 (Trend Screen) passed: 2 tickers." in call for call in log_calls))
        self.assertTrue(any("Stage 2 (VCP Screen) passed: 1 tickers." in call for call in log_calls))
        self.assertTrue(any("Inserted 1 candidate documents into the database." in call for call in log_calls))

    #  Corrected patching for this test
    @patch('builtins.print')
    @patch('app.get_db_collections')
    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_job_continues_when_downstream_service_returns_malformed_json(self, mock_requests_get, mock_requests_post, mock_get_db_collections, mock_print):
        # --- Arrange: Mock a workflow where one downstream service returns bad JSON ---
        mock_results_collection, mock_jobs_collection = MagicMock(), MagicMock()
        mock_get_db_collections.return_value = (mock_results_collection, mock_jobs_collection)

        def get_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if 'ticker-service' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = ['PASS_TICKER', 'BAD_JSON_TICKER']
            elif '/analyze/PASS_TICKER' in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {'vcp_pass': True, 'ticker': 'PASS_TICKER'}
            elif '/analyze/BAD_JSON_TICKER' in url:
                mock_resp.status_code = 200
                mock_resp.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", "doc", 0)
            else:
                mock_resp.status_code = 404
                mock_resp.json.return_value = {"error": "URL not mocked"}
            return mock_resp

        mock_requests_get.side_effect = get_side_effect
        mock_requests_post.return_value = MagicMock(
            status_code=200,
            json=lambda: ['PASS_TICKER', 'BAD_JSON_TICKER']
        )

        # --- Act ---
        response = self.app.post('/jobs/screening/start')
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)

        mock_results_collection.insert_many.assert_called_once()
        args, _ = mock_results_collection.insert_many.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0]['ticker'], 'PASS_TICKER')

        log_calls = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Could not decode JSON for ticker BAD_JSON_TICKER" in call for call in log_calls))

if __name__ == '__main__':
    unittest.main()