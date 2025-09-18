# data-service/app.py
import os
import pandas as pd
from flask import Flask, request, jsonify
from datetime import date, datetime, timedelta, timezone
import pandas_market_calendars as mcal
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError
import re
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler

# Import provider modules
from providers import yfinance_provider, finnhub_provider, marketaux_provider
# Import the logic
from helper_functions import check_market_trend_context

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 3001))

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
        'data_service.log',
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

    # Also set the app logger's level to ensure it processes messages.
    app.logger.setLevel(logging.INFO)

# --- End of Logging Setup ---
setup_logging(app)
app.logger.info("Data service logging initialized.")

# Global variables for MongoDB client and collections
client = None
db = None
price_cache = None
news_cache = None
financials_cache = None
industry_cache = None # New cache for industry data
market_trends = None # New collection for market trends

# Cache expiration times in seconds
PRICE_CACHE_TTL = 342800 # 2 days = 172800
NEWS_CACHE_TTL = 14400
INDUSTRY_CACHE_TTL = 86400 # 1 day = 86400

# Using a ThreadPoolExecutor for concurrent requests in batch endpoints
executor = ThreadPoolExecutor(max_workers=10)

# A helper function to make index creation robust
def _create_ttl_index(collection, field, ttl_seconds, name):
    """
    Creates a TTL index, handling conflicts if the TTL value has changed.
    """
    try:
        # Attempt to create the index with the new TTL and name
        collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
        app.logger.info(f"TTL index '{name}' on '{collection.name}' set to {ttl_seconds} seconds.")
    except OperationFailure as e:
        # Error code 85 is for "IndexOptionsConflict"
        if e.code == 85:
            app.logger.warning(f"Index conflict on '{collection.name}'. Dropping old index and recreating.")
            
            # Drop the index by its actual name, which caused the conflict.
            collection.drop_index(name)
            
            # Re-create the index with the correct TTL and new name
            collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
            app.logger.info(f"Successfully recreated TTL index with new name '{name}' on '{collection.name}'.")
        else:
            # For any other database error, re-raise the exception to halt startup
            raise

def init_db():
    global client, db, price_cache, news_cache, financials_cache, industry_cache, market_trends
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
    client = MongoClient(MONGO_URI)
    db = client.stock_analysis # Database name

    price_cache = db.price_cache # Collection for price data
    news_cache = db.news_cache   # Collection for news data
    financials_cache = db.financials_cache # Collection for financial data
    industry_cache = db.industry_cache # New collection for industry data
    market_trends = db.market_trends # New collection for market trends

    # Use the robust helper function to create/update TTL indexes
    _create_ttl_index(price_cache, "createdAt", PRICE_CACHE_TTL, "createdAt_ttl_index")
    _create_ttl_index(news_cache, "createdAt", NEWS_CACHE_TTL, "createdAt_ttl_index")
    _create_ttl_index(financials_cache, "createdAt", PRICE_CACHE_TTL, "createdAt_ttl_index_financials")
    _create_ttl_index(industry_cache, "createdAt", INDUSTRY_CACHE_TTL, "createdAt_ttl_index_industry")

    market_trends.create_index([("date", 1)], unique=True, name="date_unique_idx")
 
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
        cached_data = financials_cache.find_one({'ticker': ticker})
        if cached_data:
            app.logger.info(f"Cache HIT for financials: {ticker}")
            processed_data[ticker] = cached_data
            # Refresh TTL
            financials_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
        else:
            app.logger.info(f"Cache MISS for financials: {ticker}")
            tickers_to_fetch.append(ticker)

    # Fetch data from provider
    tickers_to_fetch = yfinance_provider.get_batch_core_financials(tickers, executor)

    failed_tickers = []

    for ticker, data in tickers_to_fetch.items():
        if data:
            # Enforce data contract
            total_revenue = data.get('totalRevenue')
            net_income = data.get('netIncome')
            market_cap = data.get('marketCap')

            # Validate and substitute if not numerical
            processed_total_revenue = total_revenue if isinstance(total_revenue, (int, float)) else 0
            processed_net_income = net_income if isinstance(net_income, (int, float)) else 0
            processed_market_cap = market_cap if isinstance(market_cap, (int, float)) else 0

            processed_data[ticker] = {
                "totalRevenue": processed_total_revenue,
                "netIncome": processed_net_income,
                "marketCap": processed_market_cap,
                **{k: v for k, v in data.items() if k not in ['totalRevenue', 'netIncome', 'marketCap']} # Keep other fields
            }
        else:
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

    cached_data = financials_cache.find_one({'ticker': ticker})
    if cached_data:
        app.logger.info(f"Cache HIT for financials: {ticker}")
        # Refresh TTL
        financials_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
        return jsonify(cached_data['data'])

    app.logger.info(f"Cache MISS for financials: {ticker}")
    # If not in cache, fetch from provider
    data = yfinance_provider.get_core_financials(ticker)

    if data:
        # Cache the new data
        financials_cache.insert_one({
            "ticker": ticker,
            "data": data,
            "createdAt": datetime.now(timezone.utc)
        })
        app.logger.info(f"CACHE INSERT for financials: {ticker}")
        return jsonify(data)
    else:
        return jsonify({"error": "Data not found for ticker"}), 404

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
        return jsonify({"success": [], "failed": []}), 200

    # --- Cache Lookup ---
    cached_results = {}
    # Find all documents where the ticker is in the requested list and source matches
    cached_cursor = price_cache.find({
        'ticker': {'$in': tickers},
        'source': source
    })
    for doc in cached_cursor:
        cached_results[doc['ticker']] = doc['data']

    # --- Identify Cache Misses ---
    cached_tickers = set(cached_results.keys())
    missed_tickers = [t for t in tickers if t not in cached_tickers]
    
    app.logger.info(f"Batch request. Cache hits: {len(cached_tickers)}, Cache misses: {len(missed_tickers)}")

    # --- Fetch Data for Cache Misses ---
    newly_fetched_data = {}
    failed_tickers = []

    if missed_tickers:
        if source == 'yfinance':
            period_to_fetch = "1y"
            fetched_data = yfinance_provider.get_stock_data(
                missed_tickers, 
                start_date=None, 
                period=period_to_fetch
            )

            if fetched_data:
                for ticker, data in fetched_data.items():
                    if data:
                        newly_fetched_data[ticker] = data
                    else:
                        failed_tickers.append(ticker)
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

    # --- Store Newly Fetched Data in Cache ---
    if newly_fetched_data:
        new_cache_entries = []
        for ticker, data in newly_fetched_data.items():
            new_cache_entries.append({
                "ticker": ticker,
                "source": source,
                "data": data,
                "createdAt": datetime.now(timezone.utc)
            })
        if new_cache_entries:
            price_cache.insert_many(new_cache_entries)
            app.logger.info(f"Cached {len(new_cache_entries)} new price entries.")

    # --- Combine Results and Return ---
    successful_data = {**cached_results, **newly_fetched_data}
    
    # The data is nested inside a list for each ticker, so we need to flatten it
    # flat_successful_data = [item for sublist in successful_data for item in sublist]

    return jsonify({
        "success": successful_data,
        "failed": failed_tickers
    }), 200

