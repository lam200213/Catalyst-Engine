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

        # Extract cache bounds from valid date entries only
        dates = [d for d in (item.get("formatted_date") for item in cached_data) if d]
        if not dates:
            return False

        cache_start_dt = datetime.fromisoformat(min(dates)).date()
        cache_end_dt = datetime.fromisoformat(max(dates)).date()

        # log the extracted bounds and request shape
        logger.info(f"coverage: bounds start={cache_start_dt}, end={cache_end_dt}, req_period={req_period}, req_start={req_start}")

        if req_start:
            req_start_dt = datetime.fromisoformat(req_start).date()
            decision = (cache_start_dt <= req_start_dt)
            logger.info(f"coverage:req_start check: req_start_dt={req_start_dt}, decision={decision}")
            return decision

        if req_period:
            trading_days_by_period = {
                "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252,
                "2y": 504, "5y": 1260, "10y": 2520
            }
            count = trading_days_by_period.get(req_period, 252)

            # row-count fast path
            if len(dates) >= count:
                logger.info(f"coverage:row_count path: row_count={len(dates)}, needed={count}, decision=True")
                return True

            # Keep anchor vars for completeness (they may be helpful if you want to revert to a stricter mode later)
            yesterday = date.today() - timedelta(days=1)
            anchor_end = min(yesterday, cache_end_dt)

            nyse = mcal.get_calendar("NYSE")
            approx_back = max(365, int(count * 3))
            approx_start = anchor_end - timedelta(days=approx_back)

            # Build schedule
            schedule = nyse.schedule(start_date=approx_start, end_date=anchor_end)
            logger.info(
                f"coverage:calendar schedule: len={len(schedule.index)}, "
                f"first={(schedule.index[0].date() if not schedule.empty else None)}, "
                f"last={(schedule.index[-1].date() if not schedule.empty else None)}"
            )
            # treat a DataFrame with only an index as valid if the index has length
            idx = getattr(schedule, "index", None)
            idx_len = (len(idx) if idx is not None else 0)
            logger.info(
                f"coverage:calendar schedule: len={idx_len}, "
                f"first={(idx[0].date() if idx_len > 0 else None)}, "
                f"last={(idx[-1].date() if idx_len > 0 else None)}"
            )

            if idx is None or idx_len == 0:
                logger.info("coverage:calendar index empty → decision=False")
                return False

            # compute required_start directly from the last `count` sessions
            if idx_len >= count:
                required_start_dt = idx[-count].date()
                logger.info(f"coverage:required_start(length-based)={required_start_dt} (count={count})")
            else:
                required_start_dt = idx[0].date()
                logger.info(f"coverage:required_start(fallback first)={required_start_dt} (len<{count})")

            decision = (cache_start_dt <= required_start_dt)
            logger.info(f"coverage:decision start={cache_start_dt} required_start={required_start_dt} -> {decision}")
            return decision
        # No constraints
        logger.info("coverage:no constraints → decision=True")
        return True

    except Exception:
        # Be safe: force refetch on errors
        return False

# Allowed yfinance periods (kept consistent with original route logic)
ALLOWED_YF_PERIODS = {"1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"}

# Trading calendar cache
_TRADING_CAL = None

# Get (and cache) NYSE calendar
def get_trading_calendar():
    global _TRADING_CAL
    if _TRADING_CAL is None:
        # NYSE symbol stays consistent with existing codebase imports
        _TRADING_CAL = mcal.get_calendar('NYSE')
    return _TRADING_CAL

# Compute next trading day after d (skip weekends/holidays)
def next_trading_day(d: date) -> date:
    cal = get_trading_calendar()
    # Search a small forward window for the next session
    start = d + timedelta(days=1)
    end = d + timedelta(days=10)
    sched = cal.schedule(start_date=start, end_date=end)
    if not sched.empty:
        # The first index is the next trading session date (tz-naive date from Timestamp)
        return sched.index[0].date()
    # Fallback: if calendar returns nothing, move 1 day forward
    return d + timedelta(days=1)

