from curl_cffi import requests
import datetime as dt
import random
import time

# A list of user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
]

# In a real-world scenario, this would be a more extensive and dynamic list of proxies.
# For this example, we'll use a small, static list.
PROXIES = [
    # Add your proxy URLs here, e.g., "http://user:pass@host:port"
]

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

def get_stock_data(ticker: str, start_date: dt.date = None) -> list | None:
    """
    Fetches historical stock data from Yahoo Finance using curl_cffi
    and formats it into the application's standard list-of-dictionaries format.
    Accepts an optional start_date for incremental fetches.
    """
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
        session = requests.AsyncSession()
        response = session.get(
            url,
            headers=headers,
            proxies=proxy,
            impersonate="chrome110",
            timeout=10
        ).result()

        if response.status_code != 200:
            print(f"Yahoo Finance API returned status {response.status_code} for {ticker}")
            return None

        data = response.json()
        # Latest Add: Pass ticker to transformation function
        return _transform_yahoo_response(data, ticker)

    except Exception as e:
        print(f"Error fetching data from yfinance with curl_cffi for {ticker}: {e}")
        return None