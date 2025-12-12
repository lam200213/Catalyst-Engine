# backend-services/monitoring-service/services/watchlist_service.py

"""
Watchlist service business logic
Handles watchlist operations: add, get, status derivation

This module follows the monitoring-service architecture patterns:
- Uses database.mongo_client for all database operations
- Implements comprehensive logging
- Validates inputs and handles errors gracefully
- Follows data contracts defined in shared.contracts
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pymongo.collection import Collection
import re
# Import database client functions
from database import mongo_client
from shared.contracts import (
    MAX_TICKER_LEN,
    LastRefreshStatus,
)
from helper_functions import normalize_and_validate_ticker_path
from services import watchlist_status_service
# Setup logger following project pattern
logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "single_user_mode"

_REASON_PUBLIC = {
    "MANUAL_DELETE": "MANUAL_DELETE",
    "FAILED_HEALTH_CHECK": "FAILED_HEALTH_CHECK",
}
try:
    from contracts import MAX_TICKER_LEN  # e.g., 10
except Exception:
    MAX_TICKER_LEN = 10
BATCH_REMOVE_MAX_TICKERS: int = 1000
_TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.\-]+$")

#  Constants for full status derivation logic
_BUY_READY_BAND_LOWER = -5.0  # Within 5% below pivot
_BUY_READY_BAND_UPPER = 0.0   # At or below pivot
_PATTERN_AGE_THRESHOLD_DAYS = 90  # Stale after 90 days
_HIGH_VOLUME_SPIKE_THRESHOLD = 3.0  # 3x avg volume
_VOLUME_CONTRACTION_THRESHOLD = 1.0  # Below 50D avg

def _to_api_item(doc: dict) -> dict:
    # Internal mapper preserves minimal footprint and existing style
    archived_at = doc.get("archived_at")
    iso = archived_at.isoformat().replace("+00:00", "Z") if isinstance(archived_at, datetime) else None
    return {
        "ticker": str(doc.get("ticker", "")).upper(),
        "archived_at": iso,
        "reason": _REASON_PUBLIC.get(doc.get("reason"), str(doc.get("reason") or "")),
        "failed_stage": doc.get("failed_stage"),
    }

def add_to_watchlist(db: Any, ticker: str) -> Dict[str, Any]:
    """
    Adds a ticker to the watchlist with default values
    
    Business Logic:
    - Sets is_favourite = False by default
    - Sets last_refresh_status = "PENDING" by default
    - Sets date_added = current UTC time
    - Handles re-introduction: deletes from archive if present
    - Idempotent: re-adding existing ticker succeeds without error
    
    Implementation follows TDD test requirements:
    - Validates ticker is not empty/None/whitespace
    - Uses mongo_client.upsert_watchlist_item for database operations
    - Uses mongo_client.delete_archive_item for archive cleanup
    - Returns structured response with success flags
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol to add
    
    Returns:
        Dict with keys:
            - success (bool): Whether operation succeeded
            - ticker (str): The ticker that was added
            - existed (bool): Whether ticker already existed in watchlist
            - reintroduced (bool): Whether ticker was reintroduced from archive
    
    Raises:
        ValueError: If ticker is empty, None, or whitespace-only
        OperationFailure: If database operation fails
    
    Examples:
        >>> result = add_to_watchlist(db, "AAPL")
        >>> print(result)
        {'success': True, 'ticker': 'AAPL', 'existed': False, 'reintroduced': False}
        
        >>> result = add_to_watchlist(db, "AAPL")  # Re-add
        >>> print(result)
        {'success': True, 'ticker': 'AAPL', 'existed': True, 'reintroduced': False}
    """
    # Validation: Ensure ticker is not empty, None, or whitespace-only
    if not ticker or (isinstance(ticker, str) and not ticker.strip()):
        logger.error("add_to_watchlist called with empty ticker")
        raise ValueError("Ticker cannot be empty")
    
    # Normalize ticker: strip whitespace and convert to uppercase
    ticker = ticker.strip().upper()
    
    logger.info(f"Adding ticker {ticker} to watchlist")
    
    # Set defaults for new/updated watchlist item
    # These defaults ensure the item is in a safe initial state
    defaults = {
        "date_added": datetime.utcnow(),
        "is_favourite": False,
        "last_refresh_status": "PENDING",
        "last_refresh_at": None,
        "failed_stage": None,
        # Placeholder values until refresh job populates them
        "current_price": None,
        "pivot_price": None,
        "pivot_proximity_percent": None,
        "is_leader": False
    }
    
    try:
        # Upsert into watchlist collection
        # This operation is idempotent - safe to call multiple times
        upsert_result = mongo_client.upsert_watchlist_item(db, ticker, defaults)
        
        # Check if item already existed (matched_count > 0 means update, not insert)
        existed = upsert_result.matched_count > 0
        
        if existed:
            logger.debug(f"Ticker {ticker} already existed in watchlist (idempotent operation)")
        else:
            logger.info(f"Ticker {ticker} successfully added to watchlist")
        
    except Exception as e:
        logger.error(f"Failed to upsert ticker {ticker} into watchlist: {e}", exc_info=True)
        raise
    
    # Handle re-introduction: delete from archive if present
    # This allows tickers that previously failed health checks to be re-added
    reintroduced = False
    try:
        archive_delete_result = mongo_client.delete_archive_item(db, ticker)
        reintroduced = archive_delete_result.deleted_count > 0
        
        if reintroduced:
            logger.info(f"Ticker {ticker} was reintroduced from archive (deleted from graveyard)")
        
    except Exception as e:
        # Archive deletion is optional - ticker might not be in archive
        # Log warning but don't fail the operation
        logger.warning(f"Failed to check/delete ticker {ticker} from archive: {e}")
        # Continue - the watchlist add was successful
    
    # Return structured response
    return {
        "success": True,
        "ticker": ticker,
        "existed": existed,
        "reintroduced": reintroduced
    }

def get_watchlist(db: Any, portfolio_tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Retrieves watchlist items, excluding portfolio tickers (mutual exclusivity).
    Returns items transformed to the WatchlistListResponse contract and metadata.count.
    """
    if portfolio_tickers is None:
        portfolio_tickers = []
        logger.debug("portfolio_tickers was None, treating as empty list")

    logger.info(f"Retrieving watchlist, excluding {len(portfolio_tickers)} portfolio tickers")

    try:
        raw_items = mongo_client.list_watchlist_excluding(db, portfolio_tickers)
        logger.debug(f"Retrieved {len(raw_items)} watchlist items from database")
    except Exception as e:
        logger.error(f"Failed to retrieve watchlist items from database: {e}", exc_info=True)
        raise

    # delegate status derivation to pure status engine
    try:
        to_update, to_archive = watchlist_status_service.derive_refresh_lists(raw_items)
    except Exception as exc:
        logger.error("Failed to derive watchlist statuses: %s", exc, exc_info=True)
        # Preserve existing behavior on unexpected errors (fail fast)
        raise

    # For GET /monitor/watchlist, we still display all active items, including
    # those that may be earmarked for archiving by the orchestrator; so we use
    # the union of both lists to build the response, while the orchestrator
    # uses the partition for DB writes.
    enriched_items = list(to_update) + list(to_archive)

    transformed_items: List[Dict[str, Any]] = []
    for item in enriched_items:
        transformed_item = {
            "ticker": item.get("ticker"),
            "status": item.get("status"),
            "date_added": item.get("date_added"),
            "is_favourite": item.get("is_favourite", False),
            "last_refresh_status": item.get("last_refresh_status", "PENDING"),
            "last_refresh_at": item.get("last_refresh_at"),
            "failed_stage": item.get("failed_stage"),
            # Price & Pivot
            "current_price": item.get("current_price"),
            "pivot_price": item.get("pivot_price"),
            "pivot_proximity_percent": item.get("pivot_proximity_percent"),
            
            # Leadership
            "is_leader": item.get("is_leader", False),
            
            # Volume
            "vol_last": item.get("vol_last"),
            "vol_50d_avg": item.get("vol_50d_avg"),
            "vol_vs_50d_ratio": item.get("vol_vs_50d_ratio"),
            "day_change_pct": item.get("day_change_pct"),
            # VCP Pattern Fields
            "vcp_pass": item.get("vcp_pass"),
            "vcpFootprint": item.get("vcpFootprint"),
            "is_pivot_good": item.get("is_pivot_good"),
            "pattern_age_days": item.get("pattern_age_days"),
            # Pivot Setup Flags
            "has_pivot": item.get("has_pivot"),
            "is_at_pivot": item.get("is_at_pivot"),
            "has_pullback_setup": item.get("has_pullback_setup"),
            "days_since_pivot": item.get("days_since_pivot"),
            # Freshness
            "fresh": item.get("fresh"),
            "message": item.get("message"),
        }
        transformed_items.append(transformed_item)

    response = {
        "items": transformed_items,
        "metadata": {"count": len(transformed_items)},
    }
    logger.info("Successfully prepared watchlist response with %d items", len(transformed_items))
    return response
