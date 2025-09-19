# backend-services/data-service/database.py

import os
from pymongo import MongoClient
from pymongo.errors import OperationFailure

# A helper function to make index creation robust
def _create_ttl_index(collection, field, ttl_seconds, name, logger):
    """
    Creates a TTL index, handling conflicts if the TTL value has changed.
    """
    try:
        # Attempt to create the index with the new TTL and name
        collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
        logger.info(f"TTL index '{name}' on '{collection.name}' set to {ttl_seconds} seconds.")
    except OperationFailure as e:
        # Error code 85 is for "IndexOptionsConflict"
        if e.code == 85:
            logger.warning(f"Index conflict on '{collection.name}'. Dropping old index and recreating.")
            
            # Drop the index by its actual name, which caused the conflict.
            collection.drop_index(name)
            
            # Re-create the index with the correct TTL and new name
            collection.create_index([(field, 1)], expireAfterSeconds=ttl_seconds, name=name)
            logger.info(f"Successfully recreated TTL index with new name '{name}' on '{collection.name}'.")
        else:
            # For any other database error, re-raise the exception to halt startup
            raise

def init_db(logger):
    """
    Initializes the database connection and collections.
    Returns the database collections for the app to use.
    """
    global client, db, price_cache, news_cache, financials_cache, industry_cache, market_trends
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
    client = MongoClient(MONGO_URI)
    db = client.stock_analysis # Database name

    price_cache = db.price_cache # Collection for price data
    news_cache = db.news_cache   # Collection for news data
    financials_cache = db.financials_cache # Collection for financial data
    industry_cache = db.industry_cache # Collection for industry data
    market_trends = db.market_trends # Collection for market trends

    # Cache expiration times in seconds
    PRICE_CACHE_TTL = 342800
    NEWS_CACHE_TTL = 14400
    INDUSTRY_CACHE_TTL = 86400

    # Use the robust helper function to create/update TTL indexes
    _create_ttl_index(price_cache, "createdAt", PRICE_CACHE_TTL, "createdAt_ttl_index", logger)
    _create_ttl_index(news_cache, "createdAt", NEWS_CACHE_TTL, "createdAt_ttl_index", logger)
    _create_ttl_index(financials_cache, "createdAt", PRICE_CACHE_TTL, "createdAt_ttl_index_financials", logger)
    _create_ttl_index(industry_cache, "createdAt", INDUSTRY_CACHE_TTL, "createdAt_ttl_index_industry", logger)

    market_trends.create_index([("date", 1)], unique=True, name="date_unique_idx")
 
    logger.info("Database initialized successfully.")

    collections = {
        "price_cache": price_cache,
        "news_cache": news_cache,
        "financials_cache": financials_cache,
        "industry_cache": industry_cache,
        "market_trends": market_trends
    }
    
    return collections