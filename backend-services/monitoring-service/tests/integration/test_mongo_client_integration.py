# backend-services/monitoring-service/tests/integration/test_mongo_client_integration.py
"""
Integration tests for mongo_client.py
Tests real database interactions and complex workflows
"""
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
from database.mongo_client import (
    connect,
    upsert_watchlist_item,
    list_watchlist_excluding,
    bulk_update_status,
    toggle_favourite,
    bulk_archive_failed,
    list_archive,
    delete_archive_item,
    DEFAULT_USER_ID
)

class TestIntegrationWorkflows:
    """Test complete workflows that span multiple operations"""
    
    def test_complete_watchlist_lifecycle(self, clean_test_db):
        """
        Integration test: Complete lifecycle of a watchlist item
        Add -> Update Status -> Mark Favourite -> Health Check Fail -> Archive -> Delete
        """
        db = clean_test_db
        ticker = "CRWD"
        
        # Step 1: Add to watchlist
        upsert_watchlist_item(db, ticker, {
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PENDING"
        })
        
        watchlist = list_watchlist_excluding(db, [])
        assert len(watchlist) == 1
        assert watchlist[0]["ticker"] == ticker
        
        # Step 2: Update health status to PASS
        bulk_update_status(db, [{
            "ticker": ticker,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow()
        }])
        
        item = db.watchlistitems.find_one({"ticker": ticker})
        assert item["last_refresh_status"] == "PASS"
        
        # Step 3: Mark as favourite
        toggle_favourite(db, ticker, True)
        
        item = db.watchlistitems.find_one({"ticker": ticker})
        assert item["is_favourite"] is True
        
        # Step 4: Health check fails
        bulk_archive_failed(db, [{
            "ticker": ticker,
            "failed_stage": "vcp",
            "reason": "FAILED_HEALTH_CHECK"
        }])
        
        # Should be removed from watchlist
        watchlist = list_watchlist_excluding(db, [])
        assert len(watchlist) == 0
        
        # Should be in archive
        archive = list_archive(db)
        assert len(archive) == 1
        assert archive[0]["ticker"] == ticker
        assert archive[0]["failed_stage"] == "vcp"
        
        # Step 5: Permanently delete from archive
        delete_archive_item(db, ticker)
        
        archive = list_archive(db)
        assert len(archive) == 0
    
    def test_re_add_archived_ticker(self, clean_test_db):
        """
        Integration test: Re-adding a ticker that was previously archived
        Simulates ticker passing health check again after failure
        """
        db = clean_test_db
        ticker = "NET"
        
        # Initially add to watchlist
        upsert_watchlist_item(db, ticker, {"date_added": datetime.utcnow()})
        
        # Fails health check, gets archived
        bulk_archive_failed(db, [{
            "ticker": ticker,
            "failed_stage": "screening",
            "reason": "FAILED_HEALTH_CHECK"
        }])
        
        # Verify in archive
        archive = list_archive(db)
        assert len(archive) == 1
        
        # Later, ticker passes screening again and is re-added
        # Implementation should handle: delete from archive, add to watchlist
        delete_archive_item(db, ticker)
        upsert_watchlist_item(db, ticker, {
            "date_added": datetime.utcnow(),
            "last_refresh_status": "PASS"
        })
        
        # Verify state
        archive = list_archive(db)
        assert len(archive) == 0
        
        watchlist = list_watchlist_excluding(db, [])
        assert len(watchlist) == 1
        assert watchlist[0]["ticker"] == ticker
    
    def test_batch_health_check_workflow(self, clean_test_db):
        """
        Integration test: Complete batch health check workflow
        Simulates scheduler-service health check job
        """
        db = clean_test_db
        
        # Setup: Add multiple tickers to watchlist
        tickers = ["AAPL", "MSFT", "GOOGL", "CRM", "NET"]
        for ticker in tickers:
            upsert_watchlist_item(db, ticker, {
                "date_added": datetime.utcnow(),
                "last_refresh_status": "PENDING",
                "is_favourite": False
            })
        
        # Mark CRM as favourite
        toggle_favourite(db, "CRM", True)
        
        # Simulate health check results:
        # AAPL, MSFT: PASS
        # GOOGL: FAIL (not favourite, should archive)
        # CRM: FAIL (favourite, should stay but mark failed)
        # NET: PASS
        
        # Update passed items
        bulk_update_status(db, [
            {"ticker": "AAPL", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow(), "failed_stage": None},
            {"ticker": "MSFT", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow(), "failed_stage": None},
            {"ticker": "NET", "last_refresh_status": "PASS", "last_refresh_at": datetime.utcnow(), "failed_stage": None},
        ])
        
        # Update failed favourite (stays in watchlist)
        bulk_update_status(db, [
            {"ticker": "CRM", "last_refresh_status": "FAIL", "last_refresh_at": datetime.utcnow(), "failed_stage": "vcp"}
        ])
        
        # Archive failed non-favourite
        bulk_archive_failed(db, [{
            "ticker": "GOOGL",
            "failed_stage": "screening",
            "reason": "FAILED_HEALTH_CHECK"
        }])
        
        # Verify final state
        watchlist = list_watchlist_excluding(db, [])
        assert len(watchlist) == 4  # AAPL, MSFT, NET, CRM (favourite)
        
        archive = list_archive(db)
        assert len(archive) == 1
        assert archive[0]["ticker"] == "GOOGL"
        
        # Verify CRM is still in watchlist despite failing
        crm = db.watchlistitems.find_one({"ticker": "CRM"})
        assert crm is not None
        assert crm["is_favourite"] is True
        assert crm["last_refresh_status"] == "FAIL"

    # end-to-end integration for bulk manual delete

    def test_batch_remove_integration_moves_items_to_archive_and_updates_counts(
        self,
        clean_test_db,
    ):
        """
        Req #1, #2, #5, #10, #11:
        - Use real mongo_client helpers against the test database.
        - Verify that:
          * watchlistitems documents are removed for the specified tickers,
            scoped to DEFAULT_USER_ID.
          * archived_watchlist_items receives new docs with reason MANUAL_DELETE
            and archived_at set.
          * The helper returns correct removed/notfound counts with identifiers.
        """
        from database.mongo_client import (
            upsert_watchlist_item,
            list_watchlist_excluding,
            list_archive,
            bulk_manual_delete,
            DEFAULT_USER_ID,
        )

        db = clean_test_db
        now = datetime.utcnow()

        # Arrange: add two watchlist items
        upsert_watchlist_item(
            db,
            "NET",
            {
                "user_id": DEFAULT_USER_ID,
                "status": "Watch",
                "is_favourite": False,
                "date_added": now,
                "last_updated": now,
            },
        )
        upsert_watchlist_item(
            db,
            "CRWD",
            {
                "user_id": DEFAULT_USER_ID,
                "status": "Watch",
                "is_favourite": False,
                "date_added": now,
                "last_updated": now,
            },
        )

        # Sanity: both appear in watchlist
        initial_watchlist = list(list_watchlist_excluding(db, exclude=[]))
        tickers_before = {doc["ticker"] for doc in initial_watchlist}
        assert {"NET", "CRWD"}.issubset(tickers_before)

        # Act: bulk delete NET and a non-existent ticker
        result = bulk_manual_delete(db, ["NET", "MISSING"])

        # Assert helper return structure and types
        assert isinstance(result["removed"], int)
        assert isinstance(result["notfound"], int)
        assert isinstance(result["tickers"], list)
        assert isinstance(result["not_found_tickers"], list)

        assert result["removed"] == 1
        assert result["notfound"] == 1
        assert "NET" in result["tickers"]
        assert "MISSING" in result["tickers"]
        assert "MISSING" in result["not_found_tickers"]

        # Assert watchlist no longer includes NET but still includes CRWD
        remaining = list(list_watchlist_excluding(db, exclude=[]))
        remaining_tickers = {doc["ticker"] for doc in remaining}
        assert "NET" not in remaining_tickers
        assert "CRWD" in remaining_tickers

        # Assert archive contains NET with correct metadata
        archived = list(list_archive(db))
        archived_tickers = {doc["ticker"] for doc in archived}
        assert "NET" in archived_tickers

        net_docs = [doc for doc in archived if doc["ticker"] == "NET"]
        assert len(net_docs) == 1
        net_doc = net_docs[0]
        assert net_doc["user_id"] == DEFAULT_USER_ID
        assert net_doc["reason"] == "MANUAL_DELETE"
        assert net_doc.get("failed_stage") is None
        assert isinstance(net_doc["archived_at"], datetime)

    @patch('database.mongo_client.connect')
    def test_post_favourite_route_persists_toggle(self, mock_connect, clean_test_db, client):
        """
        Integration-level: verify POST /monitor/watchlist/:ticker/favourite persists is_favourite True then False.
        """
        db = clean_test_db
        # Seed watchlist item under DEFAULT_USER_ID
        db.watchlistitems.insert_one({
            "user_id": DEFAULT_USER_ID,
            "ticker": "DDOG",
            "is_favourite": False,
            "date_added": datetime.utcnow(),
            "last_refresh_status": "PENDING"
        })
        # Route should use this same db via patched connect
        mock_connect.return_value = (MagicMock(), db)

        # Mark favourite
        r1 = client.post('/monitor/watchlist/DDOG/favourite', json={"is_favourite": True})
        assert r1.status_code == 200
        doc = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": "DDOG"})
        assert doc is not None and doc["is_favourite"] is True

        # Unmark favourite
        r2 = client.post('/monitor/watchlist/DDOG/favourite', json={"is_favourite": False})
        assert r2.status_code == 200
        doc2 = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": "DDOG"})
        assert doc2 is not None and doc2["is_favourite"] is False