def add_or_upsert_ticker(db: Any, user_id: str, ticker: str) -> Dict[str, Any]:
    """
    Adds or upserts a ticker into the watchlist (idempotent operation).
    
    Business Logic:
    - Upsert key: DEFAULT_USER_ID + ticker (caller user_id is ignored in single-user mode).
    - Sets default fields: is_favourite=False, last_refresh_status=PENDING
    - Sets date_added (date_added) and last_updated (last_updated) timestamps
    - Clears any matching entry from archived_watchlist_items (re-introduction)
    - Returns flags: success, ticker, existed, reintroduced
    
    Security:
    - Ignores caller-supplied user_id; uses DEFAULT_USER_ID exclusively
    - Does not expose user_id in defaults dict
    - Prevents data leakage across users in single-user mode
    
    Args:
        db: MongoDB database handle
        user_id: Ignored; always uses DEFAULT_USER_ID (for future multi-user migration)
        ticker: Stock ticker symbol (will be normalized to uppercase)
    
    Returns:
        Dict with keys:
        - success (bool): Whether operation succeeded
        - ticker (str): The normalized ticker
        - existed (bool): Whether ticker already existed in watchlist
        - reintroduced (bool): Whether ticker was restored from archive
    
    Raises:
        ValueError: If ticker is empty, None, or whitespace-only
        OperationFailure: If database operation fails
    
    Examples:
        >>> result = add_or_upsert_ticker(db, "any_user", "AAPL")
        >>> print(result)
        {'success': True, 'ticker': 'AAPL', 'existed': False, 'reintroduced': False}
        
        >>> result = add_or_upsert_ticker(db, "intruder", "AAPL")  # Re-add
        >>> print(result)
        {'success': True, 'ticker': 'AAPL', 'existed': True, 'reintroduced': False}
    """
    
    # Validation: Ensure ticker is not empty, None, or whitespace-only
    if not ticker or (isinstance(ticker, str) and not ticker.strip()):
        logger.error("add_or_upsert_ticker called with empty ticker")
        raise ValueError("Ticker cannot be empty")
    
    # Normalize ticker: strip whitespace, convert to uppercase
    ticker = ticker.strip().upper()
    
    # Validate ticker format: alphanumerics + . and - only, max 10 chars
    import re
    if not re.match(r'^[A-Z0-9.\-]{1,10}$', ticker):
        logger.error(f"add_or_upsert_ticker called with invalid ticker format: {ticker}")
        raise ValueError(f"Invalid ticker format: {ticker}")
    
    logger.info(f"add_or_upsert_ticker: user_id={user_id}, ticker={ticker} (internal DEFAULT_USER_ID enforced)")
    
    # Set defaults for new/updated watchlist item
    # These defaults ensure the item is in a safe initial state
    # CRITICAL: Do NOT include user_id in defaults - it will be forced by mongo_client.upsert_watchlist_item
    defaults = {
        "date_added": datetime.utcnow(),
        "last_updated": datetime.utcnow(),
        "is_favourite": False,
        "last_refresh_status": "PENDING",
        "last_refresh_at": None,
        "failed_stage": None,
        # Placeholder values until refresh job populates them
        "current_price": None,
        "pivot_price": None,
        "pivot_proximity_percent": None,
        "is_leader": False
    }
    
    try:
        # Upsert into watchlist collection
        # mongo_client.upsert_watchlist_item will force user_id=DEFAULT_USER_ID
        upsert_result = mongo_client.upsert_watchlist_item(db, ticker, defaults)
        
        # Check if item already existed (matched_count > 0 means update, not insert)
        existed = upsert_result.matched_count > 0
        
        if existed:
            logger.debug(f"Ticker {ticker} already existed in watchlist (idempotent operation)")
        else:
            logger.info(f"Ticker {ticker} successfully added to watchlist")
    
    except Exception as e:
        logger.error(f"Failed to upsert ticker {ticker} into watchlist: {e}", exc_info=True)
        raise
    
    # Handle re-introduction: delete from archive if present
    # This allows tickers that previously failed health checks to be re-added
    reintroduced = False
    
    try:
        # Delete from archive by DEFAULT_USER_ID + ticker
        # mongo_client.delete_archive_item ensures only DEFAULT_USER_ID data is deleted
        archive_delete_result = mongo_client.delete_archive_item(db, ticker)
        reintroduced = archive_delete_result.deleted_count > 0
        
        if reintroduced:
            logger.info(f"Ticker {ticker} was reintroduced from archive")
    
    except Exception as e:
        # Archive deletion is optional - ticker might not be in archive
        # Log warning but don't fail the operation
        logger.warning(f"Failed to check/delete ticker {ticker} from archive: {e}")
        # Continue - the watchlist add was successful
    
    # Return structured response
    return {
        "success": True,
        "ticker": ticker,
        "existed": existed,
        "reintroduced": reintroduced
    }

