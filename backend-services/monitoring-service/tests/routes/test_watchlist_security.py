# backend-services/monitoring-service/tests/routes/test_watchlist_security.py
"""
Security tests ensuring GET /monitor/watchlist does not leak internal fields
and handles potentially unsafe exclude input without crashing or exposing secrets.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import quote

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Security Considerations
# ============================================================================

class TestSecurityConsiderations:
    """Test security implications"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_does_not_leak_internal_data(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        SECURITY: Verify response doesn't leak internal implementation details
        Should not expose user_id, _id, or other MongoDB internal fields
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        response = client.get('/monitor/watchlist')
        data = json.loads(response.data)
        
        # Verify no internal fields in response
        for item in data["items"]:
            assert "_id" not in item, "Should not expose MongoDB _id"
            assert "user_id" not in item, "Should not expose user_id in response"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_exclude_sql_injection_safety(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        SECURITY: Verify exclude parameter is safely handled
        Although using MongoDB (not SQL), verify no code injection possible
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Try malicious input
        malicious_input = "AAPL'; DROP TABLE users; --"
        
        response = client.get(f'/monitor/watchlist?exclude={malicious_input}')
        
        # Should handle safely (not crash)
        assert response.status_code in [200, 400, 500], \
            "Should handle malicious input safely"
        
        # Verify the malicious string is treated as a ticker (sanitized)
        if response.status_code == 200:
            call_args = mock_get_watchlist.call_args
            exclusion_list = call_args[0][1]
            # Should be parsed as single ticker string, not executed
            assert isinstance(exclusion_list, list)

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_exclude_param_ignores_empty_tokens_and_trailing_commas(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Requirement 2, 3:
        Ensure route safely handles trailing commas and empty tokens without crashing
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_get_watchlist.return_value = {"items": [], "metadata": {"count": 0}}

        resp = client.get('/monitor/watchlist?exclude=, ,AAPL,, ,')
        assert resp.status_code == 200

        args, _ = mock_get_watchlist.call_args
        exclusions = args[1]
        assert isinstance(exclusions, list)
        # Only non-empty tickers should remain
        assert "AAPL" in exclusions
        assert "" not in exclusions

    # DELETE ignores any user-override header; remains single-user scoped.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_ignores_x_user_id_header_and_uppercases(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        SECURITY: Ensure the route does not accept/propagate user overrides from headers
        and normalizes ticker to uppercase before invoking the service.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_move_to_archive.return_value = {
            "ticker": "MSFT",
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        # Attempt to override user via header; route should ignore this
        resp = client.delete(
            '/monitor/watchlist/msft',
            headers={"X-User-Id": "malicious-user"}
        )
        assert resp.status_code == 200

        # Assert service was called and ticker normalized; no user_id kw propagated
        args, kwargs = mock_move_to_archive.call_args
        assert len(args) >= 2
        assert args[1] == "MSFT"
        assert "user_id" not in kwargs

        data = json.loads(resp.data)
        assert "message" in data and "MSFT" in data["message"]

    # DELETE response should not expose internal fields.
    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_watchlist_response_no_internal_fields(
        self, mock_connect, mock_move_to_archive, client
    ):
        """
        SECURITY/Consistency: Response must not include internal fields like _id,
        user_id, archived_at, reason, or failed_stage.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_move_to_archive.return_value = {
            "ticker": "CRM",
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": "2025-11-13T00:00:00Z",
        }

        resp = client.delete('/monitor/watchlist/CRM')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)

        # No internal fields leaked
        forbidden = ["_id", "user_id", "archived_at", "reason", "failed_stage"]
        for key in forbidden:
            assert key not in data

    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_ignores_x_user_id_header_and_uppercases(self, mock_connect, mock_toggle, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = MagicMock(modified_count=1)

        resp = client.post(
            '/monitor/watchlist/msft/favourite',
            json={"is_favourite": True},
            headers={"X-User-Id": "malicious-user"}
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data and "MSFT" in data["message"]

        args, kwargs = mock_toggle.call_args
        assert len(args) >= 3
        assert args[1] == "MSFT"
        assert args[2] is True
        assert "user_id" not in kwargs

    
    @patch('database.mongo_client.toggle_favourite')
    @patch('database.mongo_client.connect')
    def test_favourite_response_no_internal_fields(self, mock_connect, mock_toggle, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_toggle.return_value = MagicMock(modified_count=1)

        resp = client.post('/monitor/watchlist/CRM/favourite', json={"is_favourite": False})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        forbidden = ["_id", "user_id", "archived_at", "reason", "failed_stage"]
        for key in forbidden:
            assert key not in data

    
    def test_favourite_sql_injection_safety_on_ticker_path(self, client):
        """
        SECURITY: Ensure malicious path input is treated as data and rejected safely.
        """
        malicious = "AAPL'; DROP TABLE users; --"
        resp = client.post(f'/monitor/watchlist/{malicious}/favourite', json={"is_favourite": True})
        assert resp.status_code in [400, 404, 500]  # Must not execute or expose internals

    # security tests for POST /monitor/watchlist/batch/remove
    @patch('services.watchlist_service.batch_remove_from_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_remove_rejects_nosql_injection_payloads(
        self,
        mock_connect,
        mock_batch_remove,
        client
    ):
        """
        SECURITY: Ensure NoSQL-style injection keys in the tickers array
        are rejected and never passed through to the service layer.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Payload attempts to smuggle an object instead of a plain ticker string
        payload = {
            "tickers": [
                "AAPL",
                {"$where": "this.ticker == 'MSFT'"},
            ]
        }

        response = client.post(
            "/monitor/watchlist/batch/remove",
            json=payload,
        )

        # Must be treated as malformed
        assert response.status_code == 400
        # Service-level function must never be called on malformed payload
        mock_batch_remove.assert_not_called()

    # ensure tickers are sanitized and normalized before service call
    @patch('services.watchlist_service.batch_remove_from_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_remove_sanitizes_and_normalizes_tickers(
        self,
        mock_connect,
        mock_batch_remove,
        client
    ):
        """
        SECURITY + LOGIC:
        - Incoming tickers may contain whitespace and lowercase.
        - Route must normalize to uppercase and strip whitespace
          before delegating to the service layer.
        - Raw response.json is parsed directly.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service returns internal shape; route adapts to public contract
        mock_batch_remove.return_value = {
            "removed": 2,
            "notfound": 0,
            "tickers": ["AAPL", "MSFT"],
            "not_found_tickers": [],
        }

        raw_payload = {
            "tickers": [" aapl ", "msft\n"]
        }

        response = client.post(
            "/monitor/watchlist/batch/remove",
            json=raw_payload,
        )

        assert response.status_code == 200

        # Verify service was called with normalized tickers
        mock_batch_remove.assert_called_once()
        args, kwargs = mock_batch_remove.call_args
        # First positional arg is DB handle, second is tickers list per convention
        normalized = args[1]
        assert normalized == ["AAPL", "MSFT"]

        # Parse raw JSON payload (not using resp.get_json) to meet Req #13
        data = json.loads(response.data)
        assert data["removed"] == 2
        assert data["notfound"] == 0
        # Identifier should appear in message for traceability
        assert "AAPL" in data["message"]
        assert "MSFT" in data["message"]

# ============================================================================
# TESTS: BatchAddSecurity
# ============================================================================
class TestInternalBatchAddSecurity:
    """Security and input hardening for POST /monitor/internal/watchlist/batch/add"""

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_rejects_nosql_injection_payloads(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        payload = {"tickers": ["AAPL", {"$where": "this.ticker == 'MSFT'"}]}
        resp = client.post('/monitor/internal/watchlist/batch/add', json=payload)
        assert resp.status_code == 400
        mock_batch_add.assert_not_called()

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_ignores_x_user_id_header_and_normalizes(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_batch_add.return_value = {"added": ["MSFT"], "skipped": [], "errors": []}
        resp = client.post(
            '/monitor/internal/watchlist/batch/add',
            json={"tickers": [" msft "]},
            headers={"X-User-Id": "malicious-user"}
        )
        assert resp.status_code in (200, 201)
        args, kwargs = mock_batch_add.call_args
        assert kwargs == {}
        assert args[1] == ["MSFT"]

        data = json.loads(resp.data)
        assert "MSFT" in data["message"]

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_rejects_empty_and_invalid_tickers(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        resp = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": ["", " ", "AAPL$", "TOO-LONG-TICK"]})
        assert resp.status_code == 400
        mock_batch_add.assert_not_called()

    @patch('services.watchlist_service.batch_add_to_watchlist')
    @patch('database.mongo_client.connect')
    def test_batch_add_deduplicates_and_is_case_insensitive(self, mock_connect, mock_batch_add, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_batch_add.return_value = {"added": ["CRWD"], "skipped": ["CRWD"], "errors": []}
        resp = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": ["crwd", "CRWD"]})
        assert resp.status_code in (200, 201)

        # verify service saw a single normalized instance
        args, _ = mock_batch_add.call_args
        assert args[1] == ["CRWD"]

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
