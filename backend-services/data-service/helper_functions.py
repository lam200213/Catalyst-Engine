# data-service/helper_functions.py
import logging
from pymongo import MongoClient, errors
from datetime import datetime, timezone, date, timedelta
import os
from typing import List
from pydantic import ValidationError, TypeAdapter
from shared.contracts import PriceDataItem, CoreFinancials
import pandas_market_calendars as mcal

# Use logger
logger = logging.getLogger(__name__)

# A consistent structure for failure responses
def failed_check(metric, message, **kwargs):
    # Log the technical failure for developers
    logger.warning(f"Check failed for metric '{metric}': {message} | Details: {kwargs}")
    return {metric: {"pass": False, "message": message, **kwargs}}

def validate_and_prepare_price_data(data: list, ticker: str) -> list | None:
    """
    Validates raw price data against the PriceDataItem contract.

    Args:
        data (list): The raw price data list from the provider or cache.
        ticker (str): The ticker symbol for logging purposes.

    Returns:
        list: A validated list of price data dictionaries, or None if validation fails.
    """
    if not data:
        return None
    try:
        PriceDataValidator = TypeAdapter(List[PriceDataItem])
        validated_items = PriceDataValidator.validate_python(data)
        # Convert back to a list of dicts for JSON serialization
        return [item.model_dump() for item in validated_items]
    except ValidationError as e:
        logger.error(f"Price data for {ticker} failed contract validation: {e}")
        return None


def validate_and_prepare_financials(data: dict, ticker: str):
    """
    Validates raw financial data against the CoreFinancials contract,
    cleans key numerical fields, and returns a processed dictionary.

    Args:
        data (dict): The raw data dictionary from the provider.
        ticker (str): The ticker symbol for logging purposes.

    Returns:
        dict: A validated and cleaned data dictionary, or None if validation fails.
    """
    if not data:
        return None
    
    # Special handling for market index data. If the ticker is a known index
    # and the data contains 'current_price', we treat it as valid market data
    # and bypass the stricter CoreFinancials Pydantic validation.
    if ticker in ['^GSPC', '^DJI', '^IXIC'] and 'current_price' in data:
        logger.debug(f"Bypassing CoreFinancials validation for market index: {ticker}")
        return data

    try:
        # Enforce data contract
        validated_data = CoreFinancials.model_validate(data)
        final_data = validated_data.model_dump(by_alias=True)  # Convert back to dict

        # Centralize the data cleaning logic from the batch endpoint
        total_revenue = final_data.get('totalRevenue')
        net_income = final_data.get('Net Income')
        market_cap = final_data.get('marketCap')

        # Substitute non-numerical values with 0 to prevent downstream errors
        final_data['totalRevenue'] = total_revenue if isinstance(total_revenue, (int, float)) else 0
        final_data['Net Income'] = net_income if isinstance(net_income, (int, float)) else 0
        final_data['marketCap'] = market_cap if isinstance(market_cap, (int, float)) else 0
        
        return final_data
        
    except ValidationError as e:
        logger.error(f"Financial data for {ticker} failed contract validation: {e}")
        return None

def check_market_trend_context(index_data, details):
    """
    Determine the market trend context based on all three major indices (SPY, DIA, ^IXIC) technical indicators.
    
    Args:
        index_data (dict): Dictionary containing market data for all three indices including:
                          '^GSPC', '^DJI', '^IXIC' each with 'current_price', 'sma_50', 'sma_200', 'high_52_week', 'low_52_week'
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'market_trend_context' key of the details dictionary.
    """
    metric_key = 'market_trend_context'
    try:
        # Define the three major indices
        indices = ['^GSPC', '^DJI', '^IXIC']
        
        # Check if we have data for all three indices
        if not index_data or not all(index in index_data for index in indices):
            details.update(failed_check(metric_key, "Missing data for one or more major indices."))
            return
        
        # Determine trend for each index
        index_trends = {}
        
        for index in indices:
            index_info = index_data[index]
            
            # Extract required data points
            current_price = index_info.get('current_price')
            sma_50 = index_info.get('sma_50')
            sma_200 = index_info.get('sma_200')
            high_52_week = index_info.get('high_52_week')
            low_52_week = index_info.get('low_52_week')
            
            # Detailed logging for debugging
            # calc_logger.info(f"Market Context Check for {index}: Price={current_price}, SMA50={sma_50}")

            # Validate required data is present
            if any(value is None for value in [current_price, sma_50, sma_200, high_52_week, low_52_week]):
                details.update(failed_check(metric_key, f"Missing technical indicators for index {index}."))
                return
            
            # Determine individual index trend
            if current_price > sma_50:
                index_trends[index] = 'Bullish'
            elif current_price < sma_50:
                index_trends[index] = 'Bearish'
            else:
                index_trends[index] = 'Neutral'
        
        # Determine overall market trend based on all three indices
        bullish_count = sum(1 for trend in index_trends.values() if trend == 'Bullish')
        bearish_count = sum(1 for trend in index_trends.values() if trend == 'Bearish')
        
        if bullish_count == 3:
            # All three indices are bullish (above their 50-day SMA)
            trend = 'Bullish'
        elif bearish_count == 3:
            # All three indices are bearish (below their 50-day SMA)
            trend = 'Bearish'
        else:
            # Mixed signals
            trend = 'Neutral'
        
        is_pass = trend != 'Bearish'
        message = f"Market trend is {trend}, with {bullish_count}/3 indices in a bullish posture."

        details[metric_key] = {
            "pass": is_pass,
            "trend": trend,
            "index_trends": index_trends,
            "message": message
        }   

    except Exception as e:
        # Handle any errors gracefully
        details.update(failed_check(metric_key, f"An unexpected error occurred: {str(e)}", trend='Unknown'))

