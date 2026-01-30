# backend-services/monitoring-service/tests/db/test_mongo_watchlist_security.py
"""
Test suite for database/mongo_client.py
"""

import pytest
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import os
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
from database.mongo_client import (
    connect,
    initialize_indexes,
    upsert_watchlist_item,
    delete_watchlist_item,
    insert_archive_item,
    delete_archive_item,
    list_watchlist_excluding,
    list_archive,
    toggle_favourite,
    bulk_archive_failed,
    bulk_update_status,
    DEFAULT_USER_ID
)

# ============================================================================
# TEST: Watchlist CRUD Operations
# ============================================================================

class TestWatchlistCRUD:
    """Test watchlist item CRUD operations"""
    
    def test_upsert_watchlist_item_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify user_id is ALWAYS hardcoded to DEFAULT_USER_ID
        Even if caller tries to override it
        """
        client, db = test_db_connection
        
        ticker = "TSLA"
        malicious_defaults = {
            "user_id": "malicious_user",  # Attempt to override
            "date_added": datetime.utcnow(),
            "is_favourite": False
        }
        
        upsert_watchlist_item(db, ticker, malicious_defaults)
        
        # CRITICAL: Verify user_id is forced to DEFAULT_USER_ID
        saved_item = db.watchlistitems.find_one({"ticker": ticker})
        assert saved_item["user_id"] == DEFAULT_USER_ID, "SECURITY: user_id must ALWAYS be DEFAULT_USER_ID"
        assert saved_item["user_id"] != "malicious_user", "SECURITY: Must not accept user-provided user_id"
    
    def test_delete_watchlist_item_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify delete only affects DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Manually insert item with different user_id (simulating data pollution)
        db.watchlistitems.insert_one({
            "user_id": "other_user",
            "ticker": ticker,
            "date_added": datetime.utcnow()
        })
        
        # Attempt to delete
        result = delete_watchlist_item(db, ticker)
        
        # Should NOT delete the other user's item
        other_user_item = db.watchlistitems.find_one({"user_id": "other_user", "ticker": ticker})
        assert other_user_item is not None, "SECURITY: Should not delete items from other users"
        assert result.deleted_count == 0, "Should not delete items that don't belong to DEFAULT_USER_ID"
    
    def test_list_watchlist_excluding_ensures_user_id_filter(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify list_watchlist_excluding only returns DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        # Insert items for different users
        db.watchlistitems.insert_many([
            {"user_id": DEFAULT_USER_ID, "ticker": "AAPL", "date_added": datetime.utcnow()},
            {"user_id": "other_user", "ticker": "MSFT", "date_added": datetime.utcnow()},
            {"user_id": DEFAULT_USER_ID, "ticker": "GOOGL", "date_added": datetime.utcnow()},
        ])
        
        result = list_watchlist_excluding(db, [])
        
        # Should only return DEFAULT_USER_ID items
        assert len(result) == 2, "Should return only 2 items for DEFAULT_USER_ID"
        assert all(item["user_id"] == DEFAULT_USER_ID for item in result), "SECURITY: Must filter by DEFAULT_USER_ID"
        
        tickers = [item["ticker"] for item in result]
        assert "MSFT" not in tickers, "Should not return other user's items"
    
    def test_toggle_favourite_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify toggle_favourite only affects DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Insert items for different users
        db.watchlistitems.insert_many([
            {"user_id": DEFAULT_USER_ID, "ticker": ticker, "is_favourite": False, "date_added": datetime.utcnow()},
            {"user_id": "other_user", "ticker": ticker, "is_favourite": False, "date_added": datetime.utcnow()},
        ])
        
        # Toggle favourite
        toggle_favourite(db, ticker, True)
        
        # Verify only DEFAULT_USER_ID item was updated
        default_user_item = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": ticker})
        other_user_item = db.watchlistitems.find_one({"user_id": "other_user", "ticker": ticker})
        
        assert default_user_item["is_favourite"] is True, "Should update DEFAULT_USER_ID item"
        assert other_user_item["is_favourite"] is False, "SECURITY: Should not affect other user's items"


# ============================================================================
# TEST: Archive CRUD Operations
# ============================================================================

class TestArchiveCRUD:
    """Test archive (graveyard) CRUD operations"""

    def test_insert_archive_item_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify user_id is hardcoded in archive items
        """
        client, db = test_db_connection
        
        ticker = "TSLA"
        # Even if we try to inject user_id, it should be ignored
        result = insert_archive_item(db, ticker, "MANUAL_DELETE", None)
        
        archived_item = db.archived_watchlist_items.find_one({"ticker": ticker})
        assert archived_item["user_id"] == DEFAULT_USER_ID, "SECURITY: Must always use DEFAULT_USER_ID"

    def test_delete_archive_item_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify delete_archive_item only affects DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Insert archive items for different users
        db.archived_watchlist_items.insert_many([
            {
                "user_id": DEFAULT_USER_ID,
                "ticker": ticker,
                "archived_at": datetime.utcnow(),
                "reason": "MANUAL_DELETE"
            },
            {
                "user_id": "other_user",
                "ticker": ticker,
                "archived_at": datetime.utcnow(),
                "reason": "MANUAL_DELETE"
            }
        ])
        
        # Attempt to delete
        result = delete_archive_item(db, ticker)
        
        # Verify only DEFAULT_USER_ID item was deleted
        assert result.deleted_count == 1, "Should delete only one item"
        
        remaining = list(db.archived_watchlist_items.find({"ticker": ticker}))
        assert len(remaining) == 1, "One item should remain"
        assert remaining[0]["user_id"] == "other_user", "SECURITY: Should not delete other user's archive items"

    def test_list_archive_hardcoded_user_id_filter(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify list_archive only returns DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        # Insert archive items for different users
        db.archived_watchlist_items.insert_many([
            {
                "user_id": DEFAULT_USER_ID,
                "ticker": "AAPL",
                "archived_at": datetime.utcnow(),
                "reason": "MANUAL_DELETE"
            },
            {
                "user_id": "other_user",
                "ticker": "MSFT",
                "archived_at": datetime.utcnow(),
                "reason": "MANUAL_DELETE"
            },
            {
                "user_id": DEFAULT_USER_ID,
                "ticker": "GOOGL",
                "archived_at": datetime.utcnow(),
                "reason": "FAILED_HEALTH_CHECK",
                "failed_stage": "vcp"
            }
        ])
        
        result = list_archive(db)
        
        assert len(result) == 2, "Should return only DEFAULT_USER_ID items"
        assert all(item["user_id"] == DEFAULT_USER_ID for item in result), "SECURITY: Must filter by DEFAULT_USER_ID"
        
        tickers = [item["ticker"] for item in result]
        assert "MSFT" not in tickers, "Should not return other user's archive items"

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
