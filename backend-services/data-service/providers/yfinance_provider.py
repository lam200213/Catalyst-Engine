# backend-services/data-service/providers/yfinance_provider.py
from curl_cffi import requests as cffi_requests
import datetime as dt
import time # Add time for throttling
import random # Add random for throttling
import pandas as pd
import logging
import time
import threading
#DEBUG
import sys

session = cffi_requests.Session()
_YAHOO_CRUMB = None
_AUTH_LOCK = threading.Lock()

# --- HIGH-VISIBILITY LOGGING TO CONFIRM FILE IS LOADED ---
# This will print the moment the Python interpreter loads this file.
# If you don't see this in the logs, the container is using old code.
sys.stderr.write("--- yfinance_provider.py MODULE LOADED ---\n")
sys.stderr.flush()
# --- END HIGH-VISIBILITY LOGGING ---

# A list of user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
]

# Proxies are now loaded from an environment variable for better configuration management.
import os # Add os import for environment variable access
PROXIES = [p.strip() for p in os.getenv("YAHOO_FINANCE_PROXIES", "").split(',') if p.strip()]

def _get_yahoo_auth():
    """
    Performs an initial request to Yahoo Finance to get the necessary
    cookies and the API 'crumb' for authenticated requests.
    This is thread-safe to prevent multiple requests in a concurrent environment.
    """
    global _YAHOO_CRUMB
    # Use a lock to ensure only one thread tries to get the crumb at a time
    with _AUTH_LOCK:
        # If another thread already got the crumb while this one was waiting, just return it
        if _YAHOO_CRUMB:
            return _YAHOO_CRUMB

        print("PROVIDER-DEBUG: No auth crumb found. Fetching new one...", flush=True)
        try:
            # The 'getcrumb' endpoint is a reliable way to get a valid crumb
            crumb_url = "https://query1.finance.yahoo.com/v1/test/getcrumb"
            headers = {'User-Agent': _get_random_user_agent()}
            proxy = _get_random_proxy()

            # The session object will automatically store the required cookies
            crumb_response = session.get(
                crumb_url,
                headers=headers,
                proxies=proxy,
                impersonate="chrome110",
                timeout=10
            )
            crumb_response.raise_for_status()
            _YAHOO_CRUMB = crumb_response.text
            print(f"PROVIDER-DEBUG: Successfully fetched new crumb: {_YAHOO_CRUMB}", flush=True)
            return _YAHOO_CRUMB
        except cffi_requests.errors.RequestsError as e:
            sys.stderr.write(f"--- CRITICAL: Failed to get Yahoo auth crumb: {e} ---\n")
            sys.stderr.flush()
            return None

def _get_random_user_agent() -> str:
    """Returns a random user-agent from the list."""
    return random.choice(USER_AGENTS)

def _get_random_proxy() -> dict | None:
    """Returns a random proxy if available."""
    if not PROXIES:
        return None
    proxy_url = random.choice(PROXIES)
    return {"http": proxy_url, "https": proxy_url}

def _transform_yahoo_response(response_json: dict, ticker: str) -> list | None:
    """Transforms Yahoo's JSON into our standard list-of-dicts format."""
    try:
        result = response_json['chart']['result'][0]
        timestamps = result['timestamp']
        ohlc = result['indicators']['quote'][0]

        standardized_data = []
        for i, ts in enumerate(timestamps):
            standardized_data.append({
                "formatted_date": dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d'),
                "open": ohlc['open'][i],
                "high": ohlc['high'][i],
                "low": ohlc['low'][i],
                "close": ohlc['close'][i],
                "volume": ohlc['volume'][i],
                "adjclose": result['indicators']['adjclose'][0]['adjclose'][i]
            })
        return standardized_data
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error transforming Yahoo Finance data for {ticker}: {e}")
        return None

