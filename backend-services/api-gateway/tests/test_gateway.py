# backend-services/api-gateway/tests/test_gateway.py
import unittest
import os
import json
from flask import Flask, jsonify
from unittest.mock import patch
import requests

# Set environment variables before importing the app
os.environ['SCREENING_SERVICE_URL'] = 'http://screening-service:3002'
os.environ['ANALYSIS_SERVICE_URL'] = 'http://analysis-service:3003'
os.environ['TICKER_SERVICE_URL'] = 'http://ticker-service:5001'
os.environ['DATA_SERVICE_URL'] = 'http://data-service:3001'
os.environ['SCHEDULER_SERVICE_URL'] = 'http://scheduler-service:3004'


from app import app

class TestGateway(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('requests.get')
    def test_routes_to_screening_service(self, mock_get):
        """Verify that a request to /screen/* is routed to the screening-service."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "AAPL", "passes": True}

        response = self.app.get('/screen/AAPL')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "AAPL", "passes": True})
        mock_get.assert_called_once_with('http://screening-service:3002/screen/AAPL', params={}, timeout=20)

    # Test to verify query parameters are forwarded
    @patch('requests.get')
    def test_routes_to_analysis_service_with_query_params(self, mock_get):
        """Verify that a request to /analyze/* with query params is routed correctly."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "MSFT", "analysis": "VCP detected"}

        response = self.app.get('/analyze/MSFT?mode=fast')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "MSFT", "analysis": "VCP detected"})
        mock_get.assert_called_once_with('http://analysis-service:3003/analyze/MSFT', params={'mode': 'fast'}, timeout=20)

    # Corrected test to verify the right endpoint is called
    @patch('requests.get')
    def test_routes_to_ticker_service(self, mock_get):
        """Verify that a request to /tickers is routed to the correct ticker-service endpoint."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = ["AAPL", "GOOG", "TSLA"]

        response = self.app.get('/tickers')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, ["AAPL", "GOOG", "TSLA"])
        mock_get.assert_called_once_with('http://ticker-service:5001/tickers', params={}, timeout=20)

    @patch('requests.post')
    def test_routes_post_to_cache_clear_endpoint(self, mock_post):
        """Verify that a POST to /cache/clear is routed to the data-service."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"message": "All data service caches have been cleared."}
        response = self.app.post('/cache/clear', data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "All data service caches have been cleared."})
        mock_post.assert_called_once_with('http://data-service:3001/cache/clear', json={}, timeout=20)
        
    # Test for the scheduler service route and its long timeout
    @patch('requests.post')
    def test_routes_to_scheduler_service_with_long_timeout(self, mock_post):
        """Verify POST to /jobs/screening/start is routed to scheduler with a long timeout."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"message": "Job started"}

        response = self.app.post('/jobs/screening/start', data=json.dumps({}), content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        mock_post.assert_called_once_with(
            'http://scheduler-service:3004/jobs/screening/start',
            json={},
            timeout=6000
        )

    # Test for gateway timeout handling
    @patch('requests.get')
    def test_gateway_handles_timeout_error(self, mock_get):
        """Verify the gateway returns a 504 status on a request timeout."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        response = self.app.get('/screen/ANY')
        
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json, {"error": "Timeout connecting to screen"})
        
    # Test for gateway connection error handling
    @patch('requests.get')
    def test_gateway_handles_connection_error(self, mock_get):
        """Verify the gateway returns a 503 status on a connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Service is down")

        response = self.app.get('/screen/ANY')
        
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['error'], "Service unavailable: screen")

    def test_invalid_service_route(self):
        """Verify that a request to an unknown service returns a 404 error."""
        response = self.app.get('/nonexistentservice/somepath')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Service not found"})

if __name__ == '__main__':
    unittest.main()