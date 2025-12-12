# backend-services/monitoring-service/services/update_orchestrator.py
"""
Watchlist refresh orchestrator.

Coordinates the refresh of watchlist item statuses by:
- Loading current watchlist documents from MongoDB.
- Collecting cross-service signals (Screen, VCP, Freshness, Data).
- Enriching items and delegating status derivation & partitioning to watchlist_status_service.
- Persisting updated statuses and archiving failed items via mongo_client.

This module:
- Owns no HTTP routing.
- Talks to mongo_client, downstream clients, and the pure status engine.
"""
import logging
from datetime import datetime  
from typing import Any, Dict, List, Tuple, Set
from database import mongo_client
from services import watchlist_status_service
from services import downstream_clients 
from helper_functions import build_sample_from_items
from shared.contracts import LastRefreshStatus

logger = logging.getLogger(__name__)

# helper functions
def _normalize_passed_from_screen(response: Any) -> Set[str]:
    """
    Normalize screening response into a set of passed tickers.

    Accepts response shapes:
    - { "passed": ["AAPL", ...] }
    - [{ "ticker": "AAPL", "pass": true }, ...]
    - ["AAPL", ...]  (implicit pass list)
    """
    passed: Set[str] = set()
    if isinstance(response, dict) and isinstance(response.get("passed"), list):
        for t in response["passed"]:
            if isinstance(t, str) and t:
                passed.add(t)
        return passed
    if isinstance(response, list):
        for item in response:
            if isinstance(item, str):
                if item:
                    passed.add(item)
            elif isinstance(item, dict) and item.get("pass") and isinstance(item.get("ticker"), str):
                passed.add(item["ticker"])
    return passed

def _index_by_ticker(items: Any) -> Dict[str, Dict[str, Any]]:
    """Create a dict[ticker] -> payload for lists or dict-like responses."""
    index: Dict[str, Dict[str, Any]] = {}
    if isinstance(items, dict):
        # data-service often returns mapping of ticker -> payload
        for k, v in items.items():
            if isinstance(k, str) and isinstance(v, dict):
                index[k] = v
        return index
    if isinstance(items, list):
        for obj in items:
            if isinstance(obj, dict):
                t = obj.get("ticker")
                if isinstance(t, str) and t:
                    index[t] = obj
    return index

def _safe_ratio(n: Any, d: Any) -> float | None:
    """Compute n/d if both are positive numbers; else None."""
    try:
        nf = float(n)
        df = float(d)
        if df > 0.0:
            return nf / df
        return None
    except Exception:
        return None

