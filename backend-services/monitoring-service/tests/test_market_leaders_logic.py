# backend-services/monitoring-service/tests/test_market_leaders_logic.py

import market_health_utils as mhu
from market_leaders import IndustryRanker, MarketLeadersService, _industry_counts_from_quotes, get_market_leaders
from unittest.mock import patch, MagicMock

def test_industry_ranker_rank_sort_and_selection():
    ranker = IndustryRanker()
    industry_to_returns = {
        "A": [("A1", 0.10), ("A2", 0.30), ("A3", None)],   # avg 0.20
        "B": [("B1", 0.05), ("B2", 0.10)],                 # avg 0.075
        "C": [("C1", None), ("C2", None)],                 # ignored (no valid returns)
    }
    ranked = ranker.rank(industry_to_returns, top_industries=2, top_stocks_per_industry=2)

    # Expect A first, then B; each with up to 2 stocks ordered by perf desc
    assert [b["industry"] for b in ranked] == ["A", "B"]
    assert [s["ticker"] for s in ranked[0]["stocks"]] == ["A2", "A1"]
    assert len(ranked[0]["stocks"]) == 2
    assert [s["ticker"] for s in ranked[1]["stocks"]] == ["B2", "B1"]


@patch("market_leaders.get_52w_highs")            
@patch("market_leaders.post_returns_batch")   
@patch("market_leaders.get_sector_industry_map")
def test_market_leaders_primary_success(mock_sector_map, mock_returns, mock_52w):
    mock_52w.return_value = [] 
    mock_sector_map.return_value = {"Tech": ["AAPL", "MSFT", "NVDA"], "Retail": ["AMZN", "COST"]}
    mock_returns.return_value = {"AAPL": 0.10, "MSFT": 0.05, "NVDA": None, "AMZN": 0.07, "COST": 0.02}
    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()

    # Should be a non-empty list of industry blocks
    assert isinstance(leaders, list)
    # Each block contains industry and up to 3 stocks ordered by perf
    tech = next(b for b in leaders if b["industry"] == "Tech")
    assert [s["ticker"] for s in tech["stocks"]] == ["AAPL", "MSFT"]  # NVDA None excluded
    retail = next(b for b in leaders if b["industry"] == "Retail")
    assert [s["ticker"] for s in retail["stocks"]] == ["AMZN", "COST"]

@patch("market_leaders.get_52w_highs") 
@patch("market_leaders.post_returns_batch")
@patch("market_leaders.get_day_gainers_map")
@patch("market_leaders.get_sector_industry_map")
def test_market_leaders_fallback_when_primary_fails(mock_sector_map, mock_day_gainers, mock_returns, mock_52w):
    mock_52w.return_value = [] 
    mock_sector_map.return_value = {}
    mock_day_gainers.return_value = {"Fallback": ["X", "Y"]}
    mock_returns.return_value = {"X": 0.12, "Y": 0.05}
    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()

    assert [b["industry"] for b in leaders] == ["Fallback"]
    assert [s["ticker"] for s in leaders[0]["stocks"]] == ["X", "Y"]

@patch("market_leaders.get_52w_highs", return_value=[])
@patch("market_leaders.post_returns_batch", return_value={})
@patch("market_leaders.get_day_gainers_map", return_value={})
@patch("market_leaders.get_sector_industry_map", return_value={})
def test_market_leaders_all_sources_fail_returns_empty_dict(
    mock_sector_map, mock_day_gainers, mock_returns, mock_52w
):
    mock_sector_map.return_value = {}
    mock_day_gainers.return_value = {}
    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()
    assert leaders == []  # service returns [] on total failure

# --- Unit-test 52-week Highs Screener Logic ---

