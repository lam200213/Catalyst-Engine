# backend-services/data-service/tests/test_yahoo_client.py
import unittest
from unittest.mock import patch, MagicMock, call
import threading
import time
from curl_cffi.requests import errors as cffi_errors

# Since yahoo_client is in a sibling directory, we adjust the path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.yfin import yahoo_client

class TestYahooClient(unittest.TestCase):

    def setUp(self):
        """Reset the pool before each test to ensure isolation."""
        with yahoo_client._POOL_LOCK:
            yahoo_client._ID_POOL = []
            yahoo_client._ID_HEALTH.clear()

    @patch('providers.yfin.yahoo_client.cffi_requests.Session.get')
    def test_identity_crumb_refresh(self, mock_get):
        """Tests that an identity can fetch and cache a crumb."""
        mock_response = MagicMock()
        mock_response.text = "new_crumb"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Initialize a single identity
        identity = yahoo_client._Identity()
        
        # First call should fetch
        crumb1 = identity.ensure_crumb()
        self.assertEqual(crumb1, "new_crumb")
        mock_get.assert_called_once()
        
        # Second call should be cached (no new network call)
        crumb2 = identity.ensure_crumb()
        self.assertEqual(crumb2, "new_crumb")
        mock_get.assert_called_once() # Still called only once

    @patch('providers.yfin.yahoo_client._Identity._refresh_crumb_locked')
    def test_pool_initialization(self, mock_refresh):
        """Tests that init_pool creates the correct number of identities."""
        mock_refresh.return_value = "crumb"
        
        self.assertEqual(len(yahoo_client._ID_POOL), 0)
        yahoo_client.init_pool(size=5)
        self.assertEqual(len(yahoo_client._ID_POOL), 5)

        # Calling again should be idempotent
        yahoo_client.init_pool(size=5)
        self.assertEqual(len(yahoo_client._ID_POOL), 5)
        
    @patch('providers.yfin.yahoo_client._Identity.ensure_crumb', return_value="test_crumb")
    @patch('providers.yfin.yahoo_client._Identity.rotate_and_refresh')
    @patch('providers.yfin.yahoo_client.cffi_requests.Session.get')
    def test_retry_decorator_recovers(self, mock_get, mock_rotate, mock_ensure_crumb):
        """Tests that the retry decorator recovers from a transient error."""
        # First call raises an error, second call succeeds
        mock_get.side_effect = [
            cffi_errors.RequestsError("Transient error"),
            MagicMock(status_code=200, json=lambda: {"result": "success"})
        ]
        
        @yahoo_client.retry_on_failure(attempts=2, delay=0)
        def sample_func(_chosen_identity=None):
            return yahoo_client._execute_json_once("http://test.url", _chosen_identity=_chosen_identity)

        result = sample_func()
        
        self.assertEqual(result, {"result": "success"})
        # The first call fails, the second (retry) call succeeds. Total calls = 2.
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_rotate.call_count, 1)

    @patch('providers.yfin.yahoo_client._Identity.ensure_crumb', return_value="test_crumb")
    @patch('providers.yfin.yahoo_client._Identity.rotate_and_refresh')
    @patch('providers.yfin.yahoo_client.cffi_requests.Session.get')
    def test_retry_decorator_fails_after_exhaustion(self, mock_get, mock_rotate, mock_ensure_crumb):
        """Tests that the retry decorator fails after exhausting all attempts."""
        mock_get.side_effect = cffi_errors.RequestsError("Persistent error")
        
        @yahoo_client.retry_on_failure(attempts=3, delay=0)
        def sample_func(_chosen_identity=None):
            return yahoo_client._execute_json_once("http://test.url", _chosen_identity=_chosen_identity)

        with self.assertRaises(cffi_errors.RequestsError):
            sample_func()
        
        self.assertEqual(mock_rotate.call_count, 3)

    @patch('providers.yfin.yahoo_client.cffi_requests.Session.get')
    def test_should_rotate_logic(self, mock_get):
        """Tests the internal logic for deciding when to rotate identity."""
        self.assertTrue(yahoo_client._should_rotate(401, ""))
        self.assertTrue(yahoo_client._should_rotate(403, ""))
        self.assertTrue(yahoo_client._should_rotate(429, ""))
        self.assertTrue(yahoo_client._should_rotate(500, "Too Many Requests"))
        self.assertFalse(yahoo_client._should_rotate(500, "Internal Server Error"))
        self.assertFalse(yahoo_client._should_rotate(200, ""))

if __name__ == '__main__':
    unittest.main()