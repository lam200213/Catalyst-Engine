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
from typing import List, Dict, Any
import os
import re

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
        self.region = _DEFAULT_REGION.upper()
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
            params = {"q": name, "lang": "en-US", "region": self.region, "quotesCount": 1}
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

    def get_industry_top_tickers(self, per_industry_limit: int = 10, region: Optional[str] = None) -> Dict[str, List[str]]:
        
        effective_region = (region or self.region).upper()
        out: Dict[str, List[str]] = {}
        started = time.time()
        for s in self._discover_sector_keys():
            if time.time() - started > self._max_seconds:
                break
            try:
                session = yahoo_client.get_yf_session()
                sec = yf.Sector(s, session=session)
                inds_df = getattr(sec, "industries", None)
                if inds_df is None:
                    continue

                # Derive industry keys from column 'key' when available, else from index
                if hasattr(inds_df, "columns") and "key" in getattr(inds_df, "columns", []):
                    ind_keys = inds_df["key"].dropna().astype(str).tolist()
                else:
                    idx = getattr(inds_df, "index", None)
                    ind_keys = idx.dropna().astype(str).tolist() if idx is not None else []

                if not ind_keys:
                    continue

                for ind_key in ind_keys[: self._max_industries_per_sector]:
                    if time.time() - started > self._max_seconds:
                        break
                    try:
                        session = yahoo_client.get_yf_session()
                        ind = yf.Industry(ind_key, session=session)

                        perf_df = getattr(ind, "top_performing_companies", None)
                        growth_df = getattr(ind, "top_growth_companies", None)

                        candidates: List[str] = []
                        candidates += self._resolve_symbols_from_top_df(perf_df, per_industry_limit * 2) if perf_df is not None else []
                        candidates += self._resolve_symbols_from_top_df(growth_df, per_industry_limit * 2) if growth_df is not None else []

                        seen = set()
                        cleaned = []
                        for c in candidates:
                            if c not in seen:
                                seen.add(c)
                                cleaned.append(c)

                        if cleaned:
                            if effective_region.upper() == "US":
                                cleaned = [c for c in cleaned if _is_us_symbol(c)]
                            out[ind_key] = cleaned[:per_industry_limit]

                    except Exception as e:
                        logger.warning(f"Failed to process industry '{ind_key}' for sector '{s}': {e}", exc_info=True)
                        continue

            except Exception as e:
                logger.warning(f"Failed to process sector '{s}': {e}", exc_info=True)
                continue
        return out


class DayGainersSource(SectorIndustrySource):
    """Fallback source using yfinance screener day_gainers."""
    def __init__(self):
        self.region = _DEFAULT_REGION.upper()

    def get_industry_top_tickers(self, per_industry_limit: int = 10, region: Optional[str] = None) -> Dict[str, List[str]]:
        effective_region = (region or self.region).upper()
        out: Dict[str, List[str]] = {}
        try:
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            params = {
                "scrIds": "day_gainers",
                "count": 200,
                "lang": "en-US",
                "region": effective_region.upper()
            }
            data = yahoo_client.execute_request(url, params=params)
            
            # The structure is nested under finance -> result -> [0]
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            
            for q in quotes:
                sym = q.get("symbol")
                # tolerate missing industry
                if not sym:
                    continue
                if effective_region == "US" and not _is_us_symbol(sym):  # enforce US by default
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
            # Path A - list-of-dicts shape
            if isinstance(data, list):
                today_str = dt.date.today().strftime("%Y-%m-%d")
                series = [
                    row for row in data
                    if row.get("formatted_date") and row.get("close") is not None
                    and row["formatted_date"] < today_str
                ]
                if len(series) < 2:
                    return None
                series.sort(key=lambda r: r["formatted_date"])
                start = float(series[0]["close"])
                end = float(series[-1]["close"])
                if start == 0:
                    return None
                return round((end - start) / start * 100.0, 2)

            # Path B - legacy Ticker-like with .history()
            if hasattr(data, "history"):
                df = data.history(period="1mo")
                if not isinstance(df, pd.DataFrame) or "Close" not in df.columns:
                    return None
                closes = [float(x) for x in df["Close"].dropna().tolist()]
                if len(closes) < 2:
                    return None
                start = closes[0]
                end = closes[-1]
                if start == 0:
                    return None
                return round((end - start) / start * 100.0, 2)

            # Unknown shape
            return None

        except Exception as e:
            logger.debug(f"1mo change via price_provider failed for {symbol}: {e}")
            return None

        
