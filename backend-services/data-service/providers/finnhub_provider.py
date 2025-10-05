# data-service/providers/finnhub_provider.py
import finnhub
import os
import datetime as dt
import time
import threading
from collections import deque

import logging
logger = logging.getLogger(__name__)

# --- Thread-safe Rate Limiting Globals ---
# A deque is efficient for adding/removing from both ends
_finnhub_call_timestamps = deque()
_finnhub_lock = threading.Lock()
FINNHUB_MAX_CALLS_PER_MINUTE = 59 # Stay just under the limit of 60 calls per minute

def get_stock_data(ticker: str) -> list | None:
    """
    Fetches historical stock data from Finnhub and transforms it
    into the application's standard list-of-dictionaries format.

    Args:
        ticker: The stock symbol to fetch data for.

    Returns:
        A list of dictionaries with OHLCV data, or None if an error occurs.
    """
    try:
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is not set in environment.")
            
        finnhub_client = finnhub.Client(api_key=api_key)
        
        # Calculate timestamps for the last year ending yesterday to avoid partial daily data.
        yesterday_dt = dt.datetime.now() - dt.timedelta(days=1)
        end_ts = int(yesterday_dt.timestamp())
        start_ts = int((yesterday_dt - dt.timedelta(days=365)).timestamp())

        # Fetch candle data from Finnhub
        res = finnhub_client.stock_candles(ticker, 'D', start_ts, end_ts)
        logger.info(f"Finnhub API response for {ticker}: {res}")

        # Finnhub returns 'no_data' in the 's' field on failure.
        if res.get('s') == 'no_data' or 'c' not in res:
            return None

        # Transform Finnhub's response (dictionary of lists) into our standard format.
        # This is the crucial transformation step.
        standardized_data = []
        for i in range(len(res['c'])):
            standardized_data.append({
                "high": res['h'][i],
                "low": res['l'][i],
                "open": res['o'][i],
                "close": res['c'][i],
                "volume": res['v'][i],
                "adjclose": res['c'][i], # Finnhub doesn't provide a separate adjusted close in this call.
                "formatted_date": dt.datetime.fromtimestamp(res['t'][i]).strftime('%Y-%m-%d')
            })
            
        return standardized_data
        
    except Exception as e:
        logger.error(f"Error fetching data from Finnhub for {ticker}: {e}")
        return None

def get_company_peers_and_industry(ticker: str) -> dict | None:
    """
    Fetches company peers and industry classification from Finnhub.

    Args:
        ticker: The stock symbol to fetch data for.

    Returns:
        A dictionary with 'industry' and 'peers' data, or None if an error occurs.
    """
    global _finnhub_call_timestamps
    with _finnhub_lock:
        now = time.time()
        # Remove timestamps older than 60 seconds
        while _finnhub_call_timestamps and _finnhub_call_timestamps[0] < now - 60:
            _finnhub_call_timestamps.popleft()

        # If we have reached the limit, calculate wait time and sleep
        if len(_finnhub_call_timestamps) >= FINNHUB_MAX_CALLS_PER_MINUTE:
            oldest_call_time = _finnhub_call_timestamps[0]
            wait_time = 60 - (now - oldest_call_time)
            logger.info(f"Finnhub rate limit reached. Waiting for {wait_time:.2f} seconds...")
            time.sleep(wait_time)
        
        # Record the timestamp of the current call
        _finnhub_call_timestamps.append(time.time())

    try:
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is not set in environment.")
            
        finnhub_client = finnhub.Client(api_key=api_key)
        
        peers = finnhub_client.company_peers(ticker)

        profile = finnhub_client.company_profile2(symbol=ticker)
        industry = profile.get('finnhubIndustry') if profile else None
        
        return {
            "industry": industry,
            "peers": peers if peers else []
        }
        
    except Exception as e:
        logger.error(f"Error fetching company peers and industry from Finnhub for {ticker}: {e}")
        return None