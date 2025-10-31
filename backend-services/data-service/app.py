# data-service/app.py
import os
import pandas as pd
from flask import Flask, request, jsonify
from datetime import date, datetime, timedelta, timezone
import datetime as dt
from flask_caching import Cache
import pandas_market_calendars as mcal
import re
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from typing import List
import threading
from pydantic import TypeAdapter

# --- 1. Initialize Flask App and Basic Config ---
app = Flask(__name__)
PORT = int(os.environ.get('PORT', 3001))

# --- 2. Define Logging Setup Function ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handlers (console + rotating file), built once
    handlers = []

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    log_directory = "/app/logs"
    os.makedirs(log_directory, exist_ok=True)
    log_file = os.path.join(log_directory, "data_service.log")

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    app.logger.setLevel(log_level)
    app.logger.propagate = False
    
    # Clear existing handlers to avoid duplication
    for h in list(app.logger.handlers):
        app.logger.removeHandler(h)

    # Attach the handlers to app.logger
    for h in handlers:
        app.logger.addHandler(h)

    # prevent werkzeug from duplicating to root/stdout
    werk = logging.getLogger("werkzeug")
    werk.propagate = False
    for h in list(werk.handlers):
        if isinstance(h, logging.StreamHandler):
            werk.removeHandler(h)

    # Module loggers that should emit through the same handlers
    module_names = [
        "providers.yfin.yahoo_client",
        "providers.yfin.price_provider",
        "providers.yfin.financials_provider",
        "providers.yfin.market_data_provider",
        "providers.yfin.webshare_proxies",
        "helper_functions",
    ]
    for name in module_names:
        module_loggers = logging.getLogger(name)
        module_loggers.setLevel(log_level)
        module_loggers.propagate = False
        # Clear existing handlers
        for h in list(module_loggers.handlers):
            module_loggers.removeHandler(h)
        # Attach shared handlers
        for h in handlers:
            module_loggers.addHandler(h)

    app.logger.info("Data service logging initialized.")
# --- End of Logging Setup ---
setup_logging(app)

# --- 3. Import Project-Specific Modules ---
# Import provider modules
from providers import finnhub_provider, marketaux_provider
from providers.yfin import yahoo_client as yf_client 
from providers.yfin import price_provider as yf_price_provider
from providers.yfin import financials_provider as yf_financials_provider
from providers.yfin.market_data_provider import DayGainersSource, YahooSectorIndustrySource, NewHighsScreenerSource, MarketBreadthFetcher
# Import the logic
from helper_functions import check_market_trend_context, validate_and_prepare_financials, cache_covers_request, plan_incremental_price_fetch, finalize_price_response, compute_returns_for_period

from shared.contracts import ScreenerQuote

# --- Flask-Caching Setup ---
# Configuration for Redis Cache. The URL is provided by the environment.
config = {
    "CACHE_TYPE": "flask_caching.backends.rediscache.RedisCache",
    "CACHE_REDIS_URL": os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0'),
    "CACHE_DEFAULT_TIMEOUT": 300, # Default 5 minutes for routes without explicit timeout
    "CACHE_KEY_PREFIX": os.environ.get("CACHE_KEY_PREFIX", "datasvc:")
}

PRICE_CACHE_TTL = 1209600 # 14 days, 0 for indefinite
NEWS_CACHE_TTL = 604800 # 7 days
FINANCIALS_CACHE_TTL = 1209600 # 14 days
INDUSTRY_CACHE_TTL = 1209600 # 14 days
BREADTH_CACHE_TTL = int(os.getenv("BREADTH_CACHE_TTL", "86400")) # 1 day

app.config.from_mapping(config)
cache = Cache(app)
# --- End of Caching Setup ---

# --- Persistent DB Client Setup ---
# This client is for non-cache collections like market_trends.
try:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
    db_client = MongoClient(MONGO_URI)
    db = db_client.stock_analysis # Database name
    # Create the unique index for market_trends
    db.market_trends.create_index([("date", 1)], unique=True, name="date_unique_idx")
    app.logger.info("Persistent database connection initialized for market_trends.")
    # Create the unique index for delisted tickers
    db.ticker_status.create_index([("ticker", 1)], unique=True, name="ticker_unique_idx")
    app.logger.info("Persistent database connection initialized for delisted tickers")
except OperationFailure as e:
    app.logger.error(f"Could not create index on market_trends: {e}")
