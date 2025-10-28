# backend-services/monitoring-service/market_leaders.py
"""
This module provides the business logic for fetching market leaders data.
"""
import os
import logging
from typing import Dict, List, Any, Optional, Tuple

#DEBUG
import logging
import json

logger = logging.getLogger(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

from data_fetcher import (
    get_sector_industry_map,
    get_day_gainers_map,
    post_returns_1m_batch,
    get_52w_highs,
)

class SectorIndustrySource:
    """Abstract source of industry -> candidate tickers mapping."""
    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        raise NotImplementedError

class IndustryRanker:
    """Ranks industries and selects top stocks by 1-month return."""
    def rank(self,
            industry_to_returns: Dict[str, List[Tuple[str, Optional[float]]]],
            top_industries: int = 5,
            top_stocks_per_industry: int = 3) -> List[Dict[str, Any]]:

        def _to_float(val) -> Optional[float]:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, (list, tuple)) and len(val) > 0:
                return _to_float(val[0])
            if isinstance(val, dict):
                for k in ("percent_change_1m", "return_1m", "ret_1m", "one_month", "value"):
                    if k in val:
                        return _to_float(val[k])
            return None

        industry_scores: List[Tuple[str, float]] = []
        for ind, items in industry_to_returns.items():
            # items is List[Tuple[ticker, return_like]]
            vals = [_to_float(r) for (_, r) in items]
            vals = [v for v in vals if isinstance(v, (int, float))]
            if not vals:
                continue
            avg_return = sum(vals) / len(vals)
            industry_scores.append((ind, avg_return))

        industry_scores.sort(key=lambda x: x[1], reverse=True)
        ranked: List[Dict[str, Any]] = []
        for ind, _ in industry_scores[:top_industries]:
            items = industry_to_returns.get(ind, [])
            entries = [(t, _to_float(r)) for (t, r) in items]
            entries = [(t, r) for (t, r) in entries if isinstance(r, (int, float))]
            entries.sort(key=lambda tr: tr[1], reverse=True)
            top = entries[:top_stocks_per_industry]
            ranked.append({
                "industry": ind,
                "stocks": [{"ticker": t, "percent_change_1m": r} for (t, r) in top]
            })
        return ranked


class MarketLeadersService:
    """Orchestrates discovery, computation, and ranking by calling the data-service."""
    def __init__(self, ranker: IndustryRanker, max_workers: int = 12):
        self.ranker = ranker
        self.max_workers = max_workers

    def get_market_leaders(self) -> Dict:
        # 1) Try primary sector/industry candidates
        industry_to_symbols = get_sector_industry_map()
        # 2) Fallback to day_gainers screener mapping
        if not industry_to_symbols:
            logger.info("Primary source failed, trying fallback day_gainers screener.")
            industry_to_symbols = get_day_gainers_map()
        if not industry_to_symbols:
            logger.error("All candidate sources failed. Cannot determine market leaders.")
            return {}

        # 3) Single batch fetch of 1m returns
        all_symbols = list({sym for syms in industry_to_symbols.values() for sym in syms})
        # Guard empty candidates 
        if not industry_to_symbols:
            logger.error("All candidate sources failed. Cannot determine market leaders.")
            return {}
        all_symbols = list({sym for syms in industry_to_symbols.values() for sym in syms})
        if not all_symbols:
            logger.warning("No symbols to fetch returns for; skipping return fetch.")
            return {}
        symbol_returns = post_returns_1m_batch(all_symbols)

        # 4) Map and rank
        industry_to_returns: Dict[str, List[Tuple[str, Optional[float]]]] = {k: [] for k in industry_to_symbols}
        for ind, syms in industry_to_symbols.items():
            for sym in syms:
                industry_to_returns[ind].append((sym, symbol_returns.get(sym)))
        return self.ranker.rank(industry_to_returns, top_industries=5, top_stocks_per_industry=3)

def _industry_counts_from_quotes(quotes: List[dict]) -> List[Dict[str, Any]]:
    """
    Collapses quotes into industry counts and returns top 5 industries by breadth.
    """
    from collections import Counter, defaultdict
    # Normalize industry
    def norm_ind(q):
        ind = (q.get("industry") or "").strip()
        return ind if ind else "Unclassified"

    counts = Counter(norm_ind(q) for q in (quotes or []))
    top_inds = [ind for ind, _ in counts.most_common(5)]

    return [{"industry": ind, "breadth_count": counts[ind]} for ind in top_inds]

class MarketLeadersService52w(MarketLeadersService):
    """
    Leaders strategy using 52-week highs clustering.
    """
    # Ensure base is initialized; ranker unused here but harmless
    def __init__(self):
        super().__init__(ranker=IndustryRanker())

    def get_industry_leaders_by_new_highs(self) -> List[Dict[str, Any]]:
        quotes = get_52w_highs()
        if not isinstance(quotes, list):
            logger.warning("52w highs screener returned no data or wrong shape.")
            return []
        return _industry_counts_from_quotes(quotes)

def get_market_leaders() -> List[Dict[str, Any]]:
    """
    Now defaults to 52-week highs breadth leaders for early bull market clustering.
    """
    svc = MarketLeadersService52w()
    leaders = svc.get_industry_leaders_by_new_highs()
    if leaders:
        return leaders
    # Fallback to previous 1-month return ranking if screener fails
    ranker = IndustryRanker()
    svc_legacy = MarketLeadersService(ranker)
    return svc_legacy.get_market_leaders()
