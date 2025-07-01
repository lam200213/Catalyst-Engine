import unittest
import os
from flask import Flask, jsonify
from unittest.mock import patch
from unittest.mock import patch # Import patch from unittest.mock

# Set environment variables before importing the app
os.environ['SCREENING_SERVICE_URL'] = 'http://screening-service:3002'
os.environ['ANALYSIS_SERVICE_URL'] = 'http://analysis-service:3003'
os.environ['TICKER_SERVICE_URL'] = 'http://ticker-service:5000'

from app import app

class TestGateway(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('requests.get')
    def test_routes_to_screening_service(self, mock_get):
        """Verify that a request to /screen/* is routed to the screening-service."""
        # Mock the response from the downstream service
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "AAPL", "passes": True}

        # Make a request to the gateway
        response = self.app.get('/screen/AAPL')

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "AAPL", "passes": True})
        # Verify that requests.get was called with the correct URL
        mock_get.assert_called_once_with('http://screening-service:3002/AAPL', params={}, timeout=20)

    @patch('requests.get')
    def test_routes_to_analysis_service(self, mock_get):
        """Verify that a request to /analyze/* is routed to the analysis-service."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "MSFT", "analysis": "VCP detected"}

        response = self.app.get('/analyze/MSFT')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "MSFT", "analysis": "VCP detected"})
        mock_get.assert_called_once_with('http://analysis-service:3003/MSFT', params={}, timeout=20)

    @patch('requests.get')
    def test_routes_to_ticker_service(self, mock_get):
        """Verify that a request to /tickers is routed to the ticker-service."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = ["AAPL", "GOOG", "TSLA"]

        response = self.app.get('/tickers')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, ["AAPL", "GOOG", "TSLA"])
        # The path for ticker-service is empty in the gateway logic, so it calls the base URL + path
        mock_get.assert_called_once_with('http://ticker-service:5000/', params={}, timeout=20)

    def test_invalid_service_route(self):
        """Verify that a request to an unknown service returns a 404 error."""
        response = self.app.get('/nonexistentservice/somepath')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Service not found"})


if __name__ == '__main__':
    unittest.main()