# backend-services/monitoring-service/tests/db/test_mongo_indexes.py
"""
Index validation tests ensuring TTL presence on archived_watchlist_items and verifying
that hard delete behavior is immediate and orthogonal to TTL lifecycle.
Index tests ensuring storage lifecycle for archive:
- TTL index exists on archived_at
- expireAfterSeconds = 2,592,000 (30 days)
"""

import pytest
from pymongo.errors import ConnectionFailure, OperationFailure
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from bson import ObjectId

# Import the module under test
from database.mongo_client import (
    initialize_indexes,
    delete_archive_item,
    DEFAULT_USER_ID
)

COLL = "archived_watchlist_items"

# ============================================================================
# TEST: Connection and Initialization
# ============================================================================

class TestIndexInitialization:
    """Test TTL index creation on archived_watchlist_items collection"""
    
    def test_initialize_indexes_creates_ttl_index(self, mock_mongo_client):
        """
        CRITICAL: Verify TTL index is created with correct expireAfterSeconds value
        Requirement: 30 days = 2,592,000 seconds
        """
        mock_client, mock_db = mock_mongo_client
        mock_collection = MagicMock()
        mock_db.archived_watchlist_items = mock_collection
        
        initialize_indexes(mock_db)
        
        # Verify create_index was called with correct parameters
        mock_collection.create_index.assert_called_once()
        call_args = mock_collection.create_index.call_args
        
        # Check index field
        assert call_args[0][0] == [("archived_at", 1)], "Index should be on 'archived_at' field in ascending order"
        # Check TTL setting
        assert call_args[1]["expireAfterSeconds"] == 2592000, "TTL should be exactly 2,592,000 seconds (30 days)"
    
    def test_initialize_indexes_idempotent(self, test_db_connection):
        """Verify calling initialize_indexes multiple times is safe"""
        client, db = test_db_connection
        
        # Call multiple times - should not raise error
        initialize_indexes(db)
        initialize_indexes(db)
        initialize_indexes(db)
        
        # Verify index exists
        indexes = list(db.archived_watchlist_items.list_indexes())
        ttl_indexes = [idx for idx in indexes if "expireAfterSeconds" in idx]
        
        assert len(ttl_indexes) >= 1, "TTL index should exist"
    
    def test_initialize_indexes_handles_operation_failure(self, mock_mongo_client):
        """Verify error handling when index creation fails"""
        mock_client, mock_db = mock_mongo_client
        mock_collection = MagicMock()
        mock_db.archived_watchlist_items = mock_collection
        mock_collection.create_index.side_effect = OperationFailure("Index creation failed")
        
        with pytest.raises(OperationFailure):
            initialize_indexes(mock_db)

# ============================================================================
# TEST: archived_watchlist_items
# ============================================================================

    def test_ttl_index_on_correct_collection_and_field(self, test_db_connection):
        client, db = test_db_connection

        initialize_indexes(db)

        # Confirm TTL index exists on archived_watchlist_items.archived_at
        ttl_indexes = [idx for idx in db.archived_watchlist_items.list_indexes() if "expireAfterSeconds" in idx]
        assert any("archived_at" in idx["key"] or ("archived_at", 1) in list(idx["key"].items()) for idx in ttl_indexes)
        assert any(idx["expireAfterSeconds"] == 2592000 for idx in ttl_indexes)

        # Guardrail: watchlist_items should not have a TTL on date_added or any other field
        wl_ttl_indexes = [idx for idx in getattr(db, "watchlist_items", db["watchlist_items"]).list_indexes() if "expireAfterSeconds" in idx]
        assert len(wl_ttl_indexes) == 0

# ============================================================================
# TEST: TTL
# ============================================================================
class TestArchiveTTLIndex:
    """TTL index presence and configuration"""

    def test_ttl_index_exists_with_expected_expiry(self, test_db_connection):
        client, db = test_db_connection
        indexes = list(db[COLL].list_indexes())
        ttl_found = False
        for idx in indexes:
            key = list(idx["key"].items())
            if key == [("archived_at", 1)] and "expireAfterSeconds" in idx:
                assert idx["expireAfterSeconds"] == 2_592_000
                ttl_found = True
                break
        assert ttl_found, "TTL index on archived_at with 2,592,000 seconds must exist"

# ============================================================================
# Hard delete vs TTL orthogonality
# ============================================================================
class TestHardDeleteVsTTL:
    def test_hard_delete_is_immediate_and_independent_of_ttl(self, test_db_connection):
        """
        Requirements 3,4,5,9: Deletion removes the document immediately irrespective of TTL
        configuration; TTL index remains configured after delete.
        """
        client, db = test_db_connection
        initialize_indexes(db)

        coll = db.archived_watchlist_items
        coll.delete_many({})
        coll.insert_one({
            "_id": ObjectId(),
            "user_id": "single_user_mode",
            "ticker": "ZEN",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
        })

        # Hard delete now
        res = delete_archive_item(db, "ZEN")
        assert res.deleted_count == 1

        # Verify immediate removal (not waiting for TTL)
        assert coll.count_documents({"ticker": "ZEN"}) == 0

        # TTL index still exists (orthogonal to hard delete behavior)
        ttl_indexes = [idx for idx in coll.list_indexes() if "expireAfterSeconds" in idx]
        assert any(idx.get("expireAfterSeconds") == 2_592_000 for idx in ttl_indexes)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
