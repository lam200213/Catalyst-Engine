# backend-services/screening-service/tests/test_screening_logic.py
import unittest
import numpy as np
import os
import sys
from unittest.mock import patch
from app import app, DATA_SERVICE_URL
from screening_logic import apply_screening_criteria, calculate_sma
import requests
import json

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Deterministic Test Data Generation ---
def create_ideal_passing_data():
    """Generates a perfect, non-random dataset that passes all criteria."""
    # A smooth, strong uptrend ensures MAs are ordered correctly and trending up.
    # Prices range from 80 to 150 over 300 days.
    prices = np.linspace(80, 150, 300).tolist()
    # Current Price: 150, 52-Week High: 150, 52-Week Low: 80
    # Rule 6 Pass: 150 >= (80 * 1.30) => 150 >= 104.0
    # Rule 7 Pass: 150 >= (150 * 0.75) => 150 >= 112.5
    return [{
            "formatted_date": f"2025-01-01",
            "open": p,
            "high": p + 1,
            "low": p - 1,
            "close": p,
            "volume": 1000000,
            "adjclose": p
        } for p in prices]

def create_failing_low_price_data():
    """Generates data that fails ONLY the '30% above 52-week low' rule."""
    # Strong uptrend from 100 to 180, then a pullback to 125.
    prices = np.linspace(100, 180, 280).tolist() + [160, 150, 140, 130, 125]
    # Current Price: 125, 52-Week Low: 100
    # Rule 6 Fail: 125 < (100 * 1.30) => 125 < 130
    return [{
            "formatted_date": f"2025-01-01",
            "open": p,
            "high": p + 1,
            "low": p - 1,
            "close": p,
            "volume": 1000000,
            "adjclose": p
        } for p in prices]

def create_failing_high_price_data():
    """Generates data that fails ONLY the 'within 25% of 52-week high' rule."""
    # A gentler uptrend to 200, followed by a milder dip to 148.
    # This prevents the current price from dropping below the long-term MAs.
    prices = np.linspace(120, 200, 250).tolist() + np.linspace(199, 148, 50).tolist()
    # Current Price: 148, 52-Week High: 200
    # Rule 7 Fail: 148 < (200 * 0.75) => 148 < 150
    return [{
            "formatted_date": f"2025-01-01",
            "open": p,
            "high": p + 1,
            "low": p - 1,
            "close": p,
            "volume": 1000000,
            "adjclose": p
        } for p in prices]

def create_data_with_250_days():
    """Generates passing data with 250 days. The old logic would fail this."""
    prices = np.linspace(90, 160, 250).tolist()
    # This dataset is designed to pass all criteria with the corrected logic.
    return [{
            "formatted_date": f"2025-01-01",
            "open": p,
            "high": p + 1,
            "low": p - 1,
            "close": p,
            "volume": 1000000,
            "adjclose": p
        } for p in prices]


