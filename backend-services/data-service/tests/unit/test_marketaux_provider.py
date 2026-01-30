# backend-services/data-service/tests/unit/test_marketaux_provider.py

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import requests

# Add the parent directory to the path to import the provider
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers import marketaux_provider

class TestMarketauxProvider(unittest.TestCase):
    @patch.dict(os.environ, {"MARKETAUX_API_KEY": "test_key"})
    @patch('requests.get')
    def test_get_news_success(self, mock_requests_get):
        """Tests successful news fetching and data extraction."""
        # 1. Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Mimic the structure of the MarketAux API response
        mock_api_data = {'data': [{'title': 'Test News 1'}, {'title': 'Test News 2'}]}
        mock_response.json.return_value = mock_api_data
        mock_requests_get.return_value = mock_response

        # 2. Act
        result = marketaux_provider.get_news_for_ticker('AAPL')

        # 3. Assert
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['title'], 'Test News 1')
        # Verify the correct API URL was called
        mock_requests_get.assert_called_once()
        self.assertIn("api.marketaux.com", mock_requests_get.call_args[0][0])

    @patch.dict(os.environ, {"MARKETAUX_API_KEY": "test_key"})
    @patch('requests.get')
    def test_get_news_api_failure(self, mock_requests_get):
        """Tests how the provider handles a network or API error."""
        # 1. Arrange
        mock_requests_get.side_effect = requests.exceptions.RequestException("Network Error")

        # 2. Act
        result = marketaux_provider.get_news_for_ticker('AAPL')

        # 3. Assert
        self.assertIsNone(result)

    def test_missing_api_key(self):
        """Tests that the provider returns None if the API key is missing."""
        # 1. Arrange
        # Unset the environment variable if it exists
        if 'MARKETAUX_API_KEY' in os.environ:
            del os.environ['MARKETAUX_API_KEY']

        # 2. Act
        result = marketaux_provider.get_news_for_ticker('AAPL')

        # 3. Assert
        self.assertIsNone(result)

    @patch.dict(os.environ, {"MARKETAUX_API_KEY": "YOUR_MARKETAUX_API_KEY"})
    def test_invalid_placeholder_api_key(self):
        """Tests that the provider returns None if the default placeholder key is used."""
        # 1. Arrange: The key is explicitly set to the placeholder value
        # 2. Act
        result = marketaux_provider.get_news_for_ticker('AAPL')
        # 3. Assert
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()