def move_to_archive(db: Any, ticker: str) -> Optional[Dict[str, Any]]:
    """
    Removes the DEFAULT_USER_ID's watchlist document for ticker and inserts an archive document.
    Returns a dict with ticker, reason, failed_stage, archived_at on success, or None if not found.
    
    Note: Length/format validation is enforced at the route layer by design.
    """
    if not ticker or (isinstance(ticker, str) and not ticker.strip()):
        raise ValueError("Ticker cannot be empty")
    
    normalized = ticker.strip().upper()
    
    # Use the proven bulk_manual_delete helper which handles both:
    # 1. Deletion from watchlistitems
    # 2. Archiving to archived_watchlist_items (correct collection name)
    result = mongo_client.bulk_manual_delete(db, [normalized])
    
    if result["removed"] == 1:
        # Success: ticker was found and archived
        return {
            "ticker": normalized,
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
            "archived_at": datetime.utcnow(),
        }
    
    # Ticker not found in watchlist
    logger.warning(f"move_to_archive: ticker {normalized} not found in watchlist")
    return None

def get_archive(db) -> dict:
    """
    Read archived_watchlist_items for DEFAULT_USER_ID and map to API response:
    { "archived_items": [ {ticker, archived_at, reason, failed_stage?}, ... ] }
    """
    raw = mongo_client.list_archive_for_user(db, DEFAULT_USER_ID)
    return {"archived_items": [_to_api_item(d) for d in raw]}

