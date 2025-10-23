# backend-services/monitoring-service/tests/test_new_highs_screener_source.py

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure local imports resolve when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
import market_leaders as ml

# Skip until NewHighsScreenerSource is implemented in monitoring-service
pytestmark = pytest.mark.skipif(
    not hasattr(ml, "NewHighsScreenerSource"),
    reason="NewHighsScreenerSource not implemented; monitoring-service currently uses data-service /market/screener/52w_highs directly"
)

def _ok_response(payload):
    r = MagicMock()
    r.status_code = 200
    r.json = lambda: payload
    return r

@patch("market_leaders.requests.get")
def test_new_highs_source_paginates_until_total(mock_get):
    """
    Verifies pagination stops when accumulated count reaches total.
    """
    # page 1
    page1 = {
        "total": 5,
        "count": 3,
        "offset": 0,
        "results": [
            {"symbol": "AAA", "region": "US", "industry": "Tech"},
            {"symbol": "BBB", "region": "US", "industry": "Tech"},
            {"symbol": "CCC", "region": "US", "industry": "Retail"},
        ],
    }
    # page 2
    page2 = {
        "total": 5,
        "count": 2,
        "offset": 3,
        "results": [
            {"symbol": "DDD", "region": "US", "industry": "Finance"},
            {"symbol": "EEE", "region": "US", "industry": "Energy"},
        ],
    }
    mock_get.side_effect = [_ok_response(page1), _ok_response(page2)]

    src = ml.NewHighsScreenerSource(region="US", page_size=3)
    results = src.fetch_all()  # Expected to return 5 total items

    assert len(results) == 5
    assert [r["symbol"] for r in results] == ["AAA", "BBB", "CCC", "DDD", "EEE"]

@patch("market_leaders.requests.get")
def test_new_highs_source_enforces_us_region(mock_get):
    """
    Verifies region=US enforcement filters out non-US symbols.
    """
    payload = {
        "total": 4,
        "count": 4,
        "offset": 0,
        "results": [
            {"symbol": "US1", "region": "US", "industry": "Tech"},
            {"symbol": "CA1", "region": "CA", "industry": "Tech"},
            {"symbol": "US2", "region": "US", "industry": "Retail"},
            {"symbol": "HK1", "region": "HK", "industry": "Retail"},
        ],
    }
    mock_get.return_value = _ok_response(payload)

    src = ml.NewHighsScreenerSource(region="US", page_size=50)
    results = src.fetch_all()

    assert [r["symbol"] for r in results] == ["US1", "US2"]