def get_stock_data(tickers: str | list[str], start_date: dt.date = None) -> dict | list | None:
    """
    Fetches historical stock data from Yahoo Finance using curl_cffi
    and formats it into the application's standard list-of-dictionaries format.
    Accepts an optional start_date for incremental fetches for single tickers.
    Handles both single ticker (str) and multiple tickers (list).
    """
    if isinstance(tickers, str):
        return _get_single_ticker_data(tickers, start_date)

    if isinstance(tickers, list):
        results = {}
        for ticker in tickers:
            # Note: start_date is ignored for batch requests for simplicity.
            # Each ticker is fetched individually.
            results[ticker] = _get_single_ticker_data(ticker, start_date=None)
        return results

    # Invalid input type
    return None

def _get_single_ticker_data(ticker: str, start_date: dt.date = None) -> list | None:
    """
    Fetches historical stock data for a single ticker from Yahoo Finance.
    """
    crumb = _get_yahoo_auth()
    if not crumb:
        return None
    #  Introduce request throttling to avoid rate-limiting.
    time.sleep(random.uniform(0.5, 1.5)) # Wait 0.5-1.5 seconds

    # --- Date Range Logic ---
    # This section determines the appropriate Yahoo Finance API URL based on whether
    # a `start_date` is provided. This supports incremental data fetching.
    if start_date:
        # If a start_date is provided, construct a URL with a specific date range.
        # `period1` is the start timestamp, `period2` is the current time.
        start_ts = int(dt.datetime.combine(start_date, dt.time.min).timestamp())
        end_ts = int(time.time())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d&crumb={crumb}"
    else:
        # If no start_date is given, default to a 1-year data range.
        # This is used for initial data population or full cache refreshes.
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d&crumb={crumb}"

    headers = {'User-Agent': _get_random_user_agent()}
    proxy = _get_random_proxy()

    try:
        response = session.get(
            url,
            headers=headers,
            proxies=proxy,
            impersonate="chrome110",
            timeout=10
        )
        # Raise an exception for bad status codes to be caught below
        response.raise_for_status()
        if response.status_code != 200:
            print(f"Yahoo Finance API returned status {response.status_code} for {ticker}")
            return None

        data = response.json()
        #  Pass ticker to transformation function
        return _transform_yahoo_response(data, ticker)

    except cffi_requests.errors.RequestsError as e:
        if e.response:
            print(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}", flush=True)
        print(f"A curl_cffi request error occurred for {ticker}: {e}", flush=True)
        return None
    except Exception as e:
        print(f"An unexpected error occurred in yfinance_provider for {ticker}: {e}")
        return None

def _transform_income_statements(statements):
    """Helper to extract raw values and create the keys expected by the leadership logic."""
    transformed = []
    for s in statements:
        # Ensure we handle cases where financial data might be missing
        net_income = s.get('netIncome', {}).get('raw')
        total_revenue = s.get('totalRevenue', {}).get('raw')
        # Get EPS instead of using Net Income for "Earnings"
        eps = (s.get('basicEps') or {}).get('raw')
        
        transformed.append({
            'Earnings': eps, # Use EPS for earnings-related checks
            'Revenue': total_revenue,
            'Net Income': net_income, # Keep Net Income for margin checks
            'Total Revenue': total_revenue,
        })
    return transformed

# Function to fetch core financial data for Leadership screening
# backend-services/data-service/providers/yfinance_provider.py