except Exception as e:
    app.logger.error(f"Failed to connect to persistent database: {e}")
    db = None
# --- End of Persistent DB Client Setup ---

# --- Initialize Yahoo Finance pool at startup ---
def _init_yf_pool_bg():
    try:
        size = int(os.getenv("YF_POOL_SIZE", "12"))
        yf_client.init_pool(size=size)
        app.logger.info(f"Initialized Yahoo Finance identity pool (size={size})")
    except Exception as e:
        app.logger.warning(f"Yahoo Finance pool initialization failed (background): {e}")
threading.Thread(target=_init_yf_pool_bg, daemon=True).start()

# --- Custom Exceptions ---
class ProviderNoDataError(Exception):
    """Custom exception raised when a data provider returns no data."""
    pass

# --- Centralized Executor ---
# Using a ThreadPoolExecutor for concurrent requests in batch endpoints
executor = ThreadPoolExecutor(max_workers=20)

@app.route('/financials/core/batch', methods=['POST'])
def get_batch_core_financials_route():
    """
    Provides core financial data for a batch of tickers, with data contract enforcement, in parallel.
    """
    payload = request.get_json()
    if not payload or 'tickers' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' is required."}), 400

    tickers = payload['tickers']
    if not isinstance(tickers, list) or not all(isinstance(ticker, str) for ticker in tickers):
        return jsonify({"error": "'tickers' must be a list of strings."}), 400

    if not tickers:
        return jsonify({"success": {}, "failed": []}), 200

    processed_data = {}
    tickers_to_fetch = []
    
    for ticker in tickers:
        # The 'financials_' prefix + the ticker is what the key_prefix='financials_%s' creates.
        cache_key = f"financials_{ticker}"
        cached_data = cache.get(cache_key)
        if cached_data:
            app.logger.info(f"Cache HIT for financials: {ticker}")
            # Validate cached data against the contract
            validated_cached_data = validate_and_prepare_financials(cached_data, ticker)
            if validated_cached_data:
                processed_data[ticker] = validated_cached_data
            else:
                 app.logger.warning(f"Cached financials data for {ticker} failed validation. Refetching.")
                 tickers_to_fetch.append(ticker)
        else:
            app.logger.info(f"Cache MISS for financials: {ticker}")
            tickers_to_fetch.append(ticker)

    # Fetch data from provider ONLY for the cache misses
    if tickers_to_fetch:
        fetched_data = yf_financials_provider.get_batch_core_financials(tickers_to_fetch, executor)

    failed_tickers = []

    for ticker in tickers_to_fetch:
        raw_data = fetched_data.get(ticker)
        # Use helper to validate and clean provider data
        final_data = validate_and_prepare_financials(raw_data, ticker)
        
        if final_data:
            processed_data[ticker] = final_data
            # Set cache for the newly fetched item
            cache.set(f"financials_{ticker}", final_data, timeout=FINANCIALS_CACHE_TTL)
            app.logger.info(f"CACHE INSERT for financials: {ticker}")
        else:
            # The helper function already logged the validation error
            failed_tickers.append(ticker)

    return jsonify({"success": processed_data, "failed": failed_tickers}), 200

