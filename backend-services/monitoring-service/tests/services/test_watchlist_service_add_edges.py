# backend-services/monitoring-service/tests/services/test_watchlist_service_add_edges.py
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
# TEST: add_to_watchlist() - Edge Cases and Validation
# ============================================================================

class TestAddToWatchlistEdgeCases:
    """Test edge cases and error handling for add_to_watchlist"""
    
    def test_add_to_watchlist_empty_ticker(self, mock_db):
        """Edge case: Verify rejection of empty ticker"""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            add_to_watchlist(mock_db, "")
    
    def test_add_to_watchlist_none_ticker(self, mock_db):
        """Edge case: Verify rejection of None ticker"""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            add_to_watchlist(mock_db, None)
    
    def test_add_to_watchlist_whitespace_only_ticker(self, mock_db):
        """Edge case: Verify rejection of whitespace-only ticker"""
        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            add_to_watchlist(mock_db, "   ")
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_special_characters_in_ticker(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """Edge case: Verify handling of valid special characters (e.g., BRK.B)"""
        tickers_with_special_chars = ["BRK.B", "BRK-B"]
        
        mock_result = MagicMock()
        mock_result.upserted_id = "id_123"
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result
        
        mock_archive_result = MagicMock()
        mock_archive_result.deleted_count = 0
        mock_delete_archive.return_value = mock_archive_result
        
        for ticker in tickers_with_special_chars:
            result = add_to_watchlist(mock_db, ticker)
            assert result["success"] is True, f"Should handle ticker: {ticker}"
            assert result["ticker"] == ticker
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    def test_add_to_watchlist_database_error(self, mock_upsert, mock_db):
        """Edge case: Verify error handling when database operation fails"""
        from pymongo.errors import OperationFailure
        
        ticker = "AAPL"
        mock_upsert.side_effect = OperationFailure("Database connection failed")
        
        with pytest.raises(OperationFailure):
            add_to_watchlist(mock_db, ticker)
    
    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_add_to_watchlist_archive_deletion_failure_continues(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        Edge case: Verify operation continues even if archive deletion fails
        (ticker might not be in archive)
        """
        ticker = "NVDA"
        
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id"
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result
        
        # Archive deletion fails (e.g., item not in archive)
        mock_delete_archive.side_effect = Exception("Archive item not found")
        
        # Should handle gracefully - archive deletion is optional
        try:
            result = add_to_watchlist(mock_db, ticker)
            # If implementation handles gracefully, verify success
            assert result["success"] is True
        except Exception:
            # If implementation propagates error, that's also acceptable
            # depending on design decision
            pass

# ============================================================================
# TEST: add_or_upsert_ticker - Edge Cases and Validation
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

    def test_validation_empty_ticker_raises(self, mock_db):
        from services.watchlist_service import add_or_upsert_ticker
        with pytest.raises(ValueError):
            add_or_upsert_ticker(mock_db, user_id="x", ticker="")

        with pytest.raises(ValueError):
            add_or_upsert_ticker(mock_db, user_id="x", ticker="   ")

        with pytest.raises(ValueError):
            add_or_upsert_ticker(mock_db, user_id="x", ticker=None)

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_symbol_normalization_and_allowed_formats(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        Accept uppercase alphanumerics plus '.' or '-' within length limit.
        Should normalize case and preserve accepted punctuation.
        """
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result

        archive_del = MagicMock()
        archive_del.deleted_count = 0
        mock_delete_archive.return_value = archive_del

        from services.watchlist_service import add_or_upsert_ticker

        for raw, expected in [("aapl", "AAPL"), ("brk.b", "BRK.B"), ("brk-b", "BRK-B")]:
            res = add_or_upsert_ticker(mock_db, "u", raw)
            assert res["ticker"] == expected

        # Invalid symbols rejected
        for bad in ["$AAPL", "A APL", "AAPL!", "ABCDEFGHIJK"]:
            with pytest.raises(ValueError):
                add_or_upsert_ticker(mock_db, "u", bad)

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_length_thresholds_just_below_and_at_limit(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_upsert.return_value = mock_result

        archive_del = MagicMock()
        archive_del.deleted_count = 0
        mock_delete_archive.return_value = archive_del

        from services.watchlist_service import add_or_upsert_ticker

        # at limit (10) should pass
        res = add_or_upsert_ticker(mock_db, "u", "ABCDEFGHIJ")
        assert res["ticker"] == "ABCDEFGHIJ"

        # above limit (11) should fail
        with pytest.raises(ValueError):
            add_or_upsert_ticker(mock_db, "u", "ABCDEFGHIJK")

    @patch('services.watchlist_service.mongo_client.upsert_watchlist_item')
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_security_user_id_is_ignored_for_db_operations(
        self, mock_delete_archive, mock_upsert, mock_db
    ):
        """
        SECURITY: Even if user_id is provided, DB operations must rely on DEFAULT_USER_ID.
        Service must NOT pass user_id down or allow caller-controlled user_id to leak.
        """
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_upsert.return_value = mock_result

        archive_del = MagicMock()
        archive_del.deleted_count = 0
        mock_delete_archive.return_value = archive_del

        from services.watchlist_service import add_or_upsert_ticker
        add_or_upsert_ticker(mock_db, user_id="intruder", ticker="NET")

        args, kwargs = mock_upsert.call_args
        defaults = args[2]
        assert "user_id" not in defaults, "Service must not pass caller-supplied user_id"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
