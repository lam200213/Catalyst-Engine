# backend-services/leadership-service/checks/market_relative_checks.py
# contain functions comparing the stock to the market.

import logging
import pandas as pd
from datetime import datetime
from .utils import failed_check

# Get a logger that's a child of the app.logger, so it inherits the file handler
logger = logging.getLogger(__name__)

DATA_SERVICE_URL = "http://data-service:3001"

# Functions for financial statements (like check_yoy_eps_growth) expect newest-to-oldest data, 
# while functions for price history expect oldest-to-newest, due to the data properties.

# Helper functions
def _find_market_turning_point(market_trends_data):
    """
    Finds the date of a confirmed market turning point, defined as the first
    'Bullish' day that follows a 'Bearish' or 'Neutral' period.

    This correctly identifies patterns like 'Bearish -> Neutral -> Bullish'.
    
    Args:
        market_trends_data (list): A list of market trend dicts, sorted oldest to newest.

    Returns:
        str or None: The date string ('YYYY-MM-DD') of the turning point, or None if not found.
    """
    # --- Start of Debug Logging ---
    # logger.info("--- Debugging _find_market_turning_point ---")
    # logger.info(f"Received {len(market_trends_data)} days of market trend data.")
    # --- End of Debug Logging ---

    # Filter out any entries with a null or missing trend value for robust processing.
    valid_trends = [d for d in market_trends_data if d and d.get('trend')]
    if len(valid_trends) < 3:
        logger.warning(f"Not enough valid trend data to find a turning point (requires >= 3). Found {len(valid_trends)} valid entries.")
        return None
    
    # --- Start of Debug Logging ---
    # Log the filtered data
    # logger.info("Filtered market_trends_data for valid trends:\n" + json.dumps(valid_trends, indent=2))
    # --- End of Debug Logging ---

    # Iterate backwards from the most recent day to find the pattern using the cleaned data.
    for i in range(len(valid_trends) - 1, 0, -1):
        current_day = valid_trends[i]
        previous_day = valid_trends[i-1] # The previous *valid* day

        current_day_trend = current_day.get('trend')
        previous_day_trend = previous_day.get('trend')

        # Log each iteration
        # logger.info(
        #     f"Checking index {i} (Date: {current_day.get('date')}): "
        #     f"Current Trend='{current_day_trend}', Previous Trend='{previous_day_trend}'"
        # )

        # Step 1: Find the first 'Bullish' day. This is our potential turning point.
        if current_day_trend == 'Bullish':
            
            # Step 2: Check if the day before was NOT Bullish. This ensures it's the *start* of a new bullish phase.
            if previous_day_trend in ['Bearish', 'Neutral']:
                # Log when a potential turning point is found
                # logger.info(f"  > Potential turning point found at {current_day.get('date')}. "
                #             f"Pattern: {previous_day_trend} -> {current_day_trend}.")
                
                # Step 3: Scan further back to confirm this bullish day was preceded by a bearish period.
                # This ensures we are coming out of a downturn.
                for j in range(i - 1, -1, -1):
                    if valid_trends[j].get('trend') == 'Bearish':
                        # Confirmation! We found a 'Bullish' day that follows a period
                        # of 'Neutral' or 'Bearish' days, which itself came after a 'Bearish' trend.
                        found_date = valid_trends[i].get('date')
                        logger.info(f"    >> CONFIRMED: Preceding 'Bearish' trend found on {valid_trends[j].get('date')}. "
                                    f"Returning turning point date: {found_date}")
                        logger.info("--- End of _find_market_turning_point Debug ---")
                        return found_date

                # Log if the confirmation fails
                logger.warning(f"  > FAILED CONFIRMATION for {current_day.get('date')}: "
                               f"No preceding 'Bearish' trend was found in the lookback window.")

    # If the loop completes without finding the full pattern, no turning point is confirmed.
    logger.info("No confirmed turning point found in the provided data.")
    logger.info("--- End of _find_market_turning_point Debug ---")
    return None

