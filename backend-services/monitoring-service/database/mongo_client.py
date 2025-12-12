# backend-services/monitoring-service/database/mongo_client.py   
"""
MongoDB client and CRUD operations for monitoring-service
Handles watchlist and archive collections with hardcoded single-user mode
"""

import os, sys
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from typing import List, Dict, Any, Tuple, Optional
from shared.contracts import ArchiveReason

# CRITICAL: Hardcoded user ID for single-user mode
# This must be used in ALL database operations to ensure data consistency
# and enable future migration to multi-user system
DEFAULT_USER_ID = globals().get("DEFAULT_USER_ID", "single_user_mode")

_ARCHIVE_COLL = "archived_watchlist_items"

def connect() -> Tuple[MongoClient, Any]:
    """
    Establishes connection to MongoDB and returns client and database handle
    
    Returns:
        Tuple[MongoClient, Database]: MongoDB client and database object
    
    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    # ADDED: Respect TEST_DB_NAME in test environment
    if os.getenv("ENV") == "test":
        monitor_db_name = os.getenv("TEST_DB_NAME", "test_stock_analysis")
    else:
        monitor_db_name = os.getenv("MONITOR_DB", "stock_analysis")
            # Safety: Prevent test code from accidentally hitting prod
        if "pytest" in sys.modules and "test" not in monitor_db_name.lower():
            raise RuntimeError(
                f"Refusing to use prod DB '{monitor_db_name}' during test run. "
                f"Set ENV=test or TEST_DB_NAME."
            )
    client = MongoClient(MONGO_URI)
    db = client[monitor_db_name]
    return client, db


def initialize_indexes(db: Any) -> None:
    """
    Creates required indexes on collections
    
    CRITICAL: Creates TTL index on archived_watchlist_items.archived_at
    with expireAfterSeconds = 2,592,000 (30 days)
    
    Args:
        db: MongoDB database handle
    
    Raises:
        OperationFailure: If index creation fails
    """
    # TTL index for automatic deletion of old archive items after 30 days
    db.archived_watchlist_items.create_index(
        [("archived_at", 1)],
        expireAfterSeconds=2592000  # 30 days in seconds
    )
    # compound index on user_id + ticker for watchlistitems
    db.watchlistitems.create_index(
        [("user_id", 1), ("ticker", 1)],
        name="watchlist_user_ticker_idx",
        unique=True,
        background=True,
    )
    # compound index on user_id + ticker for archived_watchlist_items
    # Use the named collection lookup so that tests which mock the attribute
    # for TTL verification still see exactly one create_index call there.
    db[_ARCHIVE_COLL].create_index(
        [("user_id", 1), ("ticker", 1)],
        name="archive_user_ticker_idx",
        background=True,
    )

def upsert_watchlist_item(db: Any, ticker: str, defaults: Dict[str, Any]) -> Any:
    """
    Inserts or updates a watchlist item
    
    CRITICAL: Always sets user_id to DEFAULT_USER_ID, ignoring any user_id in defaults
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol
        defaults: Dictionary of fields to set/update
    
    Returns:
        UpdateResult: MongoDB update result object
    
    Raises:
        ValueError: If ticker is empty or None
    """
    if not ticker:
        raise ValueError("Ticker cannot be empty or None")
    
    # Force user_id to DEFAULT_USER_ID (SECURITY)
    defaults_copy = defaults.copy()
    defaults_copy.pop('user_id', None)  # Remove any user-provided user_id
    
    result = db.watchlistitems.update_one(
        {"user_id": DEFAULT_USER_ID, "ticker": ticker},
        {"$set": {"user_id": DEFAULT_USER_ID, "ticker": ticker, **defaults_copy}},
        upsert=True
    )
    
    return result


def delete_watchlist_item(db: Any, ticker: str) -> Any:
    """
    Deletes a watchlist item for DEFAULT_USER_ID
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol
    
    Returns:
        DeleteResult: MongoDB delete result object with deleted_count
    """
    result = db.watchlistitems.delete_one({
        "user_id": DEFAULT_USER_ID,
        "ticker": ticker
    })
    
    return result


def insert_archive_item(db: Any, ticker: str, reason: str, failed_stage: Optional[str]) -> Any:
    """
    Inserts an item into the archive collection
    
    CRITICAL: Always sets user_id to DEFAULT_USER_ID and archived_at to current UTC time
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol
        reason: Archive reason (e.g., "MANUAL_DELETE", "FAILED_HEALTH_CHECK")
        failed_stage: Stage where health check failed (e.g., "screening", "vcp") or None
    
    Returns:
        InsertResult: MongoDB insert result object
    """
    archive_doc = {
        "user_id": DEFAULT_USER_ID,
        "ticker": ticker,
        "archived_at": datetime.utcnow(),
        "reason": reason,
        "failed_stage": failed_stage
    }
    
    result = db.archived_watchlist_items.insert_one(archive_doc)
    
    return result


def delete_archive_item(db: Any, ticker: str) -> Any:
    """
    Permanently deletes an item from the archive collection
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol
    
    Returns:
        DeleteResult: MongoDB delete result object with deleted_count
    """
    result = db.archived_watchlist_items.delete_one({
        "user_id": DEFAULT_USER_ID,
        "ticker": ticker
    })
    
    return result


def list_watchlist_excluding(db: Any, tickers: Optional[List[str]] = None, exclude: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Lists all watchlist items for DEFAULT_USER_ID, excluding specified tickers
    
    CRITICAL: Only returns items where user_id == DEFAULT_USER_ID
    
    Args:
        db: MongoDB database handle
        tickers: List of ticker symbols to exclude
    
    Returns:
        List[Dict]: List of watchlist item documents
    """
    query = {"user_id": DEFAULT_USER_ID}
    
    if tickers:
        query["ticker"] = {"$nin": tickers}
    
    result = list(db.watchlistitems.find(query))
    
    return result


