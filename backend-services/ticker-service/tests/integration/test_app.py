import unittest
from unittest.mock import patch, Mock, MagicMock
import json
import pandas as pd
from app import app
import requests
from pymongo import errors

# This is a sample response mimicking the structure of the NASDAQ API
MOCK_API_RESPONSE = {
    "data": {
        "headers": {"symbol": "Symbol", "name": "Name"},
        "rows": [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "GOOG", "name": "Alphabet Inc."},
            {"symbol": "MSFT", "name": "Microsoft Corp."},
            {"symbol": "YRI.TO", "name": "Yamana Gold Inc. (Delisted)"},
            {"symbol": "BRK.A", "name": "Berkshire Hathaway Inc."}, # Invalid symbol
            {"symbol": "JPM^", "name": "JPMorgan Chase & Co."},     # Invalid symbol
        ],
    },
    "message": None
}
class TickerServiceTest(unittest.TestCase):
    """Unit tests for the Ticker Service."""

    def setUp(self):
        """Set up the test client for the Flask app."""
        self.app = app.test_client()
        self.app.testing = True

    @patch('requests.get')
    def test_get_tickers_success(self, mock_get):
        """
        Test the /tickers endpoint for a successful API call.
        - Mocks a successful response from the NASDAQ API.
        - Confirms the endpoint returns a 200 status code.
        - Verifies the response is a non-empty, sorted list of valid tickers.
        """
        # Configure the mock to return a successful response with sample data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value = mock_response

        # Make a request to the endpoint
        response = self.app.get('/tickers')
        data = json.loads(response.data)

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        # Check that valid tickers are present and invalid ones are filtered out
        self.assertIn("AAPL", data)
        self.assertIn("GOOG", data)
        self.assertNotIn("BRK.A", data)
        self.assertNotIn("JPM^", data)
        # Check that the list is sorted
        self.assertEqual(data, sorted(data))

    @patch('requests.get')
    def test_get_tickers_api_failure(self, mock_get):
        """
        Test the /tickers endpoint when the external API call fails.
        - Mocks a network error during the requests.get call.
        - Confirms the endpoint returns a 500 status code.
        - Verifies the error message is correct.
        """
        # Configure the mock to raise a network exception
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        # Make a request to the endpoint
        response = self.app.get('/tickers')
        data = json.loads(response.data)

        # Assertions
        self.assertEqual(response.status_code, 500)
        self.assertEqual(data, {"error": "Failed to retrieve any tickers from the source."})

    @patch('app.get_all_us_tickers')
    def test_get_tickers_internal_validation_error(self, mock_get_tickers):
        """
        Test that the endpoint returns a 500 error if the internal function
        produces data that violates the Pydantic contract (e.g., not a list of strings).
        """
        # Mock the internal function to return malformed data (list of dicts instead of strings)
        mock_get_tickers.return_value = [{"ticker": "AAPL"}, {"ticker": "GOOG"}]

        # Make a request to the endpoint
        response = self.app.get('/tickers')
        data = json.loads(response.data)

        # Assertions
        self.assertEqual(response.status_code, 500)
        self.assertEqual(data, {"error": "Internal server error: malformed ticker data."})

        # Ensure the internal function was called
        mock_get_tickers.assert_called_once()

    @patch('requests.get')
    def test_get_tickers_bad_data_format(self, mock_get):
        """
        Test the /tickers endpoint when the API returns an unexpected data format.
        - Mocks a successful response but with a malformed JSON payload.
        - Confirms the endpoint gracefully handles the error and returns a 500.
        """
        # Configure the mock to return a successful response with bad data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "Unexpected format"} # Malformed data
        mock_get.return_value = mock_response

        # Make a request to the endpoint
        response = self.app.get('/tickers')
        data = json.loads(response.data)

        # Assertions
        self.assertEqual(response.status_code, 500)
        self.assertEqual(data, {"error": "Failed to retrieve any tickers from the source."})

    @patch('requests.get')
    def test_get_tickers_empty_rows(self, mock_get):
        """
        Test the /tickers endpoint when the NASDAQ API returns a 200 OK with empty "rows".
        - Mocks a successful response with an empty "rows" list.
        - Confirms the endpoint returns a 500 status code.
        - Verifies the error message is correct.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "headers": {},
                "rows": [],
            },
            "message": None
        }
        mock_get.return_value = mock_response

        response = self.app.get('/tickers')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(data, {"error": "Failed to retrieve any tickers from the source."})

# --- Tests for DB Filtering Logic ---
    
    @patch('requests.get')
    @patch('app.db')
    def test_filtering_delisted_tickers_successfully(self, mock_db, mock_get):
        """
        1. Test Business Logic: Verify that tickers present in the database's
           delisted collection are correctly removed from the final list.
        """
        # Mock the external API call
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value = mock_response

        # Mock the database call to return one delisted ticker
        mock_cursor = MagicMock()
        mock_cursor.__iter__.return_value = iter([{'ticker': 'GOOG'}])
        mock_db.ticker_status.find.return_value = mock_cursor

        # Make the request to the endpoint
        response = self.app.get('/tickers')
        data = json.loads(response.data)

        # Assertions
        self.assertEqual(response.status_code, 200)
        # Verify 'GOOG' is filtered out, but others remain
        self.assertEqual(sorted(data), ['AAPL', 'MSFT'])
        # Verify the DB was actually queried
        mock_db.ticker_status.find.assert_called_once_with({"status": "delisted"}, {"ticker": 1, "_id": 0})

    @patch('requests.get')
    @patch('app.db', None) # Simulate that the initial DB connection failed
    def test_db_connection_failure_fallback(self, mock_get):
        """
        2. Test Edge Case: Ensure the service falls back gracefully to returning
           an unfiltered list if the database connection is unavailable.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value = mock_response

        response = self.app.get('/tickers')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        # The regex filter runs regardless of DB status. 'YRI.TO' should NOT be present.
        self.assertNotIn('YRI.TO', data)
        # The list should contain all regex-valid tickers since DB is down
        self.assertEqual(sorted(data), ['AAPL', 'GOOG', 'MSFT'])

    @patch('requests.get')
    @patch('app.db')
    def test_no_delisted_tickers_in_db(self, mock_db, mock_get):
        """
        3. Test Edge Case: Ensure correct behavior when the database is connected
           but contains no delisted tickers.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_API_RESPONSE
        mock_get.return_value = mock_response

        # Mock the database to return an empty list
        mock_cursor = MagicMock()
        mock_cursor.__iter__.return_value = iter([])
        mock_db.ticker_status.find.return_value = mock_cursor

        response = self.app.get('/tickers')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        # The list should be unfiltered
        self.assertEqual(sorted(data), ['AAPL', 'GOOG', 'MSFT'])
    
    @patch('requests.get')
    @patch('app.db')
    def test_all_tickers_are_delisted(self, mock_db, mock_get):
        """
        4. Test Blind Spot: Verify that if filtering results in an empty list,
           the service returns 200 OK with an empty list, not a 500 error.
        """
        # Mock API to return only tickers that we will mark as delisted
        mock_api_resp = {"data": {"rows": [{"symbol": "YRI.TO"}, {"symbol": "XYZ"}]}}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_resp
        mock_get.return_value = mock_response

        # Mock DB to delist both tickers
        mock_cursor = MagicMock()
        mock_cursor.__iter__.return_value = iter([{'ticker': 'YRI.TO'}, {'ticker': 'XYZ'}])
        mock_db.ticker_status.find.return_value = mock_cursor

        response = self.app.get('/tickers')
        data = json.loads(response.data)
        
        # Assertion: This now passes thanks to our code fix
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data, []) # Expect an empty list

if __name__ == '__main__':
    unittest.main() 