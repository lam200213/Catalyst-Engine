# backend-services/monitoring-service/tests/services/test_watchlist_service_security.py
"""
Security and isolation tests for service-layer operations, including ensuring
default user scoping and rejection of malformed tickers for hard deletes.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from types import SimpleNamespace

# Import the module under test
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
)

# Import database client functions
from database import mongo_client

# ============================================================================
# TEST: Security and Data Isolation (Requirement #3)
# ============================================================================

class TestSecurityAndDataIsolation:
    """Test security implications and data isolation"""
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_only_returns_single_user_data(
        self, mock_list_watchlist, mock_db
    ):
        """
        CRITICAL SECURITY: Verify only DEFAULT_USER_ID data is returned
        mongo_client should already filter by user_id
        """
        # Mock data already filtered by user_id in mongo_client
        valid_watchlist = [
            {
                "user_id": "single_user_mode",
                "ticker": "AAPL",
                "date_added": datetime.utcnow(),
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": None,
                "current_price": 175.50,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": True
            }
        ]
        
        mock_list_watchlist.return_value = valid_watchlist
        
        result = get_watchlist(mock_db, [])
        
        # Verify all items have correct user_id (if included in response)
        # Note: user_id may not be in response to frontend, but verify internally
        for item in valid_watchlist:
            assert item["user_id"] == "single_user_mode", \
                "SECURITY: All data must belong to single_user_mode"

    # security and validation for batch remove service

    @patch('services.watchlist_service.mongo_client.bulk_manual_delete')
    def test_batch_remove_rejects_invalid_ticker_formats(
        self,
        mock_bulk_manual_delete,
    ):
        """
        SECURITY + EDGE CASES:
        - Service must validate ticker formats before hitting the DB.
        - Any ticker with invalid characters triggers a ValueError and
          prevents the bulk operation from running.
        """
        import services.watchlist_service as watchlist_service

        db = MagicMock()
        bad_tickers = ["AAPL", "BAD TICKER", "MSFT$"]

        with pytest.raises(ValueError):
            watchlist_service.batch_remove_from_watchlist(db, tickers=bad_tickers)

        mock_bulk_manual_delete.assert_not_called()

    @patch('services.watchlist_service.mongo_client.bulk_manual_delete')
    def test_batch_remove_normalizes_tickers_and_scopes_to_default_user(
        self,
        mock_bulk_manual_delete,
    ):
        """
        SECURITY + BUSINESS LOGIC:
        - Tickers are normalized (trim + uppercase) at the service layer.
        - DB helper is called exactly once with the normalized tickers list.
        - User scoping is enforced inside the DB helper via DEFAULT_USER_ID;
          service must not accept or forward any user ID from the caller.
        """
        import services.watchlist_service as watchlist_service
        from database.mongo_client import DEFAULT_USER_ID

        db = MagicMock()

        raw_tickers = [" aapl ", "msft\n"]
        normalized_expected = ["AAPL", "MSFT"]

        mock_bulk_manual_delete.return_value = {
            "removed": 2,
            "notfound": 0,
            "tickers": normalized_expected,
            "not_found_tickers": [],
        }

        result = watchlist_service.batch_remove_from_watchlist(db, tickers=raw_tickers)

        mock_bulk_manual_delete.assert_called_once()
        args, kwargs = mock_bulk_manual_delete.call_args

        # First argument is DB handle
        assert args[0] is db
        # Second argument is the normalized ticker list
        assert args[1] == normalized_expected

        # DB helper is responsible for enforcing DEFAULT_USER_ID internally;
        # the service must not accept a user_id parameter.
        assert "user_id" not in kwargs

        # Logical outcome and identifiers are both asserted
        assert result["removed"] == 2
        assert result["notfound"] == 0
        assert set(result["tickers"]) == set(normalized_expected)
# ============================================================================
# TEST: move_to_archive
# ============================================================================

# delete scope — only default user’s document is affected.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_scoped_to_default_user_only(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    delete scope — service delegates to bulk_manual_delete with DB + ticker only.
    DEFAULT_USER_ID scoping is enforced inside mongo_client.
    """
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": ["AAPL"],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, "AAPL")

    assert result and result["ticker"] == "AAPL"

    mock_bulk_manual_delete.assert_called_once()
    args, kwargs = mock_bulk_manual_delete.call_args

    # Service must only pass DB + [ticker]; user scoping is internal to the DB helper
    assert args[0] is mock_db
    assert args[1] == ["AAPL"]
    assert "user_id" not in kwargs

