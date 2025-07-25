# backend-services/data-service/tests/test_yfinance_provider_core.py
# Tests the fundamental data fetching (get_core_financials)
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from providers import yfinance_provider

class TestYfinanceProviderCore(unittest.TestCase):

    @patch('curl_cffi.requests.get')
    def test_get_core_financials_regular_stock(self, mock_cffi_get):
        """Tests the get_core_financials function for a regular stock ticker."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "quoteSummary": {
                "result": [{
                    "summaryDetail": {"marketCap": {"raw": 2000000000}},
                    "defaultKeyStatistics": {"floatShares": {"raw": 10000000}},
                    "assetProfile": {"ipoDate": {"fmt": "2020-01-01"}},
                    "incomeStatementHistory": {"incomeStatementHistory": []},
                    "cashflowStatementHistory": {"cashflowStatements": []}
                }]
            }
        }
        mock_cffi_get.return_value = mock_response

        # Act
        data = yfinance_provider.get_core_financials('AAPL')

        # Assert
        self.assertIsNotNone(data)
        self.assertEqual(data['marketCap'], 2000000000)
        self.assertEqual(data['floatShares'], 10000000)
        self.assertEqual(data['ipoDate'], '2020-01-01')

    @patch('providers.yfinance_provider._get_single_ticker_data')
    def test_get_core_financials_index(self, mock_get_single_ticker_data):
        """Tests the get_core_financials function for an index ticker."""
        # Arrange
        mock_data = [
            {"close": 4000, "high": 4100, "low": 3900},
            {"close": 4050, "high": 4150, "low": 3950},
            # Add more data points to reach 50 and 200 days
        ] * 200
        mock_get_single_ticker_data.return_value = mock_data

        # Act
        data = yfinance_provider.get_core_financials('^GSPC')

        # Assert
        self.assertIsNotNone(data)
        self.assertEqual(data['current_price'], 4050)
        self.assertAlmostEqual(data['sma_50'], 4025.0, places=2)
        self.assertAlmostEqual(data['sma_200'], 4025.0, places=2)
        self.assertEqual(data['high_52_week'], 4150)
        self.assertEqual(data['low_52_week'], 3900)

    @patch('curl_cffi.requests.get')
    def test_get_core_financials_api_error(self, mock_cffi_get):
        """Tests the get_core_financials function for API errors."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_cffi_get.return_value = mock_response

        # Act
        data = yfinance_provider.get_core_financials('AAPL')

        # Assert
        self.assertIsNone(data)