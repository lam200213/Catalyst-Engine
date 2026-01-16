# backend-services/data-service/tests/test_fixtures.py
# Centralized payload builders for provider tests.

from typing import Any, Dict, Optional


def make_quote_summary_payload(
    *,
    market_cap: Optional[float] = 2e12,
    shares_outstanding: Optional[float] = None,
    annual_block: Any = None,
    quarterly_block: Any = None,
    ipo_fmt: Optional[str] = "2020-01-01",
) -> Dict[str, Any]:
    """
    Minimal Yahoo quoteSummary payload.
    - annual_block / quarterly_block can be None to reproduce Task 9.1 edge cases.
    """
    return {
        "quoteSummary": {
            "result": [
                {
                    "summaryDetail": {
                        "marketCap": {"raw": market_cap} if market_cap is not None else None
                    },
                    "defaultKeyStatistics": {
                        "sharesOutstanding": {"raw": shares_outstanding}
                        if shares_outstanding is not None
                        else None,
                        "ipoDate": {"fmt": ipo_fmt} if ipo_fmt is not None else None,
                        "floatShares": {"raw": None},
                    },
                    "incomeStatementHistory": annual_block,
                    "incomeStatementHistoryQuarterly": quarterly_block,
                }
            ]
        }
    }


def make_chart_payload(*, include_timestamp: bool = True) -> Dict[str, Any]:
    """
    Minimal Yahoo chart payload.
    - include_timestamp=False reproduces Task 9.2 edge case.
    """
    result: Dict[str, Any] = {
        "indicators": {
            "quote": [
                {
                    "open": [100, 102],
                    "high": [105, 106],
                    "low": [99, 101],
                    "close": [102, 105],
                    "volume": [10000, 12000],
                }
            ],
            "adjclose": [{"adjclose": [101, 104]}],
        }
    }

    if include_timestamp:
        result["timestamp"] = [1672531200, 1672617600]

    return {"chart": {"result": [result]}}
