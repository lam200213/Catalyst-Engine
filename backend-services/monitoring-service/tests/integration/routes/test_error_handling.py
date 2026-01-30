# backend-services/monitoring-service/tests/routes/test_error_handling.py
"""
Route-level error handling tests for archive hard delete, including invalid
input (400), DB failures (503), not found (404), and idempotency behavior.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling scenarios"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_database_connection_failure(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Edge case: Verify proper error handling when database connection fails
        """
        from pymongo.errors import ConnectionFailure
        
        # Simulate database connection failure
        mock_connect.side_effect = ConnectionFailure("Cannot connect to MongoDB")
        
        response = client.get('/monitor/watchlist')
        
        # Should return 503 Service Unavailable
        assert response.status_code == 503, "DB connection failure should return 503"
        
        data = json.loads(response.data)
        assert "error" in data, "Error response should have 'error' field"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_service_exception(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Edge case: Verify proper error handling when watchlist_service raises exception
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        
        # Simulate service exception
        mock_get_watchlist.side_effect = Exception("Unexpected error in service")
        
        response = client.get('/monitor/watchlist')
        
        # Should return 500 Internal Server Error
        assert response.status_code == 500, "Service exception should return 500"
        
        data = json.loads(response.data)
        assert "error" in data

    # Not Found returns 404 for ticker not present in watchlist.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_not_found_returns_404(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        Edge/Requirements: Deleting a ticker not in the watchlist should return 404
        with a consistent error body.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service signals not found (pattern: return None indicates not found)
        mock_move_to_archive.return_value = None

        resp = client.delete('/monitor/watchlist/ZZZZZ')
        assert resp.status_code == 404

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "error" in data and isinstance(data["error"], str)

    # Invalid ticker length just above threshold returns 400.
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_invalid_ticker_length_above_threshold_returns_400(
        self, mock_connect, client
    ):
        """
        Length validation: Allowed 1–10 per API contract; use 11 chars to verify 400.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        too_long = "A" * 11
        resp = client.delete(f'/monitor/watchlist/{too_long}')
        assert resp.status_code == 400

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "error" in data

    # Valid ticker at the threshold (10 chars) succeeds.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_valid_at_threshold_succeeds(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        Length validation: Exactly 10 chars should be accepted and processed.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        ten_char = "A" * 10
        mock_move_to_archive.return_value = {
            "ticker": ten_char,
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        resp = client.delete(f'/monitor/watchlist/{ten_char.lower()}')
        assert resp.status_code == 200

        data = json.loads(resp.data)
        assert "message" in data and ten_char in data["message"]

    # Invalid character in ticker returns 400 (format check).
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_invalid_characters_returns_400(
        self, mock_connect, client
    ):
        """
        Format validation: Only [A-Z0-9.-] allowed per contract; reject other chars.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        invalid = "AAPL@"
        resp = client.delete(f'/monitor/watchlist/{invalid}')
        assert resp.status_code == 400

        data = json.loads(resp.data)
        assert "error" in data

# ============================================================================
# TEST: ArchiveErrorHandling
# ============================================================================

class TestArchiveErrorHandling:
    """Error paths for GET /monitor/archive"""

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_archive_database_connection_failure_returns_503(self, mock_connect, mock_get_archive, client):
        # Simulate DB connection failure
        from pymongo.errors import ConnectionFailure
        mock_connect.side_effect = ConnectionFailure("Cannot connect to MongoDB")

        resp = client.get('/monitor/archive')
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_archive_service_exception_returns_500(self, mock_connect, mock_get_archive, client):
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.side_effect = Exception("Unexpected error in archive service")

        resp = client.get('/monitor/archive')
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)


class TestArchiveTTLIndex:
    """Validate TTL index exists for archived_watchlist_items.archived_at"""

    def test_archive_ttl_index_is_present_and_correct(self, test_db_connection):
        # Use real test DB connection to assert TTL index shape
        client, db = test_db_connection

        # In app startup, initializeindexes should have created TTL index; if not, the service's
        # DB init path should be called by the test runner before route tests.
        # Reuse conftest helper for precise checks.
        from tests.conftest import assert_archive_ttl_index  # path may vary if tests package is present
        assert_archive_ttl_index(db, ttl_seconds=2_592_000)

# ============================================================================
# TEST: HTTP Method Validation
# ============================================================================

