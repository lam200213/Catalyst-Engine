# backend-services/monitoring-service/tests/integration/test_integration_market_health.py
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

def _series(days=252, base=100.0, step=0.5):
    # Build a monotonically increasing series to ensure last close > SMA50 (Bullish)
    start = datetime(2024, 1, 1)
    points = []
    for i in range(days):
        o = base + i * step
        h = o + 1
        l = o - 1
        c = o + 0.2  # close slightly above open
        points.append({
            "formatted_date": (start + timedelta(days=i)).date().isoformat(),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 1,
        })
    return points

def test_health_ok():
    client = flask_app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "healthy"}


@patch("market_health_utils.get_breadth")
@patch("market_leaders.get_52w_highs")
@patch("market_health_utils.post_price_batch")
def test_get_monitor_market_health_dependency_mocks(mock_post_batch, mock_get_52w, mock_breadth):
    client = flask_app.test_client()

    idx_payload = {"success": {"^GSPC": _series(), "^DJI": _series(base=200), "^IXIC": _series(base=300)}}
    mock_post_batch.return_value = idx_payload

    # Return dict directly from the helper to avoid cross-patch interference
    mock_breadth.return_value = {"new_highs": 120, "new_lows": 40, "high_low_ratio": 3.0}

    leaders_quotes = [{"industry": "Tech", "ticker": "A"}, {"industry": "Tech", "ticker": "B"}]
    mock_get_52w.return_value = leaders_quotes

    resp = client.get("/monitor/market-health")
    assert resp.status_code == 200
    data = resp.get_json()
    mo = data["market_overview"]
    assert mo["new_highs"] == 120
    assert mo["new_lows"] == 40
    assert mo["high_low_ratio"] == 3.0

    # mirroring the API compliance test’s structure requirements
    assert "leaders_by_industry" in data
    assert "leading_industries" in data["leaders_by_industry"]
    assert isinstance(data["leaders_by_industry"]["leading_industries"], list)

@patch("market_health_utils.post_price_batch")
@patch("market_health_utils.get_breadth")
def test_integration_internal_health_no_universe(mock_get_breadth, mock_post_batch):
    """
    Integration-test /monitor/internal/health: verify outputs stable without universe
    and consistent ratio against mocked data-service response.
    """
    client = flask_app.test_client()

    idx_payload = {"success": {"^GSPC": _series(), "^DJI": _series(), "^IXIC": _series()}}
    mock_post_batch.return_value = idx_payload
    mock_get_breadth.return_value = {"new_highs": 100, "new_lows": 25, "high_low_ratio": 4.0}

    # Make request without any universe parameter
    resp = client.get("/monitor/internal/health")
    assert resp.status_code == 200
    data = resp.get_json()

    # Verify output is stable and reflects mocked breadth data
    assert data["new_highs"] == 100
    assert data["new_lows"] == 25
    assert data["high_low_ratio"] == 4.0
    assert "market_stage" in data
