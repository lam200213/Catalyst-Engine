# backend-services/monitoring-service/tests/db/test_mongo_archive_crud.py
"""
CRUD-level tests for archived_watchlist_items, covering single-user scoped hard delete,
idempotency, and filter correctness without relying on TTL behaviors.
"""

import pytest
from datetime import datetime, timedelta
from bson import ObjectId

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

COLL = "archived_watchlist_items"

# ============================================================================
# TEST: index and reason conformity checks
# ============================================================================

from database.mongo_client import initialize_indexes
try:
    from shared.contracts import ArchiveReason as ArchiveReasonEnum
except Exception:
    ArchiveReasonEnum = None

class TestArchiveIndexesAndReason:
    def test_initialize_indexes_creates_user_ticker_index_on_archive(self, test_db_connection):
        """
        DB/Index behavior: ensure user_id+ticker index exists on archived_watchlist_items.
        """
        client, db = test_db_connection
        initialize_indexes(db)
        info = db.archived_watchlist_items.index_information()
        # Expect a compound index including user_id and ticker
        index_fields = [tuple(idx["key"]) for name, idx in info.items() if "key" in idx]
        assert any([("user_id", 1) in f and ("ticker", 1) in f for f in index_fields])

    def test_archive_reason_values_conform_to_enum_when_available(self, test_db_connection):
        """
        If ArchiveReason enum is available, inserted reasons should match its values.
        """
        client, db = test_db_connection
        db.archived_watchlist_items.delete_many({})
        db.archived_watchlist_items.insert_many([
            {"user_id": "default", "ticker": "CRM", "archived_at": __import__("datetime").datetime.utcnow(), "reason": "MANUAL_DELETE"},
            {"user_id": "default", "ticker": "NET", "archived_at": __import__("datetime").datetime.utcnow(), "reason": "FAILED_HEALTH_CHECK"},
        ])
        found = list(db.archived_watchlist_items.find({}))
        reasons = {d["reason"] for d in found}
        if ArchiveReasonEnum:
            allowed = {m.value for m in ArchiveReasonEnum}
            assert reasons.issubset(allowed)
        else:
            assert all(isinstance(r, str) for r in reasons)

# ============================================================================
# TEST: Archive CRUD Operations
# ============================================================================

class TestArchiveCRUD:
    """CRUD tests validating data used by GET /monitor/archive"""

    def test_insert_and_read_empty_then_single_for_default_user(self, test_db_connection, default_user_id):
        # Start from empty and verify empty read
        client, db = test_db_connection
        db[COLL].delete_many({})
        found = list(db[COLL].find({"user_id": default_user_id}))
        assert found == []

        # Insert one archived item with MANUAL_DELETE and no failed_stage
        doc = {
            "_id": ObjectId(),
            "user_id": default_user_id,
            "ticker": "CRM",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            # failed_stage intentionally omitted
        }
        db[COLL].insert_one(doc)

        found = list(db[COLL].find({"user_id": default_user_id}))
        assert len(found) == 1
        got = found[0]
        assert got["ticker"] == "CRM"
        assert got["reason"] == "MANUAL_DELETE"
        assert "failed_stage" not in got or got.get("failed_stage") is None

    def test_insert_multiple_reasons_and_failed_stage_presence(self, test_db_connection, default_user_id):
        # Insert two docs with both reason variants and different failed_stage semantics
        client, db = test_db_connection
        db[COLL].delete_many({})

        now = datetime.utcnow()
        docs = [
            {
                "_id": ObjectId(),
                "user_id": default_user_id,
                "ticker": "NET",
                "archived_at": now - timedelta(days=1),
                "reason": "FAILED_HEALTH_CHECK",
                "failed_stage": "vcp",
            },
            {
                "_id": ObjectId(),
                "user_id": default_user_id,
                "ticker": "CRM",
                "archived_at": now,
                "reason": "MANUAL_DELETE",
                "failed_stage": None,
            },
        ]
        db[COLL].insert_many(docs)

        found = list(db[COLL].find({"user_id": default_user_id}).sort("archived_at", 1))
        assert len(found) == 2
        assert {d["ticker"] for d in found} == {"NET", "CRM"}
        for d in found:
            assert d["reason"] in {"MANUAL_DELETE", "FAILED_HEALTH_CHECK"}
            assert "archived_at" in d
            assert isinstance(d["archived_at"], datetime)
            assert "failed_stage" in d  # may be None
            if d["ticker"] == "NET":
                assert d["failed_stage"] == "vcp"
            if d["ticker"] == "CRM":
                assert d["failed_stage"] is None

    def test_read_is_scoped_to_default_user_only(self, test_db_connection, default_user_id):
        # Ensure cross-user leakage does not occur at the query layer
        client, db = test_db_connection
        db[COLL].delete_many({})
        db[COLL].insert_many([
            {"user_id": default_user_id, "ticker": "ZEN", "archived_at": datetime.utcnow(), "reason": "MANUAL_DELETE"},
            {"user_id": "someone_else", "ticker": "BAD", "archived_at": datetime.utcnow(), "reason": "MANUAL_DELETE"},
        ])

        mine = list(db[COLL].find({"user_id": default_user_id}))
        others = list(db[COLL].find({"user_id": "someone_else"}))
        assert len(mine) == 1 and mine[0]["ticker"] == "ZEN"
        assert len(others) == 1 and others[0]["ticker"] == "BAD"

