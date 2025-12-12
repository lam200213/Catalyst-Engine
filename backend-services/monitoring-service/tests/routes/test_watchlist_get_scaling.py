# backend-services/monitoring-service/tests/routes/test_watchlist_get_scaling.py
"""

"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import quote

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Data Length Thresholds (Requirement #12)
# ============================================================================

class TestDataLengthThresholds:
    """Test with large data sets at threshold boundaries"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_large_exclusion_list_just_below_limit(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Test with 99 excluded tickers (just below typical URL length concerns)
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Generate 99 ticker symbols
        large_exclusion_list = [f"TICK{i:02d}" for i in range(99)]
        exclude_param = ",".join(large_exclusion_list)
        
        response = client.get(f'/monitor/watchlist?exclude={exclude_param}')
        
        assert response.status_code == 200, "Should handle 99 exclusions"
        
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        assert len(exclusion_list) == 99, "Should parse all 99 tickers"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_at_practical_limit(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Test with 100 excluded tickers (at practical limit)
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Generate exactly 100 ticker symbols
        large_exclusion_list = [f"TICK{i:03d}" for i in range(100)]
        exclude_param = ",".join(large_exclusion_list)
        
        response = client.get(f'/monitor/watchlist?exclude={exclude_param}')
        
        assert response.status_code == 200, "Should handle 100 exclusions"
        
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        assert len(exclusion_list) == 100, "Should parse all 100 tickers"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_large_response_payload(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Test with large watchlist response (500 items)
        Verify JSON serialization handles large payloads
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        
        # Generate large watchlist response
        large_items = []
        for i in range(500):
            large_items.append({
                "ticker": f"TICK{i:04d}",
                "status": "Watch",
                "date_added": "2025-10-01T10:00:00",
                "is_favourite": False,
                "last_refresh_status": "PASS",
                "last_refresh_at": "2025-11-05T08:00:00",
                "failed_stage": None,
                "current_price": 100.0 + i,
                "pivot_price": None,
                "pivot_proximity_percent": None,
                "is_leader": False
            })
        
        large_response = {
            "items": large_items,
            "metadata": {"count": 500}
        }
        
        mock_get_watchlist.return_value = large_response
        
        response = client.get('/monitor/watchlist')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["items"]) == 500, "Should return all 500 items"
        assert data["metadata"]["count"] == 500

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
