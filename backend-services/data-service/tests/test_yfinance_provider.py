# backend-services/data-service/tests/test_yfinance_provider.py

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import datetime as dt

# Make sure the provider is in the path. Adjust as necessary.
from providers import yfinance_provider

class TestYFinanceProviderFinancials(unittest.TestCase):
    """
    Tests for fetching core financial data using the yfinance provider,
    including the new yfinance library integration and fallback mechanisms.
    """

    @patch('providers.yfinance_provider.session')
    @patch('providers.yfinance_provider._get_yahoo_auth', return_value='test_crumb')
    def test_ticker_sanitization(self, mock_get_auth, mock_session):
        """
        Test that ticker symbols are correctly sanitized before being used in an API call.
        Checks for stripping whitespace and replacing slashes.
        """
        # --- Arrange ---
        # Mock the session to return a valid JSON structure to avoid unrelated errors.
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'chart': {
                'result': [{
                    'timestamp': [1672531200],
                    'indicators': {
                        'quote': [{'open': [100], 'high': [105], 'low': [99], 'close': [102], 'volume': [10000]}],
                        'adjclose': [{'adjclose': [101]}]
                    }
                }]
            }
        }
        mock_session.get.return_value = mock_response

        dirty_ticker = 'BRK/A  '
        expected_sanitized_ticker = 'BRK-A'

        # --- Act ---
        yfinance_provider._get_single_ticker_data(dirty_ticker, period="1y")

        # --- Assert ---
        # Verify that the request method was called
        mock_session.get.assert_called_once()
        
        # Get the URL that was actually called
        request_url = mock_session.get.call_args[0][0]

        # Check that the sanitized ticker is in the URL, not the original dirty one
        self.assertIn(expected_sanitized_ticker, request_url)
        self.assertNotIn(dirty_ticker, request_url)

    @patch('providers.yfinance_provider.yf.Ticker')
    def test_fetch_financials_with_yfinance_success(self, mock_yfinance_ticker):
        """
        Test successful fetching and transformation of financials using the yfinance library.
        """
        # --- Arrange ---
        # Create a proper DatetimeIndex for the columns
        date_cols = pd.to_datetime(['2023-09-30'])

        # Create mock DataFrames for earnings
        mock_q_income_stmt_df = pd.DataFrame([[1000], [100]], index=['Total Revenue', 'Net Income'], columns=date_cols)
        mock_a_income_stmt_df = pd.DataFrame([[4000], [400]], index=['Total Revenue', 'Net Income'], columns=date_cols)
        
        # Configure the mock yfinance Ticker object
        mock_instance = mock_yfinance_ticker.return_value
        mock_instance.info = {
            'marketCap': 2.5e12,
            'sharesOutstanding': 15e9,
            'floatShares': 14.9e9,
            'firstTradeDateMilliseconds': 345479400000 # Unix timestamp for 1980-12-12 (the unit is in milliseconds)
        }
        mock_instance.quarterly_income_stmt = mock_q_income_stmt_df
        mock_instance.income_stmt = mock_a_income_stmt_df


        # --- Act ---
        result = yfinance_provider._fetch_financials_with_yfinance('AAPL')
        
        # --- Assert ---
        self.assertIsNotNone(result)
        self.assertEqual(result['marketCap'], 2.5e12)
        self.assertEqual(result['ipoDate'], '1980-12-12')
        self.assertIn('quarterly_earnings', result)
        self.assertEqual(len(result['quarterly_earnings']), 1)
        self.assertEqual(result['quarterly_earnings'][0]['Revenue'], 1000)

    @patch('providers.yfinance_provider.yf.Ticker')
    def test_fetch_financials_with_yfinance_missing_info(self, mock_yfinance_ticker):
        """
        - Test that the function returns None if `stock.info` is empty or missing keys.
        """
        # --- Arrange ---
        # Configure the mock to return an empty info dictionary
        mock_instance = mock_yfinance_ticker.return_value
        mock_instance.info = {}
        
        # --- Act ---
        result = yfinance_provider._fetch_financials_with_yfinance('AAPL')
        
        # --- Assert ---
        self.assertIsNone(result)

    @patch('providers.yfinance_provider.yf.Ticker')
    def test_fetch_financials_with_yfinance_exception(self, mock_yfinance_ticker):
        """
        - Test that the function returns None if the yfinance library raises an exception.
        """
        # --- Arrange ---
        mock_yfinance_ticker.side_effect = Exception("API limit reached")

        # --- Act ---
        result = yfinance_provider._fetch_financials_with_yfinance('ERROR')

        # --- Assert ---
        self.assertIsNone(result)

    # --- Tests for the orchestrator function: get_core_financials ---

    @patch('providers.yfinance_provider._fetch_financials_with_yfinance')
    def test_get_core_financials_uses_yfinance_first(self, mock_fetch_yf):
        """
        - Test that `get_core_financials` successfully calls the new yfinance helper.
        """
        # --- Arrange ---
        # Mock a successful response from the new yfinance helper
        mock_fetch_yf.return_value = {
            'ticker': 'AAPL',
            'quarterly_earnings': [{'date': '2023-09-30', 'Revenue': 1200, 'Net Income': 120, 'Earnings': 1.2}]
        }

        # --- Act ---
        result = yfinance_provider.get_core_financials('AAPL')

        # --- Assert ---
        mock_fetch_yf.assert_called_once_with('AAPL')
        self.assertIsNotNone(result)
        self.assertEqual(result['ticker'], 'AAPL')
        self.assertIn('quarterly_earnings', result)
        self.assertEqual(result['quarterly_earnings'][0]['Revenue'], 1200)

    @patch('providers.yfinance_provider._fetch_financials_with_yfinance')
    @patch('providers.yfinance_provider.session.get')
    def test_get_core_financials_fallback_to_api(self, mock_requests_get, mock_fetch_yf):
        """
        - Test the fallback mechanism: if yfinance helper fails, it should call the API.
        """
        # --- Arrange ---
        # 1. Mock the yfinance helper to return None (simulating a failure)
        mock_fetch_yf.return_value = None

        # 2. Mock the requests session to simulate a successful API call as a fallback
        mock_api_response = {
            'quoteSummary': {
                'result': [{
                    'incomeStatementHistoryQuarterly': {
                        'incomeStatementHistory': [{
                            'totalRevenue': {'raw': 900},
                            'netIncome': {'raw': 90},
                            'basicEps': {'raw': 0.9}
                        }]
                    },
                    'defaultKeyStatistics': {'sharesOutstanding': {'raw': 100000000}}
                    # Add other required fields if necessary
                }]
            }
        }
        mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: mock_api_response)

        # Mock the auth function
        with patch('providers.yfinance_provider._get_yahoo_auth', return_value='dummy_crumb'):
            # --- Act ---
            result = yfinance_provider.get_core_financials('MSFT')

            # --- Assert ---
            # Verify yfinance helper was called
            mock_fetch_yf.assert_called_once_with('MSFT')
            # Verify the API was called as a fallback
            mock_requests_get.assert_called()
            
            self.assertIsNotNone(result)
            self.assertIn('quarterly_earnings', result)
            self.assertEqual(result['quarterly_earnings'][0]['Revenue'], 900)

    @patch('providers.yfinance_provider._get_single_ticker_data')
    def test_get_core_financials_for_index(self, mock_get_single_ticker):
        """
        - Test the specific logic for market indices like ^GSPC.
        """
        # --- Arrange ---
        mock_hist_data = [
            {'date': '2023-01-01', 'close': 4000, 'high': 4010, 'low': 3990},
            # ... add more data points ...
            {'date': '2023-09-30', 'close': 4500, 'high': 4510, 'low': 4490},
        ]
        # Ensure enough data for SMA calculations
        for i in range(200):
            mock_hist_data.append({'date': f'2022-{i//30 + 1}-{i%30+1}', 'close': 3800+i, 'high': 3810+i, 'low': 3790+i})
        
        mock_get_single_ticker.return_value = mock_hist_data

        # --- Act ---
        result = yfinance_provider.get_core_financials('^GSPC')

        # --- Assert ---
        mock_get_single_ticker.assert_called_once_with('^GSPC', start_date=dt.date.today() - dt.timedelta(days=365))
        self.assertIsNotNone(result)
        self.assertIn('current_price', result)
        self.assertIn('sma_50', result)
        self.assertIn('sma_200', result)
        self.assertIn('high_52_week', result)
        self.assertIn('low_52_week', result)
        self.assertGreater(result['current_price'], 0)


if __name__ == '__main__':
    unittest.main()