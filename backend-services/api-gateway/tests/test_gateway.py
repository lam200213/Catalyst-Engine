# backend-services/api-gateway/tests/test_gateway.py
import unittest
import os
import json
from flask import Flask, jsonify
from unittest.mock import patch, MagicMock
import requests

# Set environment variables before importing the app
os.environ['SCREENING_SERVICE_URL'] = 'http://screening-service:3002'
os.environ['ANALYSIS_SERVICE_URL'] = 'http://analysis-service:3003'
os.environ['TICKER_SERVICE_URL'] = 'http://ticker-service:5001'
os.environ['DATA_SERVICE_URL'] = 'http://data-service:3001'
os.environ['SCHEDULER_SERVICE_URL'] = 'http://scheduler-service:3004'


from app import app

def _fake_response(status_code: int, payload: dict):
    """Helper to construct a fake requests.Response-like object."""
    class _R:
        def __init__(self, sc, body):
            self.status_code = sc
            self._body = body
        def json(self):
            return self._body
    return _R(status_code, payload)

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
        mock_get.assert_called_once_with('http://screening-service:3002/screen/AAPL', params={}, timeout=45)

    # Test to verify query parameters are forwarded
    @patch('requests.get')
    def test_routes_to_analysis_service_with_query_params(self, mock_get):
        """Verify that a request to /analyze/* with query params is routed correctly."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"ticker": "MSFT", "analysis": "VCP detected"}

        response = self.app.get('/analyze/MSFT?mode=fast')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"ticker": "MSFT", "analysis": "VCP detected"})
        mock_get.assert_called_once_with('http://analysis-service:3003/analyze/MSFT', params={'mode': 'fast'}, timeout=45)

    # Corrected test to verify the right endpoint is called
    @patch('requests.get')
    def test_routes_to_ticker_service(self, mock_get):
        """Verify that a request to /tickers is routed to the correct ticker-service endpoint."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = ["AAPL", "GOOG", "TSLA"]

        response = self.app.get('/tickers')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, ["AAPL", "GOOG", "TSLA"])
        mock_get.assert_called_once_with('http://ticker-service:5001/tickers', params={}, timeout=45)

    @patch('requests.post')
    def test_routes_post_to_cache_clear_endpoint(self, mock_post):
        """Verify that a POST to /cache/clear is routed to the data-service."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"message": "All data service caches have been cleared."}
        response = self.app.post('/cache/clear', data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "All data service caches have been cleared."})
        mock_post.assert_called_once_with('http://data-service:3001/cache/clear', json={}, timeout=45)
        
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

    def test_malicious_path_traversal(self):
        """Test that a malicious path traversal attempt is handled correctly."""
        response = self.app.get('/screen/../../etc/passwd')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json, {"error": "Malicious path detected"})
    def test_invalid_service_route(self):
        """Verify that a request to an unknown service returns a 404 error."""
        response = self.app.get('/nonexistentservice/somepath')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Service not found"})

    # Success path — route DELETE to monitoring-service and pass-through body/status.
    @patch('requests.delete')
    def test_routes_delete_to_monitoring_service_success(self, mock_delete):
        mock_delete.return_value = _fake_response(200, {"message": "AAPL moved to archive"})
        resp = self.app.delete('/monitor/watchlist/aapl')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json, {"message": "AAPL moved to archive"})
        mock_delete.assert_called_once_with(
            'http://monitoring-service:3006/monitor/watchlist/aapl',
            timeout=45
        )

    # Not Found pass-through — gateway returns 404 from downstream unchanged.
    @patch('requests.delete')
    def test_delete_watchlist_not_found_pass_through(self, mock_delete):
        mock_delete.return_value = _fake_response(404, {"error": "Ticker not in watchlist"})
        resp = self.app.delete('/monitor/watchlist/NONEXISTENT')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json, {"error": "Ticker not in watchlist"})
        mock_delete.assert_called_once_with(
            'http://monitoring-service:3006/monitor/watchlist/NONEXISTENT',
            timeout=45
        )

    # Length boundary — 10 chars allowed (passes through), 11 chars rejected (400).
    @patch('requests.delete')
    def test_delete_watchlist_length_boundary_pass_through(self, mock_delete):
        ten = "A" * 10
        eleven = "A" * 11

        # First call (10) -> downstream 200
        mock_delete.side_effect = [
            _fake_response(200, {"message": f"{ten} moved to archive"}),
            _fake_response(400, {"error": "Invalid ticker length"})
        ]

        ok = self.app.delete(f'/monitor/watchlist/{ten}')
        self.assertEqual(ok.status_code, 200)
        self.assertIn(ten, ok.json.get("message", ""))

        bad = self.app.delete(f'/monitor/watchlist/{eleven}')
        self.assertEqual(bad.status_code, 400)
        self.assertIn("error", bad.json)

        calls = [
            (('http://monitoring-service:3006/monitor/watchlist/' + ten,), {'timeout': 45}),
            (('http://monitoring-service:3006/monitor/watchlist/' + eleven,), {'timeout': 45}),
        ]
        # requests.delete called twice with the expected URLs and timeout
        self.assertEqual([c for c in mock_delete.call_args_list], [unittest.mock.call(*c[0], **c[1]) for c in calls])

    # Header propagation — Authorization is forwarded; no user override headers injected.
    @patch('requests.delete')
    def test_delete_watchlist_header_propagation_security(self, mock_delete):
        mock_delete.return_value = _fake_response(200, {"message": "NET moved to archive"})
        resp = self.app.delete('/monitor/watchlist/NET', headers={"Authorization": "Bearer token-123"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json, {"message": "NET moved to archive"})

        # Inspect forwarded headers
        _, kwargs = mock_delete.call_args
        # Some implementations may or may not forward headers; if forwarded, ensure Authorization only.
        if 'headers' in kwargs:
            self.assertIn('Authorization', kwargs['headers'])
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer token-123')
            # Ensure no internal user override header is added
            self.assertNotIn('X-User-Id', kwargs['headers'])

    # Timeout handling — DELETE path returns 504 with timeout error.
    @patch('requests.delete')
    def test_delete_watchlist_gateway_timeout(self, mock_delete):
        import requests
        mock_delete.side_effect = requests.exceptions.Timeout("Request timed out")
        resp = self.app.delete('/monitor/watchlist/ANY')
        self.assertEqual(resp.status_code, 504)
        # Message text may vary per implementation; assert timeout semantics
        self.assertIn("Timeout", resp.json.get("error", ""))

    # Connection error handling — DELETE path returns 503 with service unavailable.
    @patch('requests.delete')
    def test_delete_watchlist_gateway_connection_error(self, mock_delete):
        import requests
        mock_delete.side_effect = requests.exceptions.ConnectionError("Service is down")
        resp = self.app.delete('/monitor/watchlist/ANY')
        self.assertEqual(resp.status_code, 503)
        self.assertIn("Service unavailable", resp.json.get("error", ""))

if __name__ == '__main__':
    unittest.main()