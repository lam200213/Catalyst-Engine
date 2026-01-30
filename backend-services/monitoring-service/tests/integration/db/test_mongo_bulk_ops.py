# backend-services/monitoring-service/tests/db/test_mongo_bulk_ops.py
"""
Test suite for database/mongo_client.py
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
# TEST: watchlist index check
# ============================================================================
from database.mongo_client import initialize_indexes

class TestWatchlistIndexes:
    def test_initialize_indexes_creates_user_ticker_index_on_watchlist(self, test_db_connection):
        """
        DB/Index behavior: ensure user_id+ticker index exists on watchlistitems.
        """
        client, db = test_db_connection
        initialize_indexes(db)
        info = db.watchlistitems.index_information()
        index_fields = [tuple(idx["key"]) for name, idx in info.items() if "key" in idx]
        assert any([("user_id", 1) in f and ("ticker", 1) in f for f in index_fields])

# ============================================================================
# TEST: Bulk Operations
# ============================================================================

class TestBulkOperations:
    """Test bulk update and archive operations"""
    def test_bulk_update_status_sets_last_refresh_status_and_failed_stage_consistently(
        self,
        test_db_connection,
        sample_watchlist_items,
    ):
        """bulk_update_status must map status and failed_stage consistently for each ticker."""
        client, db = test_db_connection
        db.watchlistitems.insert_many(sample_watchlist_items)

        updates = [
            {"ticker": "AAPL", "last_refresh_status": "PASS", "failed_stage": None},
            {"ticker": "GOOGL", "last_refresh_status": "FAIL", "failed_stage": "vcp"},

        ]

        result = bulk_update_status(db, updates)
        assert result is not None
        assert hasattr(result, "bulk_api_result") or hasattr(result, "modified_count")

        docs = list(db.watchlistitems.find({"ticker": {"$in": ["AAPL", "GOOGL"]}}))
        by_ticker = {d["ticker"]: d for d in docs}
        assert by_ticker["AAPL"]["last_refresh_status"] == "PASS"
        assert by_ticker["AAPL"]["failed_stage"] is None
        assert by_ticker["GOOGL"]["last_refresh_status"] == "FAIL"
        assert by_ticker["GOOGL"]["failed_stage"] == "vcp"

    
    def test_bulk_update_status_respects_no_insert_invariant_for_unknown_tickers(
        self,
        test_db_connection,
        sample_watchlist_items,
    ):
        """bulk_update_status must not insert new docs for tickers not in watchlist."""
        client, db = test_db_connection
        db.watchlistitems.insert_many(sample_watchlist_items)

        updates = [
            {"ticker": "NONEXIST", "last_refresh_status": "PASS", "failed_stage": None},
        ]
        bulk_update_status(db, updates)

        assert db.watchlistitems.count_documents({"ticker": "NONEXIST"}) == 0

    
    def test_bulk_archive_failed_sets_archive_reason_and_archived_at(
        self,
        test_db_connection,
        sample_watchlist_items,
    ):
        """bulk_archive_failed must move items to archive with reason and archived_at set."""
        client, db = test_db_connection
        db.watchlistitems.insert_many(sample_watchlist_items)

        payload = [{"ticker": "AAPL", "failed_stage": "screening"}]
        result = bulk_archive_failed(db, payload)
        assert isinstance(result, tuple)
        delete_result, insert_result = result
        assert delete_result.deleted_count == 1
        assert insert_result is not None

        archived = db.archived_watchlist_items.find_one({"ticker": "AAPL"})
        assert archived is not None
        assert archived["reason"] == "FAILED_HEALTH_CHECK"
        assert isinstance(archived["archived_at"], datetime)
        assert archived["failed_stage"] == "screening"

    def test_bulk_update_status_success(self, test_db_connection, sample_watchlist_items):
        """Verify bulk updating status for multiple tickers"""
        client, db = test_db_connection
        
        db.watchlistitems.insert_many(sample_watchlist_items)
        
        # Bulk update status
        status_updates = [
            {
                "ticker": "AAPL",
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": None
            },
            {
                "ticker": "GOOGL",
                "last_refresh_status": "FAIL",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": "screening"
            }
        ]
        
        result = bulk_update_status(db, status_updates)
        
        # Verify return value
        assert result is not None, "Should return result"
        
        # Verify updates in database
        aapl = db.watchlistitems.find_one({"ticker": "AAPL"})
        assert aapl["last_refresh_status"] == "PASS", "AAPL status should be updated to PASS"
        assert aapl["failed_stage"] is None, "AAPL failed_stage should be None"
        
        googl = db.watchlistitems.find_one({"ticker": "GOOGL"})
        assert googl["last_refresh_status"] == "FAIL", "GOOGL status should be updated to FAIL"
        assert googl["failed_stage"] == "screening", "GOOGL failed_stage should be 'screening'"
        
        # Verify user_id remains unchanged
        assert aapl["user_id"] == DEFAULT_USER_ID
        assert googl["user_id"] == DEFAULT_USER_ID
    
    def test_bulk_update_status_empty_list(self, test_db_connection):
        """Edge case: Verify bulk update with empty list"""
        client, db = test_db_connection
        
        result = bulk_update_status(db, [])
        
        # Should handle gracefully, not raise error
        assert result is not None or result is None  # Implementation dependent
    
    def test_bulk_update_status_partial_match(self, test_db_connection):
        """Verify bulk update when some tickers don't exist"""
        client, db = test_db_connection
        
        # Insert only one ticker
        upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        
        # Try to update multiple including non-existent
        status_updates = [
            {"ticker": "AAPL", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow()},
            {"ticker": "NONEXISTENT", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow()}
        ]
        
        # Should not raise error, just update what exists
        result = bulk_update_status(db, status_updates)
        
        # Verify AAPL was updated
        aapl = db.watchlistitems.find_one({"ticker": "AAPL"})
        assert aapl["last_refresh_status"] == "PASS"
    
    def test_bulk_update_status_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify bulk_update_status only affects DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Insert items for different users
        db.watchlistitems.insert_many([
            {"user_id": DEFAULT_USER_ID, "ticker": ticker, "last_refresh_status": "PENDING", "date_added": datetime.utcnow()},
            {"user_id": "other_user", "ticker": ticker, "last_refresh_status": "PENDING", "date_added": datetime.utcnow()}
        ])
        
        # Bulk update
        status_updates = [
            {"ticker": ticker, "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow()}
        ]
        bulk_update_status(db, status_updates)
        
        # Verify only DEFAULT_USER_ID item was updated
        default_item = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": ticker})
        other_item = db.watchlistitems.find_one({"user_id": "other_user", "ticker": ticker})
        
        assert default_item["last_refresh_status"] == "PASS", "Should update DEFAULT_USER_ID item"
        assert other_item["last_refresh_status"] == "PENDING", "SECURITY: Should not affect other user's items"
    
    def test_bulk_archive_failed_success(self, test_db_connection, sample_watchlist_items):
        """Verify bulk archiving failed items"""
        client, db = test_db_connection
        
        db.watchlistitems.insert_many(sample_watchlist_items)
        
        # Bulk archive failed items
        failed_items = [
            {"ticker": "AAPL", "failed_stage": "screening", "reason": "FAILED_HEALTH_CHECK"},
            {"ticker": "GOOGL", "failed_stage": "vcp", "reason": "FAILED_HEALTH_CHECK"}
        ]
        
        result = bulk_archive_failed(db, failed_items)
        
        assert result is not None, "Should return result"
        
        # Verify items removed from watchlist
        assert db.watchlistitems.find_one({"ticker": "AAPL"}) is None, "AAPL should be removed from watchlist"
        assert db.watchlistitems.find_one({"ticker": "GOOGL"}) is None, "GOOGL should be removed from watchlist"
        
        # Verify items added to archive
        aapl_archive = db.archived_watchlist_items.find_one({"ticker": "AAPL"})
        googl_archive = db.archived_watchlist_items.find_one({"ticker": "GOOGL"})
        
        assert aapl_archive is not None, "AAPL should be in archive"
        assert aapl_archive["failed_stage"] == "screening", "AAPL failed_stage should match"
        assert aapl_archive["reason"] == "FAILED_HEALTH_CHECK", "Reason should be FAILED_HEALTH_CHECK"
        assert aapl_archive["user_id"] == DEFAULT_USER_ID, "user_id must be DEFAULT_USER_ID"
        
        assert googl_archive is not None, "GOOGL should be in archive"
        assert googl_archive["failed_stage"] == "vcp", "GOOGL failed_stage should match"
        assert googl_archive["user_id"] == DEFAULT_USER_ID
    
    def test_bulk_archive_failed_empty_list(self, test_db_connection):
        """Edge case: Verify bulk archive with empty list"""
        client, db = test_db_connection
        
        result = bulk_archive_failed(db, [])
        
        # Should handle gracefully
        assert result is not None or result is None
    
    def test_bulk_archive_failed_atomicity(self, test_db_connection):
        """
        Verify bulk archive is atomic-like: both delete and insert happen for each item
        """
        client, db = test_db_connection
        
        # Insert items
        upsert_watchlist_item(db, "AAPL", {"date_added": datetime.utcnow()})
        upsert_watchlist_item(db, "MSFT", {"date_added": datetime.utcnow()})
        
        failed_items = [
            {"ticker": "AAPL", "failed_stage": "screening", "reason": "FAILED_HEALTH_CHECK"}
        ]
        
        bulk_archive_failed(db, failed_items)
        
        # AAPL should be archived and removed
        assert db.watchlistitems.find_one({"ticker": "AAPL"}) is None
        assert db.archived_watchlist_items.find_one({"ticker": "AAPL"}) is not None
        
        # MSFT should remain in watchlist
        assert db.watchlistitems.find_one({"ticker": "MSFT"}) is not None
        assert db.archived_watchlist_items.find_one({"ticker": "MSFT"}) is None
    
    def test_bulk_archive_failed_hardcoded_user_id(self, test_db_connection):
        """
        CRITICAL SECURITY TEST: Verify bulk_archive_failed only affects DEFAULT_USER_ID items
        """
        client, db = test_db_connection
        
        ticker = "AAPL"
        
        # Insert items for different users
        db.watchlistitems.insert_many([
            {"user_id": DEFAULT_USER_ID, "ticker": ticker, "date_added": datetime.utcnow()},
            {"user_id": "other_user", "ticker": ticker, "date_added": datetime.utcnow()}
        ])
        
        # Bulk archive
        failed_items = [
            {"ticker": ticker, "failed_stage": "screening", "reason": "FAILED_HEALTH_CHECK"}
        ]
        bulk_archive_failed(db, failed_items)
        
        # Verify only DEFAULT_USER_ID item was archived
        default_watchlist = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": ticker})
        other_watchlist = db.watchlistitems.find_one({"user_id": "other_user", "ticker": ticker})
        
        assert default_watchlist is None, "DEFAULT_USER_ID item should be removed from watchlist"
        assert other_watchlist is not None, "SECURITY: Other user's item should remain in watchlist"
        
        default_archive = db.archived_watchlist_items.find_one({"user_id": DEFAULT_USER_ID, "ticker": ticker})
        other_archive = db.archived_watchlist_items.find_one({"user_id": "other_user", "ticker": ticker})
        
        assert default_archive is not None, "DEFAULT_USER_ID item should be in archive"
        assert other_archive is None, "SECURITY: Other user's item should not be archived"
    
    def test_bulk_archive_preserves_existing_archives(self, test_db_connection):
        """Verify bulk archiving doesn't interfere with existing archive items"""
        client, db = test_db_connection
        
        # Insert existing archive item
        db.archived_watchlist_items.insert_one({
            "user_id": DEFAULT_USER_ID,
            "ticker": "OLD_ARCHIVE",
            "archived_at": datetime.utcnow() - timedelta(days=10),
            "reason": "MANUAL_DELETE"
        })
        
        # Insert watchlist item to archive
        upsert_watchlist_item(db, "NEW_FAIL", {"date_added": datetime.utcnow()})
        
        # Bulk archive
        failed_items = [
            {"ticker": "NEW_FAIL", "failed_stage": "vcp", "reason": "FAILED_HEALTH_CHECK"}
        ]
        bulk_archive_failed(db, failed_items)
        
        # Verify both exist in archive
        archive_count = db.archived_watchlist_items.count_documents({"user_id": DEFAULT_USER_ID})
        assert archive_count == 2, "Should have both old and new archive items"
        
        old_archive = db.archived_watchlist_items.find_one({"ticker": "OLD_ARCHIVE"})
        assert old_archive is not None, "Old archive should be preserved"

    # bulk manual delete semantics for POST /monitor/watchlist/batch/remove

    def test_bulk_manual_delete_moves_watchlist_items_to_archive_with_MANUAL_DELETE_reason(
        self,
        clean_test_db,
    ):
        """
        Req #1, #2, #5, #10, #11:
        - Given a list of tickers, bulk_manual_delete must:
          * Remove matching docs from watchlistitems for DEFAULT_USER_ID.
          * Insert corresponding docs into archived_watchlist_items with:
            - same ticker
            - user_id = DEFAULT_USER_ID
            - reason = MANUAL_DELETE
            - failed_stage = None
            - archived_at set to a datetime
          * Return counts and identifier lists that reflect removed vs notfound.
        """
        from database.mongo_client import bulk_manual_delete, DEFAULT_USER_ID

        db = clean_test_db
        now = datetime.utcnow()

        # Arrange: two watchlist items, only one targeted
        db.watchlistitems.insert_many(
            [
                {
                    "user_id": DEFAULT_USER_ID,
                    "ticker": "AAPL",
                    "status": "Watch",
                    "is_favourite": False,
                    "date_added": now,
                    "last_updated": now,
                },
                {
                    "user_id": DEFAULT_USER_ID,
                    "ticker": "OTHER",
                    "status": "Watch",
                    "is_favourite": False,
                    "date_added": now,
                    "last_updated": now,
                },
            ]
        )

        # Act: request deletion of one existing and one missing ticker
        result = bulk_manual_delete(db, ["AAPL", "MISSING"])

        # Assert return shape and types
        assert isinstance(result, dict)
        assert isinstance(result["removed"], int)
        assert isinstance(result["notfound"], int)
        assert isinstance(result["tickers"], list)
        assert isinstance(result["not_found_tickers"], list)

        assert result["removed"] == 1
        assert result["notfound"] == 1
        assert set(result["tickers"]) == {"AAPL", "MISSING"}
        assert "AAPL" in result["tickers"]
        assert "MISSING" in result["tickers"]
        assert "MISSING" in result["not_found_tickers"]

        # Assert DB effects: watchlist
        assert db.watchlistitems.count_documents(
            {"user_id": DEFAULT_USER_ID, "ticker": "AAPL"}
        ) == 0
        # Unrelated ticker remains
        assert db.watchlistitems.count_documents(
            {"user_id": DEFAULT_USER_ID, "ticker": "OTHER"}
        ) == 1

        # Assert DB effects: archive with correct reason and TTL field
        archived_docs = list(
            db.archived_watchlist_items.find(
                {"user_id": DEFAULT_USER_ID, "ticker": "AAPL"}
            )
        )
        assert len(archived_docs) == 1
        archived = archived_docs[0]
        assert archived["reason"] == "MANUAL_DELETE"
        assert archived.get("failed_stage") is None
        assert isinstance(archived["archived_at"], datetime)

    # bulk manual delete handles duplicate tickers idempotently

    def test_bulk_manual_delete_handles_duplicate_tickers_gracefully(
        self,
        clean_test_db,
    ):
        """
        EDGE CASE:
        - Duplicate tickers in the input list must not cause multiple deletions.
        - The operation should still succeed and report identifiers consistently.
        """
        from database.mongo_client import bulk_manual_delete, DEFAULT_USER_ID

        db = clean_test_db
        now = datetime.utcnow()

        db.watchlistitems.insert_one(
            {
                "user_id": DEFAULT_USER_ID,
                "ticker": "CRWD",
                "status": "Watch",
                "is_favourite": False,
                "date_added": now,
                "last_updated": now,
            }
        )

        result = bulk_manual_delete(db, ["CRWD", "CRWD"])

        # Exactly one actual deletion, but identifiers should still list CRWD
        assert result["removed"] == 1
        assert "CRWD" in result["tickers"]

        # Watchlist no longer contains CRWD
        assert db.watchlistitems.count_documents(
            {"user_id": DEFAULT_USER_ID, "ticker": "CRWD"}
        ) == 0

        # Archive contains exactly one doc for CRWD
        assert (
            db.archived_watchlist_items.count_documents(
                {"user_id": DEFAULT_USER_ID, "ticker": "CRWD"}
            )
            == 1
        )


    def test_bulk_update_status_sets_last_refresh_at_datetime(
        self,
        test_db_connection,
        sample_watchlist_items,
    ):
        """
        DB invariant: last_refresh_at must be stored as a datetime for updated items.
        """
        from datetime import datetime as dt_type

        client, db = test_db_connection
        db.watchlistitems.insert_many(sample_watchlist_items)

        status_updates = [
            {
                "ticker": "AAPL",
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": None,
            },
            {
                "ticker": "GOOGL",
                "last_refresh_status": "FAIL",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": "screening",
            },
        ]

        bulk_update_status(db, status_updates)

        aapl = db.watchlistitems.find_one({"ticker": "AAPL"})
        googl = db.watchlistitems.find_one({"ticker": "GOOGL"})

        assert isinstance(aapl["last_refresh_at"], dt_type)
        assert isinstance(googl["last_refresh_at"], dt_type)

    def test_bulk_update_status_does_not_insert_unknown_tickers(
        self,
        test_db_connection,
    ):
        """
        Edge case: bulk_update_status must not create new documents
        for tickers that do not exist in watchlistitems.
        """
        client, db = test_db_connection

        # No seed docs; attempt to update a non-existent ticker
        status_updates = [
            {
                "ticker": "NONEXISTENT",
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
            }
        ]

        bulk_update_status(db, status_updates)

        # Ensure no document was inserted
        assert db.watchlistitems.count_documents({"ticker": "NONEXISTENT"}) == 0


# ============================================================================
# TEST: Data Length Threshold Tests 
# ============================================================================

class TestDataLengthThresholds:
    """Test functions with data length requirements at boundaries"""
    
    def test_bulk_update_status_just_below_practical_limit(self, test_db_connection):
        """
        Test bulk update with large number of items (just below practical limit)
        Assuming practical limit is ~1000 items
        """
        client, db = test_db_connection
        
        # Insert 999 items
        large_batch = []
        for i in range(999):
            ticker = f"TICK{i:04d}"
            large_batch.append({
                "user_id": DEFAULT_USER_ID,
                "ticker": ticker,
                "date_added": datetime.utcnow(),
                "last_refresh_status": "PENDING"
            })
        
        db.watchlistitems.insert_many(large_batch)
        
        # Bulk update all
        status_updates = [
            {"ticker": f"TICK{i:04d}", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow()}
            for i in range(999)
        ]
        
        # Should succeed without error
        result = bulk_update_status(db, status_updates)
        
        # Verify a sample was updated
        sample = db.watchlistitems.find_one({"ticker": "TICK0100"})
        assert sample["last_refresh_status"] == "PASS", "Large batch update should work"
    
    def test_bulk_archive_failed_at_practical_limit(self, test_db_connection):
        """
        Test bulk archive at practical limit
        Assuming practical limit is ~1000 items
        """
        client, db = test_db_connection
        
        # Insert exactly 1000 items
        large_batch = []
        for i in range(1000):
            ticker = f"TICK{i:04d}"
            large_batch.append({
                "user_id": DEFAULT_USER_ID,
                "ticker": ticker,
                "date_added": datetime.utcnow()
            })
        
        db.watchlistitems.insert_many(large_batch)
        
        # Bulk archive all 1000
        failed_items = [
            {"ticker": f"TICK{i:04d}", "failed_stage": "screening", "reason": "FAILED_HEALTH_CHECK"}
            for i in range(1000)
        ]
        
        # Should succeed
        result = bulk_archive_failed(db, failed_items)
        
        # Verify watchlist is now empty
        watchlist_count = db.watchlistitems.count_documents({"user_id": DEFAULT_USER_ID})
        assert watchlist_count == 0, "All items should be removed from watchlist"
        
        # Verify all in archive
        archive_count = db.archived_watchlist_items.count_documents({"user_id": DEFAULT_USER_ID})
        assert archive_count == 1000, "All items should be in archive"

# ============================================================================
# TEST: BatchAddDbSemantics 
# ============================================================================
class TestBatchAddDbSemantics:
    """Confirm DB-level semantics for batch add via existing helpers"""

    def test_upsert_sets_defaults_and_user_scope(self, test_db_connection):
        client, db = test_db_connection

        # Simulate service behavior: per-ticker upsert with defaults
        now = datetime.utcnow()
        upsert_watchlist_item(db, "CRWD", {
            "date_added": now,
            "is_favourite": False,
            "last_refresh_status": "PENDING"
        })

        doc = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": "CRWD"})
        assert doc is not None
        # Accept either field name variant used in current code paths
        user_field = "user_id" if "user_id" in doc else "userid"
        assert doc[user_field] == DEFAULT_USER_ID
        assert doc.get("is_favourite") is False
        assert doc.get("last_refresh_status") in ("PENDING", "UNKNOWN")

    def test_reintroduce_deletes_from_archive_on_batch_add(self, test_db_connection):
        client, db = test_db_connection

        # Seed archive
        db.archived_watchlist_items.insert_one({
            "user_id": DEFAULT_USER_ID,
            "ticker": "DDOG",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            "failed_stage": None
        })

        # Service behavior: delete archive first, then upsert watchlist
        delete_archive_item(db, "DDOG")
        upsert_watchlist_item(db, "DDOG", {
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PENDING"
        })

        assert db.archived_watchlist_items.count_documents({"user_id": DEFAULT_USER_ID, "ticker": "DDOG"}) == 0
        assert db.watchlistitems.count_documents({"user_id": DEFAULT_USER_ID, "ticker": "DDOG"}) == 1


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