# --- 52-week highs / lows screener and market breadth helpers ---

class NewHighsScreenerSource(SectorIndustrySource):
    """
    Fetches the full list of current 52-week highs from Yahoo predefined screener.
    Mirrors DayGainersSource shape but uses scrIds='new_52_week_high'.
    """
    def __init__(self, region: Optional[str] = None):
        self.region = (region or _DEFAULT_REGION).upper()
        self.page_size = int(os.getenv("YF_SCREENER_PAGE_SIZE", "250"))
        # Reuse MarketBreadthFetcher's resolver
        self.fetcher = MarketBreadthFetcher(region=self.region, enable_pagination_fallback=False)

    def _fetch_page(self, offset: int, size: int) -> dict | None:
        """Try predefined screener with resolver fallback."""
        try:
            field = "price_signal_fifty_two_wk_high.datetime"
            payload = {
                "size": size,
                "offset": offset,
                "sortType": "DESC",
                "sortField": "ticker",
                "includeFields": [],
                "topOperator": "AND",
                "query": {
                    "operator": "and",
                    "operands": [
                        {"operator": "eq", "operands": ["region", self.region.lower()]},
                        {"operator": "gte", "operands": [field, "now-1w/d"]},
                    ],
                },
                "quoteType": "EQUITY",
            }
            url = "https://query1.finance.yahoo.com/v1/finance/screener"
            return yahoo_client.execute_request(
                url,
                method="POST",
                params={"formatted": "false", "lang": "en-US", "region": self.region},
                json_payload=payload,
            )
        except Exception:
            return None

    def get_all_quotes(self, max_pages: int = 40) -> list[dict]:
        """Returns the full quotes list for 52w highs, paginating until complete."""
        quotes = []
        offset = 0
        total = None
        pages = 0
        
        while pages < max_pages:
            data = self._fetch_page(offset, self.page_size)
            if not data:
                logger.warning(f"[52w highs] No data returned at offset={offset}, stopping pagination")
                break
            
            # Extract result list, then get first element
            result_list = ((data.get("finance") or {}).get("result") or [])
            node = result_list[0] if result_list else {}
            # Now node is a dict, safe to use .get()
            total = node.get("total", total)
            batch = node.get("quotes") or []
            
            if not batch:
                break
            
            # Enforce US symbols if region=US
            if self.region == "US":
                batch = [q for q in batch if _is_us_symbol(q.get("symbol", ""))]
            
            projected = [self._project_quote(q) for q in batch]
            quotes.extend(projected)
            offset += len(batch)
            pages += 1
            
            if total is not None and len(quotes) >= int(total):
                break
        
        logger.info(f"[52w highs] Fetched {len(quotes)} quotes across {pages} pages")
        return quotes

    # An explicit projection helper inside NewHighsScreenerSource
    def _project_quote(self, q: dict) -> dict:
        return {
            "symbol": q.get("symbol"),
            "industry": q.get("industry"),
            "shortName": q.get("shortName"),
            "sector": q.get("sector"),
            "regularMarketPrice": q.get("regularMarketPrice"),
            "fiftyTwoWeekHigh": q.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekHighChangePercent": q.get("fiftyTwoWeekHighChangePercent"),
            "marketCap": q.get("marketCap"),
        }