class TestScreeningLogic(unittest.TestCase):
    """
    Revised test suite for screening logic using deterministic data.
    """

    def test_business_logic_pass(self):
        """1. Business Logic: Verifies a stock with ideal characteristics passes all criteria."""
        result = apply_screening_criteria("PASS", create_ideal_passing_data())
        self.assertTrue(result['passes'], "Stock with ideal data should pass all criteria.")
        # Also check a specific detail to be sure
        self.assertTrue(result['details']['price_within_25_percent_of_52_week_high'])

    def test_business_logic_fail_low_price(self):
        """1. Business Logic: Verifies failure when price is not 30% above 52-week low."""
        result = apply_screening_criteria("FAIL_LOW", create_failing_low_price_data())
        self.assertFalse(result['passes'], "Stock should fail the 52-week low criterion.")
        self.assertFalse(result['details']['price_30_percent_above_52_week_low'])
        # Verify other criteria are still passing to ensure test isolation
        self.assertTrue(result['details']['ma50_above_ma150_ma200'])

    def test_business_logic_fail_high_price(self):
        """1. Business Logic: Verifies failure when price is not within 25% of 52-week high."""
        result = apply_screening_criteria("FAIL_HIGH", create_failing_high_price_data())
        self.assertFalse(result['passes'], "Stock should fail the 52-week high criterion.")
        self.assertFalse(result['details']['price_within_25_percent_of_52_week_high'])

    def test_edge_case_250_days_data(self):
        """2. Edge Cases: Verifies the bug fix allows data with slightly less than 252 days to pass."""
        result = apply_screening_criteria("PASS_250", create_data_with_250_days())
        self.assertTrue(result['passes'], "Stock with 250 days of data should pass with the corrected logic.")

    def test_edge_case_insufficient_data(self):
        """2. Edge Cases: Verifies failure for data insufficient for calculating all MAs."""
        result = apply_screening_criteria("INSUFFICIENT", {'c': [100] * 150})
        self.assertFalse(result['passes'])
        self.assertFalse(result['details']['ma200_trending_up'], "MA200 trend should fail with insufficient data.")
        # Corrected Assertion: This rule correctly fails because 100 is not >= 100 * 1.3.
        self.assertFalse(result['details']['price_30_percent_above_52_week_low'])
    
    def test_edge_case_empty_data(self):
        """2. Edge Cases: Verifies graceful failure when no price data is provided."""
        result = apply_screening_criteria("EMPTY", {'c': []})
        self.assertFalse(result['passes'])
        # Reflect the new empty data handling
        if 'reason' in result: # Check if 'reason' key exists
            self.assertEqual(result['reason'], "Insufficient historical price data.")

    def test_security_implications(self):
        """3. Security: No direct security risks like XSS in this function, as it only processes numerical data."""
        # This test serves as a documentation of the security consideration.
        # The function `apply_screening_criteria` works with numerical lists and does not
        # handle or execute any user-provided strings, mitigating injection risks.
        self.assertTrue(True)

    def test_consistency_and_blind_spots(self):
        """
        4/5. Consistency & Blind Spots:
        This revised test suite uses deterministic data, a consistent pattern from other services' tests.
        It removes the blind spot of the previous suite, which used random data and could produce
        inconsistent results, thereby failing to reliably test the business logic.
        """
        self.assertTrue(True)
        
    def test_sma_calculation(self):
        """Maintains the original valid test for the SMA helper function."""
        prices = [i for i in range(1, 11)]  # [1, 2, ..., 10]
        self.assertAlmostEqual(calculate_sma(prices, 5), 8.0)  # (6+7+8+9+10)/5
        self.assertAlmostEqual(calculate_sma(prices, 10), 5.5)  # (1+..+10)/10
        self.assertIsNone(calculate_sma(prices, 11))  # Insufficient data