def get_core_financials(ticker_symbol):
    """
    Fetches core financial data points required for Leadership Profile screening.
    For S&P 500 (^GSPC), returns market data including current price, SMAs, and 52-week highs/lows.
    For other tickers, returns standard financial data.
    """
    # Latest Add: High-visibility print statement with flush=True to guarantee it appears in logs
    print(f"PROVIDER-DEBUG: Attempting to get core financials for {ticker_symbol}", flush=True)

    try:
        start_time = time.time()

        # Special handling for major indices
        if ticker_symbol in ['^GSPC', '^DJI', 'QQQ']:
            hist = _get_single_ticker_data(ticker_symbol, start_date=dt.date.today() - dt.timedelta(days=365))
            if not hist:
                print(f"PROVIDER-DEBUG: No historical data for index {ticker_symbol}", flush=True)
                return None

            df = pd.DataFrame(hist)
            data = {
                'current_price': float(df['close'].iloc[-1]),
                'sma_50': float(df['close'].tail(50).mean()),
                'sma_200': float(df['close'].tail(200).mean()) if len(df) >= 200 else float(df['close'].tail(50).mean()),
                'high_52_week': float(df['high'].max()),
                'low_52_week': float(df['low'].min())
            }
        else:
            # Logic for regular stocks
            crumb = _get_yahoo_auth()
            if not crumb:
                return None
            
            url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=summaryDetail,assetProfile,financialData,defaultKeyStatistics,incomeStatementHistory,incomeStatementHistoryQuarterly,balanceSheetHistory,cashflowStatementHistory&crumb={crumb}"
            headers = {'User-Agent': _get_random_user_agent()}
            proxy = _get_random_proxy()

            response = session.get(url, headers=headers, proxies=proxy, impersonate="chrome110", timeout=15)
            response.raise_for_status()
            if response.status_code != 200:
                print(f"PROVIDER-DEBUG: Yahoo API returned non-200 status: {response.status_code}", flush=True)
                return None

            result = response.json().get('quoteSummary', {}).get('result')
            if not result:
                print(f"PROVIDER-DEBUG: Yahoo API response has no 'result' field.", flush=True)
                return None
            
            info = result[0]

            # Latest Add: More robust data extraction
            summary_detail = info.get('summaryDetail') or {}
            default_key_stats = info.get('defaultKeyStatistics') or {}
            asset_profile = info.get('assetProfile') or {}
            
            # Gone: Old parsing logic
            # income_statement_history = info.get('incomeStatementHistory') or {}
            # income_statements = income_statement_history.get('incomeStatementHistory', [])
            # raw_annual = [s for s in income_statements if s.get('periodType') == 'ANNUAL']
            # raw_quarterly = [s for s in income_statements if s.get('periodType') == 'QUARTERLY']

            # Latest Add: Correctly parse separate annual and quarterly history keys
            annual_history = info.get('incomeStatementHistory', {}).get('incomeStatementHistory', [])
            quarterly_history = info.get('incomeStatementHistoryQuarterly', {}).get('incomeStatementHistoryQuarterly', [])

            annual_earnings_list = _transform_income_statements(annual_history)
            quarterly_earnings_list = _transform_income_statements(quarterly_history)

            data = {
                'marketCap': (summary_detail.get('marketCap') or {}).get('raw'),
                'sharesOutstanding': (default_key_stats.get('sharesOutstanding') or {}).get('raw'),
                'floatShares': (default_key_stats.get('floatShares') or {}).get('raw'),
                'ipoDate': (asset_profile.get('ipoDate') or {}).get('fmt'),
                'annual_earnings': annual_earnings_list,
                'quarterly_earnings': quarterly_earnings_list,
                'quarterly_financials': quarterly_earnings_list # This assumes earnings and financials are the same for now
            }

        duration = time.time() - start_time
        print(f"PROVIDER-DEBUG: Yahoo Finance API call for {ticker_symbol} took {duration:.2f} seconds.", flush=True)

        return data
    except cffi_requests.errors.RequestsError as e:
        if e.response:
            print(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}", flush=True)
        print(f"A curl_cffi request error occurred for {ticker_symbol}: {e}", flush=True)
        return None
    except Exception as e:
        sys.stderr.write(f"--- EXCEPTION CAUGHT in get_core_financials for {ticker_symbol} ---\n")
        sys.stderr.write(f"    Exception Type: {type(e).__name__}\n")
        sys.stderr.write(f"    Exception Details: {str(e)}\n")
        sys.stderr.write(f"--- END EXCEPTION ---\n")
        sys.stderr.flush()
        return None

def get_batch_core_financials(tickers: list[str]) -> dict:
    """
    Fetches core financial data for a list of tickers.

    Args:
        tickers: A list of stock symbols to fetch data for.

    Returns:
        A dictionary where keys are tickers and values are their core financial data.
        If a ticker's data cannot be fetched, its value will be None.
    """
    results = {}
    for ticker_symbol in tickers:
        # Introduce a small delay to avoid hitting rate limits when fetching multiple tickers
        time.sleep(random.uniform(0.1, 0.5))
        results[ticker_symbol] = get_core_financials(ticker_symbol)
    return results