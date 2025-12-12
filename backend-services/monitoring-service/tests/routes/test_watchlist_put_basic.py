# backend-services/monitoring-service/tests/routes/test_watchlist_put_basic.py
"""

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
# TEST: Internal Watchlist Endpoint - Basic Functionality
# ============================================================================

class TestPutAddTickerRoute:
    """Tests for PUT /monitor/watchlist/<ticker>"""

    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_add_new_ticker_returns_201_and_defaults(
        self, mock_connect, mock_add_or_upsert, client
    ):
        """
        When adding a new ticker:
        - returns 201 Created
        - response message 'added to watchlist'
        - item defaults: is_favourite False, status 'Watch', last_refresh_status UNKNOWN/PENDING
        - validates the item shape and types
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Service indicates a new insert (not existed)
        mock_add_or_upsert.return_value = {
            "success": True,
            "ticker": "AAPL",
            "existed": False,
            "reintroduced": False,
        }

        resp = client.put('/monitor/watchlist/AAPL')
        assert resp.status_code == 201, "New add should return 201 Created"
        assert resp.content_type == 'application/json'

        data = json.loads(resp.data)
        # expected top-level keys
        assert "message" in data
        assert data["message"].lower().startswith("added to watchlist")

        assert "item" in data, "Response should return created item preview"
        item = data["item"]

        # Verify defaults and shape (consistent with project naming)
        assert item["ticker"] == "AAPL"
        assert item["status"] == "Watch"
        assert item["is_favourite"] is False
        assert item["last_refresh_status"] in ("PENDING", "UNKNOWN")

    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_readding_existing_ticker_returns_200_idempotent(self, mock_connect, mock_add_or_upsert, client):
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_add_or_upsert.return_value = {"success": True, "ticker": "AAPL", "existed": True, "reintroduced": False}

        resp = client.put('/monitor/watchlist/AAPL')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "message" in data
        assert "already" in data["message"].lower() or "exists" in data["message"].lower()
        item = data["item"]
        assert item["ticker"] == "AAPL"
        assert item["status"] == "Watch"
        assert item["is_favourite"] is False
        assert item["last_refresh_status"] in ("PENDING", "UNKNOWN")


    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_reintroduction_deletes_from_archive_indirectly(
        self, mock_connect, mock_add_or_upsert, client
    ):
        """
        Re-introduction semantics: if service reports reintroduced=True,
        this implies the archive deletion has occurred in the same operation sequence.
        Route should return 201 or 200 depending on 'existed' while remaining thin.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Reintroduced from archive but as a fresh insert (existed=False)
        mock_add_or_upsert.return_value = {
            "success": True,
            "ticker": "CRM",
            "existed": False,
            "reintroduced": True,
        }

        resp = client.put('/monitor/watchlist/CRM')
        assert resp.status_code == 201, "Fresh insert should be 201 even if reintroduced"

        data = json.loads(resp.data)
        assert "item" in data
        assert data["item"]["ticker"] == "CRM"

    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_security_ignore_client_is_favourite_field(
        self, mock_connect, mock_add_or_upsert, client
    ):
        """
        SECURITY: Client-supplied is_favourite must be ignored by route.
        The route should not accept business fields; only ticker is validated and passed.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_add_or_upsert.return_value = {"success": True, "ticker": "MSFT", "existed": False, "reintroduced": False}

        resp = client.put('/monitor/watchlist/MSFT', json={"is_favourite": True})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["item"]["ticker"] == "MSFT"
        assert data["item"]["is_favourite"] is False

    @patch('services.watchlist_service.add_or_upsert_ticker')
    @patch('database.mongo_client.connect')
    def test_route_calls_service_thin_controller(
        self, mock_connect, mock_add_or_upsert, client
    ):
        """
        Ensure app route is thin: validates ticker, delegates to service, maps status code.
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_add_or_upsert.return_value = {
            "success": True,
            "ticker": "NET",
            "existed": True,
            "reintroduced": False,
        }

        resp = client.put('/monitor/watchlist/net') # lowercase should normalize
        assert resp.status_code == 200

        # Verify service delegation with normalized ticker and a user id arg present
        # Note: service signature below is tested in service tests (db, user_id, ticker)
        args, kwargs = mock_add_or_upsert.call_args
        assert args[0] is mock_db
        assert isinstance(args[1], str)
        assert args[2] == "NET"  # normalized before delegating

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
