# backend-services/monitoring-service/tests/contracts/test_watchlist_contract_validation.py
"""
Contract validation tests for DELETE /monitor/archive/:ticker using contracts.py,
asserting strict success/error schemas and ticker path constraints/thresholds.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from flask import Flask
from urllib.parse import quote

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Pydantic Validation
# ============================================================================

class TestPydanticValidation:
    """Test Pydantic validation of WatchlistListResponse"""
    @patch("services.watchlist_service.get_watchlist")
    @patch("database.mongo_client.connect")
    def test_watchlist_status_values_within_allowed_ui_set(
        self,
        mock_connect,
        mock_get_watchlist,
        client,
        sample_watchlist_response,
    ):
        """Status field must always be one of the allowed UI labels."""
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        items = [
            {"ticker": "PEND", "status": "Pending", "last_refresh_status": "PENDING"},
            {"ticker": "FAIL", "status": "Failed", "last_refresh_status": "FAIL"},
            {"ticker": "WATCH", "status": "Watch", "last_refresh_status": "PASS"},
            {"ticker": "ALRT", "status": "Buy Alert", "last_refresh_status": "PASS"},
            {"ticker": "READY", "status": "Buy Ready", "last_refresh_status": "PASS"},
        ]
        base = dict(sample_watchlist_response)
        base["items"] = [
            dict(base["items"][0], **i) for i in items
        ]
        mock_get_watchlist.return_value = base

        resp = client.get("/monitor/watchlist")
        assert resp.status_code == 200
        data = resp.get_json()

        allowed = {"Pending", "Failed", "Watch", "Buy Alert", "Buy Ready"}
        for item in data["items"]:
            assert item["status"] in allowed
            assert isinstance(item["ticker"], str)

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_validates_against_pydantic_model(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        CRITICAL: Verify response is validated against WatchlistListResponse Pydantic model
        This ensures type safety and contract compliance
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        response = client.get('/monitor/watchlist')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Verify all required fields are present
        assert "items" in data
        assert "metadata" in data
        
        # Verify each item has required fields
        for item in data["items"]:
            required_fields = [
                "ticker", "status", "date_added", "is_favourite",
                "last_refresh_status", "last_refresh_at", "failed_stage",
                "current_price", "pivot_price", "pivot_proximity_percent", "is_leader"
            ]
            for field in required_fields:
                assert field in item, f"Item missing required field: {field}"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_validation_failure_returns_500(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Verify that Pydantic validation failure returns 500 error
        This tests the validation layer in the route
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        
        # Return invalid response (missing required fields)
        invalid_response = {
            "items": [
                {"ticker": "AAPL"}  # Missing many required fields
            ]
            # Missing metadata
        }
        mock_get_watchlist.return_value = invalid_response
        
        response = client.get('/monitor/watchlist')
        
        # Should return 500 due to validation failure
        assert response.status_code == 500, "Invalid response should return 500"
        
        data = json.loads(response.data)
        assert "error" in data, "Error response should have 'error' field"

    @patch("services.watchlist_service.get_watchlist")
    @patch("database.mongo_client.connect")
    def test_watchlist_response_validates_against_watchlist_list_response_contract_with_status(
        self,
        mock_connect,
        mock_get_watchlist,
        client,
        sample_watchlist_response,
    ):
        """
        Contract: GET /monitor/watchlist response must include status field and
        remain compatible with WatchlistListResponse Pydantic model.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Reuse sample response structure but adjust statuses for richer cases
        items = [
            {
                "ticker": "PEND",
                "status": "Pending",
                "last_refresh_status": "PENDING",
            },
            {
                "ticker": "FAIL",
                "status": "Failed",
                "last_refresh_status": "FAIL",
            },
            {
                "ticker": "WATCH",
                "status": "Watch",
                "last_refresh_status": "PASS",
            },
            {
                "ticker": "ALRT",
                "status": "Buy Alert",
                "last_refresh_status": "PASS",
            },
            {
                "ticker": "READY",
                "status": "Buy Ready",
                "last_refresh_status": "PASS",
            },
        ]
        response_body = dict(sample_watchlist_response)
        response_body["items"] = items

        mock_get_watchlist.return_value = response_body

        resp = client.get("/monitor/watchlist")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)
        # Ensure all items present and structurally valid
        assert len(data["items"]) == 5
        symbols = {i["ticker"] for i in data["items"]}
        assert symbols == {"PEND", "FAIL", "WATCH", "ALRT", "READY"}
        # Each item must have a status of type str
        for item in data["items"]:
            assert isinstance(item["status"], str)

    @patch("services.watchlist_service.get_watchlist")
    @patch("database.mongo_client.connect")
    def test_watchlist_contract_rejects_unknown_status_label_as_500(
        self,
        mock_connect,
        mock_get_watchlist,
        client,
        sample_watchlist_response,
    ):
        """
        If service returns an unknown status label, route-level validation should fail with 500.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        invalid_body = dict(sample_watchlist_response)
        invalid_items = list(invalid_body["items"])
        # Inject an invalid status label while keeping last_refresh_status valid
        invalid_items[0] = dict(invalid_items[0], status="InvalidStatus")
        invalid_body["items"] = invalid_items

        mock_get_watchlist.return_value = invalid_body

        resp = client.get("/monitor/watchlist")
        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert isinstance(data["error"], str)

    @patch("services.watchlist_service.get_watchlist")
    @patch("database.mongo_client.connect")
    def test_watchlist_response_allows_empty_items_and_zero_metadata(
        self,
        mock_connect,
        mock_get_watchlist,
        client,
        sample_empty_watchlist_response,
    ):
        """
        Empty watchlist (items []) with metadata.count 0 must be a valid 200 response.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_empty_watchlist_response

        resp = client.get("/monitor/watchlist")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "items" in data
        assert isinstance(data["items"], list)
        assert data["items"] == []

        assert "metadata" in data
        assert isinstance(data["metadata"], dict)
        assert data["metadata"].get("count") == 0

    @patch("services.watchlist_service.get_watchlist")
    @patch("database.mongo_client.connect")
    def test_watchlist_contract_preserves_leadership_flag_type(
        self,
        mock_connect,
        mock_get_watchlist,
        client,
        sample_watchlist_response,
    ):
        """
        is_leader must always be present and strictly boolean for every item.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_get_watchlist.return_value = sample_watchlist_response

        resp = client.get("/monitor/watchlist")
        assert resp.status_code == 200
        data = resp.get_json()

        for item in data["items"]:
            assert "is_leader" in item
            assert isinstance(item["is_leader"], bool)

# DELETE path validation and normalization checks
class TestDeleteContractValidation:
    """Validation and normalization for DELETE /monitor/watchlist/:ticker"""

    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_accepts_allowed_characters(self, mock_connect, mock_move_to_archive, client):
        # Allowed chars typically include [A-Z0-9.-]; ensure acceptance at route layer
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_move_to_archive.return_value = {"ticker": "BRK.B", "reason": "MANUAL_DELETE", "failed_stage": None, "archived_at": "T"}

        resp = client.delete('/monitor/watchlist/BRK.B')
        assert resp.status_code in (200, 404)

        mock_move_to_archive.return_value = {"ticker": "RDS-A", "reason": "MANUAL_DELETE", "failed_stage": None, "archived_at": "T"}
        resp2 = client.delete('/monitor/watchlist/RDS-A')
        assert resp2.status_code in (200, 404)

    @patch('database.mongo_client.connect')
    def test_delete_rejects_disallowed_characters(self, mock_connect, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        bad_inputs = ("AAPL$", "GOOGL@", "AAPL!", "TS%20LA")
        for bad in bad_inputs:
            r = client.delete(f'/monitor/watchlist/{bad}')
            assert r.status_code == 400
            data = r.get_json()
            assert "error" in data and isinstance(data["error"], str)

    @patch('services.watchlist_service.move_to_archive')
    @patch('database.mongo_client.connect')
    def test_delete_normalizes_uppercase_in_contract_surface(self, mock_connect, mock_move, client):
        mock_db = MagicMock(); mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_move.return_value = {"ticker": "AAPL", "reason": "MANUAL_DELETE", "failed_stage": None, "archived_at": "T"}

        resp = client.delete('/monitor/watchlist/aapl')
        assert resp.status_code in (200, 404)
        # Even if not found, normalized ticker should be surfaced in message if success occurs
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert "AAPL" in data["message"]

# ============================================================================
# Test: Contract checks for POST /monitor/internal/watchlist/refresh-status.
# ============================================================================
class TestRefreshStatusRouteContract:
    """Contract checks for POST /monitor/internal/watchlist/refresh-status."""

    @patch("services.update_orchestrator.refresh_watchlist_status")
    @patch("database.mongo_client.connect")
    def test_refresh_status_contract_matches_summary_shape(
        self,
        mock_connect,
        mock_refresh,
        client,
    ):
        """Response must include message and integer counts for updated, archived, and failed."""
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_refresh.return_value = {
            "message": "Watchlist refresh completed successfully.",
            "updated_items": 32,
            "archived_items": 5,
            "failed_items": 0,
        }

        resp = client.post("/monitor/internal/watchlist/refresh-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert isinstance(data["message"], str)
        assert isinstance(data["updated_items"], int)
        assert isinstance(data["archived_items"], int)
        assert isinstance(data["failed_items"], int)

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