class TestHTTPMethodValidation:
    """Test HTTP method constraints"""
    
    def test_watchlist_only_allows_get(self, client):
        """
        Verify only GET method is allowed on /monitor/watchlist
        """
        # GET should succeed (with mocked dependencies)
        # Other methods should return 405
        
        response_post = client.post('/monitor/watchlist')
        response_put = client.put('/monitor/watchlist')
        response_delete = client.delete('/monitor/watchlist')
        response_patch = client.patch('/monitor/watchlist')
        
        assert response_post.status_code == 405, "POST should not be allowed"
        assert response_put.status_code == 405, "PUT should not be allowed"
        assert response_delete.status_code == 405, "DELETE should not be allowed"
        assert response_patch.status_code == 405, "PATCH should not be allowed"

# ============================================================================
# TEST: DELETE /monitor/archive/:ticker error paths, edge cases, and DB/index behavior
# ============================================================================
class TestDeleteArchiveErrorAndEdges:
    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_not_found_returns_404(self, mock_connect, mock_delete, client):
        """
        Requirements 1,2,4,7,9,11: Not found must return 404 with error shape and include correct types.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Simulate not found
        mock_delete.return_value = SimpleNamespace(deleted_count=0)

        resp = client.delete('/monitor/archive/ZZZZZ')
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "error" in data and isinstance(data["error"], str)

    @patch('database.mongo_client.connect')
    def test_delete_archive_invalid_length_above_threshold_returns_400(self, mock_connect, client):
        """
        Requirements 2,4,7,9,12: Length > 10 must fail with 400; ensure raw input is used.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        too_long = "A" * 11
        resp = client.delete(f'/monitor/archive/{too_long}')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_valid_at_threshold_10_succeeds(self, mock_connect, mock_delete, client):
        """
        Requirements 1,2,4,7,9,12: Exactly 10 chars is valid and should succeed.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        ten = "A" * 10
        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        resp = client.delete(f'/monitor/archive/{ten.lower()}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and ten in data["message"]

    @patch('database.mongo_client.connect')
    def test_delete_archive_invalid_characters_returns_400(self, mock_connect, client):
        """
        Requirements 2,3,4,7,9: Invalid characters must be rejected with 400.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        invalid = "AAPL@"
        resp = client.delete(f'/monitor/archive/{invalid}')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    @patch('database.mongo_client.connect')
    def test_delete_archive_whitespace_ticker_below_threshold_returns_400(self, mock_connect, client):
        """
        Requirements 2,4,7,9,12,13: Just-below threshold via whitespace only should fail gracefully with 400.
        Use raw URL-encoded space to simulate raw HTTP input.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # %20 decodes to whitespace -> invalid
        resp = client.delete('/monitor/archive/%20')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_idempotent_second_call_returns_404(self, mock_connect, mock_delete, client):
        """
        Requirements 1,2,4,7,9,11: First delete removes 1 item -> 200; second call returns 404 (idempotent behavior).
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # First call: deleted_count=1, second call: deleted_count=0
        mock_delete.side_effect = [
            SimpleNamespace(deleted_count=1),
            SimpleNamespace(deleted_count=0),
        ]

        path = '/monitor/archive/NET'
        r1 = client.delete(path)
        assert r1.status_code == 200
        data1 = json.loads(r1.data)
        assert "message" in data1 and "NET" in data1["message"]

        r2 = client.delete(path)
        assert r2.status_code == 404
        data2 = json.loads(r2.data)
        assert "error" in data2 and isinstance(data2["error"], str)

    @patch('database.mongo_client.connect')
    def test_delete_archive_db_connection_failure_returns_503(self, mock_connect, client):
        """
        Requirements 2,3,4,7,9: DB connection failures must return 503 and not leak internals.
        """
        from pymongo.errors import ConnectionFailure
        mock_connect.side_effect = ConnectionFailure("Cannot connect to MongoDB")

        resp = client.delete('/monitor/archive/CRM')
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

class TestArchiveHardDeleteDBBehavior:
    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_hard_delete_does_not_require_ttl_index(self, mock_connect, mock_delete, client):
        """
        Requirements 3,4,5: Hard delete is immediate and orthogonal to TTL indexes.
        Assert that endpoint performs delete without index manipulation calls.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Simulate successful deletion
        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        # Track that no index creation is attempted as part of deletion
        arch_coll = MagicMock()
        mock_db.archived_watchlist_items = arch_coll
        mock_db.archived_watchlist_items = arch_coll

        resp = client.delete('/monitor/archive/ZEN')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and "ZEN" in data["message"]

        # No index creation should be invoked for hard delete path
        assert not arch_coll.create_index.called


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
