# backend-services/data-service/providers/yfinance_provider.py
from curl_cffi import requests as cffi_requests
import datetime as dt
import time # Add time for throttling
import random # Add random for throttling
import pandas as pd
import time
import threading
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
#DEBUG
import sys
import json

session = cffi_requests.Session()
_YAHOO_CRUMB = None
_AUTH_LOCK = threading.Lock()

# --- Soft-coded Yahoo Finance Scraper Selectors ---
# These class names are specific to the Yahoo Finance financial statements page.
# Yahoo may update its website structure, causing these to fail.
# If the scraper stops working, inspect the page's HTML and update these values.
# - YF_ROW_CLASS: Represents a row in the financial table (e.g., "Total Revenue").
# - YF_HEADER_ROW_CLASS: Represents the header row containing the dates.
YF_ROW_CLASS = 'yf-t22klz'
YF_HEADER_ROW_CLASS = 'yf-1yyu1pc'
# --- End Selectors ---

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

    # Sanitize the ticker symbol to handle special characters and whitespace.
    # This ensures tickers like 'BRK/B' become 'BRK-B' and 'ECC ' becomes 'ECC'.
    sanitized_ticker = ticker.strip().replace('/', '-')

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
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?period1={start_ts}&period2={end_ts}&interval=1d&crumb={crumb}"
    else:
        # If no start_date is given, default to a 1-year data range.
        # This is used for initial data population or full cache refreshes.
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?range=1y&interval=1d&crumb={crumb}"

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

def _transform_income_statements(statements, shares_outstanding):
    """Helper to extract raw values and manually calculate EPS if not provided."""
    transformed = []
    for s in statements:
        net_income = s.get('netIncome', {}).get('raw')
        total_revenue = s.get('totalRevenue', {}).get('raw')
        
        # Try to get pre-calculated EPS first
        eps = (s.get('basicEps') or {}).get('raw')
        
        # Fallback: Manually calculate EPS if not available and data is valid
        if eps is None and net_income is not None and shares_outstanding is not None and shares_outstanding > 0:
            eps = net_income / shares_outstanding

        transformed.append({
            'Earnings': eps,
            'Net Income': net_income,
            'Revenue': total_revenue,
            'Total Revenue': total_revenue,
        })
    return transformed