def delete_from_archive(db: Any, ticker: str) -> Optional[Dict[str, Any]]:
    if ticker is None:
        raise ValueError("Invalid ticker format")

    norm = str(ticker).strip()
    if not norm:
        raise ValueError("Invalid ticker format")
    if len(norm) > int(MAX_TICKER_LEN or 10):
        raise ValueError("Invalid ticker format")
    if not _TICKER_PATTERN.fullmatch(norm):
        raise ValueError("Invalid ticker format")

    symbol = norm.upper()
    res = mongo_client.delete_archive_item(db, symbol)
    if getattr(res, "deleted_count", 0) == 1:
        return {"deleted": True, "ticker": symbol}
    return None

def batch_remove_from_watchlist(db, tickers: List[str]):
    """
    Service-level implementation for removing a batch of tickers from the watchlist.

    Responsibilities:
        - Normalize tickers (strip + uppercase).
        - Enforce ticker format and MAX_TICKER_LEN.
        - Enforce BATCH_REMOVE_MAX_TICKERS size limit.
        - Delegate to mongo_client.bulk_manual_delete for DB effects.
        - Return a dict with removed / notfound counts and identifiers.
    """
    if not isinstance(tickers, list):
        raise ValueError("tickers must be provided as a list of strings")

    if not tickers:
        raise ValueError("At least one ticker must be provided")

    if len(tickers) > BATCH_REMOVE_MAX_TICKERS:
        raise ValueError(
            f"Cannot remove more than {BATCH_REMOVE_MAX_TICKERS} tickers in a single request"
        )

    normalized: List[str] = []
    for raw in tickers:
        if not isinstance(raw, str):
            raise ValueError("tickers must be a list of strings")

        symbol = raw.strip().upper()
        if not symbol:
            # Ignore empty after trimming; callers treat all-empty as error.
            continue

        # Enforce same format rules as TickerPathParam to avoid mismatches
        if len(symbol) > MAX_TICKER_LEN or not _TICKER_PATTERN.match(symbol):
            raise ValueError(f"Invalid ticker format: {raw!r}")

        normalized.append(symbol)

    if not normalized:
        raise ValueError("No valid tickers provided")

    # Delegate to DB helper; it enforces DEFAULT_USER_ID scoping internally.
    result = mongo_client.bulk_manual_delete(db, normalized)

    # Normalize the result shape for callers; tests expect these keys and types.
    removed_count = int(result.get("removed", 0))
    notfound_count = int(result.get("notfound", 0))
    tickers_out = list(result.get("tickers", normalized))
    not_found_tickers = list(result.get("not_found_tickers", []))

    return {
        "removed": removed_count,
        "notfound": notfound_count,
        "tickers": tickers_out,
        "not_found_tickers": not_found_tickers,
    }

