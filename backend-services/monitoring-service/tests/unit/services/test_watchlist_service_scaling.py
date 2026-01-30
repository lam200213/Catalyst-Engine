# backend-services/monitoring-service/tests/test_watchlist_service.py
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
# TEST: Data Length Thresholds 
# ============================================================================

class TestDataLengthThresholds:
    """Test functions with large data sets at threshold boundaries"""
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_large_dataset_just_below_limit(
        self, mock_list_watchlist, mock_db
    ):
        """
        Test get_watchlist with large number of items (999 items)
        Assuming practical limit is 1000 items
        """
        # Generate 999 watchlist items
        large_watchlist = []
        for i in range(999):
            large_watchlist.append({
                "user_id": "single_user_mode",
                "ticker": f"TICK{i:04d}",
                "date_added": datetime.utcnow() - timedelta(days=i % 100),
                "is_favourite": i % 10 == 0,  # Every 10th is favourite
                "last_refresh_status": "PASS" if i % 3 != 0 else "FAIL",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": "screening" if i % 3 == 0 else None,
                "current_price": 100.0 + (i % 50),
                "pivot_price": 105.0 if i % 2 == 0 else None,
                "pivot_proximity_percent": -2.5 if i % 2 == 0 else None,
                "is_leader": i % 5 == 0
            })
        
        mock_list_watchlist.return_value = large_watchlist
        
        # Execute
        result = get_watchlist(mock_db, [])
        
        # Should handle 999 items successfully
        assert len(result["items"]) == 999, "Should process 999 items"
        assert result["metadata"]["count"] == 999
        
        # Verify all items have required fields
        for item in result["items"]:
            assert "ticker" in item
            assert "status" in item
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_at_practical_limit(
        self, mock_list_watchlist, mock_db
    ):
        """
        Test get_watchlist at practical limit (1000 items)
        """
        # Generate exactly 1000 items
        large_watchlist = []
        for i in range(1000):
            large_watchlist.append({
                "user_id": "single_user_mode",
                "ticker": f"TICK{i:04d}",
                "date_added": datetime.utcnow(),
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": None,
                "current_price": 100.0,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False
            })
        
        mock_list_watchlist.return_value = large_watchlist
        
        result = get_watchlist(mock_db, [])
        
        # Should handle 1000 items at threshold
        assert len(result["items"]) == 1000
        assert result["metadata"]["count"] == 1000
    
    @patch('services.watchlist_service.mongo_client.list_watchlist_excluding')
    def test_get_watchlist_large_portfolio_exclusion_list(
        self, mock_list_watchlist, mock_db
    ):
        """
        Test get_watchlist with very large portfolio exclusion list
        """
        # Large portfolio with 500 tickers
        large_portfolio = [f"PORT{i:04d}" for i in range(500)]
        
        # Watchlist with 100 items
        watchlist = []
        for i in range(100):
            watchlist.append({
                "user_id": "single_user_mode",
                "ticker": f"WATCH{i:03d}",
                "date_added": datetime.utcnow(),
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": datetime.utcnow(),
                "failed_stage": None,
                "current_price": 100.0,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False
            })
        
        mock_list_watchlist.return_value = watchlist
        
        # Execute with large exclusion list
        result = get_watchlist(mock_db, large_portfolio)
        
        # Should handle large exclusion list
        mock_list_watchlist.assert_called_once_with(mock_db, large_portfolio)
        assert len(result["items"]) == 100

# ============================================================================
# TEST: Scaling tests for batch remove semantics
# ============================================================================
class TestBatchRemoveScaling:
    """Test data length thresholds and scaling for batch remove service."""

    @patch('services.watchlist_service.mongo_client.bulk_manual_delete')
    def test_batch_remove_large_payload_at_threshold_uses_bulk_path(
        self,
        mock_bulk_manual_delete,
    ):
        """
        Req #1, #2, #4, #11, #12:
        - Use the service-defined BATCH_REMOVE_MAX_TICKERS threshold.
        - A payload exactly at the threshold should succeed and call the bulk helper once.
        - Assert both logical outcome and identifiers are preserved.
        """
        import services.watchlist_service as watchlist_service

        # Discover the service-level max; tests do not hardcode the value
        max_size = watchlist_service.BATCH_REMOVE_MAX_TICKERS

        # Build a payload exactly at the supported threshold
        tickers = [f"TICK{i:03d}" for i in range(max_size)]

        mock_bulk_manual_delete.return_value = {
            "removed": max_size,
            "notfound": 0,
            "tickers": tickers,
            "not_found_tickers": [],
        }

        db = MagicMock()
        result = watchlist_service.batch_remove_from_watchlist(db, tickers=tickers)

        mock_bulk_manual_delete.assert_called_once()
        args, kwargs = mock_bulk_manual_delete.call_args

        # First arg is db handle, second is the normalized ticker list
        passed_tickers = args[1]
        assert len(passed_tickers) == max_size
        assert set(passed_tickers) == set(tickers)

        assert result["removed"] == max_size
        assert result["notfound"] == 0
        # Logical outcome+identifiers
        assert set(result["tickers"]) == set(tickers)

    @patch('services.watchlist_service.mongo_client.bulk_manual_delete')
    def test_batch_remove_payload_above_threshold_fails_gracefully(
        self,
        mock_bulk_manual_delete,
    ):
        """
        Req #2, #5, #12:
        - A payload above BATCH_REMOVE_MAX_TICKERS must fail gracefully.
        - The service should raise a ValueError (or a domain-specific error)
          without issuing any DB bulk operation.
        """
        import services.watchlist_service as watchlist_service

        max_size = watchlist_service.BATCH_REMOVE_MAX_TICKERS
        # Just above the allowed limit
        tickers = [f"TICK{i:03d}" for i in range(max_size + 1)]

        db = MagicMock()
        with pytest.raises(ValueError):
            watchlist_service.batch_remove_from_watchlist(db, tickers=tickers)

        mock_bulk_manual_delete.assert_not_called()

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
