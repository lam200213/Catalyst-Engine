# backend-services/monitoring-service/market_leaders.py
"""
This module provides the business logic for fetching market leaders data.
"""
import os
import requests
import logging
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

#DEBUG
import logging
import json

logger = logging.getLogger(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

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

    def _fetch_candidates_from_source(self, url: str) -> Optional[Dict[str, List[str]]]:
        """Fetches candidate tickers from a data-service endpoint."""
        try:
            resp = requests.get(url, timeout=180)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Candidate source at {url} returned status {resp.status_code}")
            return None
        except requests.RequestException as e:
            logger.error(f"Failed to fetch candidates from {url}: {e}")
            return None

    def _fetch_one_month_changes_batch(self, symbols: List[str]) -> Dict[str, Optional[float]]:
            """Fetches 1-month returns for a list of symbols from the data-service's batch endpoint."""
            try:
                url = f"{DATA_SERVICE_URL}/data/return/1m/batch"
                resp = requests.post(url, json={"tickers": symbols}, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                return {s: None for s in symbols} # Return None for all on failure
            except requests.RequestException as e:
                logger.error(f"Batch return fetch failed: {e}")
                return {s: None for s in symbols}

    def get_market_leaders(self) -> Dict:
        # 1. Fetch candidate tickers from primary source
        primary_url = f"{DATA_SERVICE_URL}/market/sectors/industries"
        industry_to_symbols = self._fetch_candidates_from_source(primary_url)

        # 2. If primary fails, try fallback source
        if not industry_to_symbols:
            logger.info("Primary source failed, trying fallback day_gainers screener.")
            fallback_url = f"{DATA_SERVICE_URL}/market/screener/day_gainers"
            industry_to_symbols = self._fetch_candidates_from_source(fallback_url)

        if not industry_to_symbols:
            logger.error("All candidate sources failed. Cannot determine market leaders.")
            return {}

        # 3. Fetch 1-month returns for all candidates in ONE batch call
        all_symbols = list(set(sym for syms in industry_to_symbols.values() for sym in syms))
        
        # Make a single, efficient batch request.
        symbol_returns = self._fetch_one_month_changes_batch(all_symbols)

        industry_to_returns: Dict[str, List[Tuple[str, Optional[float]]]] = {k: [] for k in industry_to_symbols}
        for ind, syms in industry_to_symbols.items():
            for sym in syms:
                # Map the results from the batch call back to the industry structure
                industry_to_returns[ind].append((sym, symbol_returns.get(sym)))

        # 4. Rank the results
        return self.ranker.rank(industry_to_returns, top_industries=5, top_stocks_per_industry=3)

# def get_market_leaders() -> List[Dict[str, Any]]:
#     """Facade used by Flask route; orchestrates the process."""
#     ranker = IndustryRanker()
#     svc = MarketLeadersService(ranker)
#     return svc.get_market_leaders()

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
        url = f"{DATA_SERVICE_URL}/market/screener/52w_highs"
        quotes = self._fetch_candidates_from_source(url)  # reuse existing fetch method signature
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
