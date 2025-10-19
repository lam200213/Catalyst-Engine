# backend-services/monitoring-service/tests/test_unit.py
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


def test_count_new_highs_lows_basic_and_ratio():
    # ticker_high: last close at its max high -> counts as new high
    t_high = _series_from_points(
        [
            {"open": 10, "high": 10, "low": 9, "close": 9.5},
            {"open": 11, "high": 12, "low": 10.5, "close": 12.0},  # cp == hi
        ]
    )
    # ticker_low: last close at its min low -> counts as new low
    t_low = _series_from_points(
        [
            {"open": 10, "high": 10, "low": 9, "close": 9.5},
            {"open": 9.1, "high": 9.5, "low": 9.0, "close": 9.0},  # cp == lo
        ]
    )
    # neutral: does not meet thresholds
    t_neutral = _series_from_points(
        [
            {"open": 10, "high": 10, "low": 9, "close": 9.5},
            {"open": 10, "high": 11, "low": 9.2, "close": 10.1},
        ]
    )
    highs, lows, ratio = mhu._count_new_highs_lows(
        {"H": t_high, "L": t_low, "N": t_neutral}
    )
    assert highs == 1
    assert lows == 1
    assert ratio == 1.0  # 1 / 1 rounded to 2 decimals

    # Only highs, no lows -> ratio = inf
    highs2, lows2, ratio2 = mhu._count_new_highs_lows({"H": t_high})
    assert highs2 == 1 and lows2 == 0 and ratio2 == float("inf")

    # No data -> 0,0,0.0
    h0, l0, r0 = mhu._count_new_highs_lows({})
    assert h0 == 0 and l0 == 0 and r0 == 0.0


def test_build_index_dfs_length_thresholds():
    # Build 251 days (just below 252) and 252 days (at threshold) for ^GSPC
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

    # Below threshold -> last high_52_week NaN, sma_200 NaN
    last_251 = dfs_251["^GSPC"].iloc[-1]
    assert pd.isna(last_251["high_52_week"])
# A 200-day SMA is valid with 251 data points, so it should not be NaN.
    assert pd.notna(last_251["sma_200"])

    # At threshold -> high_52_week not NaN (but sma_200 still depends on 200+ points and should be defined)
    last_252 = dfs_252["^GSPC"].iloc[-1]
    assert pd.notna(last_252["high_52_week"])
    assert pd.notna(last_252["sma_200"])


# ---------- market_health_utils: orchestrator with HTTP mocking ----------

@patch("market_health_utils.check_market_trend_context")
@patch("market_health_utils._fetch_price_single")
@patch("market_health_utils._fetch_prices_batch")
def test_get_market_health_happy_path_with_fallback(mock_batch, mock_single, mock_trend_ctx):
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
        # Second call for universe
        {
            "H": _series_from_points(
                [{"open": 10, "high": 12, "low": 9, "close": 12}]
            ),
            "N": _series_from_points(
                [{"open": 10, "high": 11, "low": 9, "close": 10}]
            ),
        },
    ]
    mock_single.return_value = mk_idx_series(15000, 16000, 14000)
    def trend_ctx(payload, details):
        # Force a bullish posture
        details["market_trend_context"] = {"trend": "Bullish"}
    mock_trend_ctx.side_effect = trend_ctx

    result = mhu.get_market_health(universe=["H", "N"])

    # Verify mapping to stage
    assert result["market_stage"] == "Bullish"
    # Compute correction depth for ^GSPC using last row close vs high_52_week
    # With close 4500 and high_52 5000, expect -10.0
    assert result["correction_depth_percent"] == -10.0
    # Universe highs/lows: H at high, N neutral -> highs=1, lows=0, ratio=inf
    assert result["new_highs"] == 1
    assert result["new_lows"] == 0
    assert result["high_low_ratio"] == float("inf")


@patch("market_health_utils._fetch_price_single")
@patch("market_health_utils._fetch_prices_batch")
def test_get_market_health_missing_index_raises(mock_batch, mock_single):
    # All indices missing should raise at orchestrator guard
    mock_batch.return_value = {}
    # Mock the fallback to also return nothing, preventing a real network call
    mock_single.return_value = None
    with pytest.raises(RuntimeError):
        mhu.get_market_health(universe=None)

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