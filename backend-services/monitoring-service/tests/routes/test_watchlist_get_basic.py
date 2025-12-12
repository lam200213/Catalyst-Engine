# backend-services/monitoring-service/tests/routes/test_app_watchlist.py  
"""
Basic success-path tests for GET /monitor/watchlist:
- Empty list returns 200 and items=[]
- Populated list returns AAPL and MSFT with correct metadata.count
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from flask import Flask
from urllib.parse import quote

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ============================================================================
# TEST: Internal Watchlist Endpoint - Basic Functionality
# ============================================================================

class TestInternalWatchlistEndpointBasic:
    """Test GET /monitor/watchlist basic functionality"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_returns_success_with_no_exclusions(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Verify GET /monitor/watchlist returns watchlist when no exclusions provided
        """
        # Setup mocks
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Execute request with no query parameters
        response = client.get('/monitor/watchlist')
        
        # Verify status code
        assert response.status_code == 200, "Should return 200 OK"
        
        # Verify response is JSON
        assert response.content_type == 'application/json'
        
        # Parse response
        data = json.loads(response.data)
        
        # Verify response structure matches WatchlistListResponse
        assert "items" in data, "Response must have 'items' field"
        assert "metadata" in data, "Response must have 'metadata' field"
        assert isinstance(data["items"], list), "items must be list"
        assert isinstance(data["metadata"], dict), "metadata must be dict"
        assert "count" in data["metadata"], "metadata must have 'count'"
        
        # Verify watchlist_service.get_watchlist was called with empty exclusion list
        mock_get_watchlist.assert_called_once()
        call_args = mock_get_watchlist.call_args
        assert call_args[0][0] == mock_db, "Should pass db handle"
        assert call_args[0][1] == [], "Should pass empty exclusion list when no query param"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_returns_empty_list_gracefully(
        self, mock_connect, mock_get_watchlist, client, sample_empty_watchlist_response
    ):
        """
        Edge case: Verify empty watchlist is handled correctly
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_empty_watchlist_response
        
        response = client.get('/monitor/watchlist')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data["items"] == [], "Items should be empty list"
        assert data["metadata"]["count"] == 0, "Count should be 0"

class TestInternalWatchlistEndpointBasicPopulatedAndEmpty:
    """Test GET /monitor/watchlist empty and populated cases"""

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_populated_list_contains_expected_symbols(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Requirement 1, 7, 9, 11:
        Populated list returns 200, contains both items, and metadata.count matches len(items)
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Ensure both AAPL and MSFT exist in the returned items
        mock_get_watchlist.return_value = sample_watchlist_response

        resp = client.get('/monitor/watchlist')
        assert resp.status_code == 200
        data = json.loads(resp.data)

        assert isinstance(data, dict)
        assert "items" in data and isinstance(data["items"], list)
        assert "metadata" in data and isinstance(data["metadata"], dict)
        tickers = {i["ticker"] for i in data["items"]}
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert data["metadata"]["count"] == len(data["items"])

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_empty_list_returns_200_empty_items(
        self, mock_connect, mock_get_watchlist, client, sample_empty_watchlist_response
    ):
        """
        Requirement 1, 2, 7, 9:
        Empty list returns 200 OK with items = [] and count = 0
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        mock_get_watchlist.return_value = sample_empty_watchlist_response

        resp = client.get('/monitor/watchlist')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["items"] == []
        assert data["metadata"]["count"] == 0

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