def test_industry_counts_from_quotes():
    """
    Tests the core logic of clustering 52-week highs by industry.
    Verifies:
    - Correct counting of tickers per industry.
    - Handling of empty/None industry strings as "Unclassified".
    - Selection of the top 5 industries by count.
    - Correct handling of ties in counts.
    """
    mock_quotes = [
        {"industry": "Tech"}, {"industry": "Tech"}, {"industry": "Tech"}, # Tech: 3
        {"industry": "Retail"}, {"industry": "Retail"},                 # Retail: 2
        {"industry": "Finance"}, {"industry": "Finance"},               # Finance: 2 (tie with Retail)
        {"industry": "Health"},                                         # Health: 1
        {"industry": "Energy"},                                         # Energy: 1
        {"industry": "Industrial"},                                     # Industrial: 1
        {"industry": ""},          # Unclassified: 1
        {"industry": None},        # Unclassified: 1
        {"industry": "  "},        # Unclassified: 1 (whitespace)
    ]

    result = _industry_counts_from_quotes(mock_quotes)

    # Should return a list of top 5 industries
    assert len(result) == 5

    # Extract industries and counts for easier assertion
    result_industries = [item['industry'] for item in result]
    result_map = {item['industry']: item['breadth_count'] for item in result}

    # Check counts
    assert result_map["Tech"] == 3
    assert result_map["Unclassified"] == 3
    assert result_map["Retail"] == 2
    assert result_map["Finance"] == 2

    # Check top 5 selection (Tech and Unclassified are guaranteed)
    assert "Tech" in result_industries
    assert "Unclassified" in result_industries
    
    # We must have Retail AND Finance
    assert "Retail" in result_industries
    assert "Finance" in result_industries
    
    # The 5th spot can be Health, Energy, or Industrial. Just check one of them is present.
    assert any(ind in result_industries for ind in ["Health", "Energy", "Industrial"])

def test_industry_counts_from_quotes_empty_input():
    """Tests that an empty or None input results in an empty list."""
    assert _industry_counts_from_quotes([]) == []
    assert _industry_counts_from_quotes(None) == []

def test_industry_ranker_handles_mixed_return_shapes():
    """
    Ranker tuple-shape safety: Feed industry_to_returns with mixed shapes:
    numbers, (num,), {"percent_change_3m": x}, and None; assert ranker.rank
    does not raise, computes averages correctly, filters None, and orders
    top_stocks_per_industry by numeric value, preventing the tuple TypeError regression.
    """
    ranker = IndustryRanker()
    industry_to_returns = {
        "Tech": [
            ("T1", 0.10),                          # Shape: float
            ("T2", (0.15,)),                       # Shape: (float,)
            ("T3", {"percent_change_3m": 0.20}),   # Shape: dict
            ("T4", None)                           # Shape: None (should be ignored)
        ],                                         # Avg: (0.10 + 0.15 + 0.20) / 3 = 0.15
        "Retail": [
            ("R1", 0.05)
        ],                                         # Avg: 0.05
        "Health": [
            ("H1", None),                          # Should be ignored entirely
            ("H2", "invalid_string")
        ]
    }

    # This call should not raise a TypeError
    ranked = ranker.rank(industry_to_returns, top_industries=5, top_stocks_per_industry=5)

    # 1. Assert correct industry ranking and filtering
    assert len(ranked) == 2  # Health industry should be excluded
    assert [b["industry"] for b in ranked] == ["Tech", "Retail"]

    # 2. Assert correct stock ranking within "Tech" industry
    tech_stocks = ranked[0]["stocks"]
    assert len(tech_stocks) == 3 # T4 with None return should be excluded
    
    # Assert logical outcome (order) and key identifying data (tickers and values)
    assert tech_stocks[0]["ticker"] == "T3"
    assert tech_stocks[0]["percent_change_3m"] == 0.20

    assert tech_stocks[1]["ticker"] == "T2"
    assert tech_stocks[1]["percent_change_3m"] == 0.15
    
    assert tech_stocks[2]["ticker"] == "T1"
    assert tech_stocks[2]["percent_change_3m"] == 0.10

    # 3. Assert correct data for "Retail" industry
    retail_stocks = ranked[1]["stocks"]
    assert len(retail_stocks) == 1
    assert retail_stocks[0]["ticker"] == "R1"
    assert retail_stocks[0]["percent_change_3m"] == 0.05