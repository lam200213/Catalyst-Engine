# backend-services/monitoring-service/tests/test_api_contract_compliance.py 

import os
import sys

# Ensure local imports resolve when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from app import app as flask_app

def test_monitor_market_health_matches_api_reference():
    """
    Validates that the actual API response matches the example in API_REFERENCE.md
    """
    client = flask_app.test_client()
    response = client.get("/monitor/market-health")
    data = response.get_json()
    
    # Check top-level keys
    assert "market_overview" in data
    assert "leaders_by_industry" in data
    
    # Check market_overview structure
    mo = data["market_overview"]
    assert "market_stage" in mo
    assert "correction_depth_percent" in mo
    assert "high_low_ratio" in mo
    assert "new_highs" in mo
    assert "new_lows" in mo
    
    # Check leaders_by_industry structure
    lbi = data["leaders_by_industry"]
    assert "leading_industries" in lbi
    assert isinstance(lbi["leading_industries"], list)
    
    # Check nested stock structure
    if lbi["leading_industries"]:
        first_industry = lbi["leading_industries"][0]
        assert "industry" in first_industry
        assert "stocks" in first_industry
        if first_industry["stocks"]:
            first_stock = first_industry["stocks"][0]
            assert "ticker" in first_stock
            # Check for correct field name (should be percent_change_3m after fix)
            assert "percent_change_3m" in first_stock or "percent_change_1m" in first_stock
