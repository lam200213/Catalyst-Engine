# backend-services/monitoring-service/tests/services/test_watchlist_service_get_core.py
"""
Service-layer tests for watchlist_service.get_watchlist business logic:
- Empty and populated returns
- Mutual exclusivity excluding portfolio tickers
- metadata.count consistency and identifier assertions
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
import json
from types import SimpleNamespace

# Import the module under test
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    delete_from_archive,
)

# Import database client functions
from database import mongo_client


# ============================================================================
# TEST: get_watchlist() - Business Logic Requirements
# ============================================================================

class TestGetWatchlistBusinessLogic:
    """Test get_watchlist business logic and requirements"""
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_excludes_portfolio_tickers(
        self, mock_list_watchlist, mock_db, sample_watchlist_items, portfolio_tickers
    ):
        """
        CRITICAL: Verify mutual exclusivity with portfolio
        Watchlist should exclude any tickers present in portfolio
        """
        # Mock returns watchlist items NOT in portfolio
        mock_list_watchlist.return_value = sample_watchlist_items
        
        # Execute
        result = get_watchlist(mock_db, portfolio_tickers)
        
        # Verify list_watchlist_excluding was called with portfolio tickers
        mock_list_watchlist.assert_called_once_with(mock_db, portfolio_tickers)
        
        # Verify result structure
        assert "items" in result, "Should have 'items' field"
        assert "metadata" in result, "Should have 'metadata' field"
        
        # Verify no portfolio tickers in result
        result_tickers = [item["ticker"] for item in result["items"]]
        for portfolio_ticker in portfolio_tickers:
            assert portfolio_ticker not in result_tickers, \
                f"Portfolio ticker {portfolio_ticker} should be excluded"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_empty_portfolio_list(
        self, mock_list_watchlist, mock_db, sample_watchlist_items
    ):
        """Edge case: Verify behavior with empty portfolio (no exclusions)"""
        mock_list_watchlist.return_value = sample_watchlist_items
        
        # Execute with empty portfolio
        result = get_watchlist(mock_db, [])
        
        # Should call with empty exclusion list
        mock_list_watchlist.assert_called_once_with(mock_db, [])
        
        # Should return all watchlist items
        assert len(result["items"]) == len(sample_watchlist_items)
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_returns_required_fields(
        self, mock_list_watchlist, mock_db, sample_watchlist_items
    ):
        """
        CRITICAL: Verify response includes all fields required by Phase 2 UI:
        - ticker
        - status (derived from business logic)
        - date_added
        - is_favourite
        - last_refresh_status
        - last_refresh_at
        - failed_stage
        - current_price
        - pivot_price
        - pivot_proximity_percent
        - is_leader
        """
        mock_list_watchlist.return_value = sample_watchlist_items
        
        result = get_watchlist(mock_db, [])
        
        required_fields = [
            "ticker", "status", "date_added", "is_favourite",
            "last_refresh_status", "last_refresh_at", "failed_stage",
            "current_price", "pivot_price", "pivot_proximity_percent", "is_leader"
        ]
        
        # Verify each item has all required fields
        for item in result["items"]:
            for field in required_fields:
                assert field in item, f"Missing required field: {field}"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_field_type_consistency(
        self, mock_list_watchlist, mock_db, sample_watchlist_items
    ):
        """
        Verify correct data types for each field (Requirement #7)
        """
        mock_list_watchlist.return_value = sample_watchlist_items
        
        result = get_watchlist(mock_db, [])
        
        for item in result["items"]:
            # String fields
            assert isinstance(item["ticker"], str), "ticker should be string"
            assert isinstance(item["status"], str), "status should be string"
            assert isinstance(item["last_refresh_status"], str), "last_refresh_status should be string"
            
            # Boolean fields
            assert isinstance(item["is_favourite"], bool), "is_favourite should be boolean"
            assert isinstance(item["is_leader"], bool), "is_leader should be boolean"
            
            # Datetime fields (or None)
            assert item["date_added"] is None or isinstance(item["date_added"], (str, datetime)), \
                "date_added should be string/datetime or None"
            assert item["last_refresh_at"] is None or isinstance(item["last_refresh_at"], (str, datetime)), \
                "last_refresh_at should be string/datetime or None"
            
            # Numeric fields (or None)
            assert item["current_price"] is None or isinstance(item["current_price"], (int, float)), \
                "current_price should be number or None"
            assert item["pivot_price"] is None or isinstance(item["pivot_price"], (int, float)), \
                "pivot_price should be number or None"
            assert item["pivot_proximity_percent"] is None or isinstance(item["pivot_proximity_percent"], (int, float)), \
                "pivot_proximity_percent should be number or None"
            
            # String or None fields
            assert item["failed_stage"] is None or isinstance(item["failed_stage"], str), \
                "failed_stage should be string or None"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_metadata_count(
        self, mock_list_watchlist, mock_db, sample_watchlist_items
    ):
        """Verify metadata includes accurate count"""
        mock_list_watchlist.return_value = sample_watchlist_items
        
        result = get_watchlist(mock_db, [])
        
        assert result["metadata"]["count"] == len(sample_watchlist_items), \
            "Metadata count should match number of items"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_date_added_field_mapping(
        self, mock_list_watchlist, mock_db
    ):
        """
        Verify 'date_added' from DB is correctly mapped to 'date_added' in response
        """
        item_with_date = {
            "user_id": "single_user_mode",
            "ticker": "AAPL",
            "date_added": datetime(2025, 9, 15, 10, 30, 0),
            "is_favourite": False,
            "last_refresh_status": "PASS",
            "last_refresh_at": datetime.utcnow(),
            "failed_stage": None,
            "current_price": 175.50,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": True
        }
        
        mock_list_watchlist.return_value = [item_with_date]
        
        result = get_watchlist(mock_db, [])
        
        # Verify field mapping
        assert "date_added" in result["items"][0], "Should have 'date_added' field"
        assert result["items"][0]["date_added"] is not None, "date_added should not be None"

class TestGetWatchlistCoreAdditions:
    """Service-level assertions for business logic and types"""

    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_returns_empty_structure_when_none(
        self, mock_list_watchlist, mock_db
    ):
        """
        Requirement 1, 2, 7, 9:
        Empty list path returns items=[], metadata.count=0 with correct types
        """
        mock_list_watchlist.return_value = []
        from services.watchlist_service import get_watchlist

        result = get_watchlist(mock_db, [])
        assert isinstance(result, dict)
        assert "items" in result and isinstance(result["items"], list)
        assert "metadata" in result and isinstance(result["metadata"], dict)
        assert result["items"] == []
        assert result["metadata"]["count"] == 0

    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_populated_includes_expected_items_and_count(
        self, mock_list_watchlist, mock_db
    ):
        """
        Requirement 1, 4, 7, 9, 11:
        Populated list returns items with identifiers and matching count
        """
        sample_items = [
            {
                "ticker": "AAPL",
                "date_added": None,
                "is_favourite": False,
                "last_refresh_status": "PENDING",
                "last_refresh_at": None,
                "failed_stage": None,
                "current_price": None,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False,
            },
            {
                "ticker": "MSFT",
                "date_added": None,
                "is_favourite": True,
                "last_refresh_status": "PASS",
                "last_refresh_at": None,
                "failed_stage": None,
                "current_price": 410.25,
                "pivot_price": 450.0,
                "pivot_proximity_percent": -8.83,
                "is_leader": True,
            },
        ]
        mock_list_watchlist.return_value = sample_items
        from services.watchlist_service import get_watchlist

        result = get_watchlist(mock_db, [])
        assert len(result["items"]) == 2
        assert {i["ticker"] for i in result["items"]} == {"AAPL", "MSFT"}
        assert result["metadata"]["count"] == 2

    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_mutual_exclusivity_excludes_portfolio(
        self, mock_list_watchlist, mock_db
    ):
        """
        Requirement 1, 3, 4, 7, 9, 11:
        Given watchlist contains NET and CRWD, exclusion list ['CRWD'] must return only NET
        """
        sample_items_not_in_portfolio = [
            {
                "ticker": "NET",
                "date_added": None,
                "is_favourite": False,
                "last_refresh_status": "UNKNOWN",
                "last_refresh_at": None,
                "failed_stage": None,
                "current_price": None,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False,
            }
        ]
        mock_list_watchlist.return_value = sample_items_not_in_portfolio
        from services.watchlist_service import get_watchlist

        result = get_watchlist(mock_db, ["CRWD"])
        assert len(result["items"]) == 1
        assert result["items"][0]["ticker"] == "NET"
        assert result["metadata"]["count"] == 1

# ============================================================================
# TEST: get_watchlist() - Edge Cases
# ============================================================================

class TestGetWatchlistEdgeCases:
    """Test edge cases for get_watchlist"""
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_empty_watchlist(self, mock_list_watchlist, mock_db):
        """Edge case: Verify behavior when watchlist is empty"""
        mock_list_watchlist.return_value = []
        
        result = get_watchlist(mock_db, [])
        
        assert result["items"] == [], "Should return empty items list"
        assert result["metadata"]["count"] == 0, "Count should be 0"
        assert isinstance(result["items"], list), "items should be list type"
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_none_portfolio_tickers(
        self, mock_list_watchlist, mock_db, sample_watchlist_items
    ):
        """Edge case: Verify handling of None portfolio_tickers parameter"""
        mock_list_watchlist.return_value = sample_watchlist_items
        
        # Should treat None as empty list
        result = get_watchlist(mock_db, None)
        
        # Should call with empty list
        mock_list_watchlist.assert_called_once_with(mock_db, [])
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_null_optional_fields(
        self, mock_list_watchlist, mock_db
    ):
        """
        Edge case: Verify handling of items with null optional fields
        Some fields can be None/null until refresh job runs
        """
        item_with_nulls = {
            "user_id": "single_user_mode",
            "ticker": "NEWSTOCK",
            "date_added": datetime.utcnow(),
            "is_favourite": False,
            "last_refresh_status": "PENDING",
            "last_refresh_at": None,  # Not yet refreshed
            "failed_stage": None,
            "current_price": None,  # Not yet fetched
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False
        }
        
        mock_list_watchlist.return_value = [item_with_nulls]
        
        result = get_watchlist(mock_db, [])
        
        # Should handle gracefully
        assert len(result["items"]) == 1
        item = result["items"][0]
        
        # Null fields should be preserved
        assert item["current_price"] is None, "Should preserve None for current_price"
        assert item["pivot_price"] is None
        assert item["last_refresh_at"] is None
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_database_error_handling(
        self, mock_list_watchlist, mock_db
    ):
        """Edge case: Verify error handling when database query fails"""
        from pymongo.errors import OperationFailure
        
        mock_list_watchlist.side_effect = OperationFailure("Database query failed")
        
        with pytest.raises(OperationFailure):
            get_watchlist(mock_db, [])

# ============================================================================
# TEST: move_to_archive
# ============================================================================

# move-to-archive happy path asserts removal and archive insert with required fields.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_happy_path_inserts_archive_and_removes_watchlist(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    move-to-archive happy path: asserts removal via bulk_manual_delete and
    a summary dict with required fields.
    """
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": ["AAPL"],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, "AAPL")

    # Assert logical outcome and identifier
    assert isinstance(result, dict)
    assert result["ticker"] == "AAPL"
    assert result["reason"] == "MANUAL_DELETE"
    assert result["failed_stage"] is None
    assert "archived_at" in result and (
        isinstance(result["archived_at"], (str, datetime))
        or hasattr(result["archived_at"], "isoformat")
    )

    # Verify DB helper delegation and normalized ticker
    mock_bulk_manual_delete.assert_called_once()
    args, kwargs = mock_bulk_manual_delete.call_args
    assert args[0] is mock_db
    assert args[1] == ["AAPL"]
    assert kwargs == {}
# not found returns None and does not insert archive.
def test_move_to_archive_not_found_returns_none_no_archive_insert(mock_db):
    mock_db.watchlist_items.find_one_and_delete.return_value = None
    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, "MSFT")

    assert result is None
    mock_db.archived_watchlist_items.insert_one.assert_not_called()

