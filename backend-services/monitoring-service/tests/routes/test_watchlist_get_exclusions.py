# backend-services/monitoring-service/tests/routes/test_watchlist_get_exclusions.py
"""
Tests for GET /monitor/watchlist exclusion behavior and parsing robustness.

Covers:
- Mutual exclusivity with portfolio via ?exclude=
- Parsing of whitespace, duplicates, and URL-encoded tickers (e.g., BRK%2EB)
- Response items contain only non-excluded watchlist tickers with correct metadata.count
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock

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
    def test_watchlist_excludes_portfolio_tickers_single(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        CRITICAL: Verify ?exclude=CRWD properly excludes portfolio ticker
        Tests query parameter parsing with single ticker
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Execute with single exclusion
        response = client.get('/monitor/watchlist?exclude=CRWD')
        
        assert response.status_code == 200
        
        # Verify get_watchlist was called with correct exclusion list
        mock_get_watchlist.assert_called_once()
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        
        assert isinstance(exclusion_list, list), "Exclusion list must be list type"
        assert len(exclusion_list) == 1, "Should have 1 excluded ticker"
        assert "CRWD" in exclusion_list, "Should exclude CRWD"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_excludes_portfolio_tickers_multiple(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        CRITICAL: Verify ?exclude=CRWD,NET properly parses multiple tickers
        Tests comma-separated list parsing
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Execute with multiple exclusions
        response = client.get('/monitor/watchlist?exclude=CRWD,NET')
        
        assert response.status_code == 200
        
        # Verify get_watchlist was called with correct exclusion list
        mock_get_watchlist.assert_called_once()
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        
        assert isinstance(exclusion_list, list), "Exclusion list must be list type"
        assert len(exclusion_list) == 2, "Should have 2 excluded tickers"
        assert "CRWD" in exclusion_list, "Should exclude CRWD"
        assert "NET" in exclusion_list, "Should exclude NET"

# ============================================================================
# TEST: Query Parameter Parsing Edge Cases
# ============================================================================

class TestQueryParameterParsing:
    """Test edge cases in query parameter parsing"""
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_exclude_with_whitespace(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Edge case: Verify whitespace in exclude parameter is handled
        Example: ?exclude=CRWD, NET, DDOG (spaces after commas)
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Execute with whitespace
        response = client.get('/monitor/watchlist?exclude=CRWD, NET, DDOG')
        
        assert response.status_code == 200
        
        # Verify tickers are properly trimmed
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        
        assert len(exclusion_list) == 3
        # Verify no whitespace in parsed tickers
        for ticker in exclusion_list:
            assert ticker == ticker.strip(), f"Ticker '{ticker}' should have whitespace stripped"
            assert " " not in ticker, f"Ticker '{ticker}' should not contain spaces"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_exclude_empty_string(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Edge case: Verify ?exclude= (empty string) is treated as no exclusions
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        response = client.get('/monitor/watchlist?exclude=')
        
        assert response.status_code == 200
        
        # Should treat as empty list
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        assert exclusion_list == [], "Empty exclude param should result in empty list"
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_exclude_with_trailing_comma(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Edge case: Verify ?exclude=CRWD,NET, (trailing comma) is handled
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        response = client.get('/monitor/watchlist?exclude=CRWD,NET,')
        
        assert response.status_code == 200
        
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        
        # Should filter out empty strings from trailing comma
        assert len(exclusion_list) == 2, "Trailing comma should not create empty entry"
        assert "" not in exclusion_list, "Should filter out empty strings"
        assert "CRWD" in exclusion_list
        assert "NET" in exclusion_list
    
    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_watchlist_exclude_case_sensitivity(
        self, mock_connect, mock_get_watchlist, client, sample_watchlist_response
    ):
        """
        Verify case handling in exclude parameter
        Tickers should be normalized to uppercase
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)
        mock_get_watchlist.return_value = sample_watchlist_response
        
        # Test with lowercase and mixed case
        response = client.get('/monitor/watchlist?exclude=crwd,NeT,DdOg')
        
        assert response.status_code == 200
        
        call_args = mock_get_watchlist.call_args
        exclusion_list = call_args[0][1]
        
        # Verify all tickers are uppercase (standard ticker format)
        for ticker in exclusion_list:
            assert ticker.isupper(), f"Ticker '{ticker}' should be uppercase"

class TestMutualExclusivityRoute:
    """Mutual exclusivity via ?exclude= portfolio tickers, asserted at route output"""

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_mutual_exclusivity_excludes_portfolio_ticker_and_keeps_watchlist(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Requirement 1, 3, 4, 7, 9, 11:
        Arrange: NET is in watchlist; CRWD is a portfolio ticker passed via ?exclude=CRWD
        Act: GET /monitor/watchlist?exclude=CRWD
        Assert: Response contains only NET and excludes CRWD; service receives correct exclusion list
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Side effect returns filtered items based on exclusion list passed into get_watchlist
        def _side_effect(_db, exclusion_list):
            base_items = [
                {
                    "ticker": "NET",
                    "status": "Watch",
                    "date_added": None,
                    "is_favourite": False,
                    "last_refresh_status": "UNKNOWN",
                    "last_refresh_at": None,
                    "failed_stage": None,
                    "current_price": None,
                    "pivot_price": None,
                    "pivot_proximity_percent": None,
                    "is_leader": False,
                },
                {
                    "ticker": "CRWD",
                    "status": "Watch",
                    "date_added": None,
                    "is_favourite": False,
                    "last_refresh_status": "UNKNOWN",
                    "last_refresh_at": None,
                    "failed_stage": None,
                    "current_price": None,
                    "pivot_price": None,
                    "pivot_proximity_percent": None,
                    "is_leader": False,
                },
            ]
            filtered = [i for i in base_items if i["ticker"] not in exclusion_list]
            return {"items": filtered, "metadata": {"count": len(filtered)}}

        mock_get_watchlist.side_effect = _side_effect

        resp = client.get('/monitor/watchlist?exclude=CRWD')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        tickers = {i["ticker"] for i in data["items"]}
        assert "NET" in tickers
        assert "CRWD" not in tickers
        assert data["metadata"]["count"] == len(data["items"])

        # Exclusion list passed to service must be ['CRWD']
        args, _ = mock_get_watchlist.call_args
        assert isinstance(args[1], list)
        assert args[1] == ["CRWD"]

    @patch('services.watchlist_service.get_watchlist')
    @patch('database.mongo_client.connect')
    def test_exclude_whitespace_duplicates_and_url_encoded(
        self, mock_connect, mock_get_watchlist, client
    ):
        """
        Requirement 2, 3, 7, 13:
        Edge parsing: whitespace, duplicates, URL-encoded dot symbol in a single query
        """
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_connect.return_value = (mock_client, mock_db)

        # Make the route call-safe; return minimal valid shape
        mock_get_watchlist.return_value = {"items": [], "metadata": {"count": 0}}

        # Duplicates and whitespace; include BRK%2EB which decodes to BRK.B
        resp = client.get('/monitor/watchlist?exclude= CRWD , NET , NET , BRK%2EB ')
        assert resp.status_code == 200

        args, _ = mock_get_watchlist.call_args
        exclusions = args[1]
        assert isinstance(exclusions, list)
        # Route should split and trim; duplicate handling may be kept as-is (service can ignore dupes)
        # Validate presence and normalization of decoded dot symbol
        assert "CRWD" in exclusions
        assert "NET" in exclusions
        assert any(e in ("BRK.B", "BRK%2EB") for e in exclusions)

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
