import unittest
import os
import json
from flask import Flask, jsonify
from unittest.mock import patch
from unittest.mock import patch

# Set environment variables before importing the app
os.environ['SCREENING_SERVICE_URL'] = 'http://screening-service:3002'
os.environ['ANALYSIS_SERVICE_URL'] = 'http://analysis-service:3003'
os.environ['TICKER_SERVICE_URL'] = 'http://ticker-service:5000'
os.environ['DATA_SERVICE_URL'] = 'http://data-service:3001'

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
        mock_get.assert_called_once_with('http://screening-service:3002/screen/AAPL', params={}, timeout=20)

    @patch('requests.get')
    def test_routes_to_analysis_service(self, mock_get):
        """Verify that a request to /analyze/* is routed to the analysis-service."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "MSFT", "analysis": "VCP detected"}

        response = self.app.get('/analyze/MSFT')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "MSFT", "analysis": "VCP detected"})
        mock_get.assert_called_once_with('http://analysis-service:3003/analyze/MSFT', params={}, timeout=20)

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

    # Test case for the data-service route
    @patch('requests.get')
    def test_routes_to_data_service(self, mock_get):
        """Verify that a request to /data/* is routed to the data-service."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"price": 150.0}
        
        # Note: The gateway logic forwards the path, so '/data/AAPL' is sent to the data service
        response = self.app.get('/data/AAPL')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"price": 150.0})
        mock_get.assert_called_once_with('http://data-service:3001/data/AAPL', params={}, timeout=20)

    # Test for the new POST route to clear the cache.
    @patch('requests.post')
    def test_routes_post_to_cache_clear_endpoint(self, mock_post):
        """Verify that a POST to /cache/clear is routed to the data-service."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"message": "All data service caches have been cleared."}
        response = self.app.post(
            '/cache/clear',
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "All data service caches have been cleared."})
        mock_post.assert_called_once_with('http://data-service:3001/cache/clear', json={}, timeout=20)

    def test_invalid_service_route(self):
        """Verify that a request to an unknown service returns a 404 error."""
        response = self.app.get('/nonexistentservice/somepath')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Service not found"})

    @patch('requests.get')
    def test_cors_headers_are_present(self, mock_get):
        """Verify that CORS headers are added to the response."""
        # Arrange: Mock a successful downstream response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "CORS", "passes": True}
        
        # Act: Make a request with an Origin header, like a browser would
        headers = {'Origin': 'http://localhost:5173'}
        response = self.app.get('/screen/CORS', headers=headers)

        # Assert: Check for the Access-Control-Allow-Origin header
        self.assertEqual(response.status_code, 200)
        self.assertIn('Access-Control-Allow-Origin', response.headers)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://localhost:5173')

if __name__ == '__main__':
    unittest.main()