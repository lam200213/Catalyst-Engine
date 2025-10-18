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

from . import yahoo_client # Use relative import

#DEBUG
import logging
import json

logger = logging.getLogger(__name__)

class SectorIndustrySource:
    """Abstract source of industry -> candidate tickers mapping."""
    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        raise NotImplementedError


class YahooSectorIndustrySource(SectorIndustrySource):
    """Primary source using yfinance Sector/Industry APIs."""
    def __init__(self, sector_keys: Optional[List[str]] = None):
        self._sector_keys = sector_keys
        # Prefer discovering sectors dynamically; allow override via config

    def _discover_sector_keys(self) -> List[str]:
        # If explicit keys provided, use them
        if self._sector_keys:
            return self._sector_keys

        # Fallback list is intentionally minimal; can be configured externally
        # Attempt to probe a small known set to avoid hardcoding all values
        return [
            "technology",
            "communication-services",
            "healthcare",
            "financial-services",
            "industrials",
            "consumer-cyclical",
            "consumer-defensive",
            "energy",
            "real-estate",
            "basic-materials",
            "utilities",
        ]

    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}

        # Use a random proxy for this batch
        proxy = yahoo_client._get_random_proxy()
        if proxy:
            yahoo_client.session.proxies = proxy

        for skey in self._discover_sector_keys():
            try:
                sector = yf.Sector(skey, session=yahoo_client.session)
                inds_df = getattr(sector, "industries", None)
                if not isinstance(inds_df, pd.DataFrame) or inds_df.empty:
                    logger.debug(f"No industries for sector {skey}")
                    continue

                for _, row in inds_df.iterrows():
                    ind_key = str(row.get("key", "")).strip()
                    ind_name = str(row.get("name", "")).strip() or ind_key
                    if not ind_key:
                        continue

                    try:
                        industry = yf.Industry(ind_key, session=yahoo_client.session)
                        top_df = getattr(industry, "top_performing_companies", None)
                        if isinstance(top_df, pd.DataFrame) and "symbol" in top_df.columns:
                            syms = [str(s) for s in top_df["symbol"].dropna().astype(str).tolist()]
                            if syms:
                                out[ind_name] = syms[:per_industry_limit]
                        else:
                            # If top_performing_companies unavailable, try top_growth_companies
                            growth_df = getattr(industry, "top_growth_companies", None)
                            if isinstance(growth_df, pd.DataFrame) and "symbol" in growth_df.columns:
                                syms = [str(s) for s in growth_df["symbol"].dropna().astype(str).tolist()]
                                if syms:
                                    out[ind_name] = syms[:per_industry_limit]
                    except Exception as ie:
                        logger.debug(f"Industry fetch failed for {ind_key}: {ie}")
                        continue
            except Exception as se:
                logger.debug(f"Sector fetch failed for {skey}: {se}")
                continue

        return out


class DayGainersSource(SectorIndustrySource):
    """Fallback source using yfinance screener day_gainers."""
    def __init__(self):
        pass 

    def get_industry_top_tickers(self, per_industry_limit: int = 10) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        try:
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            params = {
                "scrIds": "day_gainers",
                "count": 200
            }
            data = yahoo_client.execute_request(url, params=params)
            
            # The structure is nested under finance -> result -> [0]
            quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
            
            for q in quotes:
                sym = q.get("symbol")
                ind = q.get("industry")
                if not sym or not ind:
                    continue
                bucket = out.setdefault(ind, [])
                if len(bucket) < per_industry_limit:
                    bucket.append(sym)
        except Exception as e:
            logger.debug(f"day_gainers screener failed: {e}")
        return out


class ReturnCalculator:
    """Computes 1-month percent change for a ticker."""
    def __init__(self, session=None):
        yahoo_client.session = session or yahoo_client.session

    def one_month_change(self, symbol: str) -> Optional[float]:
        try:
            # Rotate proxy for history batch segments periodically
            proxy = yahoo_client._get_random_proxy()
            if proxy:
                yahoo_client.session.proxies = proxy

            hist = yf.Ticker(symbol, session=yahoo_client.session).history(period="1mo", interval="1d")
            if hist is None or hist.empty or "Close" not in hist:
                return None
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                return None
            start = float(closes.iloc[0])
            end = float(closes.iloc[-1])
            pct = round((end - start) / start * 100.0, 2)
            return pct
        except Exception as e:
            logger.debug(f"history(period='1mo') failed for {symbol}: {e}")
            return None