@app.route('/price/<string:ticker>', methods=['GET'])
def get_data(ticker: str):
    source = request.args.get('source', 'yfinance').lower()
    app.logger.info(f"Request received for price data. Ticker: {ticker}, Source: {source}")

    # --- Incremental Cache Logic ---
    # This logic determines whether to perform a full data fetch or an incremental one.
    # It checks for existing cached data and its freshness.
    cached_data = price_cache.find_one({"ticker": ticker, "source": source})
    new_start_date = None # This will be set if an incremental fetch is needed.

    if cached_data:
        # Ensure createdAt is timezone-aware for accurate comparison.
        created_at = cached_data['createdAt'].replace(tzinfo=timezone.utc) if cached_data['createdAt'].tzinfo is None else cached_data['createdAt']

        # Check if the cache entry is still within its Time-To-Live (TTL).
        if (datetime.now(timezone.utc) - created_at).total_seconds() < PRICE_CACHE_TTL:
            # If the cache is valid, check how recent the data is.
            if cached_data.get('data'):
                last_date_str = cached_data['data'][-1]['formatted_date']
                last_date = date.fromisoformat(last_date_str)

                # If the last data point is from yesterday or today, it's current enough.
                if last_date >= (date.today() - timedelta(days=1)):
                    app.logger.info(f"Cache HIT and data is current for price: {ticker}")
                    # Refresh the TTL to keep the entry alive.
                    price_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
                    return jsonify(cached_data['data'])

                # If data is old, set the start date for an incremental fetch.
                new_start_date = last_date + timedelta(days=1)
        else:
            # If the cache TTL has expired, treat it as a miss. A full fetch will occur.
            app.logger.warning(f"Cache EXPIRED for price: {ticker} from {source}")

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
        data = yfinance_provider.get_stock_data(
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
        if new_start_date and cached_data:
            # If it was an incremental fetch, append the new data to the existing cache.
            full_data = cached_data['data'] + data
            price_cache.update_one(
                {"_id": cached_data["_id"]},
                {"$set": {"data": full_data, "createdAt": datetime.now(timezone.utc)}}
            )
            app.logger.info(f"CACHE INCREMENTAL UPDATE for price: {ticker}")
            return jsonify(full_data)
        else:
            # If it was a full fetch, replace the old cache entry or insert a new one.
            update_data = {
                "ticker": ticker,
                "source": source,
                "data": data,
                "createdAt": datetime.now(timezone.utc)
            }
            price_cache.update_one(
                {"ticker": ticker, "source": source},
                {"$set": update_data},
                upsert=True # Creates the document if it doesn't exist.
            )
            app.logger.info(f"CACHE FULL REPLACE/INSERT for price: {ticker}")
            return jsonify(data)
    elif cached_data:
        # If the provider returned no new data but we have old data, return the old data.
        app.logger.info(f"No new price data for {ticker}. Returning existing cached data.")
        # Refresh the TTL to prevent the old data from being purged immediately.
        price_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
        return jsonify(cached_data['data'])
    else:
        # If there's no data from the provider and no cache, return an error.
        return jsonify({"error": f"Could not retrieve price data for {ticker} from {source}."}), 404

@app.route('/news/<string:ticker>', methods=['GET'])
def get_news(ticker: str):
    # Check cache
    cached_news = news_cache.find_one({"ticker": ticker})
    if cached_news:
        # Check if cached news is still valid (not expired)
        time_elapsed = (datetime.now(timezone.utc) - cached_news['createdAt']).total_seconds()
        if time_elapsed < NEWS_CACHE_TTL:
            app.logger.info(f"Cache HIT for news: {ticker}")
            return jsonify(cached_news['data'])
        else:
            app.logger.warning(f"Cache EXPIRED for news: {ticker}")
            news_cache.delete_one({"_id": cached_news["_id"]}) # Optionally delete expired entry immediately
        
    app.logger.info(f"DATA-SERVICE: Cache MISS for news: {ticker}")
    
    # Fetch from provider
    try:
        news_data = marketaux_provider.get_news_for_ticker(ticker)
        
        if news_data is not None:
            # Store in cache
            news_cache.insert_one({
                "ticker": ticker,
                "data": news_data,
                "createdAt": datetime.now(timezone.utc)
            })
            app.logger.info(f"CACHE INSERT for news: {ticker}")
            return jsonify(news_data)
        else:
            return jsonify({"error": f"Could not retrieve news for {ticker}."}), 404

    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

# Endpoint to manually clear the cache
@app.route('/cache/clear', methods=['POST'])
def clear_cache():
    """
    Manually drops the price and news cache collections from MongoDB.
    This is useful for forcing a data refresh after deploying application updates.
    """
    try:
        if price_cache is not None:
            price_cache.drop()
            app.logger.info("Dropped price_cache collection.")
        if news_cache is not None:
            news_cache.drop()
            app.logger.info("Dropped news_cache collection.")
        if financials_cache is not None:
            financials_cache.drop()
            app.logger.info("Dropped financials_cache collection.")
        if industry_cache is not None:
            industry_cache.drop()
            app.logger.info("Dropped industry_cache collection.")
        if market_trends is not None:
            market_trends.drop()
            app.logger.info("Dropped market_trends collection.")
            
        
        # Re-initialize the collections and their TTL indexes
        init_db()
        
        return jsonify({"message": "All data service caches have been cleared."}), 200

    except Exception as e:
        app.logger.error(f"Error clearing cache: {e}", exc_info=True)
        return jsonify({"error": "Failed to clear caches.", "details": str(e)}), 500
    
@app.route('/industry/peers/<path:ticker>', methods=['GET'])
def get_industry_peers(ticker: str):
    """
    Provides company peers and industry classification for a given ticker, with caching.
    """
    if not re.match(r'^[A-Za-z0-9\.\-\^]+$', ticker):
        return jsonify({"error": "Invalid ticker format"}), 400

    cached_data = industry_cache.find_one({'ticker': ticker})
    if cached_data:
        app.logger.info(f"Cache HIT for industry/peers: {ticker}")
        industry_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
        return jsonify(cached_data['data'])

    app.logger.info(f"DATA-SERVICE: Cache MISS for industry/peers: {ticker}")
    data = finnhub_provider.get_company_peers_and_industry(ticker)

    if data:
        industry_cache.insert_one({
            "ticker": ticker,
            "data": data,
            "createdAt": datetime.now(timezone.utc)
        })
        app.logger.info(f"CACHE INSERT for industry/peers: {ticker}")
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
    batch_price_data = yfinance_provider.get_stock_data(indices, start_date=start_date_for_fetch)

    if not all(idx in batch_price_data for idx in indices):
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
                market_trends.update_one({'date': date_str}, {'$set': document}, upsert=True)
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
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        query = {}
        if start_date_str and end_date_str:
            # Build query to filter by date string field
            query["date"] = {"$gte": start_date_str, "$lte": end_date_str}
        
        # Query the database in ascending order
        trends_cursor = market_trends.find(query, {'_id': 0}).sort("date", 1)
        
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
    init_db() # Initialize the database connection
    app.run(host='0.0.0.0', port=PORT)