# backend-services/monitoring-service/tests/db/test_mongo_watchlist_crud.py
"""
Test suite for database/mongo_client.py
Following TDD principles - these tests should be written BEFORE implementation
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
    
    def test_upsert_watchlist_item_insert_new(self, test_db_connection):
        """Verify inserting a new watchlist item"""
        client, db = test_db_connection
        
        ticker = "NVDA"
        defaults = {
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PENDING"
        }
        
        result = upsert_watchlist_item(db, ticker, defaults)
        
        # Verify return value
        assert result is not None, "Should return result object"
        
        # Verify data in database
        saved_item = db.watchlistitems.find_one({"ticker": ticker})
        assert saved_item is not None, "Item should be saved in database"
        assert saved_item["ticker"] == ticker, "Ticker should match"
        assert saved_item["user_id"] == DEFAULT_USER_ID, "CRITICAL: user_id must be DEFAULT_USER_ID"
        assert saved_item["is_favourite"] == False, "is_favourite should match defaults"
        assert saved_item["last_refresh_status"] == "PENDING", "Status should match defaults"
    
    def test_upsert_watchlist_item_update_existing(self, test_db_connection):
        """Verify updating an existing watchlist item (upsert behavior)"""
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Insert initial item
        initial_defaults = {
            "date_added": datetime.utcnow() - timedelta(days=10),
            "is_favourite": False,
            "last_refresh_status": "PENDING"
        }
        upsert_watchlist_item(db, ticker, initial_defaults)
        
        # Update same item
        update_defaults = {
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None
        }
        upsert_watchlist_item(db, ticker, update_defaults)
        
        # Verify only one document exists
        count = db.watchlistitems.count_documents({"ticker": ticker, "user_id": DEFAULT_USER_ID})
        assert count == 1, "Should not create duplicate, only update"
        
        # Verify updated fields
        updated_item = db.watchlistitems.find_one({"ticker": ticker})
        assert updated_item["last_refresh_status"] == "PASS", "Status should be updated"
        assert updated_item["user_id"] == DEFAULT_USER_ID, "user_id must remain DEFAULT_USER_ID"
    
    def test_upsert_watchlist_item_empty_ticker(self, test_db_connection):
        """Edge case: Verify handling of empty ticker"""
        client, db = test_db_connection
        
        with pytest.raises((ValueError, Exception)):
            upsert_watchlist_item(db, "", {"date_added": datetime.utcnow()})
    
    def test_upsert_watchlist_item_none_ticker(self, test_db_connection):
        """Edge case: Verify handling of None ticker"""
        client, db = test_db_connection
        
        with pytest.raises((ValueError, TypeError, Exception)):
            upsert_watchlist_item(db, None, {"date_added": datetime.utcnow()})
    
    def test_delete_watchlist_item_existing(self, test_db_connection):
        """Verify deleting an existing watchlist item"""
        client, db = test_db_connection
        
        # Insert item first
        ticker = "MSFT"
        upsert_watchlist_item(db, ticker, {"date_added": datetime.utcnow()})
        
        # Verify it exists
        assert db.watchlistitems.find_one({"ticker": ticker}) is not None
        
        # Delete
        result = delete_watchlist_item(db, ticker)
        
        # Verify deletion
        assert result.deleted_count == 1, "Should delete exactly one item"
        assert db.watchlistitems.find_one({"ticker": ticker}) is None, "Item should no longer exist"
    
    def test_delete_watchlist_item_nonexistent(self, test_db_connection):
        """Edge case: Verify deleting non-existent item returns 0"""
        client, db = test_db_connection
        
        result = delete_watchlist_item(db, "NONEXISTENT")
        
        assert result.deleted_count == 0, "Should return 0 when item doesn't exist"
 
# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios"""
    
    def test_special_characters_in_ticker(self, test_db_connection):
        """Edge case: Verify handling of special characters in ticker"""
        client, db = test_db_connection
        
        special_tickers = ["BRK.B", "BRK-B", "BRK B"]
        
        for ticker in special_tickers:
            upsert_watchlist_item(db, ticker, {"date_added": datetime.utcnow()})
            
            # Should be retrievable
            item = db.watchlistitems.find_one({"ticker": ticker})
            assert item is not None, f"Should handle special ticker: {ticker}"
            assert item["ticker"] == ticker
    
    def test_very_long_ticker_symbol(self, test_db_connection):
        """Edge case: Verify handling of very long ticker symbol"""
        client, db = test_db_connection
        
        long_ticker = "A" * 50  # Unrealistically long
        
        # Should either accept or raise clear error
        try:
            result = upsert_watchlist_item(db, long_ticker, {"date_added": datetime.utcnow()})
            # If accepted, verify it's stored correctly
            item = db.watchlistitems.find_one({"ticker": long_ticker})
            assert item is not None
        except (ValueError, Exception) as e:
            # If rejected, should be a clear error
            assert str(e)  # Error message should not be empty
    
    def test_concurrent_upsert_same_ticker(self, test_db_connection):
        """Edge case: Verify handling of concurrent upserts (race condition)"""
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Simulate rapid upserts
        for i in range(10):
            upsert_watchlist_item(db, ticker, {
                "date_added": datetime.utcnow(),
                "last_refresh_status": f"STATUS_{i}"
            })
        
        # Should only have one document
        count = db.watchlistitems.count_documents({"ticker": ticker, "user_id": DEFAULT_USER_ID})
        assert count == 1, "Should not create duplicates even with rapid upserts"
    
    def test_null_values_in_optional_fields(self, test_db_connection):
        """Edge case: Verify handling of None/null in optional fields"""
        client, db = test_db_connection
        
        upsert_watchlist_item(db, "AAPL", {
            "date_added": datetime.utcnow(),
            "last_refresh_at": None,
            "failed_stage": None
        })
        
        item = db.watchlistitems.find_one({"ticker": "AAPL"})
        assert item["last_refresh_at"] is None, "Should accept None for optional fields"
        assert item["failed_stage"] is None
    

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