# Functions to fetch core financial data for Leadership screening
# A new helper using the yfinance library
def _fetch_financials_with_yfinance(ticker):
    """
    Fetches financials for a ticker using the yfinance library.
    
    This is the primary, preferred method for fetching core financial data.
    """
    print(f"PROVIDER-DEBUG: Attempting to fetch financials for {ticker} using yfinance library.")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # --- DEBUGGING BLOCK ---
        # Print the exact data received to the container's logs
        # print("--- LEADERSHIP-SERVICE DEBUG ---", flush=True)
        # print(f"Data received from data-service for {ticker}:", flush=True)
        # Use json.dumps for pretty-printing the dictionary
        # print(json.dumps(info, indent=2), flush=True)
        # print("--- END DEBUG ---", flush=True)
        # --- END DEBUGGING BLOCK ---
        
        # The 'info' dictionary must exist and contain essential data to be useful.
        if not info or 'marketCap' not in info:
            print(f"PROVIDER-DEBUG: yfinance info missing key fields for {ticker}.")
            return None

        # --- IPO Date Handling ---
        # Yahoo Finance provides the 'firstTradeDateEpoch', which is the timestamp
        # of the first trade recorded. This serves as a reliable proxy for the IPO date.
        ipo_date = None
    
        ipo_date_timestamp = info.get('firstTradeDateMilliseconds')
        # Represents the number of milliseconds since the Unix epoch.
        # divide the millisecond value by 1000 to the number of seconds since the Unix epoch
        
        if ipo_date_timestamp:
            # Ensure the timestamp value is a number before converting.
            if isinstance(ipo_date_timestamp, (int, float)):
                try:
                    ipo_date_timestamp_val = ipo_date_timestamp / 1000
                    ipo_date = dt.datetime.fromtimestamp(ipo_date_timestamp_val).strftime('%Y-%m-%d')
                except (ValueError, TypeError) as e:
                    # Log if the timestamp is invalid (e.g., out of range).
                    print(f"PROVIDER-DEBUG: Could not convert epoch '{ipo_date_timestamp}' to date for {ticker}. Error: {e}")
            else:
                print(f"PROVIDER-DEBUG: Expected epoch for 'firstTradeDateEpoch' to be a number, but got {type(ipo_date_timestamp)} for {ticker}.")
        
        # --- Financial Statement Formatting ---
        q_income_stmt = stock.quarterly_income_stmt
        a_income_stmt = stock.income_stmt

        def format_income_statement(df):
            if df is None or df.empty:
                return []
            df_t = df.transpose()
           # This ensures consistency with the fallback method and prevents errors in leadership_logic.
            if 'Total Revenue' in df_t.columns:
                df_t['Revenue'] = df_t['Total Revenue']
            else:
                df_t['Revenue'] = None
            
            # Manually calculate EPS if not present, using sharesOutstanding from the info dict.
            shares_outstanding = info.get('sharesOutstanding')
            if 'Basic EPS' not in df_t.columns and 'Net Income' in df_t.columns and shares_outstanding:
                df_t['Earnings'] = df_t['Net Income'] / shares_outstanding
            else:
                df_t['Earnings'] = df_t.get('Basic EPS')

            return df_t.reset_index().to_dict('records')

        quarterly_financials = format_income_statement(q_income_stmt)
        annual_financials = format_income_statement(a_income_stmt)

        # Consolidate all data into the final dictionary.
        return {
            'ticker': ticker,
            'marketCap': info.get('marketCap'),
            'sharesOutstanding': info.get('sharesOutstanding'),
            'floatShares': info.get('floatShares'),
            'ipoDate': ipo_date, # Use the processed date
            'annual_earnings': annual_financials,
            'quarterly_earnings': quarterly_financials,
            'quarterly_financials': quarterly_financials,
        }
    except Exception as e:
        # Catch any other unexpected errors from the yfinance library call.
        print(f"PROVIDER-DEBUG: An unhandled exception occurred in the yfinance library for {ticker}. Error: {e}")
        return None
    
