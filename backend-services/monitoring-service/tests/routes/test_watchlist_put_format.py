# backend-services/monitoring-service/tests/routes/test_watchlist_put_format.py
"""

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

class TestPutAddTickerRoute:
    """Tests for PUT /monitor/watchlist/<ticker>"""

    @pytest.mark.parametrize(
        "invalid",
        [
            "", " ", "   ",  # empty/whitespace
            "$AAPL", "AAPL!", "AA PL",  # invalid chars/space
            "ABCDEFGHIJK",  # length 11 (assuming 10 max)
            "; DROP TABLE users; --", "AAPL'); DROP TABLE x; --"
        ],
    )
    def test_invalid_symbol_returns_400(self, client, invalid):
        """
        Invalid ticker should return 400; keep validation minimal and consistent
        with later UI rules: allow [A-Z0-9.-], 1-10 chars, normalize case.
        """
        # Use URL encoding to ensure request reaches route and triggers 400
        encoded = quote(invalid, safe="")
        resp = client.put(f'/monitor/watchlist/{encoded}')
        # For pure empty string, path would be .../monitor/watchlist/, force a single space for route
        if invalid.strip() == "":
            resp = client.put('/monitor/watchlist/%20')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_length_thresholds_validation(self, client):
        """
        Data length requirement:
        - Just below/at threshold passes
        - Above threshold fails gracefully
        """
        # just at threshold (10) -> pass
        resp_ok = client.put('/monitor/watchlist/ABCDEFGHIJ')  # 10 chars ok
        assert resp_ok.status_code in (200, 201)

        # above threshold (11) -> fail
        resp_bad = client.put('/monitor/watchlist/ABCDEFGHIJK')  # 11 chars bad
        assert resp_bad.status_code == 400

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
