# backend-services/monitoring-service/market_health_utils.py

from __future__ import annotations
import os
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import requests

import logging
logger = logging.getLogger(__name__)

from helper_functions import check_market_trend_context

# Indices to evaluate posture
INDICES = ['^GSPC', '^DJI', '^IXIC']

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

def _to_df(series: Union[List[dict], Dict]) -> pd.DataFrame:
    """
    Accepts either:
    - list[dict] with keys: formatted_date, open, high, low, close, volume
    - dict[str, list] (dict-of-lists) with the same keys

    Normalizes to a DataFrame indexed by formatted_date.
    Gracefully handles malformed inputs by returning an empty DataFrame.
    """
    if not series:
        return pd.DataFrame()

    try:
        if isinstance(series, dict):
            # Accept dict-of-lists and align lengths defensively
            keys = ['formatted_date', 'open', 'high', 'low', 'close', 'volume']
            arrays = {k: series.get(k, []) for k in keys}

            # Determine minimal length across list-like values
            lengths = [len(v) for v in arrays.values() if isinstance(v, list)]
            if not lengths:
                return pd.DataFrame()

            n = min(lengths)
            # Trim lists to n; broadcast scalars to length n
            normalized = {}
            for k, v in arrays.items():
                if isinstance(v, list):
                    normalized[k] = v[:n]
                else:
                    normalized[k] = [v] * n

            df = pd.DataFrame(normalized)
        else:
            # Expected happy path: list of dicts
            df = pd.DataFrame(series or [])
    except ValueError:
        # If pandas complains about inconsistent lengths, fail gracefully
        return pd.DataFrame()

    if df.empty:
        return df

    # Coerce and index by datetime
    df['formatted_date'] = pd.to_datetime(df.get('formatted_date'), errors='coerce')
    df = df.dropna(subset=['formatted_date'])
    if df.empty:
        return df

    df = df.set_index('formatted_date').sort_index()

    # Return only the canonical OHLCV columns if present
    cols = [c for c in ['open', 'high', 'low', 'close', 'volume'] if c in df.columns]
    if not cols:
        return pd.DataFrame()

    return df[cols].copy()