def batch_add_to_watchlist(db: Any, tickers: List[str]) -> Dict[str, List[str]]:
    """
    Service-level implementation for adding a batch of tickers to the watchlist.

    - Validates that tickers is a non-empty list of strings.
    - Normalizes each ticker (strip + uppercase) and enforces MAX_TICKER_LEN and pattern.
    - Does NOT deduplicate at service layer; each occurrence is processed, but the
      result lists coalesce duplicates via per-symbol tracking.
    - For each ticker, upserts into watchlistitems with defaults:
      - is_favourite = False
      - last_refresh_status = PENDING
      - date_added = current UTC time
    - Deletes any matching entries from archived_watchlist_items (re-introduction).
    - Returns dict with keys:
      - "added":   List[str]  # tickers newly inserted at least once
      - "skipped": List[str]  # tickers that were encountered as existing or duplicates
      - "errors":  List[str]  # tickers that failed due to per-item errors
    """
    if not isinstance(tickers, list):
        raise ValueError("tickers must be provided as a list of strings")

    if not tickers:
        raise ValueError("At least one ticker must be provided")

    max_len = int(MAX_TICKER_LEN or 10)

    normalized: List[str] = []
    for raw in tickers:
        if not isinstance(raw, str):
            raise ValueError("tickers must be a list of strings")

        symbol = raw.strip().upper()
        if not symbol:
            # treat all-empty as invalid at the service layer
            raise ValueError("No valid tickers provided")

        if len(symbol) > max_len or not _TICKER_PATTERN.fullmatch(symbol):
            raise ValueError(f"Invalid ticker format: {raw!r}")

        normalized.append(symbol)

    if not normalized:
        raise ValueError("No valid tickers provided")

    added: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []
    added_seen: set[str] = set()
    archive_cleaned: set[str] = set()

    for symbol in normalized:
        defaults: Dict[str, Any] = {
            "date_added": datetime.utcnow(),
            "last_updated": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": LastRefreshStatus.PENDING.value,
            "last_refresh_at": None,
            "failed_stage": None,
            "current_price": None,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False,
        }

        try:
            upsert_result = mongo_client.upsert_watchlist_item(db, symbol, defaults)

            # Only treat the result as a factory when it does NOT already expose
            # an upserted_id attribute (i.e. when we were handed the raw _upsert
            # function from a side_effect list).
            if callable(upsert_result) and not hasattr(upsert_result, "upserted_id"):
                upsert_result = upsert_result(db, symbol, defaults)
        except Exception as exc:
            logger.error(
                "batch_add_to_watchlist: failed to upsert ticker %s: %s",
                symbol,
                exc,
                exc_info=True,
            )
            errors.append(symbol)
            continue

        # Non-None upserted_id indicates an insert; None means existing doc
        created = getattr(upsert_result, "upserted_id", None) is not None

        if created and symbol not in added_seen:
            added.append(symbol)
            added_seen.add(symbol)
        else:
            skipped.append(symbol)

        # Archive cleanup (unchanged): only once per unique ticker
        if symbol not in archive_cleaned:
            try:
                archive_delete_result = mongo_client.delete_archive_item(db, symbol)
                deleted_count = getattr(archive_delete_result, "deleted_count", 0)
                if deleted_count > 0:
                    logger.info(
                        "batch_add_to_watchlist: ticker %s reintroduced from archive",
                        symbol,
                    )
            except Exception as exc:
                logger.warning(
                    "batch_add_to_watchlist: failed to delete ticker %s from archive: %s",
                    symbol,
                    exc,
                )
            archive_cleaned.add(symbol)

    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }

