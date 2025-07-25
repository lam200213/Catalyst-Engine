# backend-services/data-service/providers/yfinance_provider.py
from curl_cffi import requests
import datetime as dt
import time # Add time for throttling
import random # Add random for throttling
import pandas as pd
import logging
import time

# A list of user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
]

# Proxies are now loaded from an environment variable for better configuration management.
import os # Add os import for environment variable access
PROXIES = [p.strip() for p in os.getenv("YAHOO_FINANCE_PROXIES", "").split(',') if p.strip()]

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
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
    else:
        # If no start_date is given, default to a 1-year data range.
        # This is used for initial data population or full cache refreshes.
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"

    headers = {'User-Agent': _get_random_user_agent()}
    proxy = _get_random_proxy()

    try:
        response = requests.get(
            url,
            headers=headers,
            proxies=proxy,
            impersonate="chrome110",
            timeout=10
        )

        if response.status_code != 200:
            print(f"Yahoo Finance API returned status {response.status_code} for {ticker}")
            return None

        data = response.json()
        #  Pass ticker to transformation function
        return _transform_yahoo_response(data, ticker)

    except requests.errors.RequestsError as e:
        print(f"A curl_cffi request error occurred for {ticker}: {e}")
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
def get_core_financials(ticker_symbol):
    """
    Fetches core financial data points required for Leadership Profile screening.
    For S&P 500 (^GSPC), returns market data including current price, SMAs, and 52-week highs/lows.
    For other tickers, returns standard financial data.
    """
    try:
        start_time = time.time()

        # Special handling for major indices
        if ticker_symbol in ['^GSPC', '^DJI', 'QQQ']:
            # Get historical data for calculating SMAs and 52-week ranges
            hist = _get_single_ticker_data(ticker_symbol, start_date=dt.date.today() - dt.timedelta(days=365))

            if not hist:
                return None

            # Calculate required data points
            current_price = float(hist[-1]['close'])
            sma_50 = float(pd.DataFrame(hist)['close'].tail(50).mean())
            sma_200 = float(pd.DataFrame(hist)['close'].tail(200).mean()) if len(hist) >= 200 else sma_50
            high_52_week = float(pd.DataFrame(hist)['high'].max())
            low_52_week = float(pd.DataFrame(hist)['low'].min())

            data = {
                'current_price': current_price,
                'sma_50': sma_50,
                'sma_200': sma_200,
                'high_52_week': high_52_week,
                'low_52_week': low_52_week
            }
        else:
            # Fetch financial data from Yahoo Finance API
            url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=summaryDetail,assetProfile,financialData,defaultKeyStatistics,incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory"
            headers = {'User-Agent': _get_random_user_agent()}
            proxy = _get_random_proxy()

            response = requests.get(
                url,
                headers=headers,
                proxies=proxy,
                impersonate="chrome110",
                timeout=10
            )
            # --- START DEBUGGING BLOCK ---
            print("--- YAHOO FINANCE API DEBUG ---")
            print(f"Request URL: {url}")
            print(f"Status Code: {response.status_code}")
            try:
                # Attempt to pretty-print the JSON response for readability
                import json
                print(f"Raw Response JSON: {json.dumps(response.json(), indent=2)}")
            except Exception as json_e:
                print(f"Could not decode JSON. Raw Text: {response.text}")
                print(f"JSON Decode Error: {json_e}")
            print("--- END DEBUGGING BLOCK ---")
            # --- END DEBUGGING BLOCK ---

            if response.status_code != 200:
                print(f"Yahoo Finance API returned status {response.status_code} for {ticker_symbol}")
                return None

            # Robust data extraction to prevent crashes on null values
            info = response.json()['quoteSummary']['result'][0]

            # --- Safer Data Extraction ---
            # This pattern (e.g., info.get('key') or {}) prevents crashes if the API
            # returns a 'null' value for a key instead of an object.
            summary_detail = info.get('summaryDetail') or {}
            default_key_stats = info.get('defaultKeyStatistics') or {}
            asset_profile = info.get('assetProfile') or {}
            income_statement_history = info.get('incomeStatementHistory') or {}

            # Correctly parse and separate the financial statements
            income_statements = income_statement_history.get('incomeStatementHistory', [])
            
            # 1. Filter the raw statements first
            raw_annual = [s for s in income_statements if s.get('periodType') == 'ANNUAL']
            raw_quarterly = [s for s in income_statements if s.get('periodType') == 'QUARTERLY']
            
            # 2. Then transform the filtered lists
            annual_earnings_list = _transform_income_statements(raw_annual)
            quarterly_earnings_list = _transform_income_statements(raw_quarterly)
            quarterly_financials_list = quarterly_earnings_list

            data = {
                'marketCap': (summary_detail.get('marketCap') or {}).get('raw'),
                'sharesOutstanding': (default_key_stats.get('sharesOutstanding') or {}).get('raw'),
                'floatShares': (default_key_stats.get('floatShares') or {}).get('raw'),
                'ipoDate': (asset_profile.get('ipoDate') or {}).get('fmt'),
                'annual_earnings': annual_earnings_list,
                'quarterly_earnings': quarterly_earnings_list,
                'quarterly_financials': quarterly_financials_list
            }

        duration = time.time() - start_time
        logging.info(f"Yahoo Finance API call for {ticker_symbol} took {duration:.2f} seconds.")

        return data
    except Exception as e:
        print(f"Error fetching core financials for {ticker_symbol}: {e}")
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