# ============================================================================
# CRUD-level tests for hard deletion of archive items
# ============================================================================
class TestArchiveHardDeleteCRUD:
    def test_hard_delete_removes_single_matching_doc_for_default_user(self, test_db_connection, default_user_id):
        """
        Requirements 1,4,7,9,11: Insert AAPL for default user, hard delete it, assert it is gone and
        identify by ticker; verify no type mismatches in counts.
        """
        client, db = test_db_connection
        coll = db.archived_watchlist_items
        coll.delete_many({})

        doc = {
            "_id": ObjectId(),
            "user_id": default_user_id,
            "ticker": "AAPL",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
        }
        coll.insert_one(doc)

        res = delete_archive_item(db, "AAPL")
        assert hasattr(res, "deleted_count") and isinstance(res.deleted_count, int)
        assert res.deleted_count == 1

        found = list(coll.find({"user_id": default_user_id, "ticker": "AAPL"}))
        assert found == []

    def test_hard_delete_idempotent_second_call_noop(self, test_db_connection, default_user_id):
        """
        Requirements 1,2,4,7,9: Second delete returns deleted_count=0 and dataset remains consistent.
        """
        client, db = test_db_connection
        coll = db.archived_watchlist_items
        coll.delete_many({})
        coll.insert_one({
            "_id": ObjectId(),
            "user_id": default_user_id,
            "ticker": "NET",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            "failed_stage": None,
        })

        first = delete_archive_item(db, "NET")
        assert first.deleted_count == 1
        second = delete_archive_item(db, "NET")
        assert second.deleted_count == 0

    def test_hard_delete_scoped_to_default_user_only(self, test_db_connection, default_user_id):
        """
        Requirements 3,4,5,9,11: Ensure deletion filter does not remove other users’ documents.
        """
        client, db = test_db_connection
        coll = db.archived_watchlist_items
        coll.delete_many({})
        coll.insert_many([
            {"_id": ObjectId(), "user_id": default_user_id, "ticker": "CRM",
             "archived_at": datetime.utcnow(), "reason": "MANUAL_DELETE", "failed_stage": None},
            {"_id": ObjectId(), "user_id": "someone_else", "ticker": "CRM",
             "archived_at": datetime.utcnow(), "reason": "MANUAL_DELETE", "failed_stage": None},
        ])

        res = delete_archive_item(db, "CRM")
        assert res.deleted_count == 1

        mine = list(coll.find({"user_id": default_user_id, "ticker": "CRM"}))
        others = list(coll.find({"user_id": "someone_else", "ticker": "CRM"}))
        assert mine == []
        assert len(others) == 1 and others[0]["ticker"] == "CRM"

    def test_hard_delete_rejects_invalid_format_at_db_layer_boundary(self, test_db_connection):
        """
        Requirements 2,3,4,7,9: If the DB helper enforces format, invalid symbols should not delete;
        this test asserts no accidental deletions occur for invalid input.
        """
        client, db = test_db_connection
        coll = db.archived_watchlist_items
        count_before = coll.count_documents({})
        res = delete_archive_item(db, "AAPL@")  # Depending on implementation, this should delete zero
        # Res may not raise; assert safety by dataset checks
        count_after = coll.count_documents({})
        assert count_after == count_before


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
