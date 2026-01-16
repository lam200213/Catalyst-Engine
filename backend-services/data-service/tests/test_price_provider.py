# backend-services/data-service/tests/test_price_provider.py
import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
import os
import sys
from curl_cffi.requests import errors as cffi_errors
from concurrent.futures import ThreadPoolExecutor

# Add the project root to the path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import price_provider
from .test_fixtures import make_chart_payload

class TestYFinancePriceProvider(unittest.TestCase):
    """Tests for the yfinance price data provider."""

    def setUp(self):
        """Set up a ThreadPoolExecutor for tests."""
        self.executor = ThreadPoolExecutor(max_workers=1)

    def tearDown(self):
        """Shutdown the ThreadPoolExecutor."""
        self.executor.shutdown(wait=True)

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    @patch('providers.yfin.price_provider.is_ticker_delisted', return_value=True)
    def test_get_stock_data_skips_single_delisted_ticker(self, mock_is_delisted, mock_fetch):
        """
        Tests that get_stock_data (single mode) skips API calls for a delisted ticker.
        """
        # --- Act ---
        result = price_provider.get_stock_data('DELISTED', self.executor, period="1y")

        # --- Assert ---
        self.assertIsNone(result)
        mock_is_delisted.assert_called_once_with('DELISTED')
        mock_fetch.assert_not_called()

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    @patch('providers.yfin.price_provider.is_ticker_delisted')
    def test_get_stock_data_filters_delisted_in_batch(self, mock_is_delisted, mock_fetch):
        """
        Tests that get_stock_data (batch mode) filters out delisted tickers.
        """
        # --- Arrange ---
        # Mock is_ticker_delisted to return True only for 'BADD'
        mock_is_delisted.side_effect = lambda ticker: ticker == 'BADD'
        # Mock the actual fetcher to return simple data
        mock_fetch.return_value = [{"close": 100}]

        # --- Act ---
        results = price_provider.get_stock_data(['GOOD1', 'BADD', 'GOOD2'], self.executor, period="1y")

        # --- Assert ---
        # Check that the delisted check was called for all tickers
        self.assertEqual(mock_is_delisted.call_count, 3)
        
        # Check that the API fetch was only called for the good tickers
        self.assertEqual(mock_fetch.call_count, 2)
        
        # Verify the final result dictionary does not contain the delisted ticker
        self.assertIn('GOOD1', results)
        self.assertIn('GOOD2', results)
        self.assertNotIn('BADD', results)


    def _get_mock_yahoo_response(self):
        return {
            'chart': {
                'result': [{
                    'timestamp': [1672531200, 1672617600],
                    'indicators': {
                        'quote': [{'open': [100, 102], 'high': [105, 106], 'low': [99, 101], 'close': [102, 105], 'volume': [10000, 12000]}],
                        'adjclose': [{'adjclose': [101, 104]}]
                    }
                }]
            }
        }

    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_get_single_ticker_data_success(self, mock_execute_request):
        """Tests a successful fetch and transformation for a single ticker."""
        # --- Arrange ---
        mock_execute_request.return_value = self._get_mock_yahoo_response()

        # --- Act ---
        data = price_provider._get_single_ticker_data('AAPL', period="1y")

        # --- Assert ---
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['formatted_date'], '2023-01-01')
        self.assertEqual(data[0]['close'], 102)
        self.assertEqual(data[1]['volume'], 12000)

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_get_single_ticker_data_api_404(self, mock_execute_request, mock_mark_delisted):
        """Tests that a 404 response correctly marks the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=404)
        mock_execute_request.side_effect = cffi_errors.RequestsError("404 Error", response=mock_response)

        # --- Act ---
        result = price_provider._get_single_ticker_data('DELISTED', period="1y")

        # --- Assert ---
        self.assertIsNone(result) # The function should return None on failure
        mock_mark_delisted.assert_called_once_with('DELISTED', "Yahoo Finance API call failed with status 404 for chart data.")

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_provider_does_not_mark_delisted_on_other_http_errors(self, mock_execute_request, mock_mark_delisted):
        """Tests that a non-404 HTTP error does NOT mark the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=500)
        mock_execute_request.side_effect = cffi_errors.RequestsError("500 Server Error", response=mock_response)

        # --- Act ---
        data = price_provider._get_single_ticker_data('SERVERERROR', period="1y")

        # --- Assert ---
        self.assertIsNone(data)
        mock_mark_delisted.assert_not_called()
            
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_ticker_sanitization(self, mock_execute_request):
        """Tests that ticker symbols are correctly sanitized."""
        # --- Arrange ---
        mock_execute_request.return_value = self._get_mock_yahoo_response()
        dirty_ticker = 'BRK/A  '
        expected_sanitized_ticker = 'BRK-A'

        # --- Act ---
        price_provider._get_single_ticker_data(dirty_ticker, period="1y")

        # --- Assert ---
        mock_execute_request.assert_called_once()
        request_url = mock_execute_request.call_args[0][0]
        self.assertIn(expected_sanitized_ticker, request_url)
        self.assertNotIn(dirty_ticker, request_url)

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    def test_get_stock_data_batch_with_failures(self, mock_get_single):
        """Tests the batch function with a mix of successful and failed tickers."""
        # --- Arrange ---
        def side_effect(ticker, start_date=None, period=None, interval="1d"): # Correct signature
            if ticker == 'AAPL':
                return [{"close": 150}]
            elif ticker == 'FAIL':
                # The function is expected to handle its own exceptions and return None on failure
                raise Exception("API failure")
            return None
        mock_get_single.side_effect = side_effect

        # --- Act ---
        results = price_provider.get_stock_data(['AAPL', 'FAIL', 'NONE'], self.executor, period="1y")

        # --- Assert ---
        self.assertIn('AAPL', results)
        self.assertEqual(results['AAPL'], [{"close": 150}])
        self.assertIn('FAIL', results)
        self.assertIsNone(results['FAIL'])
        self.assertIn('NONE', results)
        self.assertIsNone(results['NONE'])

    def test_transform_yahoo_response_missing_timestamp_returns_none(self):
        """
        Week 9 Plan 1: chart.result[0].timestamp may be missing for delisted/stale tickers.
        Expected: transform returns None (no exception).
        """
        bad = make_chart_payload(include_timestamp=False)
        out = price_provider._transform_yahoo_response(bad, "NOTS")
        self.assertIsNone(out)

    @patch("providers.yfin.price_provider.yahoo_client.execute_request")
    def test_get_single_ticker_data_missing_timestamp_returns_none(self, mock_execute_request):
        """
        Week 9 Plan 1: _get_single_ticker_data should not crash on missing timestamp.
        Expected: returns None, does not mark delisted (not a 404).
        """
        mock_execute_request.return_value = make_chart_payload(include_timestamp=False)
        out = price_provider._get_single_ticker_data("NOTS", period="1y")
        self.assertIsNone(out)

    def test_transform_yahoo_response_missing_result_returns_none(self):
        bad = {"chart": {"result": []}}
        out = price_provider._transform_yahoo_response(bad, "EMPTY")
        self.assertIsNone(out)