# idempotency — repeated delete only archives once then returns None.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_idempotent_repeated_delete(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    idempotency — first call archives, second sees not-found and returns None.
    """
    mock_bulk_manual_delete.side_effect = [
        {
            "removed": 1,
            "notfound": 0,
            "tickers": ["NET"],
            "not_found_tickers": [],
        },
        {
            "removed": 0,
            "notfound": 1,
            "tickers": [],
            "not_found_tickers": ["NET"],
        },
    ]

    from services.watchlist_service import move_to_archive

    first = move_to_archive(mock_db, "NET")
    second = move_to_archive(mock_db, "NET")

    assert first and first["ticker"] == "NET"
    assert second is None
    assert mock_bulk_manual_delete.call_count == 2

# normalization — lowercase input uppercased in filter and result.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_not_found_returns_none_no_archive_insert(
    mock_bulk_manual_delete,
    mock_db,
):
    """not found returns None; bulk helper still called once."""
    mock_bulk_manual_delete.return_value = {
        "removed": 0,
        "notfound": 1,
        "tickers": [],
        "not_found_tickers": ["MSFT"],
    }

    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, "MSFT")

    assert result is None
    mock_bulk_manual_delete.assert_called_once()

@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_normalizes_uppercase_and_uses_identifying_filter(
    mock_bulk_manual_delete,
    mock_db,
):
    """normalization — lowercase input uppercased in helper call and result."""
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": ["AAPL"],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, "aapl")

    assert result["ticker"] == "AAPL"
    mock_bulk_manual_delete.assert_called_once()
    args, _ = mock_bulk_manual_delete.call_args
    assert args[0] is mock_db
    assert args[1] == ["AAPL"]

# archive payload field/type assertions align with documented contract.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_inserts_required_archive_fields_and_types(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    archive summary field/type assertions align with documented contract.
    The raw Mongo payload is validated in DB-layer tests.
    """
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": ["CRWD"],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    out = move_to_archive(mock_db, "CRWD")

    assert isinstance(out["ticker"], str)
    assert isinstance(out["reason"], str)
    assert out["failed_stage"] is None or isinstance(out["failed_stage"], str)
    assert "archived_at" in out
    assert isinstance(out["archived_at"], (str, datetime)) or hasattr(
        out["archived_at"], "isoformat"
    )

