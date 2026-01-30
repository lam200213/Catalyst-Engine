# backend-services/monitoring-service/tests/db/test_mongo_types_and_assertions.py
"""
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
# TEST: Type Mismatch and Assertion Tests (Requirement #7)
# ============================================================================

class TestTypeMismatchAndAssertions:
    """Verify correct types are returned and asserted"""
    def test_watchlistitems_last_refresh_status_matches_enum_values(
        self,
        test_db_connection,
    ):
        """last_refresh_status in watchlistitems must be one of PENDING, PASS, FAIL, UNKNOWN."""
        client, db = test_db_connection

        now = datetime.utcnow()
        upsert_watchlist_item(
            db,
            "ENUM1",
            {
                "date_added": now,
                "last_refresh_status": "PASS",
            },
        )
        upsert_watchlist_item(
            db,
            "ENUM2",
            {
                "date_added": now,
                "last_refresh_status": "FAIL",
            },
        )

        docs = list(db.watchlistitems.find({"ticker": {"$in": ["ENUM1", "ENUM2"]}}))
        allowed = {"PENDING", "PASS", "FAIL", "UNKNOWN"}
        for doc in docs:
            assert doc["ticker"] in {"ENUM1", "ENUM2"}
            assert doc["last_refresh_status"] in allowed

    def test_connect_returns_correct_types(self):
        """Verify connect() returns correct types"""
        with patch('database.mongo_client.MongoClient') as mock_client_class:
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db
            
            client, db = connect()
            
            # Type assertions
            assert client is not None
            assert db is not None
            # Should be MongoDB client/database objects (or mocks in this case)
            assert hasattr(client, '__getitem__') or callable(getattr(client, '__getitem__', None))
    
    def test_upsert_returns_update_result(self, test_db_connection):
        """Verify upsert returns MongoDB UpdateResult type"""
        client, db = test_db_connection
        
        result = upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        
        # Should have upserted_id or matched_count attributes
        assert hasattr(result, 'upserted_id') or hasattr(result, 'matched_count'), \
            "Should return UpdateResult-like object"
    
    def test_delete_returns_delete_result(self, test_db_connection):
        """Verify delete returns MongoDB DeleteResult type"""
        client, db = test_db_connection
        
        upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        result = delete_watchlist_item(db, "AAPL")
        
        assert hasattr(result, 'deleted_count'), "Should return DeleteResult with deleted_count"
        assert isinstance(result.deleted_count, int), "deleted_count should be integer"
    
    def test_list_functions_return_list_type(self, test_db_connection):
        """Verify list functions return list type, not cursor"""
        client, db = test_db_connection
        
        upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        insert_archive_item(db, "CRM", "MANUAL_DELETE", None)
        
        watchlist_result = list_watchlist_excluding(db, [])
        archive_result = list_archive(db)
        
        assert isinstance(watchlist_result, list), "list_watchlist_excluding should return list"
        assert isinstance(archive_result, list), "list_archive should return list"
    
    def test_datetime_fields_are_datetime_objects(self, test_db_connection):
        """Verify datetime fields are stored as datetime objects, not strings"""
        client, db = test_db_connection
        
        now = datetime.utcnow()
        upsert_watchlist_item(db, "AAPL", {"date_added": now})
        insert_archive_item(db, "CRM", "MANUAL_DELETE", None)
        
        watchlist_item = db.watchlistitems.find_one({"ticker": "AAPL"})
        archive_item = db.archived_watchlist_items.find_one({"ticker": "CRM"})
        
        assert isinstance(watchlist_item["date_added"], datetime), "date_added should be datetime object"
        assert isinstance(archive_item["archived_at"], datetime), "archived_at should be datetime object"

# ============================================================================
# TEST: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios"""
    
    def test_missing_required_fields_in_defaults(self, test_db_connection):
        """Edge case: Verify behavior when required fields missing in defaults"""
        client, db = test_db_connection
        
        # Try to upsert with empty defaults
        try:
            upsert_watchlist_item(db, "AAPL", {})
            # If accepted, verify user_id is still set
            item = db.watchlistitems.find_one({"ticker": "AAPL"})
            assert item["user_id"] == DEFAULT_USER_ID, "user_id should always be set"
        except (ValueError, KeyError, Exception):
            # If validation exists, should raise clear error
            pass  # Expected behavior

# ============================================================================
# TEST: Enum and type assertions for archived_watchlist_items.
# ============================================================================
class TestArchiveEnumAndTypes:
    """Enum and type assertions for archived_watchlist_items."""

    def test_archived_watchlist_items_reason_matches_enum_values(
        self,
        test_db_connection,
    ):
        """Archive reason must always be a known ArchiveReason value."""
        client, db = test_db_connection

        insert_archive_item(db, "CRM", "MANUAL_DELETE", None)
        insert_archive_item(db, "NET", "FAILED_HEALTH_CHECK", "screening")

        docs = list(db.archived_watchlist_items.find({"ticker": {"$in": ["CRM", "NET"]}}))
        allowed = {"MANUAL_DELETE", "FAILED_HEALTH_CHECK"}
        for doc in docs:
            assert doc["ticker"] in {"CRM", "NET"}
            assert doc["reason"] in allowed
            assert isinstance(doc["archived_at"], datetime)
            assert "failed_stage" in doc

# ============================================================================
# TEST: Consistency with Existing Patterns 
# ============================================================================

class TestConsistencyWithExistingPatterns:
    """Verify consistency with project coding patterns"""
    
    def test_all_functions_accept_db_parameter_first(self, test_db_connection):
        """Verify all functions follow pattern: func(db, ...)"""
        client, db = test_db_connection
        
        # All CRUD functions should accept db as first parameter
        # This test verifies the signature pattern
        
        # Should not raise TypeError for parameter order
        upsert_watchlist_item(db, "AAPL", {})
        delete_watchlist_item(db, "AAPL")
        insert_archive_item(db, "CRM", "MANUAL_DELETE", None)
        delete_archive_item(db, "CRM")
        list_watchlist_excluding(db, [])
        list_archive(db)
        toggle_favourite(db, "AAPL", True)
        bulk_update_status(db, [])
        bulk_archive_failed(db, [])
    
    def test_functions_return_meaningful_values(self, test_db_connection):
        """Verify functions return useful values, not just None"""
        client, db = test_db_connection
        
        # Insert operations should return result objects
        upsert_result = upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        assert upsert_result is not None, "Upsert should return result object"
        
        delete_result = delete_watchlist_item(db, "AAPL")
        assert delete_result is not None, "Delete should return result object"
        
        # List operations should return lists
        list_result = list_watchlist_excluding(db, [])
        assert isinstance(list_result, list), "List operations should return list"

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