def plan_incremental_price_fetch(
    cached_data: list | None,
    req_period: str | None,
    req_start: str | None,
    *,
    today: date | None = None,
    validate_fn=validate_and_prepare_price_data,
    covers_fn=cache_covers_request,
):
    """
    Returns a plan dict describing how to satisfy the request:
    {
      'action': 'return_cache' | 'fetch_full' | 'fetch_incremental',
      'start_date': date | None,       # for incremental/full-by-start
      'period': str | None,            # for full-by-period
      'cached': list | None,           # validated cache (if any)
      'reason': str                    # for logging/diagnostics
      'status': int | None,      # when action == 'error'
      'message': str | None      # when action == 'error'
    }
    """
    today = today or date.today()

    # 1) Validate cache
    validated = validate_fn(cached_data, "<batch-or-single>") if cached_data else None

    # 2) Respect explicit request constraints first
    if req_start:
        # Explicit start overrides incremental choice
        return {
            'action': 'fetch_full',
            'start_date': date.fromisoformat(req_start),
            'period': None,
            'cached': validated,
            'reason': 'explicit_start',
            'status': None,
            'message': None,
        }

    # If req_period is provided but not in allowed set, ignore it and fallback later.
    normalized_period = req_period if (req_period and req_period in ALLOWED_YF_PERIODS) else None

    if normalized_period:
        # If cache fully covers the requested period, we might still decide to return cache
        if validated and covers_fn(validated, normalized_period, None):
            # Also ensure recency; if recent, return cache, else incremental from last+1
            # Do not assume cached data is sorted. Find the actual maximum date
            last_date = date.fromisoformat(max(item['formatted_date'] for item in validated if item.get('formatted_date')))
            if last_date >= (today - timedelta(days=1)):
                return {
                    'action': 'return_cache',
                    'start_date': None,
                    'period': None,
                    'cached': validated,
                    'reason': 'cache_covers_and_recent',
                    'status': None,
                    'message': None,
                }
            # Use next trading day for incremental start
            return {
                'action': 'fetch_incremental',
                'start_date': last_date + timedelta(days=1),
                'period': None,
                'cached': validated,
                'reason': 'cache_covers_but_stale',
                'status': None,
                'message': None,
            }
        # Otherwise, fetch full for requested period
        return {
            'action': 'fetch_full',
            'start_date': None,
            'period': normalized_period,
            'cached': validated,
            'reason': 'explicit_period_refetch',
            'status': None,
            'message': None,
        }

    # 3) No explicit constraints: decide by recency (or invalid period was ignored)
    if validated:
        last_date = date.fromisoformat(max(item['formatted_date'] for item in validated if item.get('formatted_date')))
        if last_date >= (today - timedelta(days=1)):
            return {
                'action': 'return_cache',
                'start_date': None,
                'period': None,
                'cached': validated,
                'reason': 'no_constraints_cache_recent',
                'status': None,
                'message': None,
            }
        return {
            'action': 'fetch_incremental',
            'start_date': last_date + timedelta(days=1),
            'period': None,
            'cached': validated,
            'reason': 'no_constraints_cache_stale',
            'status': None,
            'message': None,
        }

    # 4) Cache miss: choose simple default full period, "1y"
    return {
        'action': 'fetch_full',
        'start_date': None,
        'period': '1y',
        'cached': None,
        'reason': 'cache_miss_default_period',
        'status': None,
        'message': None,
    }

# De-duplicate by date when merging incremental data
def _dedup_merge_by_date(old_list: list, new_list: list) -> list:
    # Prefer 'formatted_date' key if present, else fallback to 'date'
    by_key = {}
    if old_list:
        for item in old_list:
            k = item.get('formatted_date') or item.get('date')
            if k is not None:
                by_key[k] = item
    if new_list:
        for item in new_list:
            k = item.get('formatted_date') or item.get('date')
            if k is not None:
                # New data replaces old for same date key
                by_key[k] = item
    # Return sorted by date key if possible
    def _key(x):
        k = x.get('formatted_date') or x.get('date')
        return k or ''
    return sorted(by_key.values(), key=_key)

# shared merger + cache writer
def finalize_price_response(
    cache_key: str,
    plan: dict,
    provider_data: list | dict | None,
    *,
    validate_fn=validate_and_prepare_price_data,
    cache=None,
    ttl_seconds: int = 0,
    # Route-level context to restore original error messages/status
    error_context: dict | None = None,
):
    """
    Returns (json_data, http_status).
    Applies validation, merges with cache if incremental, and writes back to cache.
    On provider/validation failure: falls back to cache if present; otherwise
    returns route-specific error per error_context (message_404, message_500).
    """
    cached = plan.get('cached')

    # Early error passthrough from planner (kept for extensibility)
    if plan.get('action') == 'error':
        return {'error': plan.get('message')}, plan.get('status', 400)

    # If provider returned nothing but cache exists, return cache gracefully
    if provider_data is None:
        if cached:
            if cache:
                cache.set(cache_key, cached, timeout=ttl_seconds)
            return cached, 200
        # No cached either → original 404 wording if available
        if error_context and error_context.get('message_404'):
            return {'error': error_context['message_404']}, 404
        return {'error': 'Could not retrieve price data.'}, 404

    validated_new = validate_fn(provider_data, error_context.get('ticker') if error_context else "<batch-or-single>")
    if not validated_new:
        # Validation failure → fallback to cached if exists
        if cached:
            if cache:
                cache.set(cache_key, cached, timeout=ttl_seconds)
            return cached, 200
        # No cache → original 500 wording if available
        if error_context and error_context.get('message_500'):
            return {'error': error_context['message_500']}, 500
        return {'error': 'Provider returned invalid price data.'}, 500

    # Merge or replace
    if plan['action'] == 'fetch_incremental' and cached:
        merged = _dedup_merge_by_date(cached, validated_new)
        if cache:
            cache.set(cache_key, merged, timeout=ttl_seconds)
        return merged, 200

    # Full replace or fresh insert
    if cache:
        cache.set(cache_key, validated_new, timeout=ttl_seconds)
    return validated_new, 200

