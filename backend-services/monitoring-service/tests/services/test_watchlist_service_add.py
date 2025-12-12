# backend-services/monitoring-service/tests/services/test_watchlist_service_add.py
"""
Test suite for services/watchlist_service.py
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from typing import List, Dict, Any

# Import the module under test
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
)

# Import database client functions
from database import mongo_client

# ============================================================================
# TEST: add_to_watchlist() - Business Logic Requirements
# ============================================================================

class TestAddToWatchlistBusinessLogic:
    """Test add_to_watchlist business logic and requirements"""
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_new_ticker_with_defaults(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        Verify add_to_watchlist sets correct defaults for new ticker:
        - is_favourite: False
        - last_refresh_status: PENDING
        - date_added: current timestamp
        """
        ticker = "NVDA"
        
        # Mock successful upsert (new item)
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id_123"
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result
        
        # Mock no archive deletion needed
        mock_archive_result = MagicMock()
        mock_archive_result.deleted_count = 0
        mock_delete_archive.return_value = mock_archive_result
        
        # Execute
        result = add_to_watchlist(mock_db, ticker)
        
        # Verify upsert was called with correct defaults
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        
        assert call_args[0][0] == mock_db, "Should pass db handle"
        assert call_args[0][1] == ticker, "Should pass ticker"
        
        defaults = call_args[0][2]
        assert defaults["is_favourite"] is False, "is_favourite should default to False"
        assert defaults["last_refresh_status"] == "PENDING", "last_refresh_status should default to PENDING"
        assert "date_added" in defaults, "Should include date_added timestamp"
        assert isinstance(defaults["date_added"], datetime), "date_added should be datetime object"
        
        # Verify archive deletion was attempted (re-introduction handling)
        mock_delete_archive.assert_called_once_with(mock_db, ticker)
        
        # Verify return value structure
        assert result["success"] is True, "Should return success"
        assert result["ticker"] == ticker, "Should return ticker"
        assert result["existed"] is False, "Should indicate new item"
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_idempotent_existing_ticker(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        CRITICAL: Verify idempotent behavior - re-adding existing ticker succeeds
        Should return existed=True but still succeed
        """
        ticker = "AAPL"
        
        # Mock upsert finding existing item (matched_count > 0)
        mock_result = MagicMock()
        mock_result.upserted_id = None
        mock_result.matched_count = 1
        mock_result.modified_count = 0
        mock_upsert.return_value = mock_result
        
        # Mock no archive deletion
        mock_archive_result = MagicMock()
        mock_archive_result.deleted_count = 0
        mock_delete_archive.return_value = mock_archive_result
        
        # Execute
        result = add_to_watchlist(mock_db, ticker)
        
        # Verify success despite already existing
        assert result["success"] is True, "Idempotent: should still succeed"
        assert result["existed"] is True, "Should indicate item already existed"
        assert result["ticker"] == ticker, "Should return ticker"
        
        # Verify upsert was still called (idempotent operation)
        mock_upsert.assert_called_once()
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_reintroduction_from_archive(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        CRITICAL: Verify re-introduction logic
        When adding ticker that exists in archive:
        1. Upsert into watchlistitems
        2. Delete from archived_watchlist_items
        """
        ticker = "CRM"
        
        # Mock new upsert
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id_456"
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result
        
        # Mock successful archive deletion (item was in archive)
        mock_archive_result = MagicMock()
        mock_archive_result.deleted_count = 1
        mock_delete_archive.return_value = mock_archive_result
        
        # Execute
        result = add_to_watchlist(mock_db, ticker)
        
        # Verify both operations occurred
        mock_upsert.assert_called_once()
        mock_delete_archive.assert_called_once_with(mock_db, ticker)
        
        # Verify result indicates successful re-introduction
        assert result["success"] is True
        assert result["reintroduced"] is True, "Should flag as re-introduction"
        assert result["ticker"] == ticker
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_multiple_calls_same_ticker(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        Edge case: Verify multiple rapid calls with same ticker are idempotent
        """
        ticker = "TSLA"
        
        # Setup mocks
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 0
        mock_upsert.return_value = mock_result
        
        mock_archive_result = MagicMock()
        mock_archive_result.deleted_count = 0
        mock_delete_archive.return_value = mock_archive_result
        
        # Execute multiple times
        result1 = add_to_watchlist(mock_db, ticker)
        result2 = add_to_watchlist(mock_db, ticker)
        result3 = add_to_watchlist(mock_db, ticker)
        
        # All should succeed
        assert result1["success"] is True
        assert result2["success"] is True
        assert result3["success"] is True
        
        # All should indicate existed (after first call)
        assert result1["existed"] is True  # assuming it existed before
        assert result2["existed"] is True
        assert result3["existed"] is True

# ============================================================================
# TEST: add_or_upsert_ticker
# ============================================================================

class TestAddOrUpsertTickerService:
    """
    Tests for services.watchlist_service.add_or_upsert_ticker(db, user_id, ticker)
    Business logic:
      - Upsert into watchlistitems for DEFAULT_USER_ID (ignore provided user_id)
      - Set is_favourite False by default (if missing)
      - Set date_added (date_added semantics) and last_updated timestamps
      - Delete any matching entry from archived_watchlist_items (re-introduction)
      - Return flags: success, ticker, existed, reintroduced
    """

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_upsert_new_sets_defaults_and_timestamps(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        mock_result = MagicMock()
        mock_result.matched_count = 0  # new insert
        mock_upsert.return_value = mock_result

        archive_del = MagicMock()
        archive_del.deleted_count = 0
        mock_delete_archive.return_value = archive_del

        # import inside to avoid circulars in test loads
        from services.watchlist_service import add_or_upsert_ticker

        result = add_or_upsert_ticker(mock_db, user_id="random_user", ticker="AAPL")
        assert result["success"] is True
        assert result["ticker"] == "AAPL"
        assert result["existed"] is False
        assert result["reintroduced"] is False

        # Verify defaults passed to upsert
        args, kwargs = mock_upsert.call_args
        defaults = args[2]
        assert defaults["is_favourite"] is False
        assert defaults["last_refresh_status"] in ("PENDING", "UNKNOWN")
        assert isinstance(defaults["date_added"], datetime), "date_added timestamp must be set"
        assert isinstance(defaults["last_updated"], datetime), "last_updated timestamp must be set"
        # No user-controlled fields should leak
        assert "user_id" not in defaults

        mock_delete_archive.assert_called_once_with(mock_db, "AAPL")

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_idempotent_existing_returns_existed_true(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        mock_result = MagicMock()
        mock_result.matched_count = 1  # existing doc
        mock_upsert.return_value = mock_result

        archive_del = MagicMock()
        archive_del.deleted_count = 0
        mock_delete_archive.return_value = archive_del

        from services.watchlist_service import add_or_upsert_ticker

        result = add_or_upsert_ticker(mock_db, user_id="any", ticker="MSFT")
        assert result["success"] is True
        assert result["existed"] is True
        assert result["ticker"] == "MSFT"

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_reintroduction_deletes_from_archive_before_returning(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        # Track operation order manually
        call_order = []

        def upsert_side_effect(*args, **kwargs):
            call_order.append("upsert")
            m = MagicMock()
            m.matched_count = 0
            return m

        def delete_side_effect(*args, **kwargs):
            call_order.append("delete_archive")
            d = MagicMock()
            d.deleted_count = 1
            return d

        mock_upsert.side_effect = upsert_side_effect
        mock_delete_archive.side_effect = delete_side_effect

        from services.watchlist_service import add_or_upsert_ticker

        result = add_or_upsert_ticker(mock_db, user_id="ignored", ticker="CRM")
        assert result["success"] is True
        assert result["reintroduced"] is True
        assert call_order == ["upsert", "delete_archive"], "Should upsert then delete from archive"

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