def _check_new_high_in_window(stock_data, window_days, start_date_str=None):
    """
    Checks if a stock made a new high within a given time window compared to its preceding history.
    This version is robust and does not require a fixed 252-day lookback.
    """
    logger.info("--- Inside _check_new_high_in_window (Robust Version) ---")
    
    # We need at least enough data for the window plus one preceding day to compare against.
    if len(stock_data) < window_days + 1:
        logger.warning(f"Insufficient data: Found {len(stock_data)} days, need at least {window_days + 1}. Returning False.")
        return False

    df = pd.DataFrame(stock_data)
    df['date'] = pd.to_datetime(df['formatted_date'])
    logger.info(f"DataFrame created with {len(df)} rows. Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")

    if start_date_str:
        # This logic path remains for specific date-bound checks like 'Recovery Phase'
        start_date = pd.to_datetime(start_date_str)
        end_date = start_date + pd.Timedelta(days=window_days - 1)
        window_df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        pre_window_df = df[df['date'] < start_date]
        logger.info(f"Evaluating specific window: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    else:
        # Simplified logic for 'Bullish' context: Compare the last N days to all prior history.
        window_df = df.tail(window_days)
        pre_window_df = df.iloc[:-window_days]
        logger.info(f"Evaluating last {window_days} trading days against preceding history.")

    if window_df.empty or pre_window_df.empty:
        logger.warning(f"Could not create valid analysis windows. Window empty: {window_df.empty}, Pre-window empty: {pre_window_df.empty}. Returning False.")
        return False

    # The critical comparison
    reference_high = pre_window_df['high'].max()
    max_high_in_window = window_df['high'].max()
    
    logger.info(f"Analysis window starts: {window_df['date'].iloc[0].strftime('%Y-%m-%d')}")
    logger.info(f"Analysis window ends: {window_df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    logger.info(f"Reference period ends: {pre_window_df['date'].iloc[-1].strftime('%Y-%m-%d')}")

    logger.info(f"CRITICAL CHECK: Max high in recent window = {max_high_in_window}")
    logger.info(f"CRITICAL CHECK: Reference high from preceding period = {reference_high}")

    new_high_made = max_high_in_window > reference_high

    date_of_high = None
    if new_high_made:
        # Find the date of the highest high in the window
        date_of_high = window_df.loc[window_df['high'].idxmax()]['date'].strftime('%Y-%m-%d')
    
    logger.info(f"FINAL COMPARISON: {max_high_in_window} > {reference_high} is {new_high_made}")
    logger.info("--- Exiting _check_new_high_in_window ---")
    
    return bool(new_high_made), date_of_high

def _get_market_context(market_trends_data):
    """Determines the overall market context ('Bearish', 'Recovery', 'Bullish', 'Neutral')."""
    if not market_trends_data or len(market_trends_data) < 8:
        return 'Unknown', None, False

    current_market_trend = market_trends_data[-1].get('trend', 'Unknown')
    turning_point_date = _find_market_turning_point(market_trends_data)
    
    is_recovery_phase = False
    if turning_point_date:
        # Define recovery phase as within 20 calendar days of a market turn
        days_since_turn = (datetime.now().date() - datetime.strptime(turning_point_date, '%Y-%m-%d').date()).days
        if 0 <= days_since_turn <= 20:
            is_recovery_phase = True
            
    # The recovery phase takes precedence over a simple bullish context for more specific checks.
    final_context = "Recovery" if is_recovery_phase else current_market_trend
    
    return final_context, turning_point_date, is_recovery_phase

def _calculate_drawdown(price_history: list, days: int = 240):
    """
    Calculates the high, current price, and drawdown percentage from a list of price data.
    Returns (None, None, None) if data is insufficient.
    """
    # Handling for summary dictionary structure.
    if isinstance(price_history, dict):
        # This path is for test structures that pass a summary dictionary.
        high_price = price_history.get('high_52_week')
        current_price = price_history.get('current_price')
        # The test modifies 'current_price', but live data might not have it.
        # Fallback to 'close' if 'current_price' isn't in the dict.
        if current_price is None:
            current_price = price_history.get('close')

        if high_price is None or current_price is None or high_price == 0:
            return high_price, current_price, None
        
        drawdown = (high_price - current_price) / high_price
        return high_price, current_price, drawdown

    if not price_history or len(price_history) < days:
        return None, None, None

    relevant_period = price_history[-days:]
    
    # Ensure highs are valid numbers before calculating max
    valid_highs = [p['high'] for p in relevant_period if p.get('high') is not None]
    if not valid_highs:
        return None, None, None

    high_price = max(valid_highs)
    current_price = relevant_period[-1].get('close')

    if high_price is None or current_price is None or high_price == 0:
        return high_price, current_price, None

    drawdown = (high_price - current_price) / high_price
    return high_price, current_price, drawdown

def _check_shallow_decline(stock_data, sp500_data, sub_results):
    """Check if stock's decline is shallower than the S&P 500's."""
    _, _, stock_decline = _calculate_drawdown(stock_data)
    _, _, sp500_decline = _calculate_drawdown(sp500_data)

    passes = False
    if stock_decline is not None and sp500_decline is not None and sp500_decline > 0:
        passes = stock_decline < sp500_decline
        message = f"Stock decline ({stock_decline:.1%}) is {'shallower' if passes else 'not shallower'} than S&P 500 ({sp500_decline:.1%})."
    else:
        message = "Could not calculate or compare declines."

    sub_results['shallow_decline'] = {"pass": passes, "message": message}
    return passes

def _check_recent_breakout(stock_data, sub_results):
    """
    Checks if a stock showed a recent breakout on high volume.
    A breakout is defined as today's price being >5% above the 20-day average
    and today's volume being >50% above the 20-day average.

    Args:
        stock_data (list): List of stock price data dictionaries.
        sub_results (dict): Dictionary to store detailed check results.

    Returns:
        bool: True if a recent breakout is detected, False otherwise.
    """
    key = 'recent_breakout'
    if not stock_data or len(stock_data) < 20:
        sub_results[key] = {"pass": False, "message": "Insufficient data for breakout check (requires 20 days)."}
        return False

    # Use last 20 trading days
    recent_data = stock_data[-20:]
    recent_prices = [day['close'] for day in recent_data if day and day.get('close') is not None]
    recent_volumes = [day['volume'] for day in recent_data if day and day.get('volume') is not None]

    # Need at least two data points to calculate an average and compare
    if len(recent_prices) < 2 or len(recent_volumes) < 2:
        sub_results[key] = {"pass": False, "message": "Not enough valid price/volume data in the last 20 days."}
        return False

    # Averages are calculated on the 19 days preceding the most recent day
    avg_price = sum(recent_prices[:-1]) / len(recent_prices[:-1])
    avg_volume = sum(recent_volumes[:-1]) / len(recent_volumes[:-1])

    current_price = recent_prices[-1]
    current_volume = recent_volumes[-1]

    # Define breakout conditions
    price_breakout = current_price > (avg_price * 1.05)  # 5% above average
    volume_breakout = current_volume > (avg_volume * 1.5) if avg_volume > 0 else False

    is_pass = price_breakout and volume_breakout

    message = (f"Recent breakout detected: Price {current_price:.2f} vs avg {avg_price:.2f}, "
               f"Volume {current_volume} vs avg {int(avg_volume)}.") if is_pass else "No recent price/volume breakout detected."

    sub_results[key] = {
        "pass": is_pass,
        "message": message
    }
    return is_pass

def _check_recovery_strength(stock_data, turning_point_date, sub_results):
    """
    Checks if the stock showed leadership during a market recovery.
    Passes if EITHER of the following is true:
    1. It made a new 52-week high within 20 days of the market turning point.
    2. It showed a recent price/volume breakout in the last 20 days.
    """
    key_new_high = 'new_52_week_high_in_recovery'
    if not turning_point_date:
        sub_results[key_new_high] = {"pass": False, "message": "No turning point date provided for recovery check."}
        # Also add a placeholder for the breakout check to ensure consistent output structure
        sub_results['recent_breakout'] = {"pass": False, "message": "Skipped due to missing turning point."}
        return False

    # Check 1: New 52-week high since the turn
    new_high_pass, high_date = _check_new_high_in_window(stock_data, 20, start_date_str=turning_point_date)
    message_high = (f"Market recovery started {turning_point_date}. "
                    f"Stock {'made' if new_high_pass else 'did not make'} a new 52-week high "
                    f"within 20 days (High on: {high_date}).")
    sub_results[key_new_high] = {
        "pass": new_high_pass,
        "high_date": high_date,
        "message": message_high
    }

    # Check 2: Recent price and volume breakout
    breakout_pass = _check_recent_breakout(stock_data, sub_results)

    # A stock is considered strong in recovery if it achieves EITHER a new high OR a breakout
    return new_high_pass or breakout_pass
def _check_bullish_strength(stock_data, sp500_data, turning_point_date, sub_results):
    """Run all checks for a Bullish or Neutral market context."""
    # Check 1: New high in last 20 days
    new_high_pass, high_date = _check_new_high_in_window(stock_data, 20)
    # Corrected message to use its own pass flag
    new_high_message = (f"Stock {'showed' if new_high_pass else 'did not show'} recent strength by making a new high in the last 20 days.")
    if high_date:
        new_high_message += f" (High on {high_date})"
    sub_results['new_52_week_high_last_20d'] = {"pass": new_high_pass, "high_date": high_date, "message": new_high_message}
    
    # Check 2: Relative strength vs S&P 500
    rs_pass, rs_message = _check_relative_strength(stock_data, sp500_data)
    sub_results['relative_strength_vs_sp500'] = {"pass": rs_pass, "message": rs_message}
    
    # Check 3 (optional): If there was a recent turning point, did it show strength then?
    recovery_pass = True # Default to true if no recent turning point
    if turning_point_date:
        recovery_pass = _check_recovery_strength(stock_data, turning_point_date, sub_results)

    # Final pass condition for this context
    return all([new_high_pass, rs_pass, recovery_pass])

def _check_relative_strength(stock_data, sp500_data):
    """Compare stock drawdown to S&P 500 drawdown."""
    _, _, stock_drawdown = _calculate_drawdown(stock_data)
    _, _, sp500_drawdown = _calculate_drawdown(sp500_data)

    if stock_drawdown is not None and sp500_drawdown is not None:
        passes = stock_drawdown < sp500_drawdown
        message = f"Stock drawdown ({stock_drawdown:.1%}) is {'better' if passes else 'not better'} than S&P 500 ({sp500_drawdown:.1%})."
        return passes, message
    
    return False, "Could not compare performance against S&P 500."

# Logic functions
def evaluate_market_trend_impact(stock_data, index_data, market_trends_data, details):
    """ 
    Evaluate the stock's behavior relative to the market trend context.
    - Bearish: Checks for shallow decline relative to S&P 500.
    - Recovery Phase: Checks if stock made a new 52-week high within 20 days of a market turning point.
    - Bullish/Neutral: Checks if stock made a new 52-week high in the last 10 or 20 days.
    
    Args:
        stock_data (list): List of stock price data dictionaries.
        index_data (dict): Dictionary containing the LATEST market index data.
        market_trends_data (list): List of trend dicts for the last 8 workdays.
        details (dict): A dictionary to store the result.

    Returns:
        None: The results are stored in the details dictionary.
    """
    metric_key = 'market_trend_impact'
    try:

        # The current market context is the most recent entry in the list
        if not market_trends_data:
            details.update(failed_check(metric_key, "Market trends data not available."))
            return
        if len(market_trends_data) < 8:
            details.update(failed_check(metric_key, "Market trends data is insufficient (requires >= 8 days)."))
            return

        # --- 1. Determine Market Context ---
        context, turning_point_date, is_recovery = _get_market_context(market_trends_data)
        sp500_data = index_data.get('^GSPC')

        if context == 'Unknown' or not sp500_data:
            details.update(failed_check(metric_key, "Market context is unknown or S&P 500 data is missing."))
            return

        # --- 2. Execute Checks Based on Context ---
        # Initialize evaluation results
        is_pass = False
        message = "No specific leadership signal detected for current market context."
        sub_results = {}

        if context == 'Bearish':
            is_pass = _check_shallow_decline(stock_data, sp500_data, sub_results)
        elif context == 'Recovery':
            is_pass = _check_recovery_strength(stock_data, turning_point_date, sub_results)
        elif context in ['Bullish', 'Neutral']:
            is_pass = _check_bullish_strength(stock_data, sp500_data, turning_point_date, sub_results)

        # --- 3. Finalize Result ---
        message = f"Market trend impact evaluated in {context} context."

        details[metric_key] = {
            "pass": is_pass,
            "market_trend_context": context,
            "is_recovery_phase": is_recovery,
            "turning_point_date": turning_point_date,
            "sub_results": sub_results,
            "message": message
        }

    except Exception as e:
        # Handle any errors gracefully
        logger.error(f"Error in evaluate_market_trend_impact: {e}", exc_info=True)
        details.update(failed_check(metric_key, f"An unexpected error occurred: {str(e)}"))