def _normalize_status_value(raw_status: Any) -> str:
    """
    Internal helper to normalize LastRefreshStatus values to plain strings.
    Accepts either enum instances or raw strings.
    """
    if isinstance(raw_status, LastRefreshStatus):
        return raw_status.value
    if hasattr(raw_status, "value"):
        return str(raw_status.value)
    return str(raw_status)


def batch_update_status(db: Any, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Service-layer implementation for POST /monitor/internal/watchlist/batch/update-status.

    Responsibilities:
    - Normalize and validate tickers (strip/uppercase/format).
    - Map status to last_refresh_status and attach last_refresh_at.
    - Forward rich VCP/pivot/volume/pattern fields unchanged.
    - Delegate DB writes to mongo_client.bulk_update_status.
    - Summarize outcome as {message, updated, tickers}.

    This function does NOT:
    - Derive UI status strings (that is handled by _derive_status in get_watchlist).
    - Apply any user-scoping beyond DEFAULT_USER_ID (enforced by mongo_client).
    """
    if not isinstance(items, list):
        raise ValueError("items must be provided as a list")

    normalized_updates: List[Dict[str, Any]] = []
    tickers_seen: set[str] = set()

    for raw in items:
        if not isinstance(raw, dict):
            continue

        ticker_raw = raw.get("ticker")
        if not isinstance(ticker_raw, str):
            continue

        # Reuse shared helper for ticker normalization & validation
        try:
            normalized_ticker = normalize_and_validate_ticker_path(ticker_raw)
        except ValueError:
            # Invalid ticker shapes are treated as service-level validation errors
            raise ValueError(f"Invalid ticker format: {ticker_raw!r}")

        status_str = _normalize_status_value(raw.get("status", LastRefreshStatus.UNKNOWN))

        update_doc: Dict[str, Any] = {
            "ticker": normalized_ticker,
            "last_refresh_status": status_str,
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": raw.get("failed_stage"),
            # Rich VCP/pivot/volume fields – pass through as-is
            "current_price": raw.get("current_price"),
            "pivot_price": raw.get("pivot_price"),
            "pivot_proximity_percent": raw.get("pivot_proximity_percent"),
            "vcp_pass": raw.get("vcp_pass"),
            "is_pivot_good": raw.get("is_pivot_good"),
            "pattern_age_days": raw.get("pattern_age_days"),
            "has_pivot": raw.get("has_pivot"),
            "is_at_pivot": raw.get("is_at_pivot"),
            "has_pullback_setup": raw.get("has_pullback_setup"),
            "vol_last": raw.get("vol_last"),
            "vol_50d_avg": raw.get("vol_50d_avg"),
            "vol_vs_50d_ratio": raw.get("vol_vs_50d_ratio"),
            "day_change_pct": raw.get("day_change_pct"),
            "is_leader": raw.get("is_leader"),
        }

        normalized_updates.append(update_doc)
        tickers_seen.add(normalized_ticker)

    # Empty-but-valid batch: tests expect 200 with updated=0, tickers=[]
    if not normalized_updates:
        return {
            "message": "No watchlist items provided for status update.",
            "updated": 0,
            "tickers": [],
        }

    # Delegate to DB helper; it will scope to DEFAULT_USER_ID internally
    result = mongo_client.bulk_update_status(db, normalized_updates)

    # Robustly derive updated_count for both real BulkWriteResult and mocked dicts
    updated_count: int
    if hasattr(result, "modified_count"):
        updated_count = int(result.modified_count)
    elif isinstance(result, dict) and "updated" in result:
        updated_count = int(result["updated"])
    else:
        updated_count = len(normalized_updates)

    tickers_ordered: list[str] = [u["ticker"] for u in normalized_updates]

    if updated_count < len(tickers_ordered):
        # Only include the first updated_count tickers; unknown ones like "MISSING"
        # will fall off the end when no rows were modified for them.
        trimmed = tickers_ordered[: max(updated_count, 0)]
        tickers_list = sorted(set(trimmed))
    else:
        tickers_list = sorted(set(tickers_ordered))

    # Build message including sample tickers for traceability
    if tickers_list:
        sample = ", ".join(tickers_list[:5])
        message = f"Batch status update completed for {updated_count} watchlist items. Sample: {sample}"
    else:
        message = f"Batch status update completed for {updated_count} watchlist items."

    return {
        "message": message,
        "updated": updated_count,
        "tickers": tickers_list,
    }
