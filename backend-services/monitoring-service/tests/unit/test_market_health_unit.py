# backend-services/monitoring-service/tests/unit/test_market_health_unit.py
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest
from unittest.mock import patch
from shared.contracts import MarketOverview

# Ensure local imports resolve when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

import market_health_utils as mhu
from market_leaders import IndustryRanker, MarketLeadersService


# ---------- market_health_utils: math & counting ----------

def test_compute_correction_depth_basic():
    # Close 95 vs 52w high 100 -> -5.00%
    df = pd.DataFrame({"close": [95.0], "high_52_week": [100.0]})
    assert mhu._compute_correction_depth(df) == -5.00


def test_compute_correction_depth_edge_empty_none_nan():
    assert mhu._compute_correction_depth(None) == 0.0
    assert mhu._compute_correction_depth(pd.DataFrame()) == 0.0

    df_nan = pd.DataFrame({"close": [float("nan")], "high_52_week": [100.0]})
    assert mhu._compute_correction_depth(df_nan) == 0.0

    df_zero_high = pd.DataFrame({"close": [100.0], "high_52_week": [0.0]})
    assert mhu._compute_correction_depth(df_zero_high) == 0.0


def _series_from_points(points):
    # Helper to build provider-like series accepted by _to_df
    return [
        {
            "formatted_date": (datetime(2024, 1, 1) + timedelta(days=i)).date().isoformat(),
            "open": p["open"],
            "high": p["high"],
            "low": p["low"],
            "close": p["close"],
            "volume": p.get("volume", 1),
        }
        for i, p in enumerate(points)
    ]

def test_build_index_dfs_length_thresholds():
    """
    Build 251 days (just below 252) and 252 days (at threshold) for ^GSPC
    Below threshold -> last high_52_week NaN; 200-day SMA is defined with 251 points
    At threshold -> high_52_week not NaN; 200-day SMA remains defined
    """
    base = datetime(2024, 1, 1)
    def day(i): return (base + timedelta(days=i)).date().isoformat()

    # Increasing highs to make 52w high window well-defined
    series_251 = [
        {
            "formatted_date": day(i),
            "open": 100 + i,
            "high": 100 + i,
            "low":  90 + i,
            "close": 95 + i,
            "volume": 1,
        }
        for i in range(251)
    ]
    series_252 = series_251 + [{
        "formatted_date": day(251),
        "open": 351, "high": 351, "low": 341, "close": 346, "volume": 1
    }]

    idx_data_251 = {"^GSPC": series_251, "^DJI": series_251, "^IXIC": series_251}
    idx_data_252 = {"^GSPC": series_252, "^DJI": series_252, "^IXIC": series_252}

    dfs_251 = mhu._build_index_dfs(idx_data_251)
    dfs_252 = mhu._build_index_dfs(idx_data_252)

    # Below threshold -> last high_52_week NaN; 200-day SMA is defined with 251 points and should not be NaN.
    last_251 = dfs_251["^GSPC"].iloc[-2]
    assert pd.isna(last_251["high_52_week"])
    # A 200-day SMA is valid with 251 data points, so it should not be NaN.
    assert pd.notna(last_251["sma_200"])

    # At threshold -> high_52_week not NaN (but sma_200 still depends on 200+ points and should be defined)
    last_252 = dfs_252["^GSPC"].iloc[-2]
    assert pd.notna(last_252["high_52_week"])
    assert pd.notna(last_252["sma_200"])


