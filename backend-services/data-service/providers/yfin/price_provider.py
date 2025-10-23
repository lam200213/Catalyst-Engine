# backend-services/data-service/providers/yfin/price_provider.py
from curl_cffi import requests as cffi_requests
from curl_cffi.requests import errors as cffi_errors
import datetime as dt
import pandas as pd
import time # for throttling
import random # for throttling
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import yahoo_client # Use relative import
from helper_functions import is_ticker_delisted, mark_ticker_as_delisted
import os
import json

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

def get_stock_data(tickers: str | list[str], executor: ThreadPoolExecutor, start_date: dt.date = None, period: str = None, interval: str = "1d") -> dict | list | None:
    """
    Fetches historical stock data from Yahoo Finance using curl_cffi
    and formats it into the application's standard list-of-dictionaries format.
    Accepts an optional start_date for incremental fetches for single tickers, ie start_date is ignored for batch.
    Handles both single ticker (str) and multiple tickers (list).
    """    
    if isinstance(tickers, str):
        # Pre-flight check to see if we already know this ticker is delisted
        if is_ticker_delisted(tickers):
            logger.info(f"Skipping delisted ticker: {tickers}")
            return None
        return _get_single_ticker_data(tickers, start_date, period, interval)

    if isinstance(tickers, list):
        # Filter out known delisted tickers *before* making API calls.
        active_tickers = [t for t in tickers if not is_ticker_delisted(t)]
        
        if not active_tickers:
            logger.info("All tickers in the batch were identified as delisted. No API calls made.")
            return {} # Return an empty dict for a fully filtered batch

        results = {}
        # Create a future for each ticker
        # Note: start_date is ignored for batch requests for simplicity.
        # Each ticker is fetched individually.
        future_to_ticker = {
            executor.submit(_get_single_ticker_data, ticker, start_date=start_date, period=period, interval=interval): ticker 
            for ticker in active_tickers # Use the filtered list
        }
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

def _get_single_ticker_data(ticker: str, start_date: dt.date = None, period: str = None, interval: str = "1d") -> list | None:
    """
    Fetches historical stock data for a single ticker from Yahoo Finance.
    """

    # Sanitize the ticker symbol to handle special characters and whitespace.
    # This ensures tickers like 'BRK/B' become 'BRK-B' and 'ECC ' becomes 'ECC'.
    sanitized_ticker = ticker.strip().replace('/', '-')

    #  Introduce request throttling to avoid rate-limiting.
    # time.sleep(random.uniform(0.5, 1.5)) # Wait 0.5-1.5 seconds

    # param builder honoring start_date vs period
    def _build_chart_params(period: str | None, start_date: str | None, interval: str) -> dict:
        params = {"includePrePost": "false", "interval": interval}
        if start_date:
            start_ts = int(dt.datetime.combine(start_date, dt.time.min).timestamp())
            # Set end_ts to the end of yesterday to avoid fetching partial, real-time data.
            yesterday = dt.date.today() - dt.timedelta(days=1)
            end_ts = int(dt.datetime.combine(yesterday, dt.time.max).timestamp())
            
            params["period1"] = start_ts
            params["period2"] = end_ts
        else:
            params["range"] = period or "1y"
        return params 

    # --- Date Range Logic ---
    # This section determines the appropriate Yahoo Finance API URL based on whether
    # a `start_date` for an incremental fetch or a period (e.g., "1y") is provided. This supports incremental data fetching.

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sanitized_ticker}"
    params = _build_chart_params(period, start_date, interval=interval)
    try:
        resp_json = yahoo_client.execute_request(url, params=params)
    except cffi_errors.RequestsError as e:
        # Check if it's a 404 (delisted ticker)
        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
            logger.warning(f"Ticker {sanitized_ticker} returned 404, marking as delisted.")
            mark_ticker_as_delisted(sanitized_ticker, "Yahoo Finance API call failed with status 404 for chart data.")
            return None
        # For other HTTP errors (5xx, etc.), just return None without marking delisted
        logger.error(f"HTTP error fetching {sanitized_ticker}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {sanitized_ticker}: {e}")
        return None
    transformed_data = _transform_yahoo_response(resp_json, sanitized_ticker)

    # if transformed_data:
    #     # --- LOGGING/SAVING BLOCK ---
    #     try:
    #         log_dir = os.path.join('/app/logs', 'price_fetches')
    #         date_str = dt.datetime.now().strftime('%Y-%m-%d')
    #         ticker_log_dir = os.path.join(log_dir, date_str)
    #         os.makedirs(ticker_log_dir, exist_ok=True)
    #         file_path = os.path.join(ticker_log_dir, f"{ticker}.json")

    #         with open(file_path, 'w') as f:
    #             json.dump(transformed_data, f, indent=4)

    #         logger.debug(f"Successfully saved price data for {ticker} to {file_path}")

    #     except Exception as log_e:
    #         logger.error(f"Failed to save price fetch log for {ticker}: {log_e}")
    #     # --- END LOGGING/SAVING BLOCK ---

    return transformed_data # returns list[dict] or None
