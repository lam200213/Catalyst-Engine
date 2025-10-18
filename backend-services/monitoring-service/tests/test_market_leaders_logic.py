# backend-services/monitoring-service/tests/test_market_leaders_logic.py

import market_health_utils as mhu
from market_leaders import IndustryRanker, MarketLeadersService
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


@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
def test_market_leaders_primary_success(mock_get, mock_post):
    # Primary candidate source succeeds
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {
        "Tech": ["AAPL", "MSFT", "NVDA"],
        "Retail": ["AMZN", "COST"]
    })
    # Batch returns include some None which should be filtered out from per-stock listing
    returns_map = {"AAPL": 0.10, "MSFT": 0.05, "NVDA": None, "AMZN": 0.07, "COST": 0.02}
    mock_post.return_value = MagicMock(status_code=200, json=lambda: returns_map)

    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()

    # Should be a non-empty list of industry blocks
    assert isinstance(leaders, list)
    # Each block contains industry and up to 3 stocks ordered by perf
    tech = next(b for b in leaders if b["industry"] == "Tech")
    assert [s["ticker"] for s in tech["stocks"]] == ["AAPL", "MSFT"]  # NVDA None excluded
    retail = next(b for b in leaders if b["industry"] == "Retail")
    assert [s["ticker"] for s in retail["stocks"]] == ["AMZN", "COST"]


@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
def test_market_leaders_fallback_when_primary_fails(mock_get, mock_post):
    # Primary fails -> fallback day_gainers used
    # First GET (primary) fails
    mock_get.side_effect = [
        MagicMock(status_code=500, json=lambda: None),
        MagicMock(status_code=200, json=lambda: {"Fallback": ["X", "Y"]}),
    ]
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"X": 0.12, "Y": 0.08})

    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()
    assert [b["industry"] for b in leaders] == ["Fallback"]
    assert [s["ticker"] for s in leaders[0]["stocks"]] == ["X", "Y"]


@patch("market_leaders.requests.post")
@patch("market_leaders.requests.get")
def test_market_leaders_all_sources_fail_returns_empty_dict(mock_get, mock_post):
    # Both primary and fallback fail -> service returns {}
    mock_get.side_effect = [
        MagicMock(status_code=500, json=lambda: None),
        MagicMock(status_code=404, json=lambda: None),
    ]
    mock_post.return_value = MagicMock(status_code=500, json=lambda: {})

    service = MarketLeadersService(IndustryRanker())
    leaders = service.get_market_leaders()
    # Function returns {} on complete failure per implementation
    assert leaders == {}
