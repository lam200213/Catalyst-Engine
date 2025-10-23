# backend-services/data-service/providers/yfin/market_data_provider.py
"""
This module provides the business logic for fetching market-wide data
like sector/industry candidates, screeners, and specific metrics like returns.
"""

import yfinance as yf
import datetime as dt
import pandas as pd
import time
import random
from typing import Dict, List, Tuple, Optional
from curl_cffi import requests as cffi_requests
from typing import List, Dict, Any
from collections import defaultdict
import os
import re
from typing import Iterable

from . import yahoo_client, price_provider # Use relative import

#DEBUG
import logging
import json

logger = logging.getLogger(__name__)

# canonical sector keys from yfinance docs
SECTOR_KEYS = [
    "basic-materials","communication-services","consumer-cyclical","consumer-defensive",
    "energy","financial-services","healthcare","industrials","real-estate","technology","utilities",
]

# helpers
_US_BLOCK_SUFFIX = {".TO",".V",".CN",".L",".F",".SW",".PA",".DE",".MI",".AS",".AX",".HK",".SI",".KS",".KQ",".NZ",".MC",".OL",".ST",".IR"}
_DEFAULT_REGION = (os.getenv("YF_REGION_DEFAULT") or "US").upper()

def _is_us_symbol(sym: str) -> bool:
    # US listings on Yahoo typically lack a dot suffix (e.g., BRK-B not BRK.B)
    return bool(sym) and "." not in sym and not sym.endswith("-USD")

class SectorIndustrySource:
    """Abstract source of industry -> candidate tickers mapping."""
    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        raise NotImplementedError


class YahooSectorIndustrySource(SectorIndustrySource):
    """Primary source using yfinance Sector/Industry APIs."""
    def __init__(self, sector_keys: Optional[List[str]] = None):
        self._sector_keys = sector_keys
        # Prefer discovering sectors dynamically; allow override via config
        # soft limits to avoid long blocking calls
        self._max_sectors: int = int(os.getenv("YF_MAX_SECTORS", "11"))
        self._max_industries_per_sector: int = int(os.getenv("YF_MAX_INDUSTRIES_PER_SECTOR", "10"))
        self._max_seconds: int = int(os.getenv("YF_MAX_SECONDS", "180"))

    def _discover_sector_keys(self) -> List[str]:
        # If explicit keys provided, use them
        
        if self._sector_keys:
            return self._sector_keys

        # Fallback list is intentionally minimal; can be configured externally
        # Attempt to probe a small known set to avoid hardcoding all values
        # preserve ordering but enforce a soft cap
        return SECTOR_KEYS[: self._max_sectors]

    # helper to parse symbols from a DataFrame row 'name' like "Company (TICK)"
    def _parse_symbol_from_name(self, name: str) -> Optional[str]:
        if not name or not isinstance(name, str):
            return None
        m = re.search(r"\(([A-Za-z.\-]{1,6})\)", name)
        if m:
            return m.group(1)
        # Fallback: if the name itself looks like a ticker
        if re.fullmatch(r"[A-Za-z.\-]{1,6}", name):
            return name
        return None

    # Yahoo search fallback for a company name -> symbol
    def _search_symbol_for_name(self, name: str) -> Optional[str]:
        try:
            url = "https://query2.finance.yahoo.com/v1/finance/search"
            params = {"q": name, "lang": "en-US", "region": "US", "quotesCount": 1}
            data = yahoo_client.execute_request(url, params=params)
            quotes = (data or {}).get("quotes") or []
            for q in quotes:
                sym = q.get("symbol")
                qt = (q.get("quoteType") or "").upper()
                if sym and qt in ("EQUITY", "ETF", "MUTUALFUND"):
                    return sym
        except Exception:
            pass
        return None

    # normalize symbols from the top_performing_companies table
    def _resolve_symbols_from_top_df(self, top_df: pd.DataFrame, limit: int) -> List[str]:
        syms: List[str] = []
        if not isinstance(top_df, pd.DataFrame) or top_df.empty:
            return syms

        # 1) Direct column
        if "symbol" in top_df.columns:
            syms = top_df["symbol"].dropna().astype(str).tolist()

        # 2) Index labeled as symbol/ticker
        if not syms:
            idx_name = getattr(top_df.index, "name", None)
            if idx_name in ("symbol", "ticker", "Symbol", "Ticker"):
                syms = top_df.index.dropna().astype(str).tolist()

        # 3) Parse from 'name' column patterns like "NVIDIA (NVDA)"
        if not syms and "name" in top_df.columns:
            for name in top_df["name"].dropna().astype(str).tolist():
                sym = self._parse_symbol_from_name(name)
                if sym:
                    syms.append(sym)
                if len(syms) >= limit:
                    break

        # 4) Yahoo search fallback for remaining rows if still short
        if len(syms) < limit and "name" in top_df.columns:
            for name in top_df["name"].dropna().astype(str).tolist():
                if len(syms) >= limit:
                    break
                # Skip if already parsed this symbol pattern
                maybe = self._parse_symbol_from_name(name)
                if maybe and maybe in syms:
                    continue
                sym = self._search_symbol_for_name(name)
                if sym:
                    syms.append(sym)

        # Final gate: enforce ticker-like format and limit
        out = []
        for s in syms:
            if re.fullmatch(r"[A-Za-z.\-]{1,6}", s):
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def get_industry_top_tickers(self, per_industry_limit: int = 10, region: str = "US") -> Dict[str, List[str]]:
        
        out: Dict[str, List[str]] = {}
        started = time.time()

        for s in self._discover_sector_keys():
            # respect global time budget
            if time.time() - started > self._max_seconds:
                break
            
            try:
                session = yahoo_client.get_yf_session()
                sec = yf.Sector(s, session=session)  
                inds_df = getattr(sec, "industries", None)  # DataFrame of industries
                if inds_df is None or getattr(inds_df, "empty", True):
                    continue
                
                # handle index-labeled "key"
                ind_keys = (
                    inds_df["key"].dropna().astype(str).tolist()
                    if "key" in getattr(inds_df, "columns", [])
                    else inds_df.index.dropna().astype(str).tolist()
                )
                for ind_key in ind_keys[: self._max_industries_per_sector]:
                    if time.time() - started > self._max_seconds:
                        break
                    try:
                        session = yahoo_client.get_yf_session()
                        ind = yf.Industry(ind_key, session=session)
                        # combine performing and growth candidates
                        perf_df = getattr(ind, "top_performing_companies", None)
                        growth_df = getattr(ind, "top_growth_companies", None)
                        candidates: List[str] = []
                        candidates += self._resolve_symbols_from_top_df(perf_df, per_industry_limit * 2) if perf_df is not None else []
                        candidates += self._resolve_symbols_from_top_df(growth_df, per_industry_limit * 2) if growth_df is not None else []
                        # de-duplicate while preserving order
                        seen = set()
                        cleaned = []
                        for c in candidates:
                            if c not in seen:
                                seen.add(c)
                                cleaned.append(c)
                        if cleaned:
                            if region.upper() == "US":
                                cleaned = [c for c in cleaned if _is_us_symbol(c)]
                            out[ind_key] = cleaned[:per_industry_limit]
                    except Exception:
                        continue
            except Exception:
                continue
        return out