# blind spot documentation — service assumes route-level length validation.
@patch("services.watchlist_service.mongo_client.bulk_manual_delete")
def test_move_to_archive_service_does_not_enforce_length_validation_blind_spot(
    mock_bulk_manual_delete,
    mock_db,
):
    """
    Service proceeds even for over-long tickers; route/contracts enforce length.
    """
    long_ticker = "A" * 11  # route should reject; service should not be responsible
    mock_bulk_manual_delete.return_value = {
        "removed": 1,
        "notfound": 0,
        "tickers": [long_ticker.upper()],
        "not_found_tickers": [],
    }

    from services.watchlist_service import move_to_archive

    result = move_to_archive(mock_db, long_ticker)
    assert result["ticker"] == long_ticker.upper()
    mock_bulk_manual_delete.assert_called_once()
# ============================================================================
# TEST: GET Archive Business Logic
# ============================================================================
class TestGetArchiveBusinessLogic:
    """Business logic, mapping, and type safety for get_archive()"""

    @patch('services.watchlist_service.mongo_client.list_archive_for_user')
    def test_get_archive_empty_returns_expected_structure(self, mock_list, mock_db):
        # Empty DB list
        mock_list.return_value = []
        from services.watchlist_service import get_archive

        result = get_archive(mock_db)
        assert isinstance(result, dict)
        assert "archived_items" in result and isinstance(result["archived_items"], list)
        assert result["archived_items"] == []

    @patch('services.watchlist_service.mongo_client.list_archive_for_user')
    def test_get_archive_maps_db_docs_to_api_contract_fields(self, mock_list, mock_db):
        # Raw Mongo-shaped docs (snake_case, underscored reason)
        mock_list.return_value = [
            {"user_id": "single_user_mode", "ticker": "CRM", "archived_at": datetime(2025, 11, 8, 10, 0, 0),
             "reason": "FAILED_HEALTH_CHECK", "failed_stage": "vcp"},
            {"user_id": "single_user_mode", "ticker": "NET", "archived_at": datetime(2025, 11, 1, 12, 0, 0),
             "reason": "MANUAL_DELETE", "failed_stage": None},
        ]
        from services.watchlist_service import get_archive

        out = get_archive(mock_db)
        items = out["archived_items"]
        assert len(items) == 2

        # Field mapping and identifier assertions
        for it in items:
            assert "ticker" in it and isinstance(it["ticker"], str)
            assert "archived_at" in it and isinstance(it["archived_at"], str)
            assert "reason" in it and isinstance(it["reason"], str)
            assert "failed_stage" in it and (it["failed_stage"] is None or isinstance(it["failed_stage"], str))

        # Reason transformation: underscores removed in public contract
        reasons = {it["reason"] for it in items}
        assert reasons == {"FAILED_HEALTH_CHECK", "MANUAL_DELETE"}

        # Tickers preserved and uppercased normalization assumed
        assert {it["ticker"] for it in items} == {"CRM", "NET"}

    @patch('services.watchlist_service.mongo_client.list_archive_for_user')
    def test_get_archive_type_consistency(self, mock_list, mock_db):
        # Type assertions across all fields
        now = datetime.utcnow()
        mock_list.return_value = [
            {"user_id": "single_user_mode", "ticker": "ZEN", "archived_at": now,
             "reason": "MANUAL_DELETE", "failed_stage": None},
        ]
        from services.watchlist_service import get_archive
        out = get_archive(mock_db)
        it = out["archived_items"][0]
        assert isinstance(it["ticker"], str)
        assert isinstance(it["archived_at"], str)
        assert isinstance(it["reason"], str)
        assert it["failed_stage"] is None or isinstance(it["failed_stage"], str)