def is_ticker_delisted(ticker: str) -> bool:
    """
    Checks the ticker_status collection to see if a ticker has been marked as delisted.
    Returns True if the ticker is found in the collection, False otherwise.
    """
    client = None  # Initialize client to None
    try:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
        # Use a short timeout to avoid blocking the request for too long
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client.stock_analysis
        ticker_status_coll = db.ticker_status
        
        # Check if a document with the ticker exists. count_documents is efficient.
        count = ticker_status_coll.count_documents({"ticker": ticker}, limit=1)
        
        if count > 0:
            logger.debug(f"Pre-flight check: Ticker {ticker} is known to be delisted. Skipping API call.")
            return True
        return False
        
    except errors.PyMongoError as e:
        # If the DB check fails, log it but don't block the request.
        # It's better to attempt the API call than to fail because of a transient DB issue.
        logger.warning(f"Could not check delisted status for {ticker} from MongoDB: {e}")
        return False
    finally:
        if client:
            client.close()

def mark_ticker_as_delisted(ticker: str, reason: str):
    """Writes a ticker's status as 'delisted' to the ticker_status collection."""
    try:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client.stock_analysis
        ticker_status_coll = db.ticker_status
        
        update_doc = {
            "$set": {
                "ticker": ticker,
                "status": "delisted",
                "reason": reason,
                "last_updated": datetime.now(timezone.utc)
            }
        }
        ticker_status_coll.update_one({"ticker": ticker}, update_doc, upsert=True)
        logger.info(f"Marked ticker {ticker} as delisted in the database. Reason: {reason}")
    except errors.PyMongoError as e:
        logger.error(f"Failed to write delisted status for {ticker} to MongoDB: {e}")
    finally:
        if 'client' in locals() and client:
            client.close()

# helper to check if cached data covers the requested period/date range
# trading-day-aware cache coverage validation using pandas_market_calendars
def cache_covers_request(cached_data: list, req_period: str | None, req_start: str | None) -> bool:
    """
    Check if cached price data covers the requested time range using NYSE trading calendar.
    Returns True if cache has sufficient trading-day coverage for the request.
    """
    if not cached_data:
        return False
    
    try:
        import pandas_market_calendars as mcal
        from datetime import datetime, date, timedelta
        
        # Extract cache bounds and size
        dates = [d for d in (item.get("formatted_date") for item in cached_data) if d]
        if not dates:
            return False
        cache_start_dt = datetime.fromisoformat(min(dates)).date()
        cache_end_dt = datetime.fromisoformat(max(dates)).date()
        row_count = len(dates)
        
        # If specific start_date requested, simple date comparison
        if req_start:
            req_start_dt = datetime.fromisoformat(req_start).date()
            return cache_start_dt <= req_start_dt
        
        # If period requested, calculate required start using trading calendar
        if req_period:
            yesterday = date.today() - timedelta(days=1)
            
            # Map period to approximate calendar days for initial range
            approx_days = {
                "1mo": 31, "3mo": 92, "6mo": 183, "1y": 365,
                "2y": 730, "5y": 1826, "10y": 3652
            }.get(req_period, 365)
            
            # Calculate the nominal start date
            approx_start = yesterday - timedelta(days=approx_days)

            # Use NYSE calendar to get valid trading days in the period
            nyse = mcal.get_calendar("NYSE")
            schedule = nyse.schedule(start_date=approx_start, end_date=yesterday)
            
            if schedule.empty:
                return True  # No trading days expected, cache is sufficient
            
            # First required trading day in the period
            required_start_dt = datetime.fromisoformat(schedule.index[0].strftime("%Y-%m-%d")).date()

            # Accept by boundary OR by bar count (daily bars)
            min_rows = {
                "1mo": 18, "3mo": 55, "6mo": 120, "1y": 240,
                "2y": 480, "5y": 1200, "10y": 2400
            }.get(req_period, 240)

            return cache_start_dt <= required_start_dt or row_count >= min_rows

        # No strict requirement; accept
        return True
    except Exception:
        # On error, force a refetch to be safe
        return False