class DayGainersSource(SectorIndustrySource):
    """Fallback source using yfinance screener day_gainers."""
    def __init__(self):
        pass 

    def get_industry_top_tickers(self, per_industry_limit: int = 10, region: str = "US") -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        try:
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            params = {
                "scrIds": "day_gainers",
                "count": 200,
                "lang": "en-US",
                "region": region.upper()
            }
            data = yahoo_client.execute_request(url, params=params)
            
            # The structure is nested under finance -> result -> [0]
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            
            for q in quotes:
                sym = q.get("symbol")
                # tolerate missing industry
                if not sym:
                    continue
                if region.upper() == "US" and not _is_us_symbol(sym):  # enforce US by default
                    continue
                ind = q.get("industry") or "Unclassified"
                bucket = out.setdefault(ind, [])
                if len(bucket) < per_industry_limit:
                    bucket.append(sym)
        except Exception as e:
            logger.debug(f"day_gainers screener failed: {e}")
        return out


class ReturnCalculator:
    """Computes 1-month percent change for a ticker."""
    def __init__(self, executor=None):
        self.executor = executor

    def one_month_change(self, symbol: str) -> Optional[float]:
        try:
            data = price_provider.get_stock_data(
                symbol,
                executor=self.executor,  # may be None; provider will handle
                period="1mo"
            )
            if not data or not isinstance(data, list):
                return None
            # exclude today's partial; use last bar with date < today
            today_str = dt.date.today().strftime("%Y-%m-%d")
            series = [row for row in data if row.get("formatted_date") and row["formatted_date"] < today_str]
            if len(series) < 2:
                return None
            start = float(series[0]["close"])
            end = float(series[-1]["close"])
            pct = round((end - start) / start * 100.0, 2)
            return pct
        except Exception as e:
            logger.debug(f"1mo change via price_provider failed for {symbol}: {e}")
            return None