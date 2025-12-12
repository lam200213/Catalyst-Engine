# backend-services/monitoring-service/services/watchlist_status_service.py
"""
Pure functions for:
- Deriving UI-facing watchlist status labels from raw analysis signals.
- Partitioning items into update-vs-archive buckets for the refresh orchestrator.

This module has:
- No direct database or HTTP calls.
- No dependency on Flask.
It operates only on in-memory dictionaries shaped like MongoDB watchlist documents.
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# status thresholds (mirroring watchlist_service)
_BUY_READY_BAND_LOWER = -5.0
_BUY_READY_BAND_UPPER = 0.0
_PATTERN_AGE_THRESHOLD_DAYS = 90
_HIGH_VOLUME_SPIKE_THRESHOLD = 3.0
_VOLUME_CONTRACTION_THRESHOLD = 1.0

def _derive_status(item: Dict[str, Any]) -> str:
    """
    Pure status derivation based on Phase 1/2 rules.

    - FAIL => "Failed"
    - PENDING/UNKNOWN => "Pending"
    - PASS => apply VCP/pivot/volume/pattern rules
    - Fallback => "Watch"
    """
    lrs = item.get("last_refresh_status")

    if lrs == "FAIL":
        return "Failed"
    if lrs in ("PENDING", "UNKNOWN"):
        return "Pending"
    if lrs != "PASS":
        return "Watch"

    pivot_price = item.get("pivot_price")
    pivot_proximity_pct = item.get("pivot_proximity_percent")
    vcp_pass = item.get("vcp_pass", False)
    is_pivot_good = item.get("is_pivot_good", False)
    pattern_age_days = item.get("pattern_age_days")
    has_pivot = item.get("has_pivot", False)
    has_pullback_setup = item.get("has_pullback_setup", False)
    vol_vs_50d_ratio = item.get("vol_vs_50d_ratio")
    day_change_pct = item.get("day_change_pct")

    rich_signals_present = any(
        key in item
        for key in (
            "vcp_pass",
            "is_pivot_good",
            "pattern_age_days",
            "has_pivot",
            "has_pullback_setup",
            "vol_vs_50d_ratio",
            "day_change_pct",
        )
    )

    # Simple mode: no rich VCP / volume fields present
    # backward‑compatibility and incomplete‑data mode
    if not rich_signals_present:
        if (
            pivot_price is not None
            and pivot_proximity_pct is not None
            and _BUY_READY_BAND_LOWER <= pivot_proximity_pct <= _BUY_READY_BAND_UPPER
        ):
            return "Buy Ready"
        return "Watch"

    # Guardrails
    if pattern_age_days is not None and pattern_age_days > _PATTERN_AGE_THRESHOLD_DAYS:
        return "Watch"

    if (
        vol_vs_50d_ratio is not None
        and vol_vs_50d_ratio >= _HIGH_VOLUME_SPIKE_THRESHOLD
        and day_change_pct is not None
        and day_change_pct < 0
    ):
        return "Watch"

    # Buy Ready
    if (
        vcp_pass
        and is_pivot_good
        and pivot_price is not None
        and pivot_proximity_pct is not None
        and _BUY_READY_BAND_LOWER <= pivot_proximity_pct <= _BUY_READY_BAND_UPPER
    ):
        return "Buy Ready"

    # Buy Alert – maturing pivot with contraction
    if (
        has_pivot
        and pivot_price is not None
        and pivot_proximity_pct is not None
        and pivot_proximity_pct < _BUY_READY_BAND_LOWER
        and vol_vs_50d_ratio is not None
        and vol_vs_50d_ratio < _VOLUME_CONTRACTION_THRESHOLD
    ):
        return "Buy Alert"

    # Buy Alert – pullback zone with contraction
    if (
        has_pullback_setup
        and vol_vs_50d_ratio is not None
        and 0.7 <= vol_vs_50d_ratio <= 0.8
    ):
        return "Buy Alert"

    return "Watch"

def derive_refresh_lists(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Partition raw watchlist items into update vs archive buckets
    and attach a UI-facing status label.

    Returns:
        (to_update, to_archive)
        - to_update: items that should remain on the active watchlist
                     and be sent to bulk_update_status.
        - to_archive: items that should be passed to bulk_archive_failed.
    """
    to_update: List[Dict[str, Any]] = []
    to_archive: List[Dict[str, Any]] = []

    if not items:
        return to_update, to_archive

    for item in items:
        if not isinstance(item, dict):
            continue

        ticker = item.get("ticker")
        lrs = item.get("last_refresh_status")

        # Validation: skip records missing key identifiers
        if not ticker or not isinstance(ticker, str) or not lrs:
            continue

        status = _derive_status(item)
        derived = dict(item)
        derived["ticker"] = ticker  # normalize type
        derived["last_refresh_status"] = lrs
        derived["status"] = status

        is_favourite = bool(item.get("is_favourite", False))

        if lrs == "FAIL" and not is_favourite:
            to_archive.append(derived)
        else:
            to_update.append(derived)

    return to_update, to_archive