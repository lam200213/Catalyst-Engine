# backend-services/screening-service/tests/test_app.py
import unittest
from unittest.mock import patch, Mock
import json
from app import app, _process_chunk

class TestScreeningServiceDataContracts(unittest.TestCase):

    def setUp(self):
        """Set up a test client for the Flask application."""
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_screen_ticker_handles_data_contract_violation(self, mock_get):
        """
        Assert that the single ticker endpoint returns a 502 error
        when the data-service returns a payload that violates the PriceDataItem contract.
        (e.g., 'volume' is a string instead of an integer).
        """
        # 1. Arrange: Mock an invalid payload from the data-service
        invalid_payload = [{
            "formatted_date": "2025-09-25",
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": "a-lot-of-shares",  # <-- Type mismatch: should be int
            "adjclose": 151.5
        }]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(invalid_payload).encode('utf-8')
        # This function is needed because the app calls .json() after validation
        mock_response.json.return_value = invalid_payload 
        mock_get.return_value = mock_response

        # 2. Act: Make a request to the endpoint
        response = self.app.get('/screen/AAPL')
        response_data = json.loads(response.data.decode('utf-8'))

        # 3. Assert: Verify the response indicates a contract violation
        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response_data)
        self.assertEqual(response_data["error"], "Invalid data structure received from upstream data-service.")
        self.assertIn("details", response_data)
        self.assertIn("validation error for list[PriceDataItem]", response_data["details"]) # Pydantic error message
        self.assertIn("volume", response_data["details"]) # Pinpoint the failing field

    @patch('app.print') # Mock the print function
    @patch('app.requests.post')
    def test_process_chunk_handles_batch_contract_violation(self, mock_post, mock_print):
        """
        Assert that _process_chunk returns an empty list AND logs a warning
        when the data-service payload has a missing required field.
        """
        # 1. Arrange
        ticker_chunk = ["MSFT", "GOOG"]
        invalid_batch_payload = {
            "success": {
                "MSFT": [{"formatted_date": "2025-09-25", "open": 400.0, "high": 405.0, "low": 398.0, "volume": 20000000, "adjclose": 402.0}] # "close" is missing
            },
            "failed": ["GOOG"]
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(invalid_batch_payload).encode('utf-8')
        mock_post.return_value = mock_response

        # 2. Act
        result = _process_chunk(ticker_chunk)

        # 3. Assert
        self.assertEqual(result, []) # Still check the return value
        
        # New Assertion: Check that a specific warning was printed
        mock_print.assert_called()
        # Get the first argument of the first call to print()
        log_message = mock_print.call_args[0][0] 
        self.assertIn("Batch data contract violation", log_message)

    @patch('app.requests.post')
    def test_process_chunk_handles_malformed_top_level_key(self, mock_post):
        """
        Assert that _process_chunk fails if the top-level keys of the batch
        response are incorrect (e.g., 'succeeded' instead of 'success').
        """
        # 1. Arrange
        ticker_chunk = ["NVDA"]
        malformed_structure_payload = {
            "succeeded": {}, # <-- Malformed key, should be "success"
            "failed": []
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(malformed_structure_payload).encode('utf-8')
        mock_post.return_value = mock_response

        # 2. Act
        result = _process_chunk(ticker_chunk)
        
        # 3. Assert
        self.assertEqual(result, [])

    @patch('app.apply_screening_criteria')
    @patch('app.requests.post')
    def test_process_chunk_happy_path(self, mock_post, mock_apply_screening):
        """
        Assert that _process_chunk correctly processes a valid payload,
        applies screening logic, and returns tickers that pass.
        """
        # 1. Arrange: Mock a valid chunk and a valid batch response
        ticker_chunk = ["AAPL", "GOOD", "FAIL"]
        valid_batch_payload = {
            "success": {
                "AAPL": [{"formatted_date": "2025-09-25", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.5, "volume": 1000000, "adjclose": 151.5}],
                "GOOD": [{"formatted_date": "2025-09-25", "open": 200.0, "high": 202.0, "low": 199.0, "close": 201.5, "volume": 2000000, "adjclose": 201.5}]
            },
            "failed": ["FAIL"]
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(valid_batch_payload).encode('utf-8')
        mock_post.return_value = mock_response

        # Mock the screening logic to control the outcome
        # Let's say AAPL passes and GOOD fails the screening criteria
        def screening_side_effect(ticker, data):
            if ticker == "AAPL":
                return {"passes": True}
            return {"passes": False}
        mock_apply_screening.side_effect = screening_side_effect

        # 2. Act: Call the helper function
        result = _process_chunk(ticker_chunk)

        # 3. Assert: Verify the outcome
        self.assertEqual(result, ["AAPL"]) # Only AAPL should be in the final list
        self.assertEqual(mock_apply_screening.call_count, 2) # Ensures logic was run for both successful tickers

if __name__ == '__main__':
    unittest.main()