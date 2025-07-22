# data-service/app.py
import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import date, datetime, timedelta, timezone
from pymongo.errors import OperationFailure

# Import provider modules
from providers import yfinance_provider, finnhub_provider, marketaux_provider

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 3001))

# Global variables for MongoDB client and collections
client = None
db = None
price_cache = None
news_cache = None

# Cache expiration times in seconds
PRICE_CACHE_TTL = 172800 # 2 days
NEWS_CACHE_TTL = 14400

# A helper function to make index creation robust
def _create_ttl_index(collection, field, ttl_seconds, name):
    """
    Creates a TTL index, handling conflicts if the TTL value has changed.
    """
    try:
        # Attempt to create the index with the new TTL and name
        collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
        print(f"TTL index '{name}' on '{collection.name}' is set to {ttl_seconds} seconds.")
    except OperationFailure as e:
        # Error code 85 is for "IndexOptionsConflict"
        if e.code == 85:
            print(f"Index conflict on '{collection.name}'. Dropping old index and recreating.")
            
            # drop the OLD, default-named index.
            # The default name for an index on a single field is 'field_1'.
            old_index_name = f"{field}_1"
            collection.drop_index(old_index_name)
            
            # Re-create the index with the correct TTL and new name
            collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
            print(f"Successfully recreated TTL index with new name '{name}' on '{collection.name}'.")
        else:
            # For any other database error, re-raise the exception to halt startup
            raise

def init_db():
    global client, db, price_cache, news_cache
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
    client = MongoClient(MONGO_URI)
    db = client.stock_analysis # Database name

    price_cache = db.price_cache # Collection for price data
    news_cache = db.news_cache   # Collection for news data

    # Use the robust helper function to create/update TTL indexes
    _create_ttl_index(price_cache, "createdAt", PRICE_CACHE_TTL, "createdAt_ttl_index")
    _create_ttl_index(news_cache, "createdAt", NEWS_CACHE_TTL, "createdAt_ttl_index")

@app.route('/data/<string:ticker>', methods=['GET'])
def get_data(ticker: str):
    source = request.args.get('source', 'yfinance').lower()
    print(f"Received request for ticker: {ticker}, source: {source}")

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
                    print(f"DATA-SERVICE: Cache HIT and data is current for price: {ticker}")
                    # Refresh the TTL to keep the entry alive.
                    price_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
                    return jsonify(cached_data['data'])

                # If data is old, set the start date for an incremental fetch.
                new_start_date = last_date + timedelta(days=1)
        else:
            # If the cache TTL has expired, treat it as a miss. A full fetch will occur.
            print(f"Cache EXPIRED for price: {ticker} from {source}")

    # --- Data Fetching ---
    # Based on the cache check, decide whether to fetch full or incremental data.
    if new_start_date:
        print(f"DATA-SERVICE: Incremental Cache MISS for price: {ticker}. Fetching from {new_start_date}.")
    else:
        print(f"DATA-SERVICE: Full Cache MISS for price: {ticker} from {source}")

    data = None
    if source == 'yfinance':
        # yfinance supports incremental fetching via the `start_date` parameter.
        data = yfinance_provider.get_stock_data(ticker, start_date=new_start_date)
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
            print(f"DATA-SERVICE: CACHE INCREMENTAL UPDATE for price: {ticker}")
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
            print(f"DATA-SERVICE: CACHE FULL REPLACE/INSERT for price: {ticker}")
            return jsonify(data)
    elif cached_data:
        # If the provider returned no new data but we have old data, return the old data.
        print(f"DATA-SERVICE: No new price data for {ticker}. Returning existing cached data.")
        # Refresh the TTL to prevent the old data from being purged immediately.
        price_cache.update_one({"_id": cached_data["_id"]}, {"$set": {"createdAt": datetime.now(timezone.utc)}})
        return jsonify(cached_data['data'])
    else:
        # If there's no data from the provider and no cache, return an error.
        return jsonify({"error": f"Could not retrieve price data for {ticker} from {source}."}), 404

@app.route('/data/batch', methods=['POST'])
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
    
    print(f"DATA-SERVICE: Batch request. Cache hits: {len(cached_tickers)}, Cache misses: {len(missed_tickers)}")

    # --- Fetch Data for Cache Misses ---
    newly_fetched_data = {}
    failed_tickers = []

    if missed_tickers:
        if source == 'yfinance':
            # The yfinance provider now supports batch fetching
            fetched_data = yfinance_provider.get_stock_data(missed_tickers)
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
            print(f"DATA-SERVICE: Cached {len(new_cache_entries)} new entries.")

    # --- Combine Results and Return ---
    successful_data = list(cached_results.values()) + list(newly_fetched_data.values())
    
    # The data is nested inside a list for each ticker, so we need to flatten it
    flat_successful_data = [item for sublist in successful_data for item in sublist]

    return jsonify({
        "success": flat_successful_data,
        "failed": failed_tickers
    }), 200

@app.route('/news/<string:ticker>', methods=['GET'])
def get_news(ticker: str):
    # Check cache
    cached_news = news_cache.find_one({"ticker": ticker})
    if cached_news:
        # Check if cached news is still valid (not expired)
        time_elapsed = (datetime.now(timezone.utc) - cached_news['createdAt']).total_seconds()
        if time_elapsed < NEWS_CACHE_TTL:
            print(f"DATA-SERVICE: Cache HIT for news: {ticker}")
            return jsonify(cached_news['data'])
        else:
            print(f"Cache EXPIRED for news: {ticker}")
            news_cache.delete_one({"_id": cached_news["_id"]}) # Optionally delete expired entry immediately
        
    print(f"DATA-SERVICE: Cache MISS for news: {ticker}")
    
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
            print(f"DATA-SERVICE: CACHE INSERT for news: {ticker}")
            return jsonify(news_data)
        else:
            return jsonify({"error": f"Could not retrieve news for {ticker}."}), 404

    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

#  New endpoint to manually clear the cache
@app.route('/cache/clear', methods=['POST'])
def clear_cache():
    """
    Manually drops the price and news cache collections from MongoDB.
    This is useful for forcing a data refresh after deploying application updates.
    """
    try:
        if price_cache is not None:
            price_cache.drop()
            print("DATA-SERVICE: Dropped price_cache collection.")
        if news_cache is not None:
            news_cache.drop()
            print("DATA-SERVICE: Dropped news_cache collection.")
        
        # Re-initialize the collections and their TTL indexes
        init_db()
        
        return jsonify({"message": "All data service caches have been cleared."}), 200

    except Exception as e:
        print(f"Error clearing cache: {e}")
        return jsonify({"error": "Failed to clear caches.", "details": str(e)}), 500

if __name__ == '__main__':
    init_db() # Initialize the database connection
    app.run(host='0.0.0.0', port=PORT)