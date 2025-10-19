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


@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
@patch("market_health_utils.requests.get")
@patch("market_health_utils.requests.post")
def test_get_monitor_market_health_dependency_mocks(mock_mhu_post, mock_mhu_get, mock_ml_get, mock_ml_post):
    client = flask_app.test_client()

    # 1) Indices batch for market health
    idx_payload = {
        "success": {
            "^GSPC": _series(), "^DJI": _series(base=200), "^IXIC": _series(base=300)
        }
    }
    mock_mhu_post.side_effect = [
        _ok_response(idx_payload),  # first POST: indices
    ]
    mock_mhu_get.return_value = _ok_response({})  # not used (no fallback needed)

    # 2) Market leaders: primary candidates + 1m returns batch
    mock_ml_get.return_value = _ok_response({
        "Tech": ["AAPL", "MSFT", "NVDA"],
        "Retail": ["AMZN", "COST"]
    })
    mock_ml_post.return_value = _ok_response({
        "AAPL": 0.10, "MSFT": 0.05, "NVDA": None, "AMZN": 0.07, "COST": 0.02
    })

    resp = client.get("/monitor/market-health")
    assert resp.status_code == 200
    data = resp.get_json()

    # Assert structure and allowed stage
    assert "market_overview" in data and "leaders_by_industry" in data
    mo = data["market_overview"]
    assert mo["market_stage"] in ("Bullish", "Bearish", "Neutral", "Recovery")
    assert isinstance(mo["correction_depth_percent"], float)
    assert isinstance(mo["high_low_ratio"], float)
    assert isinstance(mo["new_highs"], int)
    assert isinstance(mo["new_lows"], int)

    leaders = data["leaders_by_industry"]["leading_industries"]
    assert isinstance(leaders, list)
    # Tech expected to include AAPL and MSFT in descending return
    tech = next(block for block in leaders if block["industry"] == "Tech")
    assert [s["ticker"] for s in tech["stocks"]] == ["AAPL", "MSFT"]


@patch("market_health_utils.requests.get")
@patch("market_health_utils.requests.post")
def test_get_internal_health_uses_uppercased_universe_and_dependency(mock_mhu_post, mock_mhu_get):
    client = flask_app.test_client()

    # Side effects: first POST for indices, second POST for universe
    idx_payload = {"success": {"^GSPC": _series(), "^DJI": _series(base=200), "^IXIC": _series(base=300)}}
    uni_payload = {"success": {
        "AAPL": _series(days=2, base=10), "MSFT": _series(days=2, base=20), "TSLA": _series(days=2, base=30)
    }}
    mock_mhu_post.side_effect = [
        _ok_response(idx_payload),
        _ok_response(uni_payload),
    ]
    mock_mhu_get.return_value = _ok_response({})  # not used

    resp = client.get("/monitor/internal/health?tickers=aapl, msft , Tsla")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["market_stage"] in ("Bullish", "Bearish", "Neutral", "Recovery")

    # Verify the second POST (universe) used uppercased tickers
    assert len(mock_mhu_post.call_args_list) >= 2
    second_post_kwargs = mock_mhu_post.call_args_list[1].kwargs
    assert sorted(second_post_kwargs["json"]["tickers"]) == ["AAPL", "MSFT", "TSLA"]


@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
def test_get_internal_leaders_handles_failures(mock_ml_get, mock_ml_post):
    client = flask_app.test_client()

    # Both candidate sources fail => returns {}
    mock_ml_get.side_effect = [
        _ok_response({}),  # simulate empty/invalid primary
        _ok_response({}),  # simulate empty/invalid fallback
    ]
    mock_ml_post.return_value = _ok_response({})

    resp = client.get("/monitor/internal/leaders")
    # Route returns 404 when no data
    assert resp.status_code == 404