@app.route('/financials/core/<path:ticker>', methods=['GET'])
def get_core_financials(ticker):
    """
    Provides core financial data for a given ticker, with caching.
    """
    app.logger.info(f"Request received for core financials: {ticker}")

    # Input validation
    if not re.match(r'^[A-Za-z0-9\.\-\^]+$', ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    cache_key = f"financials_{ticker}"
    cached_data = cache.get(cache_key)

    if cached_data:
        app.logger.info(f"Cache HIT for financials: {ticker}")
        # Validate cached data against the contract
        validated_cached_data = validate_and_prepare_financials(cached_data, ticker)
        if validated_cached_data:
            return jsonify(validated_cached_data)
        else:
            app.logger.warning(f"Cached financials data for {ticker} failed validation. Refetching.")
            # Continue to fetch new data as if it were a cache miss

    app.logger.info(f"Cache MISS for financials: {ticker}")
    # If not in cache, fetch from the provider
    raw_data = yf_financials_provider.get_core_financials(ticker)
    # Use helper to validate provider data
    final_data = validate_and_prepare_financials(raw_data, ticker)

    if final_data:
        cache.set(cache_key, final_data, timeout=FINANCIALS_CACHE_TTL)
        app.logger.info(f"CACHE INSERT for financials: {ticker}")
        return jsonify(final_data)
    else:
        # Helper function already logged the error
        return jsonify({"error": "Data not found or failed validation for ticker"}), 404

@app.route('/price/batch', methods=['POST'])
def get_batch_data():
    """
    Handles fetching data for a batch of tickers with incremental cache logic.
    - Checks cache for each ticker and validates coverage
    - For stale cache, performs incremental fetch
    - For cache miss, performs full fetch
    - Combines cached and newly fetched data.
    - Returns successful and failed tickers.
    """
    payload = request.get_json()
    if not payload or 'tickers' not in payload or 'source' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' and 'source' are required."}), 400

    tickers = payload['tickers']
    source = payload['source'].lower()
    
    if source not in ('yfinance', 'finnhub'):
        return jsonify({"error": "Invalid data source. Use 'finnhub' or 'yfinance'."}), 400

    if not isinstance(tickers, list):
        return jsonify({"error": "'tickers' must be a list of strings."}), 400

    # --- Handle Empty Ticker List ---
    if not tickers:
        return jsonify({"success": {}, "failed": []}), 200

    # --- Cache Access ---
    plans = {}
    cached_results = {}
    missed_tickers = {}   # key: (period, start_date) -> [tickers]
    tickers_for_incremental_fetch = []  # list of (ticker, start_date, cached)
    failed_tickers = set() # avoid duplicates

    # Extract requested period/start for coverage checks
    req_period = (payload.get('period') or "").lower()
    req_start = payload.get('start_date')

    # Find all documents where the ticker is in the requested list and source matches
    for ticker in tickers:
        cache_key = f"price_{source}_{ticker}"
        raw_cached = cache.get(cache_key)
        plan = plan_incremental_price_fetch(raw_cached, req_period, req_start)
        plans[ticker] = (cache_key, plan)

        if plan['action'] == 'return_cache':
            cached_results[ticker] = plan['cached']
        elif plan['action'] == 'fetch_full':
            key = (plan['period'], plan['start_date'])
            missed_tickers.setdefault(key, []).append(ticker)
        elif plan['action'] == 'fetch_incremental':
            tickers_for_incremental_fetch.append((ticker, plan['start_date'], plan['cached']))
        elif plan['action'] == 'error':
            failed_tickers.append(ticker)
        else:
            # Defensive fallback to avoid dropping any ticker
            failed_tickers.append(ticker)
        total_miss_tickers = sum(len(v) for v in missed_tickers.values())
    app.logger.info(f"Batch request. Cache hits: {len(cached_results)}, Cache misses: {len(missed_tickers)}, Cache miss tickers: {total_miss_tickers}")

    # --- Execute full fetches for Cache Misses ---
    results = cached_results
    failed_tickers = []

    if source == 'yfinance':
        for (period, start), group in missed_tickers.items():
            # ensure deduplication before provider call (keep as-is if already present)
            unique_group = list(dict.fromkeys(group))
            fetched = yf_price_provider.get_stock_data(unique_group, executor, start_date=start, period=period)

            for ticker in group:
                cache_key, plan = plans[ticker]
                data = fetched.get(ticker) if isinstance(fetched, dict) else None
                error_cotext = {
                    "ticker": ticker,
                    "message_500": f"Could not retrieve valid price data for {ticker}.",
                    "message_404": f"Could not retrieve price data for {ticker} from {source}.",
                }
                final_json, status = finalize_price_response(
                    cache_key, plan, data, cache=cache, ttl_seconds=PRICE_CACHE_TTL, error_context=error_cotext
                )
                if status == 200:
                    results[ticker] = final_json
                else:
                    failed_tickers.append(ticker)

        # Execute incremental fetches per ticker and merge
        for ticker, start, _cached in tickers_for_incremental_fetch:
            cache_key, plan = plans[ticker]
            data = yf_price_provider.get_stock_data(ticker, executor, start_date=start, period=None)
            error_cotext = {
                "ticker": ticker,
                "message_500": f"Could not retrieve valid price data for {ticker}.",
                "message_404": f"Could not retrieve price data for {ticker} from {source}.",
            }
            final_json, status = finalize_price_response(cache_key, plan, data, cache=cache, ttl_seconds=PRICE_CACHE_TTL, error_context=error_cotext)
            if status == 200:
                results[ticker] = final_json
            else:
                failed_tickers.append(ticker)
    else:
        # finnhub: per-ticker fetch path (no batch API)
        all_to_fetch = [ticker for group in missed_tickers.values() for ticker in group]
        for t in all_to_fetch:
            if t in results: # Should not happen with new logic, but safe to keep
                continue
            cache_key, plan = plans[t]
            data = finnhub_provider.get_stock_data(t)
            error_ctx = {
                "ticker": t,
                "message_500": f"Could not retrieve valid price data for {t}.",
                "message_404": f"Could not retrieve price data for {t} from {source}.",
            }
            final_json, status = finalize_price_response(
                cache_key, plan, data, cache=cache, ttl_seconds=PRICE_CACHE_TTL, error_context=error_ctx
            )
            if status == 200:
                results[t] = final_json
            else:
                failed_tickers.append(t)
    return jsonify({"success": results, "failed": sorted(list(failed_tickers))}), 200

@app.route('/price/<path:ticker>', methods=['GET'])
def get_data(ticker: str):
    if not re.match(r'^[A-Za-z0-9\.\-\^]+$', ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    source = request.args.get('source', 'yfinance').lower()
    if source not in ('yfinance', 'finnhub'):
    # Restore original error text (single route)
        return jsonify({"error": "Invalid data source. Use 'finnhub' or 'yfinance'."}), 400

    app.logger.info(f"Request received for price data. Ticker: {ticker}, Source: {source}")

    # --- Incremental Cache Logic ---
    # This logic determines whether to perform a full data fetch or an incremental one.
    # It checks for existing cached data and its freshness.
    cache_key = f"price_{source}_{ticker}"

    raw_cached = cache.get(cache_key)
    plan = plan_incremental_price_fetch(
        raw_cached,
        request.args.get('period'),
        request.args.get('start_date'),
    )

    if plan['action'] == 'return_cache':
        return jsonify(plan['cached']), 200

    # Map plan to provider call
    if source == 'yfinance':
        data = yf_price_provider.get_stock_data(
            ticker, executor,
            start_date=plan['start_date'],
            period=plan['period']
        )
    elif source == 'finnhub':
        data = finnhub_provider.get_stock_data(ticker)
    else:
        return jsonify({"error": "Invalid data source"}), 400

    error_context = {
        "ticker": ticker,
        "message_500": f"Could not retrieve valid price data for {ticker}.",
        "message_404": f"Could not retrieve price data for {ticker} from {source}.",
    }

    final_json, status = finalize_price_response(
        cache_key, plan, data, cache=cache, ttl_seconds=PRICE_CACHE_TTL, error_context=error_context
    )
    return jsonify(final_json), status

# Helper function for caching news data as a dict.
@cache.cached(timeout=NEWS_CACHE_TTL, key_prefix='news_%s', unless=lambda result: result is None)
def get_news_cached(ticker: str):
    """Helper function that fetches and returns news data (dict). Cachable."""
    app.logger.info(f"DATA-SERVICE: Cache MISS for news: {ticker}")
    news_data = marketaux_provider.get_news_for_ticker(ticker)
    if news_data is not None:
        app.logger.info(f"CACHE INSERT for news: {ticker}")
    return news_data

@app.route('/news/<string:ticker>', methods=['GET'])
def get_news(ticker: str):    
    # Fetch from provider
    try:
        news_data = get_news_cached(ticker)
        
        if news_data is not None:
            # Store in cache
            return jsonify(news_data)
        else:
            return jsonify({"error": f"Could not retrieve news for {ticker}."}), 404

    except Exception as e:
        app.logger.error(f"Error fetching news for {ticker}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

# Endpoint to manually clear the cache
@app.route('/cache/clear', methods=['POST'])
def clear_cache():
    """
    Manually clears specified application caches from Redis.
    - If no type is specified or type is 'all', clears all caches.
    - If a type ('price', 'news', 'financials', 'industry') is specified,
      clears only that cache.
    """
    app.logger.info(f"Received /cache/clear request with payload: {request.get_json(silent=True)}")
    payload = request.get_json(silent=True) or {}
    cache_type = payload.get('type')

    try:
        # Use the configured prefix; default should match your app config
        prefix = app.config.get("CACHE_KEY_PREFIX", "datasvc:")

        # Use the underlying redis client (Flask-Caching Redis backend)
        redis_client = cache.cache._write_client  # type: ignore[attr-defined]

        # When 'all', only delete keys with this service's prefix (safer than flushdb)
        if not cache_type or cache_type == 'all':
            total_deleted = 0
            # SCAN to avoid blocking
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=f"{prefix}*",
                                                 count=1000)  # tune COUNT as needed
                if keys:
                    total_deleted += len(keys)
                    redis_client.delete(*keys)
                if cursor == 0:
                    break
            message = f"Cleared {total_deleted} entries for prefix '{prefix}'"
            app.logger.info(message)
            # The market_trends collection is persistent storage, not a cache, so it is managed separately.
            # It can be cleared if needed using direct DB access, but is excluded from the general cache clear.
            return jsonify({"message": message, "keys_deleted": total_deleted}), 200

        valid_types = {
            'price': ['price_*'],
            'news': ['news_*'],
            'financials': ['financials_*'],
            'industry': ['peers_*', 'industry_candidates_*', 'day_gainers_*'],
            'breadth': ['breadth_*'], 
        }

        all_keys = []  # preserve order
        seen_keys = set()

        if cache_type not in valid_types:
            return jsonify({
                "error": f"Invalid cache type '{cache_type}'. Valid types are: {list(valid_types.keys())} or 'all'."
            }), 400

        total_deleted = 0
        suffixes = valid_types[cache_type]

        for suffix in suffixes:
            pattern = f"{prefix}{suffix}"
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=1000)
                if keys:
                    # append in order but dedupe
                    for k in keys:
                        if k not in seen_keys:
                            all_keys.append(k)
                            seen_keys.add(k)
                if cursor == 0:
                    break

        total_deleted = len(all_keys)

        if total_deleted:
            # delete in discovered order
            redis_client.delete(*all_keys)

        message = f"Cleared {total_deleted} entries from the '{cache_type}' cache."
        app.logger.info(message)
        return jsonify({"message": message, "keys_deleted": total_deleted}), 200

    except Exception as e:
        app.logger.error(f"Error clearing cache: {e}", exc_info=True)
        return jsonify({"error": "Failed to clear caches.", "details": str(e)}), 500

    
# Helper function for caching industry/peers data as a dict.
@cache.cached(timeout=INDUSTRY_CACHE_TTL, key_prefix='peers_%s')
def get_industry_peers_cached(ticker: str):
    """
    Helper function that fetches industry/peers data.
    Raises ProviderNoDataError if the provider returns no data.
    """
    app.logger.info(f"DATA-SERVICE: Cache MISS for industry/peers: {ticker}")
    data = finnhub_provider.get_company_peers_and_industry(ticker)
    
    # If the provider had a total failure, it returns None.
    if data is None:
        app.logger.warning(f"DATA-SERVICE: Provider returned None for {ticker}. Caching default empty result.")
        return

    # If the provider returned data but the peers list is empty, log it.
    if not data.get("peers"):
        app.logger.warning(f"DATA-SERVICE: Provider returned data with an empty peer list for {ticker}. This is now a valid, non-error state.")

    if data and data.get('peers'):
        app.logger.info(f"CACHE INSERT for industry/peers: {ticker}")
        return data

    # In all successful cases (with or without peers), return the data.
    return data

@app.route('/industry/peers/<path:ticker>', methods=['GET'])
def get_industry_peers(ticker: str):
    """
    Provides company peers and industry classification for a given ticker, with caching.
    """
    if not re.match(r'^[A-Za-z0-9\.\-\^]+$', ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    data = get_industry_peers_cached(ticker)

    if not data or not data.get("peers"):
        app.logger.warning(f"Finnhub returned no peers for {ticker}. Returning None as per service logic.")
        return jsonify({"error": f"No industry peers found for ticker {ticker}"}), 404

    # Filter out delisted tickers from the peer list.
    if data and data.get('peers'):
        if db is not None:
            try:
                # 1. Get the raw list of peers
                raw_peers = data['peers']
                
                # 2. Query the database for delisted tickers that are in our peer list
                delisted_docs = db.ticker_status.find(
                    {"ticker": {"$in": raw_peers}, "status": "delisted"},
                    {"ticker": 1, "_id": 0}
                )
                delisted_set = {doc['ticker'] for doc in delisted_docs}

                if delisted_set:
                    # 3. Clean the peer list
                    active_peers = [p for p in raw_peers if p not in delisted_set]
                    app.logger.info(f"Removed {len(delisted_set)} delisted peers for {ticker}. Original: {len(raw_peers)}, Clean: {len(active_peers)}")
                    data['peers'] = active_peers
                
            except Exception as e:
                app.logger.error(f"Failed to filter delisted peers for {ticker}: {e}")
                # Return unfiltered data on error to avoid breaking the request
        return jsonify(data)
    elif data:
        # Data exists but no peers list, return as is
        return jsonify(data)
    else:
        return jsonify({"error": "Data not found for ticker"}), 404

@app.route('/market-trend/calculate', methods=['POST'])
def calculate_market_trend():
    """
    On-demand endpoint to correctly calculate, store, and return market trend for specific historical dates.
    """
    payload = request.get_json()
    if not payload or 'dates' not in payload or not isinstance(payload['dates'], list):
        return jsonify({"error": "Invalid payload. 'dates' list is required."}), 400

    raw_dates = sorted(list(set(payload['dates']))) # Unique and sorted
    if not raw_dates:
        return jsonify({"trends": [], "failed_dates": []}), 200

    # Use a market calendar to get only valid trading days
    nyse = mcal.get_calendar('NYSE')
    start_date_for_calendar = raw_dates[0]
    end_date_for_calendar = raw_dates[-1]
    schedule = nyse.schedule(start_date=start_date_for_calendar, end_date=end_date_for_calendar)
    
    # Filter the requested dates to only include valid market open days
    valid_trading_dates_set = set(schedule.index.strftime('%Y-%m-%d'))
    dates_to_process = [d for d in raw_dates if d in valid_trading_dates_set]
    
    # Identify non-trading days to report back as "failed" upfront
    non_trading_days = [d for d in raw_dates if d not in valid_trading_dates_set]

    calculated_trends = []
    failed_dates = non_trading_days

    # Set a guard clause to handle cases where no valid trading dates are found
    # in the request after filtering. This prevents the IndexError.
    if not dates_to_process:
        app.logger.warning(f"No valid trading dates to process from the request payload after filtering. Raw dates: {raw_dates}")
        return jsonify({"trends": calculated_trends, "failed_dates": raw_dates}), 200

    indices = ['^GSPC', '^DJI', '^IXIC']
    
    # --- 1. Fetch Sufficient Historical Data ---
    # Fetch ~1.5 years of data to ensure 50-day SMA can be calculated for all dates.
    # Convert the first date string to a datetime object for calculation.
    first_date_obj = datetime.strptime(dates_to_process[0], '%Y-%m-%d').date()
    # Perform the date subtraction.
    start_date_for_fetch = first_date_obj - timedelta(days=550)
    
    # Use the batch price fetcher for efficiency.
    batch_price_data = yf_price_provider.get_stock_data(indices, executor, start_date=start_date_for_fetch)

    # Robust check to ensure the provider returned valid data for all indices, not just None.
    if not batch_price_data or not all(batch_price_data.get(idx) for idx in indices):
        app.logger.error(f"Failed to fetch historical data for one or more major indices. Data received: {batch_price_data}")
        return jsonify({"error": "Failed to fetch historical data for one or more major indices."}), 503

    # --- 2. Process Data with Pandas for Efficient Lookups ---
    index_dfs = {}
    for index in indices:
        df = pd.DataFrame(batch_price_data[index])
        df['formatted_date'] = pd.to_datetime(df['formatted_date'])
        df.set_index('formatted_date', inplace=True)
        # Calculate all required indicators for the entire series at once
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        df['high_52_week'] = df['high'].rolling(window=252).max()
        df['low_52_week'] = df['low'].rolling(window=252).min()
        index_dfs[index] = df

    # --- 3. Iterate Through Requested Dates and Calculate Trend ---
    for date_str in dates_to_process:
        try:
            target_date = pd.to_datetime(date_str)
            index_data_for_date = {}

            # For each index, get the price and pre-calculated indicators for the target date
            for index in indices:
                df = index_dfs[index]
                # Use .loc to get data for the specific date
                day_data = df.loc[target_date]
                index_data_for_date[index] = {
                    'current_price': day_data['close'],
                    'sma_50': day_data['sma_50'],
                    'sma_200': day_data['sma_200'],
                    'high_52_week': day_data['high_52_week'],
                    'low_52_week': day_data['low_52_week']
                }

            # Now call the trend logic function with correct historical data
            details = {}
            check_market_trend_context(index_data_for_date, details)
            trend_result = details.get('market_trend_context')

             # Data Integrity Check - Only store valid, non-null results
            if trend_result and trend_result.get('trend') is not None:
                document = {
                    "date": date_str,
                    "trend": trend_result.get("trend"),
                    "pass": trend_result.get("pass"),
                    "details": trend_result.get("index_trends"),
                    "createdAt": datetime.now(timezone.utc)
                }
                db.market_trends.update_one({'date': date_str}, {'$set': document}, upsert=True)
                calculated_trends.append(document)
            else:
                # If trend calculation returns None or fails, log it as a failure.
                raise KeyError("Trend calculation resulted in a null or invalid value.")

        except (KeyError, IndexError) as e:
            # This happens if the date is a trading day but data is still missing from provider
            app.logger.warning(f"Could not calculate market trend for date {date_str}: No data available. Details: {e}")
            failed_dates.append(date_str)
        except Exception as e:
            app.logger.error(f"An unexpected error occurred processing date {date_str}: {e}")
            failed_dates.append(date_str)

    return jsonify({"trends": calculated_trends, "failed_dates": failed_dates}), 200

@app.route('/market-trends', methods=['GET'])
def get_market_trends():
    """
    Retrieves stored market trends, optionally filtered by a date range, in ascending order
    """
    if db is None:
        return jsonify({"error": "Database connection is not available."}), 503
    
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        query = {}
        if start_date_str and end_date_str:
            # Build query to filter by date string field
            query["date"] = {"$gte": start_date_str, "$lte": end_date_str}
        
        # Query the database in ascending order
        trends_cursor = db.market_trends.find(query, {'_id': 0}).sort("date", 1)
        
        trends_list = []
        for trend in trends_cursor:
            # Access the 'trend' field, not 'status'
            trends_list.append({
                "date": trend.get('date'),
                "trend": trend.get('trend') 
            })

        return jsonify(trends_list), 200
    except Exception as e:
        app.logger.error(f"Error in get_market_trends: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

@app.route('/market/sectors/industries', methods=['GET'])
def get_sector_industry_candidates():
    """Provides a list of potential leader stocks sourced from yfinance sectors."""
    try:
        region = (request.args.get("region") or "US").upper()
        cache_key = f"industry_candidates_{region}"
        cached = cache.get(cache_key)
        if cached:
            return jsonify(cached), 200
        source = YahooSectorIndustrySource()
        data = source.get_industry_top_tickers(region=region)
        if data:
            cache.set(cache_key, data, timeout=INDUSTRY_CACHE_TTL)
            return jsonify(data), 200
        if not data:
            logging.warning("sectors/industries returned no quotes; Yahoo response likely empty or blocked.")
            # fallback to day_gainers to avoid 404 and client timeouts
            try:
                fallback = DayGainersSource().get_industry_top_tickers()
                if fallback:
                    app.logger.info("Serving fallback day_gainers map for sectors/industries request.")
                    return jsonify(fallback), 200
            except Exception as _e:
                app.logger.warning(f"Day gainers fallback failed: {_e}")
            return jsonify({"message": "Could not retrieve sector/industry data."}), 404
        return jsonify(data), 200
    except Exception as e:
        logging.error(f"Failed in /market/sectors/industries: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/market/screener/day_gainers', methods=['GET'])
def get_day_gainers_candidates():
    """Provides a list of potential leader stocks sourced from the yfinance day_gainers screener."""
    try:
        region = (request.args.get("region") or "US").upper()
        cache_key = f"day_gainers_{region}"
        cached = cache.get(cache_key)
        if cached:
            return jsonify(cached), 200
        source = DayGainersSource()
        data = source.get_industry_top_tickers(region=region)
        if data:
            cache.set(cache_key, data, timeout=INDUSTRY_CACHE_TTL)
            return jsonify(data), 200
        if not data:
            logging.warning("day_gainers returned no quotes; Yahoo response likely empty or blocked.")
            return jsonify({"message": "Could not retrieve day gainers data."}), 404
        return jsonify(data), 200
    except Exception as e:
        logging.error(f"Failed in /market/screener/day_gainers: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/data/return/batch', methods=['POST'])
def get_n_month_return_batch():
    """
    Calculates the percentage return for a batch of tickers over the requested yfinance period.
    Request: { "tickers": [...], "period": "3mo" }  # period optional; defaults to 3mo
    Response: { "AAPL": 12.34, "MSFT": 9.87, ... }
    """
    data = request.get_json()
    tickers = data.get("tickers")

    if not tickers or not isinstance(tickers, list):
        return jsonify({"error": "Invalid or missing 'tickers' list in request body"}), 400

    # Default to 3mo; validate against known allowed YF periods when available
    period = (data.get("period") or "3mo").lower()
    try:
        from helper_functions import ALLOWED_YF_PERIODS  # reuse canonical set if present
        if period not in ALLOWED_YF_PERIODS:
            return jsonify({"error": f"Invalid period '{period}'. Allowed: {sorted(list(ALLOWED_YF_PERIODS))}"}), 400
    except Exception:
        pass  # Soft-accept if constant import not available; yfinance will error downstream if invalid   

    results = compute_returns_for_period(tickers, period)
    return jsonify(results), 200

@app.route('/data/return/1m/batch', methods=['POST'])
def get_one_month_return_batch():
    """
    Backward-compatible alias for 1-month returns. Use /data/return/batch with {"period":"1mo"}.
    Accepts: { "tickers": [...] } and returns { "TICK": float_or_null, ... }
    """
    data = request.get_json()
    tickers = data.get("tickers")

    if not tickers or not isinstance(tickers, list):
        return jsonify({"error": "Invalid or missing 'tickers' list in request body"}), 400

    results = compute_returns_for_period(tickers, "1mo")
    
    return jsonify(results), 200

@app.route('/market/screener/52w_highs', methods=['GET'])
def get_52w_highs_quotes():
    """
    Returns the full quotes list for current 52-week highs (US region by default).
    Query params: region=US|... (optional)
    Response: strictly validated against the ScreenerQuote contract.
    """
    region = (request.args.get('region') or os.getenv('YF_REGION_DEFAULT') or 'US').upper()
    try:
        src = YahooSectorIndustrySource()  # keep imported for consistency
        highs_src = NewHighsScreenerSource(region=region)
        quotes = highs_src.get_all_quotes() 
        # returns a wrapper object like {"finance":{"result":[{"total": N, "quotes":[{...}, ...], "offset": 0, ...}], "error": null}}
        # include symbol, region, quoteType, industry, sector (sometimes), regularMarketPrice, marketCap, and 52-week fields
        validator = TypeAdapter(List[ScreenerQuote])
        items = validator.validate_python(quotes)
        return jsonify([it.model_dump(mode="json") for it in items]), 200
    except Exception as e:
        app.logger.error(f"/market/screener/52w_highs failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch 52w highs"}), 500

@app.route('/market/breadth', methods=['GET'])
def get_market_breadth():
    """
    Returns aggregate breadth for US markets:
    { new_highs, new_lows, high_low_ratio }
    Query params: region=US|... (optional)
    """
    try:
        region = (request.args.get('region') or 'US').upper()
        cache_key = f"breadth_{region}"

        # Only treat a real dict as a cache hit to avoid MagicMock/json errors
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            app.logger.info(f"breadth cache HIT for region={region}")
            return jsonify(cached), 200

        # Compute on miss
        mbf = MarketBreadthFetcher(region=region)
        data = mbf.get_breadth()  # {'new_highs': int, 'new_lows': int, 'high_low_ratio': float}
        app.logger.info(f"breadth computed for region={region}")

        # Normalize response keys that tests assert on
        response = {
            "newhighs": data.get("new_highs", 0),
            "newlows": data.get("new_lows", 0),
            "ratio": data.get("high_low_ratio", 0.0),
        }

        # Best-effort cache set; do not fail the route on cache errors
        try:
            cache.set(cache_key, response, timeout=BREADTH_CACHE_TTL)
        except Exception as e:
            app.logger.debug(f"breadth cache SET failed for region={region}: {e}")

        return jsonify(response), 200

    except Exception as e:
        app.logger.error(f"Failed to fetch market breadth: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch market breadth"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    redis_ok = False
    mongo_ok = db is not None
    yf_pool_ready = False
    try:
        # Flask-Caching Redis backend write client
        rc = cache.cache._write_client  # type: ignore[attr-defined]
        redis_ok = bool(rc.ping())
    except Exception:
        redis_ok = False
    try:
        # Do not block on Yahoo; just report status
        yf_pool_ready = getattr(yf_client, "is_pool_ready", lambda: False)()
    except Exception:
        yf_pool_ready = False

    ok = redis_ok and mongo_ok  # core readiness for serving
    status = 200 if ok else 503
    return jsonify({"ok": ok, "redis": redis_ok, "mongo": mongo_ok, "yf_pool_ready": yf_pool_ready}), status

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)