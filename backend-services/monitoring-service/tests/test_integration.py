# backend-services/monitoring-service/tests/test_integration.py
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd

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

@patch("market_leaders.post_returns_batch")
@patch("market_leaders.get_day_gainers_map")
@patch("market_leaders.get_sector_industry_map")
@patch("market_leaders.get_52w_highs")
def test_get_internal_leaders_handles_failures(mock_52w, mock_sector, mock_day_gainers, mock_returns):
    client = flask_app.test_client()

    mock_52w.return_value = None
    mock_sector.return_value = {}
    mock_day_gainers.return_value = {}
    mock_returns.return_value = {}

    resp = client.get("/monitor/internal/leaders")
    # internal leaders now returns 200 with empty MarketLeaders on total failure
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"leading_industries": []}

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


@patch("market_leaders.get_52w_highs")
def test_integration_internal_leaders_top_5_selection(mock_52w):
    """
    Verify top 5 industries are selected (breadth) and emitted via MarketLeaders.
    """
    client = flask_app.test_client()

    mock_quotes = [
        {"industry": "Tech"}, {"industry": "Tech"}, {"industry": "Tech"}, {"industry": "Tech"},  # 4
        {"industry": "Finance"}, {"industry": "Finance"}, {"industry": "Finance"},               # 3
        {"industry": "Retail"}, {"industry": "Retail"},                                         # 2
        {"industry": "Health"}, {"industry": "Health"},                                         # 2
        {"industry": None},  # Unclassified: 1
        {"industry": "Energy"},                                                                 # 1
        {"industry": "Industrial"},                                                             # 1
    ]
    mock_52w.return_value = mock_quotes

    resp = client.get("/monitor/internal/leaders")
    assert resp.status_code == 200
    data = resp.get_json()
    
    # The contract is {"leading_industries": [...]}
    industries = data["leading_industries"]
    # Check names only, since stocks are returned not breadth_count
    assert len(industries) == 5
    names = [item["industry"] for item in industries]
    assert "Tech" in names
    assert "Finance" in names
    assert "Retail" in names
    assert "Health" in names
    # 5th is one of the ties
    assert any(n in names for n in ["Unclassified", "Energy", "Industrial"])