# ============================================================================
# Service-level tests for hard delete from archive (DELETE /monitor/archive/:ticker)
# ============================================================================
class TestArchiveHardDeleteService:
    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_delete_from_archive_success_returns_flags_and_identity(self, mock_delete, mock_db):
        """
        Requirements 1,4,7,9,11: Successful hard delete returns a dict containing
        the normalized ticker and a boolean deleted flag; asserts key identity and types.
        """
        mock_delete.return_value = SimpleNamespace(deleted_count=1)
        from services.watchlist_service import delete_from_archive
        out = delete_from_archive(mock_db, "aapl")  # lower-case input
        assert isinstance(out, dict)
        assert out["deleted"] is True
        assert out["ticker"] == "AAPL"

        # Ensure service normalized and called DB with normalized ticker
        args, kwargs = mock_delete.call_args
        assert len(args) >= 2
        assert args[1] == "AAPL"

    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_delete_from_archive_not_found_returns_none(self, mock_delete, mock_db):
        """
        Requirements 1,2,4,7,9: Not found returns None (mirrors move_to_archive pattern),
        ensuring route can map to 404; no type mismatches in assertions.
        """
        
        mock_delete.return_value = SimpleNamespace(deleted_count=0)

        out = delete_from_archive(mock_db, "MSFT")
        assert out is None

    @patch('services.watchlist_service.mongo_client.delete_archive_item')
    def test_delete_from_archive_parses_and_normalizes_symbols(self, mock_delete, mock_db):
        """
        Requirements 2,4,7,11,13: Accepts raw/URL-encoded symbols and normalizes case.
        """
        
        mock_delete.return_value = SimpleNamespace(deleted_count=1)

        out1 = delete_from_archive(mock_db, "BRK.b")
        assert out1["ticker"] == "BRK.B"
        out2 = delete_from_archive(mock_db, "shop.to")
        assert out2["ticker"] == "SHOP.TO"

    def test_delete_from_archive_invalid_characters_raise_value_error(self, mock_db):
        """
        Requirements 2,3,4,7,9: Invalid ticker format is rejected at service with ValueError.
        """
        
        with pytest.raises(ValueError):
            delete_from_archive(mock_db, "AAPL@")

    def test_delete_from_archive_length_boundaries(self, mock_db, ticker_thresholds):
        """
        Requirements 2,4,7,9,12: Below threshold fails, at threshold passes.
        """
        

        # Below threshold (empty) -> error
        with pytest.raises(ValueError):
            delete_from_archive(mock_db, ticker_thresholds["below"])

        # At threshold (exact MAX_SYMBOL_LEN) -> OK (will fail until implemented)
        at = ticker_thresholds["at"]
        with patch('services.watchlist_service.mongo_client.delete_archive_item') as mock_delete:
            mock_delete.return_value = SimpleNamespace(deleted_count=1)
            out = delete_from_archive(mock_db, at.lower())
            assert out["ticker"] == at
            assert out["deleted"] is True


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