class TestInternalBatchAddIntegration:
    """End-to-end route->service->db behavior for batch add"""

    @patch('database.mongo_client.connect')
    def test_batch_add_integration_adds_and_normalizes(self, mock_connect, clean_test_db, client):
        db = clean_test_db
        mock_connect.return_value = (MagicMock(), db)

        resp = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": ["crwd", "ddog"]})
        assert resp.status_code in (200, 201)

        # Verify DB state
        tickers = {d["ticker"] for d in db.watchlistitems.find({"user_id": DEFAULT_USER_ID})}
        assert {"CRWD", "DDOG"}.issubset(tickers)

        # Defaults present
        for t in ("CRWD", "DDOG"):
            doc = db.watchlistitems.find_one({"user_id": DEFAULT_USER_ID, "ticker": t})
            assert doc is not None
            assert doc.get("is_favourite") is False
            assert doc.get("last_refresh_status") in ("PENDING", "UNKNOWN")

    @patch('database.mongo_client.connect')
    def test_batch_add_integration_reintroduces_from_archive(self, mock_connect, clean_test_db, client):
        db = clean_test_db
        mock_connect.return_value = (MagicMock(), db)

        # Seed archive
        db.archived_watchlist_items.insert_one({
            "user_id": DEFAULT_USER_ID,
            "ticker": "NET",
            "archived_at": datetime.utcnow(),
            "reason": "MANUAL_DELETE",
            "failed_stage": None
        })

        resp = client.post('/monitor/internal/watchlist/batch/add', json={"tickers": ["NET"]})
        assert resp.status_code in (200, 201)

        # Removed from archive and present in watchlist
        assert db.archived_watchlist_items.count_documents({"user_id": DEFAULT_USER_ID, "ticker": "NET"}) == 0
        assert db.watchlistitems.count_documents({"user_id": DEFAULT_USER_ID, "ticker": "NET"}) == 1
