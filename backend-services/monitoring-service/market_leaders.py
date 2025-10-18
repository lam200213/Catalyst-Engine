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

        ranked_industries: List[Dict[str, Any]] = []
        industry_scores = []

        # Compute average returns per industry
        for industry, stock_returns in industry_to_returns.items():
            valid_returns = [r for _, r in stock_returns if r is not None]
            if not valid_returns:
                continue
            avg_return = sum(valid_returns) / len(valid_returns)
            industry_scores.append((industry, avg_return, stock_returns))

        # Sort industries by their average performance
        industry_scores.sort(key=lambda x: x[1], reverse=True)

        # Build the final structure
        for industry, _, stock_returns in industry_scores[:top_industries]:
            # Sort stocks within this industry by performance
            sorted_stocks = sorted([s for s in stock_returns if s[1] is not None], key=lambda x: x[1], reverse=True)

            industry_payload = {
                "industry": industry,
                "stocks": [
                    {"ticker": ticker, "percent_change_1m": perf}
                    for ticker, perf in sorted_stocks[:top_stocks_per_industry]
                ]
            }
            if industry_payload["stocks"]: # Only add if there are stocks
                ranked_industries.append(industry_payload)

        return ranked_industries


class MarketLeadersService:
    """Orchestrates discovery, computation, and ranking by calling the data-service."""
    def __init__(self, ranker: IndustryRanker, max_workers: int = 12):
        self.ranker = ranker
        self.max_workers = max_workers

    def _fetch_candidates_from_source(self, url: str) -> Optional[Dict[str, List[str]]]:
        """Fetches candidate tickers from a data-service endpoint."""
        try:
            resp = requests.get(url, timeout=45)
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

def get_market_leaders() -> List[Dict[str, Any]]:
    """Facade used by Flask route; orchestrates the process."""
    ranker = IndustryRanker()
    svc = MarketLeadersService(ranker)
    return svc.get_market_leaders()