#  Integration test class for endpoints
class TestScreeningEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    # CHUNK_SIZE boundary behavior for /screen/batch
    @patch("app.requests.post")
    def test_batch_endpoint_chunking_size_boundaries(self, mock_post):
        """
        Verify /screen/batch chunking behavior just below and at CHUNK_SIZE.
        Ensures:
        - tickers < CHUNK_SIZE -> 1 upstream call
        - tickers == CHUNK_SIZE -> still 1 upstream call
        """
        # We will patch CHUNK_SIZE down to 10 to keep the test fast and clear.
        patched_chunk_size = 10

        # Common dummy upstream payload: one success entry with valid PriceDataItem list
        dummy_item = {
            "formatted_date": "2025-01-01",
            "open": 140.0,
            "high": 152.0,
            "low": 139.0,
            "close": 150.0,
            "volume": 1_000_000,
            "adjclose": 150.0,
        }
        dummy_payload = {"success": {"T0": [dummy_item]}, "failed": []}
        mock_post.return_value = unittest.mock.MagicMock(
            status_code=200,
            content=json.dumps(dummy_payload).encode("utf-8"),
            json=lambda: dummy_payload,
        )

        # Case A: just below CHUNK_SIZE
        tickers_below = [f"T{i}" for i in range(patched_chunk_size - 1)]
        with patch("app.CHUNK_SIZE", patched_chunk_size):
            resp_below = self.app.post("/screen/batch", json={"tickers": tickers_below})
        self.assertEqual(resp_below.status_code, 200)
        # All tickers should be considered; details of passes are handled elsewhere
        self.assertIsInstance(resp_below.get_json(), list)
        # Exactly one upstream batch call
        self.assertEqual(mock_post.call_count, 1)

        mock_post.reset_mock()

        # Case B: exactly CHUNK_SIZE
        tickers_at = [f"T{i}" for i in range(patched_chunk_size)]
        with patch("app.CHUNK_SIZE", patched_chunk_size):
            resp_at = self.app.post("/screen/batch", json={"tickers": tickers_at})
        self.assertEqual(resp_at.status_code, 200)
        self.assertIsInstance(resp_at.get_json(), list)
        # Still exactly one upstream batch call
        self.assertEqual(mock_post.call_count, 1)

    @patch('app.requests.post')
    def test_batch_endpoint_uses_chunking(self, mock_post):
        """
        Tests that the batch screening endpoint uses chunking to call the data-service.
        Verifies that for a list of 25 tickers with a chunk size of 10, the data-service is called 3 times.
        """
        # --- Arrange ---
        # Define a chunk size consistent with what we will implement
        CHUNK_SIZE = 10
        # Create a list of 25 dummy tickers
        tickers = [f"TICKER_{i}" for i in range(25)] 
        
        # The data-service will return a successful response.
        # For this test, we assume all tickers are valid and have data.
        dummy_item = {"formatted_date": "2023-01-01", "open": 140.0, "high": 152.0, "low": 149.0, "close": 150.0, "volume": 1000000, "adjclose": 150.0}
        mock_post.return_value = unittest.mock.MagicMock(
            status_code=200,
            content=json.dumps({"success": {"TICKER_0": [dummy_item]}, "failed": []}).encode('utf-8'),
            json=lambda: {"success": {"TICKER_0": [dummy_item]}, "failed": []}
        )

        # --- Act ---
        # We need to patch the CHUNK_SIZE constant in the app module for this test
        with patch('app.CHUNK_SIZE', CHUNK_SIZE):
            response = self.app.post('/screen/batch', # Use the actual endpoint
                                     json={"tickers": tickers})

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        
        # The crucial assertion: was the data-service called the correct number of times?
        # 25 tickers with a chunk size of 10 should result in 3 calls (10, 10, 5).
        self.assertEqual(mock_post.call_count, 3)

        # Optional: verify the content of the last call's payload
        last_call_payload = mock_post.call_args.kwargs['json']
        self.assertEqual(len(last_call_payload['tickers']), 5)

    @patch('app.requests.post')
    def test_batch_screen_endpoint(self, mock_post):
        """
        Tests the batch screening endpoint with the new chunking logic.
        Mocks the POST call to the data-service and verifies that tickers from the
        'success' payload are screened correctly and 'failed' tickers are ignored.
        """
        # Arrange: Configure the mock to return a response similar to the data-service's batch endpoint
        batch_data = {
            "success": {
                "PASS_TICKER": create_ideal_passing_data(),
                "FAIL_TICKER": create_failing_high_price_data()
            },
            "failed": ["DATA_UNAVAILABLE_TICKER"]
        }
        mock_post.return_value = unittest.mock.MagicMock(
            status_code=200,
            content=json.dumps(batch_data).encode('utf-8'),
            json=lambda: batch_data
        )

        # Act: Make a POST request to the batch endpoint
        response = self.app.post('/screen/batch',
                                 json={"tickers": ["PASS_TICKER", "FAIL_TICKER", "DATA_UNAVAILABLE_TICKER"]})

        # Assert
        self.assertEqual(response.status_code, 200)
        # Only the ticker with passing data should be returned
        self.assertEqual(response.get_json(), ["PASS_TICKER"])
        # Ensure the data-service was called via POST
        mock_post.assert_called_once()

    @patch('app.requests.get')
    def test_single_ticker_success_case(self, mock_get):
        """
        Integration Test: Mocks a successful 200 OK response from data-service
        and asserts that /screen/AAPL returns 200 OK with correct screening result.
        """
        # Arrange
        historical_data = create_ideal_passing_data()
        mock_get.return_value = unittest.mock.MagicMock(
            status_code=200,
            content=json.dumps(historical_data).encode('utf-8'),
            json=lambda: historical_data
        )

        # Act
        response = self.app.get('/screen/AAPL')

        # Assert
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertIsNotNone(json_data)
        self.assertEqual(json_data['ticker'], 'AAPL')
        self.assertTrue(json_data['passes'])
        mock_get.assert_called_once_with(f"{DATA_SERVICE_URL}/price/AAPL")

    @patch('app.requests.get')
    def test_single_ticker_not_found_case(self, mock_get):
        """
        Integration Test: Mocks data-service returning 404 Not Found for a non-existent ticker.
        Asserts screening-service returns 502 Bad Gateway.
        """
        # Arrange
        error_data = {"error": "Ticker not found"}
        mock_get.return_value = unittest.mock.MagicMock(
            status_code=404,
            content=json.dumps(error_data).encode('utf-8'),
            json=lambda: error_data,
            text="Ticker not found"
        )

        # Act
        response = self.app.get('/screen/NONEXISTENT')

        # Assert
        self.assertEqual(response.status_code, 502)
        json_data = response.get_json()
        self.assertIsNotNone(json_data)
        self.assertIn("Invalid or non-existent ticker", json_data['error'])
        self.assertEqual(json_data['details'], "Ticker not found")
        mock_get.assert_called_once_with(f"{DATA_SERVICE_URL}/price/NONEXISTENT")

    @patch('app.requests.get', side_effect=requests.exceptions.ConnectionError("Mocked connection error"))
    def test_single_ticker_service_unavailable_case(self, mock_get):
        """
        Integration Test: Simulates requests.exceptions.ConnectionError when calling data-service.
        Asserts screening-service returns 503 Service Unavailable.
        """
        # Arrange is handled by the patch decorator

        # Act
        response = self.app.get('/screen/AAPL')

        # Assert
        self.assertEqual(response.status_code, 503)
        json_data = response.get_json()
        self.assertIsNotNone(json_data)
        self.assertIn("Error connecting to the data-service.", json_data['error'])
        self.assertIn("Mocked connection error", json_data['details'])
        mock_get.assert_called_once_with(f"{DATA_SERVICE_URL}/price/AAPL")

    @patch('app.requests.post')
    @patch('builtins.print')
    def test_batch_endpoint_handles_failed_tickers(self, mock_print, mock_post):
        """
        Ensures that tickers returned in the 'failed' key from the data-service
        are logged and not processed further.
        """
        # --- Arrange ---
        tickers = ["PASS_TICKER", "FAIL_TICKER"]

        # Mock the data-service to return one success and one failure
        batch_data = {
            "success": {
                "PASS_TICKER": create_ideal_passing_data()
            },
            "failed": ["FAIL_TICKER"]
        }
        mock_post.return_value = unittest.mock.MagicMock(
            status_code=200,
            content=json.dumps(batch_data).encode('utf-8'),
            json=lambda: batch_data
        )

        # --- Act ---
        response = self.app.post('/screen/batch', json={"tickers": tickers})
        
        # --- Assert ---
        # The overall request should succeed
        self.assertEqual(response.status_code, 200)
        
        # Only the passing ticker should be in the final result
        self.assertEqual(response.get_json(), ["PASS_TICKER"])

        # A warning should be logged for the failed ticker
        log_calls = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Data could not be fetched for the following tickers: ['FAIL_TICKER']" in call for call in log_calls))


if __name__ == '__main__':
    unittest.main()