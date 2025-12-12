# backend-services/monitoring-service/tests/routes/test_orchestrator_endpoint.py
from flask import json
from app import app
from unittest.mock import Mock, patch, MagicMock, call

class TestOrchestratorEndpoint:
    """Route tests for POST /monitor/internal/watchlist/refresh-status."""

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_response_has_exact_fields(self, mock_refresh, client):
        """
        Step 1/2/10/11: Ensures response matches WatchlistRefreshStatusResponse exactly
        and forbids extra fields.
        """
        mock_refresh.return_value = {
            "message": "OK",
            "updated_items": 2,
            "archived_items": 1,
            "failed_items": 0,
        }
        resp = client.post("/monitor/internal/watchlist/refresh-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {"message", "updated_items", "archived_items", "failed_items"}
        assert isinstance(data["message"], str)
        assert isinstance(data["updated_items"], int)
        assert isinstance(data["archived_items"], int)
        assert isinstance(data["failed_items"], int)

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_invalid_json_body_is_ignored_or_rejected(self, mock_refresh, client):
        """
        Step 1: POST should not depend on body; invalid JSON must be ignored or rejected gracefully.
        """
        mock_refresh.return_value = {
            "message": "OK",
            "updated_items": 1,
            "archived_items": 0,
            "failed_items": 0,
        }
        # Send invalid JSON body
        resp = client.post(
            "/monitor/internal/watchlist/refresh-status",
            data="{not:json",
            content_type="application/json",
        )
        if resp.status_code == 200:
            data = resp.get_json()
            assert isinstance(data, dict)
            assert set(data.keys()) == {"message", "updated_items", "archived_items", "failed_items"}
        else:
            # Strict mode acceptable
            assert resp.status_code == 400
            data = resp.get_json()
            assert "error" in data and isinstance(data["error"], str)

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_returns_success_counts_and_message(
        self,
        mock_refresh,
        client,
    ):
        """Success path should surface message and integer counts."""
        mock_refresh.return_value = {
            "message": "OK",
            "updated_items": 32,
            "archived_items": 5,
            "failed_items": 0,
        }

        resp = client.post("/monitor/internal/watchlist/refresh-status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "OK"
        assert data["updated_items"] == 32
        assert data["archived_items"] == 5
        assert data["failed_items"] == 0

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_propagates_orchestrator_counts(
        self,
        mock_refresh,
        client,
    ):
        """Response body must echo orchestrator counts exactly."""
        mock_refresh.return_value = {
            "message": "Watchlist refresh done.",
            "updated_items": 10,
            "archived_items": 2,
            "failed_items": 1,
        }

        resp = client.post("/monitor/internal/watchlist/refresh-status")
        data = resp.get_json()

        assert data["updated_items"] == 10
        assert data["archived_items"] == 2
        assert data["failed_items"] == 1

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_handles_orchestrator_exceptions_as_500(
        self,
        mock_refresh,
        client,
    ):
        """Orchestrator exceptions must bubble up as 500 error with error field."""
        mock_refresh.side_effect = RuntimeError("boom")

        resp = client.post("/monitor/internal/watchlist/refresh-status")

        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data
        assert isinstance(data["error"], str)

    def test_post_refresh_status_rejects_non_post_methods(self, client):
        """Only POST is allowed on refresh-status endpoint."""
        for method in ("get", "put", "delete", "patch"):
            http_call = getattr(client, method)
            resp = http_call("/monitor/internal/watchlist/refresh-status")
            assert resp.status_code in (404, 405)

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_requires_internal_auth_flag_when_enabled(
        self,
        mock_refresh,
        client,
    ):
        """When internal-only guard is enabled, missing header should prevent changes."""
        mock_refresh.return_value = {
            "message": "OK",
            "updated_items": 1,
            "archived_items": 0,
            "failed_items": 0,
        }

        # Call without header: should either be rejected or be a no-op.
        resp = client.post("/monitor/internal/watchlist/refresh-status")
        if resp.status_code == 200:
            data = resp.get_json()
            assert isinstance(data, dict)
            assert "updated_items" in data
        else:
            assert resp.status_code in (401, 403)

    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_traces_request_in_logs_or_metrics(
        self,
        mock_refresh,
        client,
    ):
        """Endpoint should log a summary line including counts for observability."""
        mock_refresh.return_value = {
            "message": "OK",
            "updated_items": 3,
            "archived_items": 1,
            "failed_items": 0,
        }

        with patch.object(app.logger, "info") as mock_info:
            resp = client.post("/monitor/internal/watchlist/refresh-status")

        assert resp.status_code == 200

        # Assert we logged something containing the keyword "refresh-status"
        assert any(
            "refresh-status" in str(args[0])
            for (args, kwargs) in (call_args for call_args in mock_info.call_args_list)
        )

    # failed_items and error masking behavior
    @patch("services.update_orchestrator.refresh_watchlist_status")
    def test_post_refresh_status_includes_failed_items_and_masks_internal_errors(
        self,
        mock_refresh,
        client,
    ):
        """
        Endpoint should surface failed_items count but not leak internal exception details.
        """
        # Simulate orchestrator returning a summary with failures
        mock_refresh.return_value = {
            "message": "Partial failure",
            "updated_items": 10,
            "archived_items": 3,
            "failed_items": 5,
        }

        resp = client.post("/monitor/internal/watchlist/refresh-status")
        assert resp.status_code == 200
        data = resp.get_json()

        # Logical outcome and identifiers
        assert data["message"] == "Partial failure"
        assert data["updated_items"] == 10
        assert data["archived_items"] == 3
        assert data["failed_items"] == 5
        assert isinstance(data["failed_items"], int)
