# backend-services/data-service/tests/test_financials_provider.py
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import datetime as dt
import os
import sys
from curl_cffi.requests import errors as cffi_errors

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import financials_provider

class TestYFinanceFinancialsProvider(unittest.TestCase):
    """Consolidated tests for the yfinance financials data provider."""

    @patch('providers.yfin.financials_provider.yf.Ticker')
    def test_primary_fetcher_success(self, mock_yfinance_ticker):
        """Tests the happy path for the primary yfinance library fetcher."""
        # --- Arrange ---
        mock_instance = mock_yfinance_ticker.return_value
        mock_instance.info = {
            'marketCap': 2.5e12,
            'sharesOutstanding': 15e9,
            'floatShares': 14.9e9,
            'firstTradeDateMilliseconds': 345479400000 # 1980-12-12
        }
        mock_instance.quarterly_income_stmt = pd.DataFrame(
            [[1000]], index=['Total Revenue'], columns=[pd.to_datetime('2023-09-30')]
        )
        mock_instance.income_stmt = pd.DataFrame() # Empty annual

        # --- Act ---
        result = financials_provider._fetch_financials_with_yfinance('AAPL')
        
        # --- Assert ---
        self.assertIsNotNone(result)
        self.assertEqual(result['marketCap'], 2.5e12)
        self.assertEqual(result['ipoDate'], '1980-12-12')
        self.assertEqual(result['quarterly_earnings'][0]['Revenue'], 1000)

    @patch('providers.yfin.financials_provider.yf.Ticker')
    def test_primary_fetcher_missing_info(self, mock_yfinance_ticker):
        """Tests that the primary fetcher returns None if essential info is missing."""
        mock_instance = mock_yfinance_ticker.return_value
        mock_instance.info = {} # Missing marketCap
        
        result = financials_provider._fetch_financials_with_yfinance('MISSING')
        self.assertIsNone(result)

    @patch('providers.yfin.financials_provider.yahoo_client.session.get')
    @patch('providers.yfin.financials_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_fallback_fetcher_success(self, mock_get_auth, mock_session_get):
        """Tests the happy path for the fallback direct API call fetcher."""
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            'quoteSummary': { 'result': [{
                'summaryDetail': {'marketCap': {'raw': 2e12}},
                'defaultKeyStatistics': {'ipoDate': {'fmt': '2020-01-01'}},
                'incomeStatementHistoryQuarterly': {'incomeStatementHistory': []}
            }]}
        }
        mock_session_get.return_value = mock_response
        
        result = financials_provider._fetch_financials_with_fallback('FB', dt.datetime.now().timestamp())
        self.assertIsNotNone(result)
        self.assertEqual(result['marketCap'], 2e12)
        self.assertEqual(result['ipoDate'], '2020-01-01')

    @patch('providers.yfin.financials_provider._fetch_financials_with_yfinance')
    @patch('providers.yfin.financials_provider._fetch_financials_with_fallback')
    def test_orchestrator_uses_fallback(self, mock_fallback, mock_primary):
        """Tests that get_core_financials uses the fallback when the primary fails."""
        mock_primary.return_value = None
        mock_fallback.return_value = {'ticker': 'MSFT', 'marketCap': 1.5e12}
        
        result = financials_provider.get_core_financials('MSFT')
        
        mock_primary.assert_called_once_with('MSFT')
        mock_fallback.assert_called_once()
        self.assertEqual(result['ticker'], 'MSFT')

    @patch('providers.yfin.financials_provider.price_provider._get_single_ticker_data')
    def test_orchestrator_handles_index(self, mock_get_price_data):
        """Tests the special logic path for market indices."""
        mock_get_price_data.return_value = [
            {'close': 4000, 'high': 4100, 'low': 3900},
            {'close': 4050, 'high': 4150, 'low': 3950},
        ] * 100 # Ensure enough data for SMAs
        
        data = financials_provider.get_core_financials('^GSPC')
        
        self.assertIsNotNone(data)
        self.assertEqual(data['current_price'], 4050)
        self.assertGreater(data['sma_50'], 0)
        self.assertGreater(data['sma_200'], 0)

    @patch('providers.yfin.financials_provider._mark_ticker_as_delisted')
    @patch('providers.yfin.financials_provider.yahoo_client.session.get')
    @patch('providers.yfin.financials_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_fallback_marks_delisted_on_404(self, mock_get_auth, mock_session_get, mock_mark_delisted):
        """Tests that the fallback provider correctly marks a ticker as delisted on a 404."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=404)
        mock_session_get.side_effect = cffi_errors.RequestsError("404 Not Found", response=mock_response)

        # --- Act ---
        result = financials_provider._fetch_financials_with_fallback('DELISTED', dt.datetime.now().timestamp())

        # --- Assert ---
        self.assertIsNone(result)
        mock_mark_delisted.assert_called_once_with('DELISTED', "Yahoo Finance API call failed with status 404.")

    @patch('providers.yfin.financials_provider._mark_ticker_as_delisted')
    @patch('providers.yfin.financials_provider.yahoo_client.session.get')
    @patch('providers.yfin.financials_provider.yahoo_client._get_yahoo_auth', return_value='test_crumb')
    def test_fallback_does_not_mark_delisted_on_500(self, mock_get_auth, mock_session_get, mock_mark_delisted):
        """Tests that the fallback provider does not mark a ticker as delisted on other server errors."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=500)
        # We need to make sure the response object has a url attribute for the logger
        mock_response.url = "http://fake.url"
        mock_session_get.side_effect = cffi_errors.RequestsError("500 Server Error", response=mock_response)

        # --- Act ---
        result = financials_provider._fetch_financials_with_fallback('SERVERERROR', dt.datetime.now().timestamp())

        # --- Assert ---
        self.assertIsNone(result)
        mock_mark_delisted.assert_not_called()