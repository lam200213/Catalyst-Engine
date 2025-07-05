# backend-services/analysis-service/tests/test_app.py
import unittest
import numpy as np
from unittest.mock import patch, MagicMock
import os
import sys
import requests # *** FIX: Import requests library ***

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (
    app,
    prepare_historical_data,
    calculate_sma_series,
    find_one_contraction,
    find_volatility_contraction_pattern
)

# --- Test Data  ---
def get_vcp_test_data():
    """Generates a predictable dataset known to contain VCPs."""
    prices = [100, 105, 102, 108, 104, 100, 103, 101, 98]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    historical_data = [{'formatted_date': d, 'close': p} for d, p in zip(dates, prices)]
    return historical_data, prices, dates

def get_flat_test_data():
    """Generates data with no volatility."""
    prices = [100] * 20
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    return prices, dates

def get_trend_test_data(up=True):
    """Generates data in a steady trend."""
    prices = [100 + i if up else 100 - i for i in range(20)]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    return prices, dates


# --- Test Cases ---

class TestHelperFunctions(unittest.TestCase):
    """
    Verify business logic and edge cases for helper functions.
    """
    def test_prepare_data_success(self):
        """Tests successful data preparation and sorting."""
        raw_data, original_prices, original_dates = get_vcp_test_data()
        unsorted_raw_data = raw_data[::-1]
        prices, dates, sorted_data = prepare_historical_data(unsorted_raw_data)
        
        self.assertEqual(prices, original_prices)
        self.assertEqual(dates, original_dates)
        self.assertEqual(sorted_data[0]['formatted_date'], '2024-01-01')

    def test_prepare_data_empty_and_none(self):
        """Tests that empty or None input is handled gracefully."""
        self.assertEqual(prepare_historical_data([]), ([], [], []))
        self.assertEqual(prepare_historical_data(None), ([], [], []))

    def test_calculate_sma_series_success(self):
        """Tests successful SMA calculation."""
        prices = [10, 20, 30, 40, 50]
        dates = [f"2024-01-0{i+1}" for i in range(5)]
        sma_series = calculate_sma_series(prices, dates, 3)
        
        self.assertEqual(len(sma_series), 3)
        self.assertAlmostEqual(sma_series[0]['value'], 20.0)
        self.assertEqual(sma_series[0]['time'], '2024-01-03')
        self.assertAlmostEqual(sma_series[-1]['value'], 40.0)
        self.assertEqual(sma_series[-1]['time'], '2024-01-05')

    def test_calculate_sma_series_insufficient_data(self):
        """Tests SMA calculation when data is insufficient."""
        prices = [10, 20]
        dates = ["2024-01-01", "2024-01-02"]
        sma_series = calculate_sma_series(prices, dates, 5)
        self.assertEqual(sma_series, [])


class TestVCPAlgorithm(unittest.TestCase):
    """
    Verify VCP algorithm logic, edge cases, and cover blind spots.
    """
    def test_find_one_contraction_success(self):
        """Tests that a single, clear contraction is found."""
        _, prices, _ = get_vcp_test_data()
        with patch('app.COUNTER_THRESHOLD', 2):
            contraction = find_one_contraction(prices, 0)
            self.assertIsNotNone(contraction)
            self.assertEqual(contraction, (3, 108, 8, 98))

    def test_vcp_with_no_contractions(self):
        """Tests that no contractions are found in steady trends or flat data."""
        up_prices, _ = get_trend_test_data(up=True)
        down_prices, _ = get_trend_test_data(up=False)
        flat_prices, _ = get_flat_test_data()
        
        self.assertEqual(find_volatility_contraction_pattern(up_prices), [])
        self.assertEqual(find_volatility_contraction_pattern(down_prices), [])
        self.assertEqual(find_volatility_contraction_pattern(flat_prices), [])

class TestAnalysisEndpoint(unittest.TestCase):
    """
    Full endpoint testing, including logic, edges, security, consistency, and outcomes.
    """
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_analyze_success_path(self, mock_get):
        """1. Business Logic: Test the ideal end-to-end flow."""
        raw_data, _, _ = get_vcp_test_data()
        mock_get.return_value = MagicMock(status_code=200, json=lambda: raw_data)

        response = self.app.get('/analyze/AAPL')
        json_data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['ticker'], 'AAPL')
        self.assertIn('analysis', json_data)

    @patch('app.requests.get')
    def test_analyze_data_service_404(self, mock_get):
        """2. Edge Case: Downstream service cannot find the ticker."""
        mock_get.return_value = MagicMock(status_code=404, json=lambda: {'error': 'Ticker not found'})
        
        response = self.app.get('/analyze/FAKETICKER')
        
        self.assertEqual(response.status_code, 502)
        #  Check for the correct, specific error message from the app logic
        self.assertIn('Invalid or non-existent ticker: FAKETICKER', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_data_service_503(self, mock_get):
        """2. Edge Case: Downstream service is unavailable."""
        # Implement the test to check for a 503 response 
        mock_get.side_effect = requests.exceptions.ConnectionError("Service unavailable")
        response = self.app.get('/analyze/ANYTICKER')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Service unavailable', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_with_empty_price_data(self, mock_get):
        """2. Edge Case: Ticker is valid but has no historical data."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        
        response = self.app.get('/analyze/NEWTICKER')
        
        self.assertEqual(response.status_code, 404)
        self.assertIn('No price data available', response.get_json()['error'])
    
    @patch('app.requests.get')
    def test_security_ticker_input(self, mock_get):
        """3. Security: Ensure malformed ticker does not crash the app."""
        mock_get.return_value = MagicMock(status_code=404, json=lambda: {'error': 'Invalid format'})
        
        response = self.app.get('/analyze/INVALIDSYMBOL')
        
        self.assertEqual(response.status_code, 502)
        self.assertIn('Invalid or non-existent ticker', response.get_json()['error'])

if __name__ == '__main__':
    unittest.main()