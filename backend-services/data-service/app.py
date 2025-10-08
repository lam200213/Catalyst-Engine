# data-service/app.py
import os
import pandas as pd
from flask import Flask, request, jsonify
from datetime import date, datetime, timedelta, timezone
from flask_caching import Cache
import pandas_market_calendars as mcal
import re
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler
from pymongo import MongoClient, errors
from pymongo.errors import OperationFailure
from pydantic import ValidationError, TypeAdapter
from typing import List
from shared.contracts import PriceDataItem, CoreFinancials

# Import provider modules
from providers import finnhub_provider, marketaux_provider
from providers.yfin import price_provider as yf_price_provider
from providers.yfin import financials_provider as yf_financials_provider
# Import the logic
from helper_functions import check_market_trend_context, validate_and_prepare_financials, validate_and_prepare_price_data

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 3001))

# --- Flask-Caching Setup ---
# Configuration for Redis Cache. The URL is provided by the environment.
config = {
    "CACHE_TYPE": "flask_caching.backends.rediscache.RedisCache",
    "CACHE_REDIS_URL": os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0'),
    "CACHE_DEFAULT_TIMEOUT": 300 # Default 5 minutes for routes without explicit timeout
}

PRICE_CACHE_TTL = 1209600 # 14 days, 0 for indefinite
NEWS_CACHE_TTL = 604800 # 7 days
FINANCIALS_CACHE_TTL = 1209600 # 14 days
INDUSTRY_CACHE_TTL = 1209600 # 14 days

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

# --- Custom Exceptions ---
class ProviderNoDataError(Exception):
    """Custom exception raised when a data provider returns no data."""
    pass

# --- Logging Setup ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    log_directory = "/app/logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # The filename is now specific to the service and in a dedicated folder.
    log_file = os.path.join(log_directory, "data_service.log")

    # Create a rotating file handler to prevent log files from growing too large.
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)

    # Create a console handler for stdout
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Define the log format
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False

    # Find and configure the loggers from the provider and helper modules
    # This ensures that log messages from background threads are captured correctly.
    module_loggers = [
        logging.getLogger('providers.yfin.price_provider'),
        logging.getLogger('providers.yfin.financials_provider'),
        logging.getLogger('helper_functions')
    ]
    
    for logger_instance in module_loggers:
        logger_instance.addHandler(file_handler)
        logger_instance.addHandler(console_handler)
        logger_instance.setLevel(logging.INFO)

    app.logger.info("Data service logging initialized.")
# --- End of Logging Setup ---
setup_logging(app)

# Using a ThreadPoolExecutor for concurrent requests in batch endpoints
executor = ThreadPoolExecutor(max_workers=10)

