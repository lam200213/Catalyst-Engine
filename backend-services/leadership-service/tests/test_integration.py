# backend-services/leadership-service/tests/test_integration.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

# --- Mock Data Generation ---
# Using helpers from the logic test file for consistency
from tests.test_leadership_logic import (
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
        pass_financials = create_mock_financial_data(ipoDate='2022-01-01') # Recent IPO
        mock_fetch_financials.return_value = (pass_financials, 200)

        # 2. Price Data (for rally check and market impact)
        stock_prices, sp500_prices = create_mock_price_data(performance_factor=2.0, length=300)
        stock_prices[-1]['close'] = max(d.get('high', 0) for d in stock_prices) + 1 # Ensure new 52w high
        def price_side_effect(ticker):
            if ticker == 'PASS-TICKER': return stock_prices
            if ticker == '^GSPC': return sp500_prices
            return None
        mock_fetch_price.side_effect = price_side_effect

        # 3. Index Data (for market context)
        mock_fetch_index.return_value = create_mock_index_data(trend='Bullish')
        
        # 4. Market Trends (for recovery check - not in recovery here)
        mock_fetch_trends.return_value = ([{'status': 'Bullish'}] * 5, None)

        # 5. Peer Data (for industry leadership)
        mock_fetch_peers.return_value = ({"peers": ["PEER1"]}, None)
        
        # 6. Batch Financials (make sure our ticker is #1)
        batch_data = {
            "success": {
                "PASS-TICKER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
                "PEER1": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000}
            }
        }
        mock_fetch_batch.return_value = (batch_data, None)

        # --- Act ---
        response = self.app.get('/leadership/PASS-TICKER')
        data = response.json

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['passes'], f"Expected passes to be True. Details: {json.dumps(data.get('details'), indent=2)}")
        self.assertTrue(data['details']['is_industry_leader']['pass'])
        self.assertTrue(data['details']['market_trend_impact']['sub_results']['new_52_week_high']['pass'])

    @patch('app.fetch_financial_data')
    def test_data_service_error_handling(self, mock_fetch_financials):
        """
        Integration Test: Service correctly handles upstream errors from data-service.
        """
        # Arrange: Mock a 500 server error from the fetcher
        mock_fetch_financials.return_value = (None, 500)
        response = self.app.get('/leadership/ERROR-TICKER')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Failed to fetch financial data', response.json['error'])

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

    @patch('app._analyze_ticker_leadership')
    def test_leadership_batch_endpoint(self, mock_analyze):
        """
        Integration Test: Batch endpoint correctly processes lists and returns only passing candidates.
        """
        # --- Arrange ---
        def analyze_side_effect(ticker):
            if ticker == 'PASS1': return {'ticker': 'PASS1', 'passes': True, 'details': {}}
            if ticker == 'FAIL1': return {'ticker': 'FAIL1', 'passes': False, 'details': {}}
            if ticker == 'ERROR1': return {'error': 'Some error', 'status': 500}
            return {}
        mock_analyze.side_effect = analyze_side_effect
        
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

    def test_leadership_batch_invalid_payload(self):
        """
        Integration Test: Batch endpoint handles bad requests.
        """
        response = self.app.post('/leadership/batch', json={"wrong_key": []})
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()