# ---------- market_health_utils: orchestrator with HTTP mocking ----------
@patch("market_health_utils._fetch_breadth")
@patch("market_health_utils.check_market_trend_context")
@patch("market_health_utils._fetch_price_single")
@patch("market_health_utils._fetch_prices_batch")
def test_get_market_health_happy_path_with_fallback_and_breadth(mock_batch, mock_single, mock_trend_ctx, mock_breadth):
    # Batch returns missing ^IXIC -> single fallback supplies it
    def mk_idx_series(close=100, hi=110, lo=90):
        return _series_from_points(
            [{"open": 99, "high": 100, "low": 98, "close": close - 1}] * 251
            + [{"open": 100, "high": hi, "low": lo, "close": close}]
        )

    mock_batch.side_effect = [
        # First call for indices
        {
            "^GSPC": mk_idx_series(4500, 5000, 4000),
            "^DJI": mk_idx_series(35000, 36500, 32000),
            # "^IXIC" intentionally missing to trigger fallback
        },
    ]
    mock_single.return_value = mk_idx_series(15000, 16000, 14000)
    def trend_ctx(payload, details):
        # Force a bullish posture
        details["market_trend_context"] = {"trend": "Bullish"}
    mock_trend_ctx.side_effect = trend_ctx
    
    # Mock the new breadth fetcher
    mock_breadth.return_value = {"new_highs": 150, "new_lows": 75, "high_low_ratio": 2.0}

    result = mhu.get_market_health()

    # Verify mapping to stage
    assert result["market_stage"] == "Bullish"
    # Compute correction depth for ^GSPC using last row close vs high_52_week
    # With close 4500 and high_52 5000, expect -10.0
    assert result["correction_depth_percent"] == -10.0
    # Assertions for breadth data from mocked endpoint
    assert result["new_highs"] == 150
    assert result["new_lows"] == 75
    assert result["high_low_ratio"] == 2.0

@patch("market_health_utils._fetch_price_single")
@patch("market_health_utils._fetch_prices_batch")
def test_get_market_health_missing_index_raises(mock_batch, mock_single):
    # All indices missing should raise at orchestrator guard
    mock_batch.return_value = {}
    # Mock the fallback to also return nothing, preventing a real network call
    mock_single.return_value = None
    with pytest.raises(RuntimeError):
        mhu.get_market_health()

def test_market_overview_market_stage_literal_enforced():
    # Valid should pass
    MarketOverview(
        market_stage="Bullish",
        correction_depth_percent=0.0,
        high_low_ratio=1.0,
        new_highs=0,
        new_lows=0
    )
    # Invalid should raise
    with pytest.raises(Exception):
        MarketOverview(
            market_stage="Confirmed Uptrend",  # invalid per contract
            correction_depth_percent=0.0,
            high_low_ratio=1.0,
            new_highs=0,
            new_lows=0
        )

# --- Unit-test MarketBreadthFetcher behavior via its consumer ---

@patch("market_health_utils.check_market_trend_context")
@patch("market_health_utils._fetch_price_single")
@patch("market_health_utils._fetch_prices_batch")
@patch("market_health_utils._fetch_breadth")
def test_get_market_health_handles_breadth_edge_cases(mock_breadth, mock_batch, mock_single, mock_trend_ctx):
    """
    Simulates various highs/lows screener responses to verify totals and ratio edge cases.
    """
    # Setup mocks for index data and trend context (can be minimal)
    def mk_idx_series():
        return _series_from_points(
            [{"open": 100, "high": 101, "low": 99, "close": 100}] * 252
        )
    mock_batch.return_value = {"^GSPC": mk_idx_series(), "^DJI": mk_idx_series(), "^IXIC": mk_idx_series()}
    mock_single.return_value = None # No fallback needed
    def trend_ctx(payload, details):
        details["market_trend_context"] = {"trend": "Neutral"}
    mock_trend_ctx.side_effect = trend_ctx

    # Case 1: Lows = 0, which should result in a very high or infinite ratio from data-service
    mock_breadth.return_value = {"new_highs": 100, "new_lows": 0, "high_low_ratio": float('inf')}
    result1 = mhu.get_market_health()
    assert result1["new_highs"] == 100
    assert result1["new_lows"] == 0
    assert result1["high_low_ratio"] == float('inf')

    # Case 2: Highs = 0
    mock_breadth.return_value = {"new_highs": 0, "new_lows": 50, "high_low_ratio": 0.0}
    result2 = mhu.get_market_health()
    assert result2["new_highs"] == 0
    assert result2["new_lows"] == 50
    assert result2["high_low_ratio"] == 0.0

    # Case 3: Breadth fetch fails (returns None), should default to 0s
    mock_breadth.return_value = None
    result3 = mhu.get_market_health()
    assert result3["new_highs"] == 0
    assert result3["new_lows"] == 0
    assert result3["high_low_ratio"] == 0.0

