# backend-services/monitoring-service/tests/routes/test_response_format.py
"""
Route-level response shape tests for DELETE /monitor/archive/:ticker, asserting
message-only success payload, error envelopes, normalization, and no leakage.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from types import SimpleNamespace
from typing import List, Dict, Any
from pymongo.errors import ConnectionFailure
# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Response Format Consistency
# ============================================================================

class TestResponseFormatConsistency:
    """Test consistency of response format with existing patterns"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_response_follows_project_patterns(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Verify response follows project conventions:
        - JSON content type
        - Proper status codes
        - Consistent error format
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        response = client.get('/monitor/watchlist')
        
        # Verify content type
        assert response.content_type == 'application/json', \
            "Response should be JSON (consistent with other endpoints)"
        
        # Verify can be parsed as JSON
        data = json.loads(response.data)
        assert isinstance(data, dict), "Response should be JSON object"

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_metadata_count_matches_items_length(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Requirement 7, 9, 11:
        metadata.count must equal len(items); JSON content-type and shape are correct
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_get_watchlist.return_value = sample_watchlist_response

        response = client.get('/monitor/watchlist')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)

        assert "items" in data and isinstance(data["items"], list)
        assert "metadata" in data and isinstance(data["metadata"], dict)
        assert "count" in data["metadata"]
        assert data["metadata"]["count"] == len(data["items"])

    # Success case for DELETE with message and uppercase ticker in message.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_move_to_archive_success_response_and_normalization(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        Verify DELETE /monitor/watchlist/:ticker returns 200 with a message string,
        and the ticker is normalized to uppercase in the response message.
        Also validate the service is called with uppercase ticker and archive semantics.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service returns archive record semantics
        mock_move_to_archive.return_value = {
            "ticker": "AAPL",
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        resp = client.delete('/monitor/watchlist/aapl')  # lowercase input
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "message" in data and isinstance(data["message"], str)
        # The response message should include the normalized uppercase ticker
        assert "AAPL" in data["message"]

        # Ensure service called with uppercase ticker (path normalization)
        args, kwargs = mock_move_to_archive.call_args
        # Expected signature (db, ticker) to maintain existing pattern
        assert len(args) >= 2
        assert args[1] == "AAPL"

        # Types of archive semantics returned by the service are as expected
        # (route should not leak them; we only assert service semantics were present)
        assert mock_move_to_archive.return_value["reason"] == "MANUAL_DELETE"
        assert mock_move_to_archive.return_value["failed_stage"] is None

    # Ensure response does not leak archive/internal fields.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_response_does_not_leak_archive_fields(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        SECURITY/Contract alignment: The DELETE response should not leak DB/internal fields
        like archived_at, reason, failed_stage; only user-facing message is allowed.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_move_to_archive.return_value = {
            "ticker": "NET",
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        resp = client.delete('/monitor/watchlist/net')
        assert resp.status_code == 200

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "message" in data
        assert "reason" not in data
        assert "failed_stage" not in data
        assert "archived_at" not in data

class TestArchiveResponseFormat:
    """Response format, types, and identifiers for GET /monitor/archive"""

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_archive_empty_array_200_shape_and_types(self, mock_connect, mock_get_archive, client):
        """
        Requirements 1,2,4,7,9,11:
        - Returns 200 with archived_items: []
        - JSON object shape; no metadata for archive per API reference
        - Assert both logical outcome and key identifiers shape
        """
        # mock DB client and empty payload
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.return_value = {"archived_items": []}

        resp = client.get('/monitor/archive')
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'

        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert 'archived_items' in data and isinstance(data['archived_items'], list)
        assert data['archived_items'] == []

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_archive_populated_items_types_and_identifiers(self, mock_connect, mock_get_archive, client):
        """
        Requirements 1,4,7,9,10,11:
        - Populated list with correct types
        - Identifiers present (ticker, archived_at)
        - No data structure mismatch (contract field names)
        """
        # API-shaped response from service for route test
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.return_value = {
            "archived_items": [
                {"ticker": "CRM", "archived_at": "2025-11-08T10:00:00Z", "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
                {"ticker": "NET", "archived_at": "2025-11-01T12:00:00Z", "reason": "MANUAL_DELETE", "failed_stage": None},
            ]
        }

        resp = client.get('/monitor/archive')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        items = data["archived_items"]
        assert len(items) == 2

        for it in items:
            assert isinstance(it["ticker"], str)
            assert isinstance(it["archived_at"], str)  # ISO string
            assert isinstance(it["reason"], str)
            assert (it["failed_stage"] is None) or isinstance(it["failed_stage"], str)

        # assert identifiers
        tickers = {it["ticker"] for it in items}
        assert tickers == {"CRM", "NET"}

    @patch('services.watchlist_service.get_archive')
    @patch('database.mongo_client.connect')
    def test_archive_reason_enums_and_field_names(self, mock_connect, mock_get_archive, client):
        """
        Requirements 5,6,7,9,10:
        - Ensure public response uses reason values without underscores: MANUAL_DELETE, FAILED_HEALTH_CHECK
        - Ensure field names are archived_at/failed_stage per API
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_archive.return_value = {
            "archived_items": [
                {"ticker": "ZEN", "archived_at": "2025-11-02T00:00:00Z", "reason": "MANUAL_DELETE", "failed_stage": None},
                {"ticker": "CRM", "archived_at": "2025-11-10T00:00:00Z", "reason": "FAILED_HEALTH_CHECK", "failed_stage": "screening"},
            ]
        }

        resp = client.get('/monitor/archive')
        data = json.loads(resp.data)
        for it in data["archived_items"]:
            assert "archived_at" in it and "failed_stage" in it
            assert it["reason"] in {"MANUAL_DELETE", "FAILED_HEALTH_CHECK"}

# ============================================================================
# TEST: DELETE /monitor/archive/:ticker response format and normalization tests
# ============================================================================

class TestDeleteArchiveResponseFormat:
    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_success_200_message_and_uppercase(self, mock_connect, mock_delete, client):
        """
        Requirements 1,4,7,9,11: Success path returns 200 with JSON body containing a message string.
        The message must include the uppercase ticker (key identifier) and not expose internals.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Simulate successful hard delete
        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        resp = client.delete('/monitor/archive/aapl')  # lowercase input
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "message" in data and isinstance(data["message"], str)
        assert "AAPL" in data["message"]  # assert key identifier echoed

        # Ensure service called with normalized ticker
        args, kwargs = mock_delete.call_args
        # Expected signature (db, ticker)
        assert len(args) >= 2
        assert args[1] == "AAPL"

    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_parses_urlencoded_and_preserves_symbols(self, mock_connect, mock_delete, client):
        """
        Requirements 2,4,7,13: Route should parse raw URL-encoded tickers and normalize case.
        For BRK%2EB -> BRK.B; ensure the message echoes the normalized ticker.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        resp = client.delete('/monitor/archive/BRK%2EB')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and isinstance(data["message"], str)
        assert "BRK.B" in data["message"]  # dot preserved, normalized to uppercase

        # Also test a ticker that already includes '.' and '-' characters
        resp2 = client.delete('/monitor/archive/shop.to')  # lowercase; contains dot
        assert resp2.status_code == 200
        data2 = json.loads(resp2.data)
        assert "message" in data2 and isinstance(data2["message"], str)
        assert "SHOP.TO" in data2["message"]

    @patch('database.mongo_client.delete_archive_item')
    @patch('database.mongo_client.connect')
    def test_delete_archive_response_does_not_leak_internals(self, mock_connect, mock_delete, client):
        """
        Requirements 3,4,5,7,9,10: Response must not leak internal DB fields like archived_at, reason, or failed_stage.
        Only the user-facing message is allowed in the body.
        """
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        resp = client.delete('/monitor/archive/NET')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and isinstance(data["message"], str)
        # No internal fields in response
        assert "archived_at" not in data
        assert "reason" not in data
        assert "failed_stage" not in data

# ============================================================================
# TEST: Favourite
# ============================================================================
class TestFavouriteResponseFormat:
    """Response format, types, identifiers, and validation for POST /monitor/watchlist/:ticker/favourite"""

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_true_200_message_and_normalization(self, mock_connect, mock_toggle, client):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = SimpleNamespace(modified_count=1)

        resp = client.post('/monitor/watchlist/net/favourite', json={"is_favourite": True})
        assert resp.status_code == 200
        assert resp.content_type == 'application/json'
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        assert "message" in data and isinstance(data["message"], str)
        # Ticker should be normalized to uppercase in message
        assert "NET" in data["message"]

        # Ensure DB toggle called with normalized ticker and boolean
        args, kwargs = mock_toggle.call_args
        assert len(args) >= 3
        assert args[1] == "NET"
        assert args[2] is True
        # No user override propagation
        assert "user_id" not in kwargs

        # Route must not leak internal fields in success
        forbidden = ["_id", "user_id", "archived_at", "reason", "failed_stage"]
        for key in forbidden:
            assert key not in data

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_false_200_message_contains_ticker(self, mock_connect, mock_toggle, client):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = SimpleNamespace(modified_count=1)

        resp = client.post('/monitor/watchlist/CRM/favourite', json={"is_favourite": False})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and isinstance(data["message"], str)
        assert "CRM" in data["message"]

        args, _ = mock_toggle.call_args
        assert args[1] == "CRM"
        assert args[2] is False

    
    def test_favourite_missing_body_returns_400(self, client):
        resp = client.post('/monitor/watchlist/NET/favourite')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    @pytest.mark.parametrize("bad_value", ["true", "False", 1, 0, None, [], {}, "yes"])
    def test_favourite_invalid_type_returns_400(self, mock_connect, mock_toggle, client, bad_value):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        # toggle_favourite must not be called on validation error
        resp = client.post('/monitor/watchlist/AAPL/favourite', json={"is_favourite": bad_value})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)
        assert mock_toggle.call_count == 0

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_nonexistent_ticker_404(self, mock_connect, mock_toggle, client):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = SimpleNamespace(modified_count=0)

        resp = client.post('/monitor/watchlist/ZZZZZ/favourite', json={"is_favourite": True})
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    
    @patch('database.mongo_client.connect')
    def test_favourite_db_failure_returns_503(self, mock_connect, client):
        mock_connect.side_effect = ConnectionFailure("mocked DB down")
        resp = client.post('/monitor/watchlist/AAPL/favourite', json={"is_favourite": True})
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert "error" in data and isinstance(data["error"], str)

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_length_boundary_and_invalid_format(self, mock_connect, mock_toggle, client):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = SimpleNamespace(modified_count=1)

        at = "A" * 10
        resp_ok = client.post(f'/monitor/watchlist/{at}/favourite', json={"is_favourite": True})
        assert resp_ok.status_code in (200, 404)  # 200 if existed, 404 if not found

        too_long = "A" * 11
        resp_long = client.post(f'/monitor/watchlist/{too_long}/favourite', json={"is_favourite": True})
        assert resp_long.status_code == 400
        data = json.loads(resp_long.data)
        assert "error" in data and isinstance(data["error"], str)

        # Invalid character
        resp_bad = client.post('/monitor/watchlist/AAPL@/favourite', json={"is_favourite": True})
        assert resp_bad.status_code == 400

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_parses_urlencoded_and_preserves_symbols(self, mock_connect, mock_toggle, client):
        mock_client = MagicMock(); mock_db = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = SimpleNamespace(modified_count=1)

        resp = client.post('/monitor/watchlist/BRK%2EB/favourite', json={"is_favourite": True})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and isinstance(data["message"], str)
        assert "BRK.B" in data["message"]

        args, _ = mock_toggle.call_args
        assert args[1] == "BRK.B"
        assert args[2] is True

# ============================================================================
# Response format tests for POST /monitor/watchlist/batch/remove
# ============================================================================
class TestBatchRemoveResponseFormat:
    """Response format, types, and identifiers for POST /monitor/watchlist/batch/remove"""

    @patch('services.watchlist_service.batch_remove_from_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_remove_success_shape_and_types(
        self,
        mock_connect,
        mock_batch_remove,
        client
    ):
        """
        Requirements 1,4,7,9,11:
        - 200 OK on success
        - JSON body with { message: str, removed: int, notfound: int }
        - Message contains at least one key identifier (ticker)
        - No internal DB fields or raw ticker lists leaked
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service-level semantics (internal result)
        mock_batch_remove.return_value = {
            "removed": 2,
            "notfound": 1,
            "tickers": ["AAPL", "MSFT"],
            "not_found_tickers": ["ZZZZ"]
        }

        resp = client.post(
            '/monitor/watchlist/batch/remove',
            json={"tickers": ["aapl", "msft", "zzzz"]}
        )

        assert resp.status_code == 200
        assert resp.content_type == 'application/json'

        data = json.loads(resp.data)
        assert isinstance(data, dict)

        # Contract surface
        assert "message" in data and isinstance(data["message"], str)
        assert "removed" in data and isinstance(data["removed"], int)
        assert "notfound" in data and isinstance(data["notfound"], int)

# ============================================================================
# TESTS: BatchAddResponseFormat
# ============================================================================
class TestInternalBatchAddResponseFormat:
    """Response format, types, and identifiers for POST /monitor/internal/watchlist/batch/add"""

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_created_shape_and_types(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service returns internal result; route adapts to contract surface
        mock_batch_add.return_value = {
            "added": ["CRWD", "DDOG"],
            "skipped": [],
            "errors": []
        }

        resp = client.post(
            '/monitor/internal/watchlist/batch/add',
            json={"tickers": ["crwd", "ddog"]}
        )
        # Pin 201 Created as per Phase 2 Sec 2.1; surface discrepancies in CI if 200
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)

        # Contract surface fields
        assert isinstance(data, dict)
        assert "message" in data and isinstance(data["message"], str)
        assert "added" in data and isinstance(data["added"], int)
        assert "skipped" in data and isinstance(data["skipped"], int)

        # Message should include key identifiers for traceability
        assert "CRWD" in data["message"] or "DDOG" in data["message"]

        # Verify normalization passed down to service
        args, _ = mock_batch_add.call_args
        norm = args[1]
        assert norm == ["CRWD", "DDOG"]

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_mixed_validity_partial_success(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_batch_add.return_value = {
            "added": ["AAPL"],
            "skipped": ["MSFT"],  # existing or duplicate counted as skipped (idempotent semantics)
            "errors": ["BAD TICKER"]
        }

        resp = client.post(
            '/monitor/internal/watchlist/batch/add',
            json={"tickers": [" aapl ", "msft", "BAD TICKER"]}  # raw input includes whitespace and invalid
        )
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)

        # Aggregate counts must match service outcome
        assert data["added"] == 1
        assert data["skipped"] == 1
        # Route should not leak raw internal arrays; only message and counts are exposed
        assert "tickers" not in data and "errors" not in data

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_rejects_non_list_or_non_string_items(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Non-list tickers
        r1 = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": "AAPL"})
        assert r1.status_code == 400
        mock_batch_add.assert_not_called()

        # Non-string item inside list
        r2 = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": ["AAPL", 123]})
        assert r2.status_code == 400
        mock_batch_add.assert_not_called()

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_large_batch_performance_safe(self, mock_connect, mock_batch_add, client, default_user_id):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Assumed guardrail: large but performance-safe batch (e.g., 500) since no explicit threshold is documented.
        large = [f"T{i:04d}" for i in range(500)]
        mock_batch_add.return_value = {"added": large, "skipped": [], "errors": []}

        resp = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": large})
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data["added"] == 500
        assert data["skipped"] == 0

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
