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

    @patch('app.fetch_batch_financials')
    @patch('app.fetch_peer_data')
    @patch('app.fetch_general_data_for_analysis')
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_leadership_endpoint_pass_scenario(self, mock_fetch_financials, mock_fetch_price, mock_fetch_general, mock_fetch_peers, mock_fetch_batch):
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
        stock_prices, _ = create_mock_price_data(performance_factor=2.0, length=300)
        stock_prices[-1]['close'] = max(d.get('high', 0) for d in stock_prices) + 1 # Ensure new 52w high  

        mock_fetch_price.return_value = (stock_prices, 200)

        # 3. Index Data (for market context)
        mock_fetch_general.return_value = (create_mock_index_data(trend='Bullish'), [{'trend': 'Bullish'}] * 365)

        # 4. Peer Data (for industry leadership)
        mock_fetch_peers.return_value = ({'industry': 'Software - Infrastructure', 'peers': ['PEER1']}, None)
        
        # 5. Batch Financials (make sure our ticker is #1)
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

    @patch('app.fetch_general_data_for_analysis') # Patched the correct higher-level function
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_data_service_error_handling(self, mock_fetch_financials, mock_fetch_price, mock_fetch_general):
        """
        Integration Test: Service correctly handles upstream errors from data-service.
        """
        # --- Test 500 Error ---
        # Arrange: Mock general and price data to return successfully
        mock_fetch_general.return_value = (create_mock_index_data(), [{'trend': 'Bullish'}] * 365)
        mock_fetch_price.return_value = (create_mock_price_data(1.0)[0], 200)
        # Arrange: Mock a 500 server error for financial data
        mock_fetch_financials.return_value = (None, 500)
        
        # Act
        response_500 = self.app.get('/leadership/ANY-TICKER')
        
        # Assert
        self.assertEqual(response_500.status_code, 500)
        self.assertIn('Failed to fetch financial data', response_500.json['error'])

        # --- Test 404 Error ---
        # Arrange: Mock a 404 not found error
        mock_fetch_financials.return_value = (None, 404)
        
        # Act
        response_404 = self.app.get('/leadership/NOT-FOUND')
        
        # Assert
        self.assertEqual(response_404.status_code, 404)
        self.assertIn('Failed to fetch financial data', response_404.json['error'])


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
    @patch('app.fetch_general_data_for_analysis') # Patched the correct higher-level function
    @patch('app.analyze_ticker_leadership')       # Patched the correct function name
    def test_leadership_batch_endpoint(self, mock_analyze, mock_fetch_general, mock_fetch_financials_batch, mock_fetch_price_batch):
        """
        Integration Test: Batch endpoint correctly processes lists and returns only passing candidates.
        """
        # --- Arrange ---
        # 1. Mock the analysis function's behavior
        def analyze_side_effect(ticker, **kwargs):
            # This mock now returns the required fields for the LeadershipProfileForBatch contract
            pass_return = {
                'ticker': 'PASS1', 'passes': True, 'details': {}, 'industry': 'Tech',
                'leadership_summary': {'qualified_profiles': ['Explosive Grower'], 'message': '...'},
                'profile_details': {'explosive_grower': {'pass': True, 'passed_checks': 4, 'total_checks': 4}}
            }
            fail_return = {
                'ticker': 'FAIL1', 'passes': False, 'details': {}, 'industry': 'Retail',
                'leadership_summary': {'qualified_profiles': [], 'message': '...'},
                'profile_details': {}
            }
            if ticker == 'PASS1': return pass_return
            if ticker == 'FAIL1': return fail_return
            if ticker == 'ERROR1': return {'error': 'Some error', 'status': 500}
            return {}
        mock_analyze.side_effect = analyze_side_effect
        
        # 2. Mock the batch data fetching functions
        mock_fetch_general.return_value = (create_mock_index_data(), [{'trend': 'Bullish'}] * 365)
        
        # Ensure the mock data includes the 'ticker' field required by the contract
        mock_financials = {
            "success": {
                "PASS1": create_mock_financial_data(ticker="PASS1"),
                "FAIL1": create_mock_financial_data(ticker="FAIL1"),
                "ERROR1": create_mock_financial_data(ticker="ERROR1")
            }
        }
        mock_prices, _ = create_mock_price_data(1.0) # Generate some valid price data
        mock_prices_batch = {
            "success": {
                "PASS1": mock_prices,
                "FAIL1": mock_prices,
                "ERROR1": mock_prices,
            }
        }
        mock_fetch_financials_batch.return_value = (mock_financials, None)
        mock_fetch_price_batch.return_value = (mock_prices_batch, None)

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

    @patch('app.fetch_general_data_for_analysis') # Patched the correct higher-level function
    @patch('app.fetch_price_data')
    @patch('app.fetch_financial_data')
    def test_leadership_endpoint_handles_data_contract_violation(self, mock_fetch_financials, mock_fetch_price, mock_fetch_general):
        """
        Consumer Test: Service correctly rejects payloads from data-service that violate the contract.
        """
        # --- Arrange ---
        # 1. Mock general data fetches to isolate the target error
        mock_fetch_general.return_value = (create_mock_index_data(), [{'trend': 'Bullish'}] * 365)
        
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