@app.route('/financials/core/batch', methods=['POST'])
def get_batch_core_financials_route():
    """
    Provides core financial data for a batch of tickers, with data contract enforcement, in parallel.
    """
    payload = request.get_json()
    if not payload or 'tickers' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' is required."}), 400

    tickers = payload['tickers']
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
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
        fetched_data = yf_financials_provider.get_batch_core_financials(tickers_to_fetch)

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
    Handles fetching data for a batch of tickers.
    - Checks the cache for each ticker.
    - Fetches data from the provider for tickers not in the cache.
    - Combines cached and newly fetched data.
    - Returns successful and failed tickers.
    """
    payload = request.get_json()
    if not payload or 'tickers' not in payload or 'source' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' and 'source' are required."}), 400

    tickers = payload['tickers']
    source = payload['source'].lower()
    
    if not isinstance(tickers, list):
        return jsonify({"error": "'tickers' must be a list of strings."}), 400

    # --- Handle Empty Ticker List ---
    if not tickers:
        return jsonify({"success": {}, "failed": []}), 200

    # --- Cache Access ---
    cached_results = {}
    missed_tickers = []

    # Find all documents where the ticker is in the requested list and source matches
    for ticker in tickers:
        cache_key = f"price_{source}_{ticker}"
        data = cache.get(cache_key)
        if data:
            validated_data = validate_and_prepare_price_data(data, ticker)
            if validated_data:
                cached_results[ticker] = validated_data
            else:
                app.logger.warning(f"Cached price data for {ticker} is invalid, refetching.")
                missed_tickers.append(ticker)
        else:
            missed_tickers.append(ticker)

    app.logger.info(f"Batch request. Cache hits: {len(cached_results)}, Cache misses: {len(missed_tickers)}")

    # --- Fetch Data for Cache Misses ---
    newly_fetched_data = {}
    failed_tickers = []

    if missed_tickers:
        if source == 'yfinance':
            period_to_fetch = "1y"
            fetched_data = yf_price_provider.get_stock_data(
                missed_tickers, 
                start_date=None, 
                period=period_to_fetch
            )
            if fetched_data:
                for ticker, data in fetched_data.items():
                    # Validate newly fetched data and fix bug (was using CoreFinancials model)
                    final_data = validate_and_prepare_price_data(data, ticker)
                    if final_data:
                        newly_fetched_data[ticker] = final_data
                        cache.set(f"price_{source}_{ticker}", final_data, timeout=PRICE_CACHE_TTL)
                        app.logger.info(f"CACHE INSERT for price: {ticker}")
                    else:
                        failed_tickers.append(ticker)
            else: 
                failed_tickers.extend(missed_tickers)
        else:
            # For other sources, fetch one by one (or implement batch in their providers)
            for ticker in missed_tickers:
                data = None
                if source == 'finnhub':
                    data = finnhub_provider.get_stock_data(ticker)
                
                if data:
                    newly_fetched_data[ticker] = data
                else:
                    failed_tickers.append(ticker)

    # --- Combine Results and Return ---
    successful_data = {**cached_results, **newly_fetched_data}
    
    # The data is nested inside a list for each ticker, so we need to flatten it
    # flat_successful_data = [item for sublist in successful_data for item in sublist]

    return jsonify({
        "success": successful_data,
        "failed": failed_tickers
    }), 200

@app.route('/price/<path:ticker>', methods=['GET'])
def get_data(ticker: str):
    if not re.match(r'^[A-Za-z0-9\.\-\^]+$', ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    source = request.args.get('source', 'yfinance').lower()
    app.logger.info(f"Request received for price data. Ticker: {ticker}, Source: {source}")

    # --- Incremental Cache Logic ---
    # This logic determines whether to perform a full data fetch or an incremental one.
    # It checks for existing cached data and its freshness.
    cache_key = f"price_{source}_{ticker}"
    cached_data = cache.get(cache_key)
    new_start_date = None # This will be set if an incremental fetch is needed.

    if cached_data:
        # Validate the cached data first
        validated_cached_data = validate_and_prepare_price_data(cached_data, ticker)
        if validated_cached_data:
            # If the cache is valid, check how recent the data is.
            last_date_str = validated_cached_data[-1]['formatted_date']
            last_date = date.fromisoformat(last_date_str)
            # If the last data point is from yesterday or today, it's current enough.
            if last_date >= (date.today() - timedelta(days=1)):
                app.logger.info(f"Cache HIT and data is current for price: {ticker}")
                return jsonify(validated_cached_data)
            # If data is old, set the start date for an incremental fetch.
            new_start_date = last_date + timedelta(days=1)
            cached_data = validated_cached_data # Use the validated version for appending later, resetting the TTL
        else:
            app.logger.warning(f"Cached data for {ticker} failed validation. Performing full fetch.")
            cached_data = None # Invalidate broken cache data

    # --- Data Fetching ---
    # Based on the cache check, decide whether to fetch full or incremental data.
    if new_start_date:
        app.logger.info(f"Incremental Cache MISS for price: {ticker}. Fetching from {new_start_date}.")
    else:
        app.logger.info(f"Full Cache MISS for price: {ticker} from {source}")

    data = None
    if source == 'yfinance':
        # If no new_start_date is given, default to a 1-year data range.
        # This is used for initial data population or full cache refreshes.
        # Otherwise, an incremental fetch is performed using start_date.
        period_to_fetch = "1y" if not new_start_date else None
        # yfinance supports incremental fetching via the `start_date` parameter.
        data = yf_price_provider.get_stock_data(
            ticker, 
            start_date=new_start_date, 
            period=period_to_fetch
        )
    elif source == 'finnhub':
        # Finnhub provider currently only supports full fetches.
        data = finnhub_provider.get_stock_data(ticker)
    else:
        return jsonify({"error": "Invalid data source. Use 'finnhub' or 'yfinance'."}), 400

    # --- Cache and Response Handling ---
    if data:
        # Validate new data from provider
        validated_data = validate_and_prepare_price_data(data, ticker)
        if not validated_data:
            # If validation fails, return error or stale cache
            if cached_data:
                app.logger.warning(f"Returning stale but valid cache for {ticker} due to provider failure.")
                return jsonify(cached_data)
            return jsonify({"error": f"Could not retrieve valid price data for {ticker}."}), 500

        if new_start_date and cached_data:
            # If it was an incremental fetch, append the new data to the existing cache.
            full_data = cached_data + data
            cache.set(cache_key, full_data, timeout=PRICE_CACHE_TTL)
            app.logger.info(f"CACHE INCREMENTAL UPDATE for price: {ticker}")
            return jsonify(full_data)
        else:
            # If it was a full fetch, replace the old cache entry or insert a new one.
            cache.set(cache_key, data, timeout=PRICE_CACHE_TTL)
            app.logger.info(f"CACHE FULL REPLACE/INSERT for price: {ticker}")
            return jsonify(data)
    elif cached_data:
        # If the provider returned no new data but we have old data, return the old data.
        app.logger.info(f"No new price data for {ticker}. Returning existing cached data.")
        return jsonify(cached_data)
    else:
        # If there's no data from the provider and no cache, return an error.
        return jsonify({"error": f"Could not retrieve price data for {ticker} from {source}."}), 404

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
        if not cache_type or cache_type == 'all':
            cache.clear()
            message = "All data service caches have been cleared."
            # The market_trends collection is persistent storage, not a cache, so it is managed separately.
            # It can be cleared if needed using direct DB access, but is excluded from the general cache clear.
            app.logger.info(message)
            return jsonify({"message": message}), 200

        valid_types = {
            'price': 'price_*',
            'news': 'news_*',
            'financials': 'financials_*',
            'industry': 'peers_*'  # User 'industry' maps to internal 'peers_' prefix
        }

        if cache_type not in valid_types:
            return jsonify({
                "error": f"Invalid cache type '{cache_type}'. Valid types are: {list(valid_types.keys())} or 'all'."
            }), 400
        
        # Get config from the Flask app object, not the cache object.
        prefix = app.config.get("CACHE_KEY_PREFIX", "flask_cache_")
        pattern = f"{prefix}{valid_types[cache_type]}"

        # Use the underlying redis client
        redis_client = cache.cache._write_client
        keys_to_delete = redis_client.keys(pattern)

        if keys_to_delete:
            redis_client.delete(*keys_to_delete)
            message = f"Cleared {len(keys_to_delete)} entries from the '{cache_type}' cache."
            app.logger.info(message)
            return jsonify({"message": message, "keys_deleted": len(keys_to_delete)}), 200
        else:
            message = f"No entries found in the '{cache_type}' cache to clear."
            app.logger.info(message)
            return jsonify({"message": message, "keys_deleted": 0}), 200

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
        raise ProviderNoDataError(f"No peer data found for {ticker}")

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
    batch_price_data = yf_price_provider.get_stock_data(indices, start_date=start_date_for_fetch)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)