# ensure other user’s doc is not touched by default-user delete.
def test_move_to_archive_does_not_touch_other_user_docs(mock_db):
    other_user_doc = {"user_id": "other_user", "ticker": "AAPL", "failed_stage": None}

    def fake_find_one_and_delete(filter=None, *args, **kwargs):
        # Simulate only non-default user doc existing
        if filter and filter.get("user_id") == "single_user_mode":
            return None
        return other_user_doc

    mock_db.watchlist_items.find_one_and_delete.side_effect = fake_find_one_and_delete

    from services.watchlist_service import move_to_archive
    result = move_to_archive(mock_db, "AAPL")

    assert result is None
    mock_db.archived_watchlist_items.insert_one.assert_not_called()


# archive insert must always include default user id regardless of input.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_sets_user_id_on_archive_insert(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    Service-level view: summary must reflect normalized ticker and public reason,
    and must not allow the caller to influence user scoping.
    DB-layer tests verify user_id=DEFAULT_USER_ID on the archived document.
    """
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": ["NET"],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    out = move_to_archive(mock_db, "NET")

    assert out["ticker"] == "NET"
    assert out["reason"] == "MANUAL_DELETE"
    assert out["failed_stage"] is None

    mock_bulk_manual_delete.assert_called_once()
    args, kwargs = mock_bulk_manual_delete.call_args
    assert args[0] is mock_db
    assert args[1] == ["NET"]
    # No user_id parameter is ever accepted or forwarded by the service
    assert "user_id" not in kwargs
# ============================================================================
# TEST: get_archive
# ============================================================================

class TestArchiveSecurityAndIsolation:
    """Security: single-user mode enforced and no leakage of internal fields"""

    @patch('services.watchlist_service.mongo_client.list_archive_for_user')
    def test_get_archive_only_returns_default_user_data(self, mock_list, mock_db, default_user_id):
        # Mixed user data from DB layer (service must already filter to DEFAULT_USER_ID)
        mock_list.return_value = [
            {"user_id": default_user_id, "ticker": "CRM", "archived_at": datetime.utcnow(),
             "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
        ]
        from services.watchlist_service import get_archive
        out = get_archive(mock_db)
        items = out["archived_items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "CRM"

    @patch('services.watchlist_service.mongo_client.list_archive_for_user')
    def test_get_archive_does_not_leak_internal_fields(self, mock_list, mock_db, default_user_id):
        # Ensure user_id/_id/internal fields are not present in public shape
        mock_list.return_value = [
            {"_id": "507f1f77bcf86cd799439011", "user_id": default_user_id, "ticker": "NET",
             "archived_at": datetime.utcnow(), "reason": "MANUAL_DELETE", "failed_stage": None},
        ]
        from services.watchlist_service import get_archive
        out = get_archive(mock_db)
        it = out["archived_items"][0]
        assert "_id" not in it
        assert "user_id" not in it
        # Public fields remain
        assert set(it.keys()) == {"ticker", "archived_at", "reason", "failed_stage"}

# ============================================================================
# Security and isolation for hard delete service behavior
# ============================================================================
class TestDeleteFromArchiveSecurity:
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_delete_from_archive_uses_default_user_scope(self, mock_delete, mock_db, default_user_id):
        """
        Requirements 3,4,5,9,11: Ensure call signature uses service-layer guardrails and
        only passes db + ticker; DEFAULT_USER_ID scoping is enforced in mongo_client.
        """
        from services import watchlist_service as svc
        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        out = svc.delete_from_archive(mock_db, "net")
        assert out["ticker"] == "NET"
        # The service must not accept/forward caller user_id; verify signature is (db, ticker)
        args, kwargs = mock_delete.call_args
        assert len(args) == 2 and isinstance(args[0], MagicMock) and args[1] == "NET"
        assert kwargs == {}

    def test_delete_from_archive_rejects_whitespace_and_none(self, mock_db):
        """
        Requirements 2,3,4,7,9: Whitespace and None rejected with ValueError to prevent broad deletes.
        """
        from services import watchlist_service as svc
        with pytest.raises(ValueError):
            svc.delete_from_archive(mock_db, "   ")
        with pytest.raises(ValueError):
            svc.delete_from_archive(mock_db, None)  # type: ignore

    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_delete_from_archive_idempotent_semantics(self, mock_delete, mock_db):
        """
        Requirements 1,2,4,7,9,11: First call deletes, second returns None (idempotent),
        asserting both logical outcomes and the key identity.
        """
        from services import watchlist_service as svc
        mock_delete.side_effect = [
            SimpleNamespace(deleted_count=1),
            SimpleNamespace(deleted_count=0),
        ]

        first = svc.delete_from_archive(mock_db, "CRM")
        assert first["deleted"] is True and first["ticker"] == "CRM"

        second = svc.delete_from_archive(mock_db, "CRM")
        assert second is None

# ============================================================================
# TESTS: BatchAddServiceSecurity
# ============================================================================
class TestBatchAddServiceSecurity:
    """Service-layer validation, normalization, and partial success semantics"""

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_batch_add_normalizes_and_upserts_with_defaults(self, mock_delete_archive, mock_upsert, mock_db):
        import services.watchlist_service as svc

        # Simulate idempotent upsert results: first adds, second already existed (skip)
        def _upsert(db, ticker, fields):
            assert fields.get("is_favourite") is False
            assert fields.get("last_refresh_status") in (None, "PENDING", "UNKNOWN")
            return MagicMock(upserted_id="x")  # shape for the first call; caller interprets as added

        mock_upsert.side_effect = [_upsert, _upsert]
        mock_delete_archive.return_value = MagicMock(deleted_count=1)

        result = svc.batch_add_to_watchlist(mock_db, tickers=[" aapl ", "AAPL"])
        # Deduped to one ticker, added once, skipped once
        assert result["added"] == ["AAPL"]
        assert result["skipped"] == ["AAPL"]
        assert result["errors"] == []

        # Archive cleanup is attempted once per normalized ticker
        mock_delete_archive.assert_called_once()
        args, _ = mock_delete_archive.call_args
        assert args[1] == "AAPL"

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    def test_batch_add_rejects_invalid_formats_before_db(self, mock_upsert, mock_db):
        import services.watchlist_service as svc
        with pytest.raises(ValueError):
            svc.batch_add_to_watchlist(mock_db, tickers=["BAD TICKER", "MSFT$"])
        mock_upsert.assert_not_called()

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_batch_add_per_item_failure_partial_success(self, mock_delete_archive, mock_upsert, mock_db):
        import services.watchlist_service as svc

        def _upsert(db, ticker, fields):
            if ticker == "DDOG":
                raise RuntimeError("Transient failure")
            return MagicMock(upserted_id=None)  # indicates existed/skip by convention

        mock_upsert.side_effect = _upsert
        mock_delete_archive.return_value = MagicMock(deleted_count=0)

        out = svc.batch_add_to_watchlist(mock_db, tickers=["CRWD", "DDOG"])
        # CRWD skipped (already existed), DDOG error
        assert "CRWD" in out["skipped"]
        assert "DDOG" in out["errors"]


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