class MarketBreadthFetcher:
    """
    Reads totals from predefined screeners for 52w highs and 52w lows and returns aggregate breadth.
    """
    def __init__(self, region: Optional[str] = None, enable_pagination_fallback: bool = True, max_pages: int = 12, page_size: int = 250):
        self.region = (region or _DEFAULT_REGION).upper()
        self.enable_pagination_fallback = enable_pagination_fallback
        self.max_pages = max_pages
        self.page_size = page_size
        self._resolved = {}  # {"high": (host, ver, scrId, params), "low": ...}

    def _candidate_variants(self, kind: str):
        # kind in {"high","low"}
        scr_ids = {
            "high": ["new_52_week_high", "NEW_52_WEEK_HIGH", "new52WeekHigh","new_52_week_highs", "NEW_52_WEEK_HIGHS", "new52weekhigh"],
            "low":  ["new_52_week_low",  "NEW_52_WEEK_LOW",  "new52WeekLow",  "new_52_week_lows",  "NEW_52_WEEK_LOWS", "new52weeklow"],
        }[kind]
        versions = ["v1", "v7"]
        hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
        param_variants = [
            {"lang": "en-US", "region": self.region, "formatted": "false"},
            {"lang": "en-US", "region": self.region},
            {"lang": "en-US", "region": self.region.lower(), "formatted": "false"},
        ]
        for host in hosts:
            for ver in versions:
                for scr in scr_ids:
                    for pv in param_variants:
                        yield host, ver, scr, pv

    def _try_predefined_total(self, host: str, ver: str, scr_id: str, params: dict) -> int | None:
        url = f"https://{host}/{ver}/finance/screener/predefined/saved"
        q = dict(params, scrIds=scr_id, count=self.page_size, offset=0)
        data = yahoo_client.execute_request(url, params=q)
        node0 = ((data or {}).get("finance") or {}).get("result") or []
        node0 = node0[0] if node0 else {}
        total = node0.get("total")
        if not total:
            quotes = node0.get("quotes") or node0.get("quotesList") or []
            if isinstance(quotes, list) and self.region == "US":
                quotes = [q for q in quotes if _is_us_symbol(q.get("symbol") or "")]
            total = len(quotes)
        return int(total) if total else None

    def _fallback_post_total(self, high: bool) -> int:
        # direct POST screener query for recent 52w highs/lows, size=1 to read total
        field = "price_signal_fifty_two_wk_high.datetime" if high else "price_signal_fifty_two_wk_low.datetime"
        payload = {
            "size": 1,
            "offset": 0,
            "sortType": "DESC",
            "sortField": "ticker",
            "includeFields": [],
            "topOperator": "AND",
            "query": {
                "operator": "and",
                "operands": [
                    {"operator": "eq", "operands": ["region", self.region.lower()]},
                    {"operator": "gte", "operands": [field, "now-1w/d"]},
                ],
            },
            "quoteType": "EQUITY",
        }
        url = "https://query1.finance.yahoo.com/v1/finance/screener"
        data = yahoo_client.execute_request(url, method="POST", params={"formatted": "false", "lang": "en-US", "region": self.region}, json_payload=payload)
        node0 = ((data or {}).get("finance") or {}).get("result") or []
        node0 = node0[0] if node0 else {}
        return int(node0.get("total") or 0)

    # Prefer POST screener first; skip legacy GET unless enabled
    def _get_total(self, scr_kind: str, region: str) -> int:
        # 1) POST screener first (most reliable now)
        try:
            total = self._fallback_post_total(high=(scr_kind == "high"))
            if total:
                return total
        except Exception:
            pass

        # 2) Optionally allow legacy predefined resolution if explicitly enabled
        if os.getenv("YF_ENABLE_PREDEFINED", "0") not in ("1", "true", "TRUE"):
            return 0

        # 3) Use cached resolution
        if scr_kind in self._resolved:
            host, ver, scr, pv = self._resolved[scr_kind]
            try:
                total = self._try_predefined_total(host, ver, scr, pv)
                if total is not None:
                    return total
            except Exception:
                pass

        # 4) Brute-force permutations with tighter cap
        attempts = 0
        for host, ver, scr, pv in self._candidate_variants(scr_kind):
            attempts += 1
            try:
                total = self._try_predefined_total(host, ver, scr, pv)
                if total is not None:
                    self._resolved[scr_kind] = (host, ver, scr, pv)
                    return total
            except Exception:
                pass
            if attempts >= 12:  # keep small to reduce noise
                break

        # 5) Finally, paginate if enabled
        if self.enable_pagination_fallback:
            return self._paginate_count(
                scr_id=(self._resolved.get(scr_kind, (None, None, "new_52_week_high" if scr_kind == "high" else "new_52_week_low", {}))[2]),
                region=region,
            )
        return 0

    def get_breadth(self) -> dict:
        highs = self._get_total("high", self.region)
        lows = self._get_total("low", self.region)

        # ratio semantics expected by tests
        if highs > 0 and lows == 0:
            ratio = float("inf")
        elif highs == 0:
            ratio = 0.0
        else:
            ratio = round(highs / lows, 3)

        return {"new_highs": highs, "new_lows": lows, "high_low_ratio": ratio}