# main functions
def refresh_watchlist_status() -> Dict[str, Any]:
    """
    End-to-end refresh for all watchlist items.

    Returns a summary dict with:
    - message: str
    - updated_items: int
    - archived_items: int
    - failed_items: int (non-fatal downstream errors)
    """
    client, db = mongo_client.connect()
    
    # 1. Load active watchlist items
    raw_items: List[Dict[str, Any]] = mongo_client.list_watchlist_excluding(db, [])
    if not raw_items:
        summary = {
            "message": "No watchlist items to refresh.",
            "updated_items": 0,
            "archived_items": 0,
            "failed_items": 0,
        }
        logger.info("refresh-watchlist-status: %s", summary)
        return summary

    # Collect tickers
    tickers: List[str] = [
        d.get("ticker") for d in raw_items
        if isinstance(d, dict) and isinstance(d.get("ticker"), str) and d.get("ticker")
    ]
    failed_downstream_tickers: Set[str] = set()

    # 2. Collect signals (The Funnel)
    # A) Screening
    try:
        screen_resp = downstream_clients.screen_batch(tickers)
        passed_screen = _normalize_passed_from_screen(screen_resp)
    except Exception as exc:
        logger.error("refresh-watchlist-status: screening failed: %s", exc, exc_info=True)
        passed_screen = set()
        failed_downstream_tickers.update(tickers)

    # B) VCP analysis (Optimization: only screen survivors)
    try:
        analyze_resp = downstream_clients.analyze_batch(sorted(list(passed_screen)))
        vcp_idx = _index_by_ticker(analyze_resp)
    except Exception as exc:
        logger.error("refresh-watchlist-status: analyze/batch failed: %s", exc, exc_info=True)
        vcp_idx = {}
        failed_downstream_tickers.update(passed_screen)

    # Determine VCP survivors
    vcp_passed: Set[str] = set(
        t for t, payload in vcp_idx.items()
        if isinstance(payload, dict) and payload.get("vcp_pass") is True
    )

    # C) Freshness analysis (Optimization: only VCP survivors)
    try:
        fresh_resp = downstream_clients.analyze_freshness_batch(sorted(list(vcp_passed)))
        fresh_idx = _index_by_ticker(fresh_resp)
    except Exception as exc:
        logger.error("refresh-watchlist-status: analyze/freshness/batch failed: %s", exc, exc_info=True)
        fresh_idx = {}
        failed_downstream_tickers.update(vcp_passed)

    # D) Data return (Fetch for ALL tickers to ensure UI data availability)
    try:
        metrics_resp = downstream_clients.watchlist_metrics_batch(tickers)
        # metrics_resp is already {ticker: {metrics...}}, compatible with _index_by_ticker
        data_idx = _index_by_ticker(metrics_resp)
    except Exception as exc:
        logger.error("refresh-watchlist-status: watchlist-metrics/batch failed: %s", exc, exc_info=True)
        data_idx = {}
        failed_downstream_tickers.update(tickers)

    # 3. Compute status & Enrich items
    enriched_items: List[Dict[str, Any]] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        t = item.get("ticker")
        if not isinstance(t, str) or not t:
            continue
        base = dict(item)  # do not mutate original

        # --- Compute Last Refresh Status & Failed Stage ---
        # Default to UNKNOWN if we hit a downstream error for this specific ticker logic path
        computed_status = LastRefreshStatus.UNKNOWN
        computed_failed_stage = None

        if t in failed_downstream_tickers:
             computed_status = LastRefreshStatus.UNKNOWN
        else:
            # Apply The Funnel Logic
            if t not in passed_screen:
                computed_status = LastRefreshStatus.FAIL
                computed_failed_stage = "screen"
            elif t not in vcp_passed:
                computed_status = LastRefreshStatus.FAIL
                computed_failed_stage = "vcp"
            else:
                # Check Freshness
                # Note: We access 'fresh' (the boolean) or 'passes_freshness_check' depending on the raw dict key
                # The Pydantic model handles alias parsing, but here we might be dealing with raw dicts from downstream_clients
                fr_data = fresh_idx.get(t, {})
                is_fresh = fr_data.get("passes_freshness_check", False) or fr_data.get("fresh", False)
                
                if not is_fresh:
                    computed_status = LastRefreshStatus.FAIL
                    computed_failed_stage = "freshness"
                else:
                    computed_status = LastRefreshStatus.PASS
                    computed_failed_stage = None

        # Attach computed status
        base["last_refresh_status"] = computed_status.value
        base["failed_stage"] = computed_failed_stage
        base["last_refresh_at"] = datetime.utcnow()

        # --- Attach Signals ---
        
        # VCP fields
        vcp = vcp_idx.get(t, {})
        if isinstance(vcp, dict):
            base["vcp_pass"] = bool(vcp.get("vcp_pass")) if "vcp_pass" in vcp else None
            base["is_pivot_good"] = bool(vcp.get("is_pivot_good")) if "is_pivot_good" in vcp else None
            base["has_pivot"] = bool(vcp.get("has_pivot")) if "has_pivot" in vcp else None
            base["is_at_pivot"] = bool(vcp.get("is_at_pivot")) if "is_at_pivot" in vcp else None
            base["has_pullback_setup"] = bool(vcp.get("has_pullback_setup")) if "has_pullback_setup" in vcp else None
            base["pivot_price"] = vcp.get("pivot_price")
            base["pattern_age_days"] = vcp.get("pattern_age_days")

        # Freshness fields
        fr = fresh_idx.get(t, {})
        if isinstance(fr, dict):
            base["fresh"] = fr.get("passes_freshness_check", False) # For internal reference if needed
            base["days_since_pivot"] = fr.get("days_since_pivot")
            base["vcpFootprint"] = fr.get("vcpFootprint")
            base["message"] = fr.get("message")

        # Data fields
        dr = data_idx.get(t, {})
        if isinstance(dr, dict):
            base["current_price"] = dr.get("current_price")
            base["vol_last"] = dr.get("vol_last")
            base["vol_50d_avg"] = dr.get("vol_50d_avg")
            base["day_change_pct"] = dr.get("day_change_pct")

        # Helper calculations
        base["vol_vs_50d_ratio"] = _safe_ratio(base.get("vol_last"), base.get("vol_50d_avg"))

        try:
            cp = float(base["current_price"]) if base.get("current_price") is not None else None
            pp = float(base["pivot_price"]) if base.get("pivot_price") is not None else None
            
            if cp is not None and pp not in (None, 0.0):
                base["pivot_proximity_percent"] = ((cp - pp) / pp) * 100.0
            else:
                base["pivot_proximity_percent"] = None
        except Exception:
            base["pivot_proximity_percent"] = None

        enriched_items.append(base)

    # 4. Derive UI status and partition lists
    try:
        to_update, to_archive = watchlist_status_service.derive_refresh_lists(enriched_items)
    except Exception as exc:
        logger.error(
            "refresh-watchlist-status: error deriving status lists: %s", exc, exc_info=True
        )
        sample = build_sample_from_items(raw_items)
        message = (
            f"Watchlist refresh failed during status derivation for tickers: {sample}"
            if sample else "Watchlist refresh failed during status derivation."
        )
        return {
            "message": message,
            "updated_items": 0,
            "archived_items": 0,
            "failed_items": len(raw_items),
        }

    # 5. Persist
    mongo_client.bulk_update_status(db, to_update)
    mongo_client.bulk_archive_failed(db, to_archive)

    update_count = len(to_update)
    archive_count = len(to_archive)
    
    # Note: We track failed_downstream_tickers for logic, but the orchestrator successfully 
    # processed them into an "UNKNOWN" state, so strictly speaking, the operation didn't fail.
    # However, for reporting purposes, we can count them.
    failed_count = len(failed_downstream_tickers) 

    total_processed = update_count + archive_count
    sample = build_sample_from_items(raw_items)
    message = (
        f"Watchlist refresh completed for {total_processed} items. Sample: {sample}"
        if sample else f"Watchlist refresh completed for {total_processed} items."
    )

    summary = {
        "message": message,
        "updated_items": update_count,
        "archived_items": archive_count,
        "failed_items": failed_count,
    }
    logger.info("refresh-watchlist-status: %s", summary)
    return summary
