# backend-services/monitoring-service/tests/integration/test_integration_leaders.py
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