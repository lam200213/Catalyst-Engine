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

# Logic functions
def evaluate_market_trend_impact(stock_data, index_data, market_trends_data, details):
    """ 
    Evaluate the stock's behavior relative to the market trend context.
    - Bearish: Checks for shallow decline relative to S&P 500.
    - Recovery Phase: Checks if stock made a new 52-week high within 20 days of a market turning point.
    - Bullish/Neutral: Checks if stock made a new 52-week high in the last 10 or 20 days.
    
    PS: Data of price history is in order of oldest-to-newest.
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
        current_market_trend_info = market_trends_data[-1]
        market_trend_context = current_market_trend_info.get('trend', 'Unknown')
        details['market_trend_context'] = current_market_trend_info # Store the full context
        turning_point_date = _find_market_turning_point(market_trends_data)

        is_recovery_phase = False
        if turning_point_date:
            days_since_turn = (datetime.now() - datetime.strptime(turning_point_date, '%Y-%m-%d')).days
            if 0 <= days_since_turn <= 20: # Recovery phase is defined as 20 days post-turn
                is_recovery_phase = True

        # --- 2. Execute Checks Based on Context ---
        # Initialize evaluation results
        is_pass = False
        message = "No specific leadership signal detected for current market context."
        sub_results = {}

        if market_trend_context == 'Bearish':
            # Shallow Decline Check
            stock_decline, sp500_decline = None, None

            # A stock's correction from its 52-week high must not be more than the current correction of the S&P 500 (SPY)
            if stock_data and '^GSPC' in index_data:
                sp500_data = index_data['^GSPC']
                sp500_high = sp500_data.get('high_52_week')
                sp500_current = sp500_data.get('current_price')
                if sp500_high and sp500_current and sp500_high > 0:
                    sp500_decline = (sp500_high - sp500_current) / sp500_high

                # Find stock's 52-week high and current price
                if len(stock_data) >= 252:  # Approximately 1 year of trading days
                    stock_high = max(day['high'] for day in stock_data[-252:])
                    stock_current = stock_data[-1]['close']
                    if stock_high > 0:
                        stock_decline = (stock_high - stock_current) / stock_high

            # Check if stock's decline is less than the S&P 500's decline
            is_pass = sp500_decline > 0 and stock_decline < sp500_decline
            message = f"Stock decline ({stock_decline:.1%}) is {'shallower' if is_pass else 'not shallower'} than S&P 500 decline ({sp500_decline:.1%})."
            sub_results['shallow_decline'] = {"pass": is_pass, "message": message}

        elif is_recovery_phase:
            # New High Check During Market Recovery
            new_high_in_last_20d, high_date = _check_new_high_in_window(stock_data, 20, start_date_str=turning_point_date)
            is_pass = new_high_in_last_20d
            message = (f"Market is in recovery (turn on {turning_point_date}). Stock {'made' if is_pass else 'did not make'} "
                       f"a new 52-week high within 20 days of the turning point, {high_date}.")

            sub_results['new_52_week_high_last_20d'] = {
                "pass": is_pass,
                "high_date": high_date,
                "message": message
            }

            recent_breakout = False
            # Breakout Check During Market Recovery
            if turning_point_date and stock_data and len(stock_data) >= 20:
                # Look for a breakout in the last 20 trading days
                recent_prices = [day['close'] for day in stock_data[-20:]]
                recent_volumes = [day['volume'] for day in stock_data[-20:] if 'volume' in day]

                if recent_prices and recent_volumes:
                    # Calculate average price and volume for the period
                    avg_price = sum(recent_prices[:-1]) / len(recent_prices[:-1])  # Exclude today
                    avg_volume = sum(recent_volumes[:-1]) / len(recent_volumes[:-1]) if len(recent_volumes) > 1 else 0

                    # Check if today's price and volume are significantly higher
                    current_price = recent_prices[-1]
                    current_volume = recent_volumes[-1] if recent_volumes else 0

                    price_breakout = current_price > (avg_price * 1.05)  # 5% above average
                    volume_breakout = current_volume > (avg_volume * 1.5) if avg_volume > 0 else False

                    if price_breakout and volume_breakout:
                        recent_breakout = True

                sub_results['recent_breakout'] = {
                    "pass": recent_breakout,
                    "message": "Stock showed recent breakout during recovery." if recent_breakout else "No recent breakout detected."
                }

        elif market_trend_context in ['Bullish', 'Neutral']:
            # Check for new high in the last 20 days and during Market Recovery
            if turning_point_date:
                new_high_in_20d_after_turn, _ = _check_new_high_in_window(stock_data, 20, start_date_str=turning_point_date)
                is_pass = new_high_in_20d_after_turn

                message = (f"When market was in recovery (turn on {turning_point_date}). Stock {'made' if is_pass else 'did not make'} "
                        f"a new 52-week high within 20 days of the turning point.")
                sub_results['new_52_week_high_after_turn'] = {
                    "pass": is_pass,
                    "message": message
                }

            new_high_in_last_20d, high_date = _check_new_high_in_window(stock_data, 20)
            is_pass = new_high_in_last_20d

            message = (f"Stock {'showed' if is_pass else 'did not show'} "
                       f"recent strength by making a new 52-week high in the last 20 days, {high_date}.")
            sub_results['new_52_week_high_last_20d'] = {
                "pass": new_high_in_last_20d,
                "high_date": high_date,
                "message": message
            }

        # --- 3. Finalize Result ---
        is_pass = any(sub.get('pass', False) for sub in sub_results.values())
        message = f"Market trend impact evaluated in {market_trend_context} context."

        details[metric_key] = {
            "pass": is_pass,
            "market_trend_context": market_trend_context,
            "is_recovery_phase": is_recovery_phase,
            "turning_point_date": turning_point_date,
            "sub_results": sub_results,
            "message": message
        }

    except Exception as e:
        # Handle any errors gracefully
        details.update(failed_check(metric_key, f"An unexpected error occurred: {str(e)}"))
