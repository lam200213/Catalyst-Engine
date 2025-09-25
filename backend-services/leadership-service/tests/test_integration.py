# backend-services/leadership-service/tests/test_integration.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
import data_fetcher

# --- Mock Data Generation ---
# Using helpers from the logic test file for consistency
from tests.mock_data_helpers import (
    create_mock_financial_data, 
    create_mock_price_data, 
    create_mock_index_data
)
class TestLeadershipScreeningIntegration(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()

    @patch('checks.industry_peer_checks.fetch_batch_financials')
    @patch('checks.industry_peer_checks.fetch_peer_data')
    @patch('app.fetch_market_trends')
    @patch('app.fetch_index_data')
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_leadership_endpoint_pass_scenario(self, mock_fetch_financials, mock_fetch_price, mock_fetch_index, mock_fetch_trends, mock_fetch_peers, mock_fetch_batch):
        """
        Integration Test: A ticker that passes all criteria in a Bullish market.
        """
        # --- Arrange Mocks ---
        # 1. Financial Data (passes all financial checks)
        # Use the 'passing_data=True' flag in the helper to generate data that passes growth checks.
        pass_financials = create_mock_financial_data(ipoDate='2022-01-01', passing_data=True, ticker="PASS-TICKER") 
        mock_fetch_financials.return_value = (pass_financials, 200)

        # 2. Price Data (for market impact)
        # Use the 'passing_data=True' flag to ensure a rally is simulated.
        stock_prices, sp500_prices = create_mock_price_data(performance_factor=2.0, length=300)
        stock_prices[-1]['close'] = max(d.get('high', 0) for d in stock_prices) + 1 # Ensure new 52w high  

        mock_fetch_price.return_value = (stock_prices, 200)

        # 3. Index Data (for market context)
        mock_fetch_index.return_value = create_mock_index_data(trend='Bullish')
        
        # 4. Market Trends (for recovery check - not in recovery here)
        mock_fetch_trends.return_value = ([{'trend': 'Bullish'}] * 365, None)

        # 5. Peer Data (for industry leadership)
        mock_fetch_peers.return_value = ({'industry': 'Software - Infrastructure', 'peers': ['PEER1']}, None)
        
        # 6. Batch Financials (make sure our ticker is #1)
        # Use the helper to create complete, valid data structures.
        pass_ticker_financials = create_mock_financial_data(passing_data=True, ticker="PASS-TICKER")
        
        peer_financials = create_mock_financial_data(passing_data=False, ticker="PEER1", marketCap=5_000_000_000)
        # Manually adjust peer data to ensure the main ticker ranks higher
        peer_financials['annual_earnings'][0]['Revenue'] = 500
        peer_financials['annual_earnings'][0]['Earnings'] = 50
        peer_financials['annual_earnings'][0]['Net Income'] = 50

        batch_data = {
            "success": {
                "PASS-TICKER": pass_ticker_financials,
                "PEER1": peer_financials
            }
        }
        mock_fetch_batch.return_value = (batch_data, None)

        # --- Act ---
        response = self.app.get('/leadership/PASS-TICKER')
        data = response.json

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        
        # Create a dictionary of failed checks for easier debugging
        failed_checks = {k: v for k, v in data.get('details', {}).items() if isinstance(v, dict) and not v.get('pass')}
        
        self.assertTrue(data['passes'], f"Expected global 'passes' to be True. Failed checks: {json.dumps(failed_checks, indent=2)}")

    @patch('app.fetch_market_trends')
    @patch('app.fetch_index_data')
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_data_service_error_handling(self, mock_fetch_financials, mock_fetch_price, mock_fetch_index, mock_fetch_trends):
        """
        Integration Test: Service correctly handles upstream errors from data-service.
        """
        # Arrange: Mock a 500 server error from the fetcher
        mock_fetch_financials.return_value = (None, 500)
        mock_fetch_index.return_value = create_mock_index_data()
        mock_fetch_trends.return_value = ([{'trend': 'Bullish'}] * 365, None)
        mock_fetch_price.return_value = (create_mock_price_data(1.0)[0], 200)
        # Arrange: Mock a 404 not found error
        mock_fetch_financials.return_value = (None, 404)
        response_404 = self.app.get('/leadership/NOT-FOUND')
        self.assertEqual(response_404.status_code, 404)

    def test_path_traversal_attack(self):
        """
        Integration Test: Endpoint rejects invalid ticker formats.
        """
        response = self.app.get('/leadership/../../etc/passwd')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid ticker format', response.json['error'])

    # Integration test for the data fetcher's logic
    @patch('data_fetcher.session.post')
    @patch('data_fetcher.session.get')
    def test_fetch_market_trends_logic(self, mock_session_get, mock_session_post):
        existing_trends = [{'date': f'2025-08-2{i}', 'trend': 'Bullish'} for i in range(5)]
        mock_session_get.return_value = MagicMock(status_code=200, json=lambda: existing_trends)
        newly_calculated_trends = [{'date': f'2025-08-2{i}', 'trend': 'Neutral'} for i in range(5, 8)]
        mock_session_post.return_value = MagicMock(status_code=200, json=lambda: {'trends': newly_calculated_trends})
        
        with patch('data_fetcher.get_last_n_workdays') as mock_get_workdays:
            required_dates = [f'2025-08-2{i}' for i in range(8)]
            mock_get_workdays.return_value = required_dates
            final_trends, error = data_fetcher.fetch_market_trends()

        self.assertIsNone(error)
        self.assertEqual(len(final_trends), 8)
        mock_session_post.assert_called_once()
        sent_payload = mock_session_post.call_args[1]['json']
        self.assertEqual(sent_payload, {'dates': ['2025-08-25', '2025-08-26', '2025-08-27']})

    @patch('app.fetch_batch_price_data')
    @patch('app.fetch_batch_financials')
    @patch('app.fetch_market_trends')
    @patch('app.fetch_index_data')
    @patch('app._analyze_ticker_leadership')
    def test_leadership_batch_endpoint(self, mock_analyze, mock_fetch_index, mock_fetch_trends, mock_fetch_financials_batch, mock_fetch_price_batch):
        """
        Integration Test: Batch endpoint correctly processes lists and returns only passing candidates.
        """
        # --- Arrange ---
        # 1. Mock the analysis function's behavior
        def analyze_side_effect(ticker, **kwargs):
            if ticker == 'PASS1': return {'ticker': 'PASS1', 'passes': True, 'details': {}, 'industry': 'Tech'}
            if ticker == 'FAIL1': return {'ticker': 'FAIL1', 'passes': False, 'details': {}, 'industry': 'Retail'}
            if ticker == 'ERROR1': return {'error': 'Some error', 'status': 500}
            return {}
        mock_analyze.side_effect = analyze_side_effect
        
        # 2. Mock the batch data fetching functions
        mock_fetch_index.return_value = create_mock_index_data()
        mock_fetch_trends.return_value = ([{'trend': 'Bullish'}] * 365, None)
        
        # Ensure the mock data includes the 'ticker' field required by the contract
        mock_financials = {
            "success": {
                "PASS1": create_mock_financial_data(passing_data=True, ticker="PASS1"),
                "FAIL1": create_mock_financial_data(passing_data=False, ticker="FAIL1"),
                "ERROR1": create_mock_financial_data(passing_data=False, ticker="ERROR1")
            }
        }
        mock_prices = {
            "success": {
                "PASS1": create_mock_price_data(1.5)[0],
                "FAIL1": create_mock_price_data(0.8)[0],
                "ERROR1": create_mock_price_data(1.0)[0]
            }
        }
        mock_fetch_financials_batch.return_value = (mock_financials, None)
        mock_fetch_price_batch.return_value = (mock_prices, None)

        payload = {
            "tickers": ["PASS1", "FAIL1", "ERROR1", "INVALID/TICKER"]
        }

        # --- Act ---
        response = self.app.post('/leadership/batch', json=payload)
        data = response.json

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['metadata']['total_processed'], 4)
        self.assertEqual(data['metadata']['total_passed'], 1)
        self.assertEqual(len(data['passing_candidates']), 1)
        self.assertEqual(data['passing_candidates'][0]['ticker'], 'PASS1')

    @patch('app.fetch_market_trends')
    @patch('app.fetch_index_data')
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_leadership_endpoint_handles_data_contract_violation(self, mock_fetch_financials, mock_fetch_price, mock_fetch_index, mock_fetch_trends):
        """
        Consumer Test: Service correctly rejects payloads from data-service that violate the contract.
        """
        # --- Arrange ---
        # 1. Mock general data fetches to isolate the target error
        mock_fetch_index.return_value = create_mock_index_data()
        mock_fetch_trends.return_value = ([{'trend': 'Bullish'}] * 365, None)
        
        # 2. Mock valid price data to isolate the financial data failure
        mock_price, _ = create_mock_price_data(performance_factor=1.0)
        mock_fetch_price.return_value = (mock_price, 200)

        # 3. Mock financial data that is *missing* a required field ('quarterly_earnings')
        invalid_financials = create_mock_financial_data(passing_data=True)
        del invalid_financials['quarterly_earnings']  # This violates the CoreFinancials contract
        mock_fetch_financials.return_value = (invalid_financials, 200)
        
        # --- Act ---
        response = self.app.get('/leadership/INVALID-CONTRACT')
        data = response.json

        # --- Assert ---
        # The service should identify the contract violation and return a 502 Bad Gateway
        self.assertEqual(response.status_code, 502)
        self.assertIn('Invalid data structure', data['error'])

if __name__ == '__main__':
    unittest.main()