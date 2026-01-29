# backend-services/monitoring-service/tests/db/test_mongo_toggle_favourite.py
"""
Database-level tests for toggle_favourite ensuring scope to DEFAULT_USER_ID, 
correct modified_count type, and persistence of is_favourite.
"""

import pytest
from datetime import datetime, timedelta

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
    def test_toggle_favourite_to_true(self, test_db_connection):
        """Verify toggling favourite status to True"""
        client, db = test_db_connection
        
        ticker = "AAPL"
        upsert_watchlist_item(db, ticker, {"date_added": datetime.utcnow(), "is_favourite": False})
        
        # Toggle to True
        result = toggle_favourite(db, ticker, True)
        
        assert result.modified_count == 1, "Should modify exactly one document"
        
        # Verify in database
        item = db.watchlistitems.find_one({"ticker": ticker})
        assert item["is_favourite"] is True, "is_favourite should be True"
        assert item["user_id"] == DEFAULT_USER_ID, "Must maintain DEFAULT_USER_ID"
    
    def test_toggle_favourite_to_false(self, test_db_connection):
        """Verify toggling favourite status to False"""
        client, db = test_db_connection
        
        ticker = "MSFT"
        upsert_watchlist_item(db, ticker, {"date_added": datetime.utcnow(), "is_favourite": True})
        
        # Toggle to False
        result = toggle_favourite(db, ticker, False)
        
        assert result.modified_count == 1, "Should modify exactly one document"
        
        item = db.watchlistitems.find_one({"ticker": ticker})
        assert item["is_favourite"] is False, "is_favourite should be False"
    
    def test_toggle_favourite_nonexistent_ticker(self, test_db_connection):
        """Edge case: Verify toggling favourite on non-existent ticker"""
        client, db = test_db_connection
        
        result = toggle_favourite(db, "NONEXISTENT", True)
        
        assert result.modified_count == 0, "Should not modify anything when ticker doesn't exist"
    

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
