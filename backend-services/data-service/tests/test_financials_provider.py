# backend-services/data-service/tests/test_financials_provider.py
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import datetime as dt
import os
import sys
from curl_cffi.requests import errors as cffi_errors
from concurrent.futures import ThreadPoolExecutor

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import financials_provider
from .test_fixtures import make_quote_summary_payload

class TestYFinanceFinancialsProvider(unittest.TestCase):
    """Consolidated tests for the yfinance financials data provider."""

    def setUp(self):
        """Set up a ThreadPoolExecutor for tests."""
        self.executor = ThreadPoolExecutor(max_workers=1)

    def tearDown(self):
        """Shutdown the ThreadPoolExecutor."""
        self.executor.shutdown(wait=True)

    @patch('providers.yfin.financials_provider.yf.Ticker')
    def test_primary_fetcher_handles_incomplete_info(self, mock_yfinance_ticker):
        """
        Tests that the primary fetcher handles info dicts that are missing non-critical fields.
        This aligns with the test plan's requirement for graceful degradation.
        """
        # --- Arrange ---
        mock_instance = mock_yfinance_ticker.return_value
        # Simulate a response that has marketCap but is missing floatShares
        mock_instance.info = {
            'marketCap': 2.5e12,
            'sharesOutstanding': 15e9,
            # 'floatShares' is intentionally missing
            'firstTradeDateMilliseconds': 345479400000
        }
        mock_instance.quarterly_income_stmt = pd.DataFrame()
        mock_instance.income_stmt = pd.DataFrame()

        # --- Act ---
        result = financials_provider._fetch_financials_with_yfinance('AAPL')

        # --- Assert ---
        # The function should still succeed and return a result
        self.assertIsNotNone(result)
        self.assertEqual(result['marketCap'], 2.5e12)
        # The missing field should be present but have a value of None
        self.assertIn('floatShares', result)
        self.assertIsNone(result['floatShares'])

    @patch('providers.yfin.financials_provider.get_core_financials')
    def test_get_batch_core_financials_handles_mix_of_success_and_failure(self, mock_get_core_financials):
        """
        Tests the batch fetching function with a mix of successful and failed tickers.
        """
        # --- Arrange ---
        # Mock the single-ticker function that the batch function calls
        def side_effect(ticker):
            if ticker == 'AAPL':
                return {'ticker': 'AAPL', 'marketCap': 2.5e12}
            elif ticker == 'FAIL':
                # Simulate a complete failure for this ticker
                return None
            else:
                return None

        mock_get_core_financials.side_effect = side_effect

        tickers_to_test = ['AAPL', 'FAIL']

        # --- Act ---
        results = financials_provider.get_batch_core_financials(tickers_to_test, self.executor)

        # --- Assert ---
        # The mock function should have been called for each ticker in the batch
        self.assertEqual(mock_get_core_financials.call_count, 2)
        
        # Verify the structure of the returned dictionary
        self.assertIn('AAPL', results)
        self.assertIn('FAIL', results)
        
        # Check the content for both the successful and failed tickers
        self.assertIsNotNone(results['AAPL'])
        self.assertEqual(results['AAPL']['marketCap'], 2.5e12)
        self.assertIsNone(results['FAIL'])

    @patch('providers.yfin.financials_provider._fetch_financials_with_yfinance')
    @patch('providers.yfin.financials_provider.is_ticker_delisted', return_value=True)
    def test_get_core_financials_skips_delisted_ticker(self, mock_is_delisted, mock_primary_fetch):
        """
        Tests that get_core_financials skips API calls for a known delisted ticker.
        """
        # --- Act ---
        result = financials_provider.get_core_financials('DELISTED')

        # --- Assert ---
        # The function should return None immediately
        self.assertIsNone(result)
        # Verify that the check was made
        mock_is_delisted.assert_called_once_with('DELISTED')
        # CRITICAL: Assert that no downstream API call was attempted
        mock_primary_fetch.assert_not_called()

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

    @patch('providers.yfin.financials_provider.yahoo_client.execute_request')
    def test_fallback_fetcher_success(self, mock_execute_request):
        """Tests the happy path for the fallback direct API call fetcher."""
        mock_execute_request.return_value = {
            'quoteSummary': { 'result': [{
                'summaryDetail': {'marketCap': {'raw': 2e12}},
                'defaultKeyStatistics': {'ipoDate': {'fmt': '2020-01-01'}},
                'incomeStatementHistoryQuarterly': {'incomeStatementHistory': []}
            }]}
        }
        
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

    @patch('providers.yfin.financials_provider.price_provider._get_single_ticker_data')
    def test_get_core_financials_for_index(self, mock_get_price_data):
        """Tests the special handling for market index tickers like ^GSPC."""
        # --- Arrange ---
        # Mock the price provider to return a simplified historical data structure
        mock_get_price_data.return_value = [
            {'formatted_date': '2023-01-01', 'open': 3800, 'high': 3850, 'low': 3790, 'close': 3840, 'volume': 1e9, 'adjclose': 3840},
            {'formatted_date': '2023-01-02', 'open': 3841, 'high': 3880, 'low': 3830, 'close': 3875, 'volume': 1.1e9, 'adjclose': 3875}
        ]
        
        # --- Act ---
        result = financials_provider.get_core_financials('^GSPC')

        # --- Assert ---
        self.assertIsNotNone(result)
        self.assertIn('current_price', result)
        self.assertIn('sma_50', result)
        self.assertNotIn('marketCap', result) # Should not have financial fields
        self.assertEqual(result['current_price'], 3875)

    @patch('providers.yfin.financials_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.financials_provider.yahoo_client.execute_request')
    def test_fallback_marks_delisted_on_404(self, mock_execute_request, mock_mark_delisted):
        """Tests that the fallback provider correctly marks a ticker as delisted on a 404."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=404)
        mock_execute_request.side_effect = cffi_errors.RequestsError("404 Not Found", response=mock_response)

        # --- Act ---
        result = financials_provider._fetch_financials_with_fallback('DELISTED', dt.datetime.now().timestamp())

        # --- Assert ---
        self.assertIsNone(result)
        mock_mark_delisted.assert_called_once_with('DELISTED', "Yahoo Finance API call failed with status 404.")

    @patch('providers.yfin.financials_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.financials_provider.yahoo_client.execute_request')
    def test_fallback_does_not_mark_delisted_on_500(self, mock_execute_request, mock_mark_delisted):
        """Tests that the fallback provider does not mark a ticker as delisted on other server errors."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=500)
        # We need to make sure the response object has a url attribute for the logger
        mock_response.url = "http://fake.url"
        mock_execute_request.side_effect = cffi_errors.RequestsError("500 Server Error", response=mock_response)

        # --- Act ---
        result = financials_provider._fetch_financials_with_fallback('SERVERERROR', dt.datetime.now().timestamp())

        # --- Assert ---
        self.assertIsNone(result)
        mock_mark_delisted.assert_not_called()

    @patch("providers.yfin.financials_provider.yahoo_client.execute_request")
    def test_fallback_handles_null_income_statement_histories(self, mock_execute_request):
        """
        Week 9 Plan 1: incomeStatementHistory / incomeStatementHistoryQuarterly can be None.
        Expected: fallback returns empty earnings lists and does not raise.
        """
        mock_execute_request.return_value = make_quote_summary_payload(
            annual_block=None,
            quarterly_block=None,
            market_cap=2e12,
            ipo_fmt="2020-01-01",
        )

        out = financials_provider._fetch_financials_with_fallback("NULLHIST", dt.datetime.now().timestamp())
        self.assertIsNotNone(out)
        self.assertEqual(out.get("marketCap"), 2e12)
        self.assertEqual(out.get("ipoDate"), "2020-01-01")
        self.assertEqual(out.get("annual_earnings"), [])
        self.assertEqual(out.get("quarterly_earnings"), [])

    @patch("providers.yfin.financials_provider.yahoo_client.execute_request")
    def test_fallback_handles_income_statement_block_present_but_nested_none(self, mock_execute_request):
        """
        Task 9.1: block exists but nested incomeStatementHistory is None.
        This is the exact shape that causes: AttributeError or NoneType iteration in many parsers.
        """
        mock_execute_request.return_value = make_quote_summary_payload(
            annual_block={"incomeStatementHistory": None},
            quarterly_block={"incomeStatementHistory": None},
            market_cap=2e12,
            ipo_fmt="2020-01-01",
        )

        out = financials_provider._fetch_financials_with_fallback(
            "NESTEDNONE", dt.datetime.now().timestamp()
        )

        self.assertIsNotNone(out)
        self.assertEqual(out.get("annual_earnings"), [])
        self.assertEqual(out.get("quarterly_earnings"), [])

    def test_transform_income_statements_accepts_none(self):
        """
        Week 9 Plan 1: transformer must accept None and return [] (no crash).
        """
        out = financials_provider._transform_income_statements(None, 1000)
        self.assertEqual(out, [])
