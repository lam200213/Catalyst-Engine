# backend-services/monitoring-service/tests/db/test_mongo_watchlist_list.py
"""
Database-layer tests for list_watchlist_excluding including:
- No exclusions
- With exclusions and exclude-all
- Large exclusion list boundary conditions
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
    
    def test_list_watchlist_excluding_empty_exclusions(self, test_db_connection, sample_watchlist_items):
        """Verify listing all watchlist items when exclusion list is empty"""
        client, db = test_db_connection
        
        # Insert sample items
        db.watchlistitems.insert_many(sample_watchlist_items)
        
        # List all (no exclusions)
        result = list_watchlist_excluding(db, [])
        
        assert len(result) == 3, "Should return all 3 items"
        assert all(item["user_id"] == DEFAULT_USER_ID for item in result), "All items must have DEFAULT_USER_ID"
        
        tickers = [item["ticker"] for item in result]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert "GOOGL" in tickers
    
    def test_list_watchlist_excluding_with_exclusions(self, test_db_connection, sample_watchlist_items):
        """Verify listing watchlist items with exclusion list"""
        client, db = test_db_connection
        
        db.watchlistitems.insert_many(sample_watchlist_items)
        
        # Exclude AAPL and GOOGL
        exclusions = ["AAPL", "GOOGL"]
        result = list_watchlist_excluding(db, exclusions)
        
        assert len(result) == 1, "Should return only 1 item after exclusions"
        assert result[0]["ticker"] == "MSFT", "Should return only MSFT"
        assert result[0]["user_id"] == DEFAULT_USER_ID, "Must have DEFAULT_USER_ID"
    
    def test_list_watchlist_excluding_all(self, test_db_connection, sample_watchlist_items):
        """Edge case: Verify when all items are excluded"""
        client, db = test_db_connection
        
        db.watchlistitems.insert_many(sample_watchlist_items)
        
        # Exclude all tickers
        exclusions = ["AAPL", "MSFT", "GOOGL"]
        result = list_watchlist_excluding(db, exclusions)
        
        assert len(result) == 0, "Should return empty list when all items excluded"
        assert isinstance(result, list), "Should return list type, not None"

# ============================================================================
# TEST: Data Length Threshold Tests (Requirement #12)
# ============================================================================

class TestDataLengthThresholds:
    """Test functions with data length requirements at boundaries"""
    def test_list_watchlist_excluding_large_exclusion_list(self, test_db_connection):
        """
        Test list_watchlist_excluding with very large exclusion list
        """
        client, db = test_db_connection
        
        # Insert 100 watchlist items
        for i in range(100):
            upsert_watchlist_item(db, f"TICK{i:03d}", {"date_added": datetime.utcnow()})
        
        # Exclude 99 items (just below all)
        exclusions = [f"TICK{i:03d}" for i in range(99)]
        
        result = list_watchlist_excluding(db, exclusions)
        
        assert len(result) == 1, "Should return only 1 item after large exclusion"
        assert result[0]["ticker"] == "TICK099", "Should return the non-excluded item"

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
