from flask import Flask, jsonify
import pandas as pd
import requests
import os
import logging
from pydantic import TypeAdapter, ValidationError
from shared.contracts import TickerList
from pymongo import MongoClient, errors

app = Flask(__name__)
PORT = int(os.getenv("PORT", 5001))

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Connection ---
db = None
try:
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongodb:27017/')
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # The ismaster command is cheap and does not require auth.
    mongo_client.admin.command('ismaster')
    db = mongo_client.stock_analysis
    logger.info("Ticker-service successfully connected to MongoDB.")
except errors.ConnectionFailure as e:
    logger.critical(f"Ticker-service could not connect to MongoDB: {e}")
    db = None # Ensure db is None if connection fails

def _get_delisted_tickers_from_db():
    """
    Fetches the set of delisted tickers from the ticker_status collection.
    Returns an empty set if the database is unavailable or the collection is empty.
    """
    if db is None:
        logger.warning("Database not available. Cannot fetch delisted tickers.")
        return set()
    try:
        delisted_cursor = db.ticker_status.find({"status": "delisted"}, {"ticker": 1, "_id": 0})
        delisted_set = {item['ticker'] for item in delisted_cursor}
        logger.info(f"Fetched {len(delisted_set)} delisted tickers from the database.")
        return delisted_set
    except errors.PyMongoError as e:
        logger.error(f"An error occurred while fetching delisted tickers: {e}")
        return set() # Return an empty set on error to prevent total failure

def get_all_us_tickers():
    """
    Fetches all stock tickers from NYSE, NASDAQ, and AMEX from the NASDAQ API.
    """
    exchanges = ['nyse', 'nasdaq', 'amex']
    all_tickers = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for exchange in exchanges:
        try:
            url = f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&exchange={exchange}&download=true"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # If the request succeeds, we mark that we were able to get data from at least one source.
            successful_fetch_from_any_exchange = True       

            df = pd.DataFrame(response.json()['data']['rows'])
            
            if 'symbol' in df.columns:
                valid_tickers = df[~df['symbol'].str.contains(r'\.|\^', na=False)]['symbol'].tolist()
                all_tickers.extend(valid_tickers)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching tickers for {exchange}: {e}")
            continue
        except (KeyError, TypeError) as e:
            logger.error(f"Error parsing data for {exchange}: {e}")
            continue
    
    # If after trying all sources, we have no tickers, it's a failure.
    # This must happen BEFORE the DB filtering, to distinguish a fetch failure
    # from a case where all fetched tickers are later filtered out.
    if not all_tickers:
        logger.error("Failed to retrieve any tickers from the source after trying all exchanges.")
        return None

    # --- Filter out delisted tickers ---
    if all_tickers:
        delisted_set = _get_delisted_tickers_from_db()
        if delisted_set:
            original_count = len(all_tickers)
            # Use set for efficient lookup
            all_tickers_set = set(all_tickers)
            filtered_tickers_set = all_tickers_set - delisted_set
            all_tickers = sorted(list(filtered_tickers_set))
            new_count = len(all_tickers)
            logger.info(f"Filtered out {original_count - new_count} delisted tickers. "
                        f"Original count: {original_count}, New count: {new_count}.")
        else:
            logger.info("No delisted tickers found in DB to filter against.")
    
    return sorted(list(set(all_tickers)))

@app.route('/tickers')
def get_tickers_endpoint():
    """The API endpoint to provide the list of tickers."""
    try:
        ticker_list = get_all_us_tickers()
        if ticker_list is None: # Explicitly check for None, allowing an empty list.
             return jsonify({"error": "Failed to retrieve any tickers from the source."}), 500
        # Validate the output against the TickerList contract before returning.
        try:
            ta = TypeAdapter(TickerList)
            ta.validate_python(ticker_list)
        except ValidationError as e:
            logger.error(f"Internal data validation error in ticker-service: {e}")
            return jsonify({"error": "Internal server error: malformed ticker data."}), 500

        return jsonify(ticker_list)
    except Exception as e:
        logger.critical(f"An unhandled exception occurred in /tickers endpoint: {e}", exc_info=True)
        return jsonify({"error": "An unexpected internal server error occurred."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)