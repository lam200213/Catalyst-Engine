# data-service/app.py
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# Import provider modules
from providers import yfinance_provider, finnhub_provider, marketaux_provider

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Global variables for MongoDB client and collections
client = None
db = None
price_cache = None
news_cache = None

# Cache expiration times in seconds
PRICE_CACHE_TTL = 3600
NEWS_CACHE_TTL = 14400

def init_db():
    global client, db, price_cache, news_cache
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
    client = MongoClient(MONGO_URI)
    db = client.stock_analysis # Database name

    price_cache = db.price_cache # Collection for price data
    news_cache = db.news_cache   # Collection for news data

    # Create TTL indexes to auto-delete old cache documents.
    price_cache.create_index("createdAt", expireAfterSeconds=PRICE_CACHE_TTL)
    news_cache.create_index("createdAt", expireAfterSeconds=NEWS_CACHE_TTL)

@app.route('/data/<string:ticker>', methods=['GET'])
def get_data(ticker: str):
    source = request.args.get('source', 'yfinance').lower()
    print(f"Received request for ticker: {ticker}, source: {source}")
    
    # Check cache first
    cached_data = price_cache.find_one({"ticker": ticker, "source": source})
    if cached_data:
        # Ensure cached_data['createdAt'] is timezone-aware for comparison
        if cached_data['createdAt'].tzinfo is None:
            cached_data['createdAt'] = cached_data['createdAt'].replace(tzinfo=timezone.utc)
        time_elapsed = (datetime.now(timezone.utc) - cached_data['createdAt']).total_seconds()
        if time_elapsed < PRICE_CACHE_TTL:
            print(f"DATA-SERVICE: Cache HIT for price: {ticker} from {source}")
            return jsonify(cached_data['data'])
        else:
            print(f"Cache EXPIRED for price: {ticker} from {source}")
            price_cache.delete_one({"_id": cached_data["_id"]}) # Optionally delete expired entry immediately
    
    print(f"DATA-SERVICE: Cache MISS for price: {ticker} from {source}")

    # If not in cache, fetch from provider
    data = None
    if source == 'yfinance':
        data = yfinance_provider.get_stock_data(ticker)
    elif source == 'finnhub':
        data = finnhub_provider.get_stock_data(ticker)
    else:
        return jsonify({"error": "Invalid data source. Use 'finnhub' or 'yfinance'."}), 400

    if data:
        # Store the fresh data in the cache
        price_cache.insert_one({
            "ticker": ticker,
            "source": source,
            "data": data,
            "createdAt": datetime.now(timezone.utc)
        })
        print(f"DATA-SERVICE: CACHE INSERT for price: {ticker} from {source}")
        return jsonify(data)
    else:
        return jsonify({"error": f"Could not retrieve price data for {ticker} from {source}."}), 404

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

# Latest Add: New endpoint to manually clear the cache
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
    port = int(os.environ.get('PORT', 3001))
    app.run(host='0.0.0.0', port=port)