def test_build_index_payload_iloc_minus2_numeric():
    from market_health_utils import _build_index_dfs, _build_index_payload, INDICES
    # Build 252 points where the final bar spikes highs so prior day has enough history
    def mk_series(base_open=100, base_high=100, base_low=90, base_close=95, spike_high=5000, n=252):
        series = []
        for i in range(n - 1):
            series.append({
                "formatted_date": f"2024-01-{(i%28)+1:02d}",
                "open": base_open, "high": base_high, "low": base_low, "close": base_close, "volume": 1
            })
        # last bar
        series.append({
            "formatted_date": "2024-02-29",
            "open": base_open + 1, "high": spike_high, "low": base_low - 1, "close": base_close + 1, "volume": 1
        })
        return series

    idx_data = {
        "^GSPC": mk_series(),
        "^DJI": mk_series(base_open=200, base_high=200, base_low=190, base_close=195, spike_high=3000),
        "^IXIC": mk_series(base_open=300, base_high=300, base_low=290, base_close=295, spike_high=4000),
    }
    dfs = _build_index_dfs(idx_data)
    payload = _build_index_payload(dfs)
    for sym in INDICES:
        p = payload.get(sym) or {}
        assert isinstance(p.get("current_price"), (int, float))
        assert (p.get("sma_50") is None) or isinstance(p.get("sma_50"), (int, float))
        assert (p.get("sma_200") is None) or isinstance(p.get("sma_200"), (int, float))
        assert (p.get("high_52_week") is None) or isinstance(p.get("high_52_week"), (int, float))
        assert (p.get("low_52_week") is None) or isinstance(p.get("low_52_week"), (int, float))

def test_leaders_from_52w_populates_stock_count(monkeypatch):
    """
    Verify that _leaders_from_52w correctly populates stock_count
    for each industry, matching the full count of stocks in that industry
    from the 52-week highs screener.
    """
    from market_leaders import _leaders_from_52w
    
    # Mock get_52w_highs to return controlled data
    mock_quotes = [
        {"symbol": "NVDA", "industry": "Semiconductors", "marketCap": 1e12},
        {"symbol": "AVGO", "industry": "Semiconductors", "marketCap": 8e11},
        {"symbol": "MU", "industry": "Semiconductors", "marketCap": 5e11},
        {"symbol": "AMD", "industry": "Semiconductors", "marketCap": 3e11},
        {"symbol": "ASML", "industry": "Semiconductors", "marketCap": 2e11},
        {"symbol": "JPM", "industry": "Banks—Regional", "marketCap": 4e11},
        {"symbol": "BAC", "industry": "Banks—Regional", "marketCap": 3e11},
        {"symbol": "WFC", "industry": "Banks—Regional", "marketCap": 2e11},
    ]
    
    # Mock post_returns_1m_batch to return dummy returns
    mock_returns = {
        "NVDA": 15.5, "AVGO": 12.3, "MU": 8.1, "AMD": 5.2, "ASML": 3.4,
        "JPM": 4.2, "BAC": 3.1, "WFC": 2.5
    }
    
    monkeypatch.setattr("market_leaders.get_52w_highs", lambda: mock_quotes)
    monkeypatch.setattr("market_leaders.post_returns_batch", lambda syms, period: mock_returns)
    
    # Call the function with per_industry=3 (display top 3 stocks per industry)
    result = _leaders_from_52w(per_industry=3)
    
    # Assert structure
    assert isinstance(result, list)
    assert len(result) == 2  # Two industries: Semiconductors, Banks—Regional
    
    # Check Semiconductors industry
    semi_ind = next((x for x in result if x["industry"] == "Semiconductors"), None)
    assert semi_ind is not None
    assert semi_ind["stock_count"] == 5  # 5 total stocks in Semiconductors from mock data
    assert len(semi_ind["stocks"]) == 3  # But only top 3 displayed
    
    # Check Banks—Regional industry
    banks_ind = next((x for x in result if x["industry"] == "Banks—Regional"), None)
    assert banks_ind is not None
    assert banks_ind["stock_count"] == 3  # 3 total stocks in Banks—Regional
    assert len(banks_ind["stocks"]) == 3  # All 3 displayed since count <= per_industry
    
    # Verify stocks are sorted by return descending
    assert semi_ind["stocks"][0]["ticker"] == "NVDA"  # Highest return
    assert semi_ind["stocks"][-1]["ticker"] == "MU"  # Lowest return among top 3