def get_core_financials(ticker_symbol):
    """
    Fetches core financial data points required for Leadership Profile screening.
    For S&P 500 (^GSPC), returns market data including current price, SMAs, and 52-week highs/lows.
    For other tickers, returns standard financial data.
    This function now prioritizes the yfinance library and uses the direct API call as a fallback.
    """
    start_time = time.time()
    print(f"PROVIDER-DEBUG: Attempting to get core financials for {ticker_symbol}", flush=True)

    # --- Special Handling for Market Indices ---
    if ticker_symbol in ['^GSPC', '^DJI', 'QQQ']:
        hist = _get_single_ticker_data(ticker_symbol, start_date=dt.date.today() - dt.timedelta(days=365))
        if not hist:
            print(f"PROVIDER-DEBUG: No historical data for index {ticker_symbol}", flush=True)
            return None

        df = pd.DataFrame(hist)
        # Ensure DataFrame has enough data for calculations
        if df.empty or len(df) < 2:
            return None

        data = {
            'current_price': float(df['close'].iloc[-1]),
            'sma_50': float(df['close'].tail(50).mean()) if len(df) >= 50 else float(df['close'].mean()),
            'sma_200': float(df['close'].tail(200).mean()) if len(df) >= 200 else float(df['close'].mean()),
            'high_52_week': float(df['high'].max()),
            'low_52_week': float(df['low'].min())
        }
        return data

    # --- Primary Fetching Strategy (yfinance library) ---
    # Prioritize fetching with the yfinance helper function.
    extended_financials_data = _fetch_financials_with_yfinance(ticker_symbol)
    if extended_financials_data:
        duration = time.time() - start_time
        print(f"PROVIDER-DEBUG: yfinance library call for {ticker_symbol} took {duration:.2f} seconds.", flush=True)
        return extended_financials_data

    # --- Fallback Fetching Strategy (Direct API Call) ---
    print(f"PROVIDER-DEBUG: Primary yfinance fetch failed for {ticker_symbol} (likely delisted or no summary data). Falling back to direct API.", flush=True)
    try:
        crumb = _get_yahoo_auth()
        if not crumb:
            return None
        
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=summaryDetail,assetProfile,financialData,defaultKeyStatistics,incomeStatementHistory,incomeStatementHistoryQuarterly,balanceSheetHistory,cashflowStatementHistory&crumb={crumb}"
        headers = {'User-Agent': _get_random_user_agent()}
        proxy = _get_random_proxy()

        response = session.get(url, headers=headers, proxies=proxy, impersonate="chrome110", timeout=15)
        response.raise_for_status()
        
        result = response.json().get('quoteSummary', {}).get('result')
        if not result:
            print(f"PROVIDER-DEBUG: Yahoo API fallback response has no 'result' field.", flush=True)
            return None
        
        info = result[0]

        summary_detail = info.get('summaryDetail') or {}
        default_key_stats = info.get('defaultKeyStatistics') or {}
        
        shares_outstanding = (default_key_stats.get('sharesOutstanding') or {}).get('raw')

        annual_history = info.get('incomeStatementHistory', {}).get('incomeStatementHistory', [])
        quarterly_history = info.get('incomeStatementHistoryQuarterly', {}).get('incomeStatementHistory', [])

        annual_earnings_list = _transform_income_statements(annual_history, shares_outstanding)
        quarterly_earnings_list = _transform_income_statements(quarterly_history, shares_outstanding)
        
        data = {
            'ticker': ticker_symbol,
            'marketCap': (summary_detail.get('marketCap') or {}).get('raw'),
            'sharesOutstanding': shares_outstanding,
            'floatShares': (default_key_stats.get('floatShares') or {}).get('raw'),
            'ipoDate': (default_key_stats.get('ipoDate') or {}).get('fmt'), 
            'annual_earnings': annual_earnings_list,
            'quarterly_earnings': quarterly_earnings_list,
            'quarterly_financials': quarterly_earnings_list
        }
        
        duration = time.time() - start_time
        print(f"PROVIDER-DEBUG: Yahoo Finance API fallback call for {ticker_symbol} took {duration:.2f} seconds.", flush=True)
        return data

    except cffi_requests.errors.RequestsError as e:
        if e.response and e.response.status_code == 404:
            print(f"PROVIDER-DEBUG: Fallback for {ticker_symbol} also failed with 404. Ticker is confirmed unavailable.", flush=True)
        else:
            if e.response:
                print(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}", flush=True)
            print(f"A curl_cffi request error occurred during fallback for {ticker_symbol}: {e}", flush=True)
        return None
    except Exception as e:
        sys.stderr.write(f"--- EXCEPTION CAUGHT in get_core_financials fallback for {ticker_symbol} ---\n")
        sys.stderr.write(f"    Exception Type: {type(e).__name__}\n")
        sys.stderr.write(f"    Exception Details: {str(e)}\n")
        sys.stderr.write(f"--- END EXCEPTION ---\n")
        sys.stderr.flush()
        return None

def get_batch_core_financials(tickers: list[str], executor: ThreadPoolExecutor) -> dict:
    """
    Fetches core financial data for a list of tickers in parallel.
    """
    results = {}
    future_to_ticker = {executor.submit(get_core_financials, ticker): ticker for ticker in tickers}

    for future in as_completed(future_to_ticker):
        ticker = future_to_ticker[future]
        try:
            data = future.result()
            results[ticker] = data
        except Exception as e:
            print(f"ERROR: Failed to process {ticker} in batch. Error: {e}", flush=True)
            results[ticker] = None
            
    return results
