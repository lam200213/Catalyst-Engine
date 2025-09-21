# backend-services/data-service/providers/yfin/price_provider.py
from curl_cffi import requests as cffi_requests
import datetime as dt
import pandas as pd
import time # for throttling
import random # for throttling
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import yahoo_client # Use relative import
from helper_functions import _mark_ticker_as_delisted

logger = logging.getLogger(__name__)

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

    crumb = yahoo_client._get_yahoo_auth()
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
        # Set end_ts to the end of yesterday to avoid fetching partial, real-time data.
        yesterday = dt.date.today() - dt.timedelta(days=1)
        end_ts = int(dt.datetime.combine(yesterday, dt.time.max).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?period1={start_ts}&period2={end_ts}&interval=1d&crumb={crumb}"
    elif period:
        # If a period is provided, use the 'range' parameter.
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}?range={period}&interval=1d&crumb={crumb}"
    else:
        # Enforce explicit control from the calling service.
        raise ValueError("Either start_date or period must be provided to fetch stock data.")


    headers = {'User-Agent': yahoo_client._get_random_user_agent()}
    proxy = yahoo_client._get_random_proxy()

    try:
        response = yahoo_client.session.get(
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
            if e.response.status_code == 404:
                _mark_ticker_as_delisted(ticker, "Yahoo Finance price API call failed with status 404.")
        logger.error(f"A curl_cffi request error occurred for {ticker}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in yfinance_provider for {ticker}: {e}")
        return None
