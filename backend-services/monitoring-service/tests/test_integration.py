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


def _ok_response(json_payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json = lambda: json_payload
    return resp


def test_health_ok():
    client = flask_app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "healthy"}

@patch("market_leaders.requests.get")
@patch("market_health_utils._fetch_breadth")
@patch("market_health_utils.requests.post")
def test_get_monitor_market_health_dependency_mocks(mock_mhu_post, mock_breadth, mock_ml_get):
    client = flask_app.test_client()

    idx_payload = {"success": {"^GSPC": _series(), "^DJI": _series(base=200), "^IXIC": _series(base=300)}}
    mock_mhu_post.return_value = _ok_response(idx_payload)

    # Return dict directly from the helper to avoid cross-patch interference
    mock_breadth.return_value = {"new_highs": 120, "new_lows": 40, "high_low_ratio": 3.0}

    leaders_quotes = [{"industry": "Tech", "ticker": "A"}, {"industry": "Tech", "ticker": "B"}]
    mock_ml_get.return_value = _ok_response(leaders_quotes)

    resp = client.get("/monitor/market-health")
    assert resp.status_code == 200
    data = resp.get_json()
    mo = data["market_overview"]
    assert mo["new_highs"] == 120
    assert mo["new_lows"] == 40
    assert mo["high_low_ratio"] == 3.0
@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
def test_get_internal_leaders_handles_failures(mock_ml_get, mock_ml_post):
    client = flask_app.test_client()

    # Mock 52w screener to fail (returns non-list), then fallback sources also fail
    mock_ml_get.side_effect = [
        MagicMock(status_code=500), # 52w highs screener
        MagicMock(status_code=500), # Primary fallback
        MagicMock(status_code=500), # Secondary fallback
    ]
    mock_ml_post.return_value = MagicMock(status_code=500)

    resp = client.get("/monitor/internal/leaders")
    assert resp.status_code == 404
    assert "No market leader data available" in resp.get_json()["message"]

@patch("market_health_utils.requests.post")
@patch("market_health_utils.requests.get")
def test_integration_internal_health_no_universe(mock_mhu_get, mock_mhu_post):
    """
    Integration-test /monitor/internal/health: verify outputs stable without universe
    and consistent ratio against mocked data-service response.
    """
    client = flask_app.test_client()

    # Mock dependencies for get_market_health
    idx_payload = {"success": {"^GSPC": _series(), "^DJI": _series(), "^IXIC": _series()}}
    mock_mhu_post.return_value = _ok_response(idx_payload)

    breadth_payload = {"new_highs": 100, "new_lows": 25, "high_low_ratio": 4.0}
    mock_mhu_get.return_value = _ok_response(breadth_payload)

    # Make request without any universe parameter
    resp = client.get("/monitor/internal/health")
    assert resp.status_code == 200
    data = resp.get_json()

    # Verify output is stable and reflects mocked breadth data
    assert data["new_highs"] == 100
    assert data["new_lows"] == 25
    assert data["high_low_ratio"] == 4.0
    assert "market_stage" in data


@patch("market_leaders.requests.get")
def test_integration_internal_leaders_top_5_selection(mock_ml_get):
    """
    Integration-test /monitor/internal/leaders: verify top 5 industries selection
    by quote industry counts with ties and “Unclassified” handling.
    """
    client = flask_app.test_client()

    mock_quotes = [
        {"industry": "Tech"}, {"industry": "Tech"}, {"industry": "Tech"}, {"industry": "Tech"}, # 4
        {"industry": "Finance"}, {"industry": "Finance"}, {"industry": "Finance"},             # 3
        {"industry": "Retail"}, {"industry": "Retail"},                                       # 2
        {"industry": "Health"}, {"industry": "Health"},                                       # 2 (tie)
        {"industry": None}, # Unclassified                                                    # 1
        {"industry": "Energy"},                                                               # 1 (tie)
        {"industry": "Industrial"},                                                           # 1 (tie)
    ]
    mock_ml_get.return_value = _ok_response(mock_quotes)

    resp = client.get("/monitor/internal/leaders")
    assert resp.status_code == 200
    data = resp.get_json()
    
    # The contract is {"leading_industries": [...]}
    industries = data["leading_industries"]
    assert len(industries) == 5

    # Verify the top 5 industries are correct, respecting counts
    counts = {item['industry']: item['breadth_count'] for item in industries}
    assert counts["Tech"] == 4
    assert counts["Finance"] == 3
    assert counts["Retail"] == 2
    assert counts["Health"] == 2
    
    # The last spot is a tie between Unclassified, Energy, Industrial. One of them should be there.
    last_industry = industries[4]['industry']
    assert last_industry in ["Unclassified", "Energy", "Industrial"]
    assert counts[last_industry] == 1