# backend-services/monitoring-service/market_leaders.py
"""
This module provides the business logic for fetching market leaders data.
"""
import os
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

#DEBUG
import logging
import json

from data_fetcher import (
    get_sector_industry_map,
    get_day_gainers_map,
    post_returns_batch,
    post_returns_1m_batch,
    get_52w_highs,
)

logger = logging.getLogger(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

# Centralize leader lookback period for easy tuning
LEADER_LOOKBACK_PERIOD = "3mo"  # Leaders are ranked by 3-month returns by default

class SectorIndustrySource:
    """Abstract source of industry -> candidate tickers mapping."""
    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        raise NotImplementedError

class IndustryRanker:
    """Ranks industries and selects top stocks by LEADER_LOOKBACK_PERIOD-month return."""
    def rank(self,
            industry_to_returns: Dict[str, List[Tuple[str, Optional[float]]]],
            top_industries: int = 5,
            top_stocks_per_industry: int = 3,
        ) -> List[Dict[str, Any]]:

        def _to_float(val) -> Optional[float]:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, (list, tuple)) and len(val) > 0:
                return _to_float(val[0])
            if isinstance(val, dict):
                for k in ("percent_change_3m", "percent_change_1m", "return_1m", "ret_1m", "one_month", "value"): 
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
                "stock_count": len(items),
                "stocks": [{"ticker": t, "percent_change_3m": r} for (t, r) in top]
            })
        return ranked

def _group_by_industry(quotes: List[dict]) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for q in quotes or []:
        ind = (q.get("industry") or "").strip()
        if not ind:
            # fallback to sector to avoid "Unclassified"
            ind = (q.get("sector") or "").strip()
        if not ind:
            ind = "Unclassified"
        buckets[ind].append(q)
    return buckets

def _top_industries_by_breadth(quotes: List[dict], k: int = 5) -> List[str]:
    """
    Select top k industries by breadth (quote count), breaking ties by 
    total marketCap of quotes in that industry, then by industry name.
    """
    stats = defaultdict(lambda: {"count": 0, "mcap": 0.0})
    
    for q in quotes:
        ind = (q.get("industry") or "").strip() or "Unclassified"
        stats[ind]["count"] += 1
        stats[ind]["mcap"] += q.get("marketCap") or 0.0
    
    # Primary: count desc, Secondary: mcap desc, Tertiary: name asc
    ranked = sorted(stats.items(), key=lambda x: (-x[1]["count"], -x[1]["mcap"], x[0]))
    return [ind for ind, _ in ranked[:k]]

def _select_symbols(buckets: Dict[str, List[dict]], inds: List[str], per_industry: int) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for ind in inds:
        rows = buckets.get(ind, [])
        rows.sort(key=lambda x: (x.get("marketCap") or 0), reverse=True)
        out[ind] = [r.get("symbol") for r in rows if r.get("symbol")][:per_industry]
    return out

def _leaders_from_52w(per_industry: int = 3) -> List[Dict[str, Any]]:
    quotes = get_52w_highs()
    if not isinstance(quotes, list) or not quotes:
        return []
    buckets = _group_by_industry(quotes)
    top_inds = _top_industries_by_breadth(quotes, k=5)
    syms_map = _select_symbols(buckets, top_inds, per_industry=per_industry)
    all_syms = [s for arr in syms_map.values() for s in arr]
    # Optional enrichment; if not supported, defaults to None per symbol
    returns = post_returns_batch(list(set(all_syms)), period=LEADER_LOOKBACK_PERIOD) or {}
    out: List[Dict[str, Any]] = []
    for ind in top_inds:
        stocks = [{"ticker": s, "percent_change_3m": returns.get(s)} for s in syms_map.get(ind, [])]
        # Sort by return descending, treating None as -inf
        stocks.sort(key=lambda x: x["percent_change_3m"] if x["percent_change_3m"] is not None else float('-inf'), reverse=True)
        # Populate stock_count from the full bucket, not just the displayed stocks
        full_count = len(buckets.get(ind, []))
        out.append({"industry": ind, "stock_count": full_count, "stocks": stocks})
    return out

class MarketLeadersService:
    """Orchestrates discovery, computation, and ranking by calling the data-service."""
    def __init__(self, ranker: IndustryRanker, max_workers: int = 12):
        self.ranker = ranker
        self.max_workers = max_workers

    def get_market_leaders(self) -> List[Dict[str, Any]]:
        leaders = _leaders_from_52w(per_industry=3)
        if leaders:
            return leaders
        return self.get_market_leaders_legacy()

    # Fallback path: use industry->symbols map and batch 1M returns + ranker
    def get_market_leaders_legacy(self) -> List[Dict[str, Any]]:
        # 1) Try primary sector/industry candidates
        industry_to_symbols = get_sector_industry_map()
        # 2) Fallback to day_gainers screener mapping
        if not industry_to_symbols:
            logger.info("Primary source failed, trying fallback day_gainers screener.")
            industry_to_symbols = get_day_gainers_map()
        if not industry_to_symbols:
            logger.error("All candidate sources failed. Cannot determine market leaders.")
            return []

        # 3) Single batch fetch of 1m returns
        all_symbols = list({sym for syms in industry_to_symbols.values() for sym in syms})
        # Guard empty candidates 
        if not industry_to_symbols:
            logger.error("All candidate sources failed. Cannot determine market leaders.")
            return []
        all_symbols = list({sym for syms in industry_to_symbols.values() for sym in syms})
        if not all_symbols:
            logger.warning("No symbols to fetch returns for; skipping return fetch.")
            return []
        symbol_returns = post_returns_batch(all_symbols, period=LEADER_LOOKBACK_PERIOD)

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

def get_market_leaders() -> Dict[str, Any]:
    """
    Returns MarketLeaders contract object:
    { "leading_industries": [ { "industry": str, "stocks": [{ "ticker": str, "percent_change_3m": float|null }] } ] }
    """
    service = MarketLeadersService(IndustryRanker())
    leading_industries = service.get_market_leaders()
    
    # Ensure we always return the correct dict structure
    if isinstance(leading_industries, dict):
        # If it's already a dict with the wrapper, return as-is
        if "leading_industries" in leading_industries:
            return leading_industries
        # If it's an error dict, wrap it properly
        return {"leading_industries": []}
    elif isinstance(leading_industries, list):
        # If it's a list, wrap it in the expected structure
        return {"leading_industries": leading_industries}
    else:
        # Fallback for unexpected types
        return {"leading_industries": []}

