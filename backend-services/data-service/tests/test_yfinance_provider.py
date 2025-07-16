import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import datetime as dt

# Add parent directory to path to import the provider
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from providers import yfinance_provider

class TestYfinanceProvider(unittest.TestCase):

    @patch('curl_cffi.requests.AsyncSession.get')
    def test_get_stock_data_uses_curl_cffi(self, mock_cffi_get):
        """Tests that the data provider uses curl_cffi for requests."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "chart": {"result": [{"timestamp": [], "indicators": {"quote": [{}], "adjclose": [{}]}}]}}
        mock_cffi_get.return_value.result.return_value = mock_response

        # Act
        yfinance_provider.get_stock_data('AAPL')

        # Assert
        mock_cffi_get.assert_called_once()

    @patch('curl_cffi.requests.AsyncSession.get')
    def test_get_stock_data_success(self, mock_cffi_get):
        """Tests successful data retrieval and transformation."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        timestamp = int(dt.datetime(2023, 1, 1).timestamp())
        mock_response.json.return_value = {
            "chart": {
                "result": [
                    {
                        "timestamp": [timestamp],
                        "indicators": {
                            "quote": [{"open": [150], "high": [155], "low": [149], "close": [153], "volume": [10000]}],
                            "adjclose": [{"adjclose": [152.5]}]
                        }
                    }
                ]
            }
        }
        mock_cffi_get.return_value.result.return_value = mock_response

        # Act
        data = yfinance_provider.get_stock_data('AAPL')

        # Assert
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['formatted_date'], '2023-01-01')
        self.assertEqual(data[0]['open'], 150)

    @patch('curl_cffi.requests.AsyncSession.get')
    def test_get_stock_data_404_error(self, mock_cffi_get):
        """Tests that the function returns None on a 404 error."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_cffi_get.return_value.result.return_value = mock_response

        # Act
        data = yfinance_provider.get_stock_data('INVALID')

        # Assert
        self.assertIsNone(data)

    @patch('curl_cffi.requests.AsyncSession.get')
    def test_get_stock_data_malformed_json(self, mock_cffi_get):
        """Tests that the function returns None for malformed JSON."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chart": {"result": [{}]}} # Missing keys
        mock_cffi_get.return_value.result.return_value = mock_response

        # Act
        data = yfinance_provider.get_stock_data('AAPL')

        # Assert
        self.assertIsNone(data)
    @patch('providers.yfinance_provider.random.uniform')
    @patch('providers.yfinance_provider.time.sleep')
    @patch('curl_cffi.requests.AsyncSession.get')
    def test_throttling_is_applied(self, mock_cffi_get, mock_sleep, mock_uniform):
        """Tests that a randomized delay is applied to throttle requests."""
        # Arrange
        mock_uniform.return_value = 1.0
        mock_response = MagicMock()
        mock_response.status_code = 404 # Return a non-200 to exit early after throttling
        mock_cffi_get.return_value.result.return_value = mock_response

        # Act
        yfinance_provider.get_stock_data('THROTTLE')

        # Assert
        mock_uniform.assert_called_once_with(0.5, 1.5)
        mock_sleep.assert_called_once_with(1.0)