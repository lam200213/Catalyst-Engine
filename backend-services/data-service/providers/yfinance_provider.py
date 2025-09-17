# backend-services/data-service/providers/yfinance_provider.py
from curl_cffi import requests as cffi_requests
import datetime as dt
import time # for throttling
import random # for throttling
import pandas as pd
import time
import threading
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
#DEBUG
import logging
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

# Get a child logger that will propagate to the main 'app' logger
logger = logging.getLogger(__name__)

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

        logger.debug("No auth crumb found. Fetching new one...")
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
            logger.debug(f"Successfully fetched new crumb: {_YAHOO_CRUMB}")
            return _YAHOO_CRUMB
        except cffi_requests.errors.RequestsError as e:
            logger.critical(f"Failed to get Yahoo auth crumb: {e}")
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
        logger.error(f"Error transforming Yahoo Finance data for {ticker}: {e}")
        return None

# A robust retry decorator with exponential backoff and jitter
def retry_on_failure(attempts=3, delay=2, backoff=2):
    """
    A decorator to retry a function call upon encountering specific transient exceptions.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = attempts, delay
            while mtries > 1:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Only retry on specific, retry-able errors
                    error_str = str(e).lower()
                    if "rate limited" in error_str or "could not resolve host" in error_str:
                        ticker = args[0] if args and isinstance(args[0], str) else 'N/A'
                        msg = f"Retrying {func.__name__} for {ticker} after error: {e}. Retries left: {mtries-1}"
                        logger.warning(msg)
                        # Add jitter (a small random delay) to prevent thundering herd problem
                        time.sleep(mdelay + random.uniform(0, 1))
                        mtries -= 1
                        mdelay *= backoff
                    else:
                        # Re-raise exceptions that are not transient (e.g., programming errors)
                        raise
            # Perform the final attempt outside the loop
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_stock_data(tickers: str | list[str], start_date: dt.date = None, period: str = None, max_workers: int = 4) -> dict | list | None:
    """
    Fetches historical stock data from Yahoo Finance using curl_cffi
    and formats it into the application's standard list-of-dictionaries format.
    Accepts an optional start_date for incremental fetches for single tickers.
    Handles both single ticker (str) and multiple tickers (list).
    """
    if isinstance(tickers, str):
        return _get_single_ticker_data(tickers, start_date, period)

    if isinstance(tickers, list):
        results = {}
        # Use ThreadPoolExecutor for concurrent requests
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create a future for each ticker
            # Note: start_date is ignored for batch requests for simplicity.
            # Each ticker is fetched individually.
            future_to_ticker = {executor.submit(_get_single_ticker_data, ticker, start_date=start_date, period=period): ticker for ticker in tickers}
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    results[ticker] = future.result()
                except Exception as exc:
                    print(f"ERROR: {ticker} generated an exception: {exc}")
                    results[ticker] = None
        return results

    # Invalid input type
    logger.error(f"Invalid input type: {type(tickers)}")
    return None

def _get_single_ticker_data(ticker: str, start_date: dt.date = None, period: str = None) -> list | None:
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
    # a `start_date` for an incremental fetch or a period (e.g., "1y") is provided. This supports incremental data fetching.
    if start_date:
        # If a start_date is provided, construct a URL with a specific date range.
        # `period1` is the start timestamp, `period2` is the current time.
        start_ts = int(dt.datetime.combine(start_date, dt.time.min).timestamp())
        end_ts = int(time.time())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?period1={start_ts}&period2={end_ts}&interval=1d&crumb={crumb}"
    elif period:
        # If a period is provided, use the 'range' parameter.
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?range={period}&interval=1d&crumb={crumb}"
    else:
        # Enforce explicit control from the calling service.
        raise ValueError("Either start_date or period must be provided to fetch stock data.")


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
            logger.error(f"Yahoo Finance API returned status {response.status_code} for {ticker}")
            return None

        data = response.json()
        #  Pass ticker to transformation function
        return _transform_yahoo_response(data, ticker)

    except cffi_requests.errors.RequestsError as e:
        if e.response:
            logger.error(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}")
            logger.error(f"A curl_cffi request error occurred for {ticker}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in yfinance_provider for {ticker}: {e}")
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
@retry_on_failure(attempts=3, delay=3, backoff=2)
def _fetch_financials_with_yfinance(ticker):
    """
    Fetches financials for a ticker using the yfinance library.
    IMPORTANT: This function DOES NOT handle its own exceptions.
    It allows them to propagate up to be handled by a decorator (e.g., retry logic).
    """
    logger.debug(f"Attempting to fetch financials for {ticker} using yfinance library.")

    stock = yf.Ticker(ticker)
    info = stock.info

    # The 'info' dictionary must exist and contain essential data to be useful.
    if not info or 'marketCap' not in info:
        logger.debug(f"yfinance info missing key fields for {ticker}.")
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
                logger.debug(f"Could not convert epoch '{ipo_date_timestamp}' to date for {ticker}. Error: {e}")
        else:
            logger.debug(f"Expected epoch for 'firstTradeDateEpoch' to be a number, but got {type(ipo_date_timestamp)} for {ticker}.")
    
    # --- Financial Statement Fetching ---
    q_income_stmt = stock.quarterly_income_stmt
    a_income_stmt = stock.income_stmt

    # --- Financial Statement Formatting ---
    def format_income_statement(df):
        if df is None or df.empty:
            logger.debug(f"Income statement DataFrame for {ticker} is empty or None. Skipping formatting.")
            return []
        
        # debug log to inspect the raw DataFrame from yfinance
        logger.debug(f"Raw income statement dtypes for {ticker}:\n{df.dtypes}")

        df_t = df.transpose()
        # This ensures consistency with the fallback method and prevents errors in leadership_logic.
        if 'Total Revenue' in df_t.columns:
            df_t['Revenue'] = df_t['Total Revenue']
        else:
            df_t['Revenue'] = None
        
        # Manually calculate EPS if not present, using sharesOutstanding from the info dict.
        shares_outstanding = info.get('sharesOutstanding')
        # Initialize 'Earnings' column with data from 'Basic EPS' if it exists
        if 'Basic EPS' in df_t.columns:
            df_t['Earnings'] = df_t['Basic EPS']
        else:
            # Use a Pandas Series of Nones to correctly initialize the column
            df_t['Earnings'] = pd.Series([None] * len(df_t), index=df_t.index)
        
        # Identify rows (quarters) where 'Earnings' is null or NaN
        mask_missing_eps = pd.isnull(df_t['Earnings'])
        
        # Add a robust try-except block and type coercion around the EPS calculation
        if shares_outstanding and 'Net Income' in df_t.columns:
            try:
                # Coerce 'Net Income' to a numeric type. Any non-numeric values become NaN.
                net_income_numeric = pd.to_numeric(df_t.loc[mask_missing_eps, 'Net Income'], errors='coerce')
                # Perform division; operations with NaN will result in NaN, which is handled later.
                df_t.loc[mask_missing_eps, 'Earnings'] = net_income_numeric / shares_outstanding
            except Exception as e:
                logger.error(f"Error during fallback EPS calculation for {ticker}: {e}. Some 'Earnings' values may be null.")

        # Convert the DataFrame to a list of dictionaries
        records = df_t.reset_index().to_dict('records')
        
        # Final loop to replace any pandas NaN/NaT with None for perfect JSON compatibility
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        return records

    quarterly_financials = format_income_statement(q_income_stmt)
    annual_financials = format_income_statement(a_income_stmt)

    # --- CONSTRUCT THE FINAL OBJECT ---
    # Consolidate all data into the final dictionary before logging and returning.
    final_data_object = {
        'ticker': ticker,
        'marketCap': info.get('marketCap'),
        'sharesOutstanding': info.get('sharesOutstanding'),
        'floatShares': info.get('floatShares'),
        'ipoDate': ipo_date,
        'annual_earnings': annual_financials,
        'quarterly_earnings': quarterly_financials,
        'quarterly_financials': quarterly_financials, # Retained for compatibility
        # Also include the raw info object for complete debugging if needed
        'raw_info': info 
    }

    # --- LOGGING/SAVING BLOCK ---
    # Save the *final constructed data object* to a structured log file.
    try:
        log_dir = os.path.join('/app/logs', 'yfinance_fetches')
        date_str = dt.datetime.now().strftime('%Y-%m-%d')
        ticker_log_dir = os.path.join(log_dir, date_str)
        os.makedirs(ticker_log_dir, exist_ok=True)
        file_path = os.path.join(ticker_log_dir, f"{ticker}.json")
        
        # Write the 'final_data_object' to the JSON file.
        with open(file_path, 'w') as f:
            # Use a custom encoder to handle potential non-serializable data like NaN
            class CustomEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, float) and (obj != obj):  # NaN
                        return None
                    if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
                        return obj.isoformat()  # Or str(obj) for a simple string representation
                    return json.JSONEncoder.default(self, obj)
            json.dump(final_data_object, f, indent=4, cls=CustomEncoder)
            
        logger.debug(f"Successfully saved complete financial data for {ticker} to {file_path}")

    except Exception as log_e:
        logger.error(f"Failed to save yfinance fetch log for {ticker}: {log_e}")
    # --- END LOGGING/SAVING BLOCK ---

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
    
def get_core_financials(ticker_symbol):
    """
    Fetches core financial data points required for Leadership Profile screening.
    For S&P 500 (^GSPC), returns market data including current price, SMAs, and 52-week highs/lows.
    For other tickers, returns standard financial data.
    This function now prioritizes the yfinance library and uses the direct API call as a fallback.
    """
    start_time = time.time()
    logger.debug(f"Attempting to get core financials for {ticker_symbol}")

    # --- Special Handling for Market Indices ---
    if ticker_symbol in ['^GSPC', '^DJI', '^IXIC']:
        hist = _get_single_ticker_data(ticker_symbol, start_date=dt.date.today() - dt.timedelta(days=365))
        if not hist:
            logger.debug(f"No historical data for index {ticker_symbol}")
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
        logger.debug(f"yfinance library call for {ticker_symbol} took {duration:.2f} seconds.")
        return extended_financials_data

    # --- Fallback Fetching Strategy (Direct API Call) ---
    logger.debug(f"Primary yfinance fetch failed for {ticker_symbol} (likely delisted or no summary data). Falling back to direct API.")
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
            logger.debug("Yahoo API fallback response has no 'result' field.")
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
        logger.debug(f"Yahoo Finance API fallback call for {ticker_symbol} took {duration:.2f} seconds.")
        return data

    except cffi_requests.errors.RequestsError as e:
        if e.response and e.response.status_code == 404:
            logger.debug(f"Fallback for {ticker_symbol} also failed with 404. Ticker is confirmed unavailable.")
        else:
            if e.response:
                logger.error(f"HTTPError: {e.response.status_code} Client Error for url: {e.response.url}")
            logger.error(f"A curl_cffi request error occurred during fallback for {ticker_symbol}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Exception in get_core_financials fallback for {ticker_symbol}")
        return None

def get_batch_core_financials(tickers: list[str], executor: ThreadPoolExecutor) -> dict:
    """
    Fetches core financial data for a list of tickers in parallel.
    """
    results = {}

    # Limit concurrency directly to prevent rate-limiting.
    # We will use a new ThreadPoolExecutor with a controlled number of workers.
    # A max_worker value of 4 is a safe starting point.
    with ThreadPoolExecutor(max_workers=4) as limited_executor:
        future_to_ticker = {limited_executor.submit(get_core_financials, ticker): ticker for ticker in tickers}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                data = future.result()
                results[ticker] = data
            except Exception as e:
                logger.error(f"Failed to process {ticker} in batch after all retries. Error: {e}")
                results[ticker] = None
            # Add a random delay to avoid hammering the API
            time.sleep(random.uniform(0.5, 1.5)) 

    return results
