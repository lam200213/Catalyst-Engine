# backend-services/data-service/tests/unit/test_finnhub_provider.py

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import finnhub # Required for FinnhubAPIException testing

# Add the parent directory to the path to import the provider
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers import finnhub_provider

class TestFinnhubProvider(unittest.TestCase):
    @patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"})
    @patch('finnhub.Client')
    def test_get_stock_data_success(self, mock_finnhub_client):
        """Tests successful data fetching and transformation."""
        # 1. Arrange
        mock_instance = MagicMock()
        mock_finnhub_client.return_value = mock_instance
        mock_api_response = {
            'c': [150.0, 152.5], 'h': [151.0, 153.0], 'l': [149.0, 152.0],
            'o': [149.5, 152.2], 's': 'ok', 't': [1672531200, 1672617600],
            'v': [100000, 120000]
        }
        mock_instance.stock_candles.return_value = mock_api_response

        # 2. Act
        result = finnhub_provider.get_stock_data('AAPL')

        # 3. Assert
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['close'], 150.0)
        self.assertEqual(result[0]['formatted_date'], '2023-01-01')

    @patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"})
    @patch('finnhub.Client')
    def test_no_data_response(self, mock_finnhub_client):
        """Tests the provider's handling of a 'no_data' response."""
        # 1. Arrange
        mock_instance = MagicMock()
        mock_finnhub_client.return_value = mock_instance
        mock_instance.stock_candles.return_value = {'s': 'no_data'}
        # 2. Act
        result = finnhub_provider.get_stock_data('FAKETICKER')
        # 3. Assert
        self.assertIsNone(result)

    def test_missing_api_key(self):
        """Tests that the provider returns None if the API key is missing."""
        # 1. Arrange
        if 'FINNHUB_API_KEY' in os.environ:
            del os.environ['FINNHUB_API_KEY']
        # 2. Act
        result = finnhub_provider.get_stock_data('AAPL')
        # 3. Assert
        self.assertIsNone(result)

    @patch.dict(os.environ, {"FINNHUB_API_KEY": "test_key"})
    @patch('finnhub.Client')
    def test_api_exception(self, mock_finnhub_client):
        """Tests the provider's exception handling."""
        # 1. Arrange
        mock_instance = MagicMock()
        mock_finnhub_client.return_value = mock_instance
        mock_instance.stock_candles.side_effect = finnhub.FinnhubAPIException(MagicMock(json=lambda: {"error": "API error"}))
        # 2. Act
        result = finnhub_provider.get_stock_data('AAPL')
        # 3. Assert
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()