def _fetch_prices_batch(tickers: List[str]) -> Dict[str, List[dict]]:
    """
    Use the app's batch endpoint to fetch price data for many tickers.
    """
    url = f"{DATA_SERVICE_URL}/price/batch"
    payload = {
        "tickers": tickers,
        "source": "yfinance",
        "period": "2y" 
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json() or {}
    success = result.get("success") or {}

    for sym in tickers:
        series = success.get(sym) or []
        logger.info(f"_fetch_prices_batch: {sym} raw_len={len(series)}")

    # totals
    logger.info(f"_fetch_prices_batch: keys={list(success.keys())}")
    return success


def _fetch_price_single(ticker: str) -> Optional[List[dict]]:
    """
    Fallback to the app's single endpoint to fetch one ticker's price data.
    """
    url = f"{DATA_SERVICE_URL}/price/{ticker}?source=yfinance"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return None
    
    data = resp.json()
    logger.info(f"_fetch_price_single: {ticker} raw_len={len(data) if isinstance(data, list) else 'na'} type={type(data).__name__}")
    return data


def _build_index_dfs(idx_data: Dict[str, List[dict]]) -> Dict[str, pd.DataFrame]:
    idx_dfs: Dict[str, pd.DataFrame] = {}
    for sym in INDICES:
        series = idx_data.get(sym) or []
        logger.info(f"_build_index_dfs: {sym} incoming_raw_len={len(series)} type={type(series).__name__}")

        df = _to_df(series)
        logger.info(f"_build_index_dfs: {sym} df_shape={df.shape}")

        if df.empty:
            idx_dfs[sym] = df
            continue
        # 1-year history from the endpoint is sufficient for 200-day SMA and 52-week metrics
        df['sma_50'] = df['close'].rolling(window=50, min_periods=50).mean()
        df['sma_200'] = df['close'].rolling(window=200, min_periods=200).mean()
        # Use min_periods=251 so high_52_week is defined on the previous workday (iloc[-2]) once total length reaches 252
        df['high_52_week'] = df['high'].rolling(window=252, min_periods=251).max()
        df['low_52_week'] = df['low'].rolling(window=252, min_periods=251).min()
        idx_dfs[sym] = df
    return idx_dfs


def _build_index_payload(idx_dfs: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
    payload: Dict[str, dict] = {}
    for sym in INDICES:
        df = idx_dfs.get(sym)
        if df is None or df.empty:
            payload[sym] = {}
            continue
        idx = -2 if len(df) >= 2 else -1
        last = df.iloc[idx]
        payload[sym] = {
            'current_price': float(last['close']) if pd.notna(last['close']) else None,
            'sma_50': float(last['sma_50']) if pd.notna(last['sma_50']) else None,
            'sma_200': float(last['sma_200']) if pd.notna(last['sma_200']) else None,
            'high_52_week': float(last['high_52_week']) if pd.notna(last['high_52_week']) else None,
            'low_52_week': float(last['low_52_week']) if pd.notna(last['low_52_week']) else None,
        }
        logger.info(f"_build_index_payload: {sym} iloc_idx={idx} "
                                f"vals={{'close': payload[sym]['current_price'], "
                                f"'sma_50': payload[sym]['sma_50'], 'sma_200': payload[sym]['sma_200'], "
                                f"'high_52_week': payload[sym]['high_52_week'], 'low_52_week': payload[sym]['low_52_week']}}")
    return payload


def _map_stage(trend: str) -> str:
    if trend == 'Bullish':
        return 'Bullish'
    if trend == 'Bearish':
        return 'Bearish'
    return 'Neutral'


def _compute_correction_depth(spx_df: pd.DataFrame) -> float:
    if spx_df is None or spx_df.empty:
        return 0.0
    idx = -2 if len(spx_df) >= 2 else -1
    try:
        last = spx_df.iloc[-1]
    except Exception:
        return 0.0
    high_52 = last.get('high_52_week')
    close = last.get('close')
    if pd.isna(high_52) or high_52 in (None, 0) or pd.isna(close) or close is None:
        return 0.0
    return round((float(close) - float(high_52)) / float(high_52) * 100.0, 2)


def _fetch_breadth() -> dict | None:
    """
    Calls data-service /market/breadth to retrieve {new_highs, new_lows, high_low_ratio}.
    """
    url = f"{DATA_SERVICE_URL}/market/breadth"
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            t = type(data).__name__
            keys = list(data.keys()) if isinstance(data, dict) else None
            logger.info(f"_fetch_breadth: type={t} keys={keys}")
            # olerate list responses by extracting first dict-like element
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and any(k in item for k in ("new_highs", "new_lows", "high_low_ratio")):
                        return item
                return None
            return None
        return None
    except requests.RequestException:
        return None

def get_market_health(universe: Optional[List[str]] = None) -> dict:
    """
    Orchestrate the market health snapshot using the app's own HTTP endpoints:
    - Fetch index data via POST /price/batch
    - Posture via check_market_trend_context
    - ^GSPC correction depth
    - 52-week highs/lows counts and ratio via data-service aggregate endpoint
    Returns a dict aligned with the plan for /market/health.
    """
    # 1) Indices via batch endpoint (unchanged)
    idx_raw = _fetch_prices_batch(INDICES)
    for sym in INDICES:
        if not idx_raw.get(sym):
            single = _fetch_price_single(sym)
            if single:
                idx_raw[sym] = single
    if not all(idx_raw.get(sym) for sym in INDICES):
        raise RuntimeError("Failed to fetch required index data")

    idx_dfs = _build_index_dfs(idx_raw)

    # 2) Posture
    details: Dict[str, dict] = {}
    check_market_trend_context(_build_index_payload(idx_dfs), details)
    trend_obj = details.get('market_trend_context') or {}
    market_stage = _map_stage(trend_obj.get('trend') or 'Unknown')

    # 3) Correction depth (^GSPC)
    correction_depth = _compute_correction_depth(idx_dfs.get('^GSPC'))

    # 4) Breadth (aggregate)
    breadth = _fetch_breadth()
    if not isinstance(breadth, dict):
        breadth = {"new_highs": 0, "new_lows": 0, "high_low_ratio": 0.0}

    return {
        "market_stage": market_stage,
        "correction_depth_percent": correction_depth,
        "high_low_ratio": breadth.get("high_low_ratio", 0.0),
        "new_highs": breadth.get("new_highs", 0),
        "new_lows": breadth.get("new_lows", 0),
    }
