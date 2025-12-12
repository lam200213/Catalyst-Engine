# backend-services/monitoring-service/services/downstream_clients.py
"""
Downstream service clients for the monitoring-service orchestrator.

This module encapsulates HTTP requests to:
- screening-service: POST /screen/batch
- analysis-service:  POST /analyze/batch
- analysis-service:  POST /analyze/freshness/batch
- data-service:      POST /data/return/batch

Each function:
- Accepts simple Python types and returns parsed JSON.
- Raises RuntimeError on network errors or unexpected responses.
"""

import os
import requests
from typing import List, Dict, Any, Tuple

DEFAULT_SCREENING_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
DEFAULT_ANALYSIS_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")
DEFAULT_DATA_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

_TIMEOUT = float(os.getenv("DOWNSTREAM_HTTP_TIMEOUT_SECONDS", "600.0"))

def _post_json(url: str, payload: Dict[str, Any], params: Dict[str, Any] = None) -> Any:
    """
    Helper to send POST requests with JSON payloads and optional query params.
    """
    try:
        # Pass 'params' to requests.post so they are encoded into the URL (e.g. ?mode=fast)
        resp = requests.post(url, json=payload, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"Downstream call failed for {url}: {exc}") from exc
    
def screen_batch(tickers: List[str]) -> Any:
    """
    Call screening-service to evaluate screening pass/fail per ticker.

    Expected contracts in this repo:
    - Request: { "tickers": [ ... ] }
    - Response: Prefer a structure indicating per-ticker pass/fail; handle both:
      * { "passed": ["AAPL", ...] } or
      * [{ "ticker": "AAPL", "pass": true }, ...] or
      * ["AAPL", ...] (implicit pass list)
    """
    url = f"{DEFAULT_SCREENING_URL}/screen/batch"
    return _post_json(url, {"tickers": list(tickers)})

def analyze_batch(tickers: List[str], mode: str = "fast") -> Any:
    """
    Call analysis-service for VCP metrics per ticker.
    - mode='fast' (default): Returns VCPAnalysisBatchItem (lean, no chart data).
    - mode='full': Returns VCPAnalysisSingle (rich, includes chart_data).
    
    Expected response items contain fields like:
    - ticker, vcp_pass, is_pivot_good, has_pivot, is_at_pivot, has_pullback_setup,
      pivot_price, pattern_age_days, and possibly more.
    """
    url = f"{DEFAULT_ANALYSIS_URL}/analyze/batch"
    # Pass mode in payload to match analysis-service expectation and ensure 'full' mode is respected.
    return _post_json(url, {"tickers": list(tickers), "mode": mode})

def analyze_freshness_batch(tickers: List[str]) -> Any:
    """
    Call analysis-service to compute freshness / health results per ticker.

    Expected response:
        A JSON array of objects compatible with the shared
        `AnalyzeFreshnessBatchItem` contract, where each item has fields:

        - ticker: str
        - passes_freshness_check: bool   # mapped to `fresh` in shared.contracts
        - vcp_detected: bool | null
        - days_since_pivot: int | null
        - message: str | null
        - vcpFootprint: str | null

    Notes:
        The monitoring-service orchestrator is responsible for combining these
        freshness signals with screening and VCP results to derive the
        watchlist-level `last_refresh_status` and `failed_stage`. The analysis-service
        does not set those fields directly.
    """
    url = f"{DEFAULT_ANALYSIS_URL}/analyze/freshness/batch"
    return _post_json(url, {"tickers": list(tickers)})

def data_return_batch(tickers: List[str]) -> Any:
    """
    Call data-service to return price/volume context per ticker.

    Expected response:
    - Mapping of ticker -> dict with fields such as current_price, vol_last, vol_50d_avg, day_change_pct
    """
    url = f"{DEFAULT_DATA_URL}/data/return/batch"
    return _post_json(url, {"tickers": list(tickers)})

def watchlist_metrics_batch(tickers: List[str]) -> Any:
    """
    Call data-service to compute compact watchlist metrics per ticker.

    Expected response JSON:
        {
          "metrics": {
            "HG": { "current_price": ..., "vol_last": ..., "vol_50d_avg": ..., "day_change_pct": ... },
            ...
          }
        }

    This function flattens the response to {ticker: {metrics...}} so that
    update_orchestrator._index_by_ticker can consume it directly.
    """
    url = f"{DEFAULT_DATA_URL}/data/watchlist-metrics/batch"
    raw = _post_json(url, {"tickers": list(tickers)})

    if isinstance(raw, dict) and isinstance(raw.get("metrics"), dict):
        return raw["metrics"]

    # Fallback to empty mapping
    return {}