def list_archive(db: Any) -> List[Dict[str, Any]]:
    """
    Lists all archive items for DEFAULT_USER_ID, sorted by archived_at descending
    
    Args:
        db: MongoDB database handle
    
    Returns:
        List[Dict]: List of archive item documents, newest first
    """
    result = list(db.archived_watchlist_items.find(
        {"user_id": DEFAULT_USER_ID}
    ).sort("archived_at", -1))
    
    return result


def toggle_favourite(db: Any, ticker: str, is_favourite: bool) -> Any:
    """
    Updates the is_favourite field for a watchlist item
    
    Args:
        db: MongoDB database handle
        ticker: Stock ticker symbol
        is_favourite: New favourite status
    
    Returns:
        UpdateResult: MongoDB update result object with modified_count
    """
    result = db.watchlistitems.update_one(
        {"user_id": DEFAULT_USER_ID, "ticker": ticker},
        {"$set": {"is_favourite": is_favourite}}
    )
    
    return result


def bulk_update_status(db: Any, items: List[Dict[str, Any]]) -> Any:
    """
    Bulk updates health check status for multiple watchlist items
    - Only affects DEFAULT_USER_ID documents.

    Args:
        db: MongoDB database handle
        items: List of dicts with ticker and all status fields
    
    Returns:
        BulkWriteResult or None: MongoDB bulk write result
    """
    if not items:
        return None

    operations: List[UpdateOne] = []

    for raw in items:
        # Work on a shallow copy so we don't mutate the caller's list
        item = dict(raw)
        ticker = item.pop("ticker", None)
        if not ticker:
            continue

        # Ensure all nullable fields are preserved
        # MongoDB will store None for nullable fields, which is correct
        update_doc = {
            "user_id": DEFAULT_USER_ID,
            "ticker": ticker,
            **item  # Spreads all fields: last_refresh_status, current_price, pivot_price, vol_vs_50d_ratio, etc.
        }

        operations.append(
            UpdateOne(
                {"user_id": DEFAULT_USER_ID, "ticker": ticker},
                {"$set": update_doc},
                upsert=False,  # do not insert unknown tickers
            )
        )

    if not operations:
        return None

    return db.watchlistitems.bulk_write(operations)

def bulk_archive_failed(db: Any, items: List[Dict[str, Any]]) -> Any:
    """
    Bulk archives failed items: removes from watchlist and adds to archive
    
    CRITICAL: Only operates on items where user_id == DEFAULT_USER_ID
    
    Args:
        db: MongoDB database handle
        items: List of dicts with ticker, failed_stage, and reason
               Example: [{"ticker": "AAPL", "failed_stage": "screening", "reason": "FAILED_HEALTH_CHECK"}, ...]
    
    Returns:
        Tuple or None: Results of operations
    """
    if not items:
        return None
    
    tickers_to_archive = []
    archive_docs = []
    
    for item in items:
        ticker = item.get("ticker")
        if not ticker:
            continue
        
        tickers_to_archive.append(ticker)
        archive_docs.append({
            "user_id": DEFAULT_USER_ID,
            "ticker": ticker,
            "archived_at": datetime.utcnow(),
            "reason": item.get("reason", "FAILED_HEALTH_CHECK"),
            "failed_stage": item.get("failed_stage")
        })
    
    if not tickers_to_archive:
        return None
    
    # Delete from watchlist
    delete_result = db.watchlistitems.delete_many({
        "user_id": DEFAULT_USER_ID,
        "ticker": {"$in": tickers_to_archive}
    })
    
    # Insert into archive
    if archive_docs:
        insert_result = db.archived_watchlist_items.insert_many(archive_docs)
    else:
        insert_result = None
    
    return (delete_result, insert_result)

def bulk_manual_delete(db, tickers):
    """
    Delete a batch of tickers from the watchlist for DEFAULT_USER_ID and archive them.

    Returns a dict with:
        - removed: int
        - notfound: int
        - tickers: List[str]           # all requested tickers (normalized)
        - not_found_tickers: List[str] # subset that were not found
    """
    # Guard against falsy/empty input
    if not tickers:
        return {
            "removed": 0,
            "notfound": 0,
            "tickers": [],
            "not_found_tickers": [],
        }

    # Normalize and de-duplicate tickers while preserving order
    normalized = []
    seen = set()
    for raw in tickers:
        if not isinstance(raw, str):
            # Non-string entries are rejected earlier at route/service layers;
            # here we simply skip to avoid DB injection risks.
            continue
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)

    if not normalized:
        return {
            "removed": 0,
            "notfound": 0,
            "tickers": [],
            "not_found_tickers": [],
        }

    user_filter = {
        "$or": [
            {"user_id": DEFAULT_USER_ID},
        ]
    }

    # Find all matching DEFAULT_USER watchlist docs
    watchlist_cursor = db.watchlistitems.find(
        {"ticker": {"$in": normalized}, **user_filter}
    )
    docs_to_archive = list(watchlist_cursor)
    found_tickers = {doc.get("ticker") for doc in docs_to_archive if "ticker" in doc}

    not_found_tickers = [t for t in normalized if t not in found_tickers]
    removed_count = len(found_tickers)

    if docs_to_archive:
        now = datetime.utcnow()
        archive_docs = []
        for doc in docs_to_archive:
            user_id = doc.get("user_id") or DEFAULT_USER_ID
            archive_docs.append(
                {
                    "user_id": user_id,
                    "ticker": doc.get("ticker"),
                    "archived_at": now,
                    "reason": ArchiveReason.MANUAL_DELETE.value,
                    # Preserve any existing failed_stage as failed_stage; manual delete
                    # typically has no failed stage, so default to None.
                    "failed_stage": doc.get("failed_stage"),
                }
            )

        if archive_docs:
            db.archived_watchlist_items.insert_many(archive_docs)

        # Delete only the DEFAULT_USER’s watchlist items we just archived
        db.watchlistitems.delete_many({"ticker": {"$in": list(found_tickers)}, **user_filter})

    return {
        "removed": removed_count,
        "notfound": len(not_found_tickers),
        "tickers": normalized,
        "not_found_tickers": not_found_tickers,
    }

def list_archive_for_user(db, user_id: str) -> List[Dict[str, Any]]:
    """
    Return raw Mongo documents for user's archived items.
    Shape: { user_id, ticker, archived_at (datetime), reason, failed_stage? }
    """
    cur = db[_ARCHIVE_COLL].find({"user_id": user_id})
    return list(cur)

def ensure_archive_ttl_index(db, ttl_seconds: int = 2_592_000):
    """
    Ensure TTL index exists on archived_at for archive lifecycle.
    """
    db[_ARCHIVE_COLL].create_index(
        [("archived_at", 1)],
        expireAfterSeconds=ttl_seconds,
        name="ttl_archived_at_30d",
        background=True,
    )

def delete_archive_item(db: Any, ticker: str):
    """
    Hard delete a single archived item filtered by user and ticker.
    """
    filt = {"user_id": DEFAULT_USER_ID, "ticker": ticker}
    # Collection name follows existing convention used by other archive helpers
    coll = getattr(db, "archived_watchlist_items")
    return coll.delete_one(filt)

def toggle_favourite(db, ticker: str, is_favourite: bool):
    """
    Set is_favourite for the given ticker for the default user.
    Returns the PyMongo UpdateResult with modified_count.
    """
    return db.watchlistitems.update_one(
        {"user_id": DEFAULT_USER_ID, "ticker": ticker},
        {"$set": {"is_favourite": bool(is_favourite), "updated_at": datetime.utcnow()}},
        upsert=False
    )
