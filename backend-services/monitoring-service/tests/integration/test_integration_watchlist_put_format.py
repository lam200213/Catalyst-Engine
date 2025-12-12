# backend-services/monitoring-service/tests/integration/test_integration_watchlist_put_format.py
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from urllib.parse import quote
import pandas as pd
import json

# Ensure local imports resolve when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from app import app as flask_app

def _mock_db_connect():
    mock_db = MagicMock()
    mock_client = MagicMock()
    return mock_client, mock_db

@patch('services.watchlist_service.add_or_upsert_ticker')
@patch('database.mongo_client.connect')
def test_put_watchlist_accepts_dot_tickers_brk_b(mock_connect, mock_add_or_upsert, client):
    """
    Accepts dot tickers like BRK.B and returns 201/200 with normalized ticker 'BRK.B'.
    """
    mock_connect.side_effect = _mock_db_connect
    mock_add_or_upsert.return_value = {
        "success": True, "ticker": "BRK.B", "existed": False, "reintroduced": False
    }

    resp = client.put('/monitor/watchlist/BRK.B')
    assert resp.status_code in (200, 201)
    data = json.loads(resp.data)
    assert data["item"]["ticker"] == "BRK.B"
    assert data["item"]["status"] == "Watch"
    assert data["item"]["last_refresh_status"] in ("PENDING", "UNKNOWN")

    # Verify service called with normalized ticker
    args, _ = mock_add_or_upsert.call_args
    assert args[2] == "BRK.B"

@patch('services.watchlist_service.add_or_upsert_ticker')
@patch('database.mongo_client.connect')
def test_put_watchlist_normalizes_lowercase_to_uppercase(mock_connect, mock_add_or_upsert, client):
    """
    Lowercase input like 'aapl' should be normalized to 'AAPL' before delegation and in response.
    """
    mock_connect.side_effect = _mock_db_connect
    mock_add_or_upsert.return_value = {
        "success": True, "ticker": "AAPL", "existed": True, "reintroduced": False
    }

    resp = client.put('/monitor/watchlist/aapl')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["item"]["ticker"] == "AAPL"

    # Verify service delegation received uppercase
    args, _ = mock_add_or_upsert.call_args
    assert args[2] == "AAPL"

@patch('services.watchlist_service.add_or_upsert_ticker')
@patch('database.mongo_client.connect')
def test_put_watchlist_accepts_urlencoded_dot(mock_connect, mock_add_or_upsert, client):
    """
    URL-encoded dot 'BRK%2EB' should be decoded to 'BRK.B' and processed correctly.
    """
    mock_connect.side_effect = _mock_db_connect
    mock_add_or_upsert.return_value = {
        "success": True, "ticker": "BRK.B", "existed": False, "reintroduced": False
    }

    resp = client.put('/monitor/watchlist/BRK%2EB')
    assert resp.status_code in (200, 201)
    data = json.loads(resp.data)
    assert data["item"]["ticker"] == "BRK.B"
