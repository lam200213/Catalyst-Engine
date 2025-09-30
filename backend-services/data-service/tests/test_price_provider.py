# backend-services/data-service/tests/test_price_provider.py
import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
import os
import sys
from curl_cffi.requests import errors as cffi_errors

# Add the project root to the path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import price_provider

class TestYFinancePriceProvider(unittest.TestCase):
    """Tests for the yfinance price data provider."""

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    @patch('providers.yfin.price_provider.is_ticker_delisted', return_value=True)
    def test_get_stock_data_skips_single_delisted_ticker(self, mock_is_delisted, mock_fetch):
        """
        Tests that get_stock_data (single mode) skips API calls for a delisted ticker.
        """
        # --- Act ---
        result = price_provider.get_stock_data('DELISTED', period="1y")

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
        results = price_provider.get_stock_data(['GOOD1', 'BADD', 'GOOD2'], period="1y")

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

    @patch('providers.yfin.price_provider.yahoo_client.session.get')
    @patch('providers.yfin.price_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_get_single_ticker_data_success(self, mock_get_auth, mock_session_get):
        """Tests a successful fetch and transformation for a single ticker."""
        # --- Arrange ---
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._get_mock_yahoo_response()
        mock_session_get.return_value = mock_response

        # --- Act ---
        data = price_provider._get_single_ticker_data('AAPL', period="1y")

        # --- Assert ---
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['formatted_date'], '2023-01-01')
        self.assertEqual(data[0]['close'], 102)
        self.assertEqual(data[1]['volume'], 12000)

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.session.get')
    @patch('providers.yfin.price_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_get_single_ticker_data_api_404(self, mock_get_auth, mock_session_get, mock_mark_delisted):
        """Tests that a 404 response correctly marks the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=404)
        mock_session_get.side_effect = cffi_errors.RequestsError("404 Error", response=mock_response)

        # --- Act ---
        data = price_provider._get_single_ticker_data('DELISTED', period="1y")

        # --- Assert ---
        self.assertIsNone(data)
        mock_mark_delisted.assert_called_once_with('DELISTED', "Yahoo Finance price API call failed with status 404.")

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.session.get')
    @patch('providers.yfin.price_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_provider_does_not_mark_delisted_on_other_http_errors(self, mock_get_auth, mock_session_get, mock_mark_delisted):
        """Tests that a non-404 HTTP error does NOT mark the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=500)
        mock_session_get.side_effect = cffi_errors.RequestsError("500 Server Error", response=mock_response)

        # --- Act ---
        data = price_provider._get_single_ticker_data('SERVERERROR', period="1y")

        # --- Assert ---
        self.assertIsNone(data)
        mock_mark_delisted.assert_not_called()

    def test_get_single_ticker_data_missing_args(self):
        """Tests that a ValueError is raised if neither start_date nor period is provided."""
        with self.assertRaises(ValueError):
            price_provider._get_single_ticker_data('AAPL', start_date=None, period=None)
            
    @patch('providers.yfin.price_provider.yahoo_client.session.get')
    @patch('providers.yfin.price_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_ticker_sanitization(self, mock_get_auth, mock_session_get):
        """Tests that ticker symbols are correctly sanitized."""
        # --- Arrange ---
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._get_mock_yahoo_response()
        mock_session_get.return_value = mock_response

        dirty_ticker = 'BRK/A  '
        expected_sanitized_ticker = 'BRK-A'

        # --- Act ---
        price_provider._get_single_ticker_data(dirty_ticker, period="1y")

        # --- Assert ---
        mock_session_get.assert_called_once()
        request_url = mock_session_get.call_args[0][0]
        self.assertIn(expected_sanitized_ticker, request_url)
        self.assertNotIn(dirty_ticker, request_url)

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    def test_get_stock_data_batch_with_failures(self, mock_get_single):
        """Tests the batch function with a mix of successful and failed tickers."""
        # --- Arrange ---
        def side_effect(ticker, start_date, period):
            if ticker == 'AAPL':
                return [{"close": 150}]
            elif ticker == 'FAIL':
                raise Exception("API failure")
            return None
        mock_get_single.side_effect = side_effect

        # --- Act ---
        results = price_provider.get_stock_data(['AAPL', 'FAIL', 'NONE'], period="1y")

        # --- Assert ---
        self.assertIn('AAPL', results)
        self.assertEqual(results['AAPL'], [{"close": 150}])
        self.assertIn('FAIL', results)
        self.assertIsNone(results['FAIL'])
        self.assertIn('NONE', results)
        self.assertIsNone(results['NONE'])