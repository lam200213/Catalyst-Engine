import requests
import pandas as pd
from datetime import datetime

# Constants for market cap ranges (in USD)
MIN_MARKET_CAP = 300_000_000      # $300M
MAX_MARKET_CAP = 10_000_000_000    # $10B

# Constants for float percentage threshold
LIMITED_FLOAT_THRESHOLD = 0.20    # 20%

# Constants for time periods
RECENT_IPO_YEARS = 10              # Last 10 years

DATA_SERVICE_URL = "http://data-service:3001"

# Functions for financial statements (like check_yoy_eps_growth) expect newest-to-oldest data, 
# while functions for price history expect oldest-to-newest, due to the data properties.

# A consistent structure for failure responses
def failed_check(metric, message, **kwargs):
    return {metric: {"pass": False, "message": message, **kwargs}}

def check_is_small_to_mid_cap(financial_data, details):
    """
    Check if the company has a market capitalization between a specified lower and upper bound.
    
    Args:
        financial_data (dict): Financial data containing 'marketCap' key.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'is_small_to_mid_cap' key of the details dictionary.
    """
    metric_key = 'is_small_to_mid_cap'

    try:
        market_cap = financial_data.get('marketCap')
        
        # Handle missing or None market cap
        if market_cap is None:
            details.update(failed_check(metric_key, "Market cap data not available.", market_cap=None))
            return
        
        is_pass = MIN_MARKET_CAP <= market_cap <= MAX_MARKET_CAP
        message = (
            f"Market cap ${market_cap:,.0f} is within the range of "
            f"${MIN_MARKET_CAP:,.0f} to ${MAX_MARKET_CAP:,.0f}."
            if is_pass
            else f"Market cap ${market_cap:,.0f} is outside the required range."
        )

        # Populate a detailed dictionary instead of a single boolean
        details[metric_key] = {
            "pass": is_pass,
            "market_cap": f"${market_cap:,.0f}",
            "required_range": f"${MIN_MARKET_CAP:,.0f} - ${MAX_MARKET_CAP:,.0f}",
            "message": message
        }
        
    except (TypeError, ValueError):
        details.update(failed_check(metric_key, "Invalid market cap data format.", market_cap=financial_data.get('marketCap')))

def check_is_early_stage(financial_data, details):
    """
    Check if the company's Initial Public Offering (IPO) was within a recent timeframe.
    
    Args:
        financial_data (dict): Financial data containing 'ipoDate' key (string in format "YYYY-MM-DD").
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'is_recent_ipo' key of the details dictionary.
    """
    metric_key = 'is_recent_ipo'
    
    try:
        ipo_date_str = financial_data.get('ipoDate')
        
        # Handle missing or None IPO date
        if not ipo_date_str:
            details.update(failed_check(metric_key, "IPO date not available.", ipo_date=None))
            return
        
        # Parse the IPO date string
        ipo_date = datetime.strptime(ipo_date_str, '%Y-%m-%d')
        
        # Calculate the difference in years
        current_date = datetime.now()
        years_since_ipo = (current_date - ipo_date).days / 365.25
        
        # Check if IPO was within the recent timeframe
        is_pass = years_since_ipo <= RECENT_IPO_YEARS
        message = (
            f"IPO was {years_since_ipo:.1f} years ago, which is within the {RECENT_IPO_YEARS}-year threshold."
            if is_pass
            else f"IPO was {years_since_ipo:.1f} years ago, which is older than the {RECENT_IPO_YEARS}-year threshold."
        )

        details[metric_key] = {
            "pass": is_pass,
            "ipo_date": ipo_date_str,
            "years_since_ipo": f"{years_since_ipo:.1f}",
            "threshold_years": RECENT_IPO_YEARS,
            "message": message
        }
        
    except (ValueError, TypeError):
        details.update(failed_check(metric_key, "Invalid IPO date format.", ipo_date=ipo_date))

def check_has_limited_float(financial_data, details):
    """
    Check if the company has a relatively small number of shares available for public trading.
    
    Args:
        financial_data (dict): Financial data containing 'sharesOutstanding' and 'floatShares' keys.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'has_limited_float' key of the details dictionary.
    """
    metric_key = 'has_limited_float'

    try:
        shares_outstanding = financial_data.get('sharesOutstanding')
        float_shares = financial_data.get('floatShares')
        
        # Handle missing or None values
        if shares_outstanding is None or float_shares is None or shares_outstanding <= 0:
            details.update(failed_check(metric_key, "Shares outstanding or float shares data not available.", 
                                        shares_outstanding=shares_outstanding, float_shares=float_shares))
            return
        
        # Calculate the float percentage
        float_percentage = float_shares / shares_outstanding
        
        # Check if the float percentage is below the threshold
        is_pass = float_percentage <= LIMITED_FLOAT_THRESHOLD
        message = (
            f"Float is {float_percentage:.1%}, which is below the {LIMITED_FLOAT_THRESHOLD:.0%} threshold."
            if is_pass
            else f"Float is {float_percentage:.1%}, which is above the {LIMITED_FLOAT_THRESHOLD:.0%} threshold."
        )
        
        details[metric_key] = {
            "pass": is_pass,
            "float_percentage": f"{float_percentage:.1%}",
            "threshold": f"<= {LIMITED_FLOAT_THRESHOLD:.0%}",
            "message": message
        }

    except (TypeError, ValueError, ZeroDivisionError):
        details.update(failed_check(metric_key, "Error calculating float percentage.", 
                                    shares_outstanding=financial_data.get('sharesOutstanding'), 
                                    float_shares=financial_data.get('floatShares')))

def check_yoy_eps_growth(financial_data, details):
    """
    Check if the YoY quarterly EPS growth is greater than 25%.
    
    The Earnings Per Share (EPS) for the most recent quarter should be at least 25% higher
    than the EPS of the same quarter in the previous year.
    
    Args:
        financial_data (dict): Financial data containing 'quarterly_earnings' key.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'has_strong_yoy_eps_growth' key of the details dictionary.
    """
    metric_key = 'has_strong_yoy_eps_growth'
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        
        # Require at least 5 quarters of data
        if len(earnings) < 5:
            details.update(failed_check(metric_key, "Insufficient quarterly earnings data (requires >=5 quarters).",
                                        quarters_found=len(earnings)))
            return
        
        # Most recent quarter (index 0) and same quarter from previous year (index 4)
        current_eps = earnings[0]['Earnings']
        previous_year_eps = earnings[4]['Earnings']
        
        # Handle division by zero or negative numbers
        if previous_year_eps <= 0:
            details.update(failed_check(metric_key, "Previous year's EPS is zero or negative, cannot calculate growth.",
                                        previous_year_eps=previous_year_eps))
            return
        
        # Calculate YoY growth percentage
        yoy_growth = (current_eps - previous_year_eps) / previous_year_eps

        # Check if the YoY growth is greater than 25%
        is_pass = yoy_growth > 0.25
        
        # Determine growth level
        if yoy_growth > 0.45:  # >45%
            yoy_eps_growth_level = 'Exceptional Growth'
        elif yoy_growth > 0.35:  # >35%
            yoy_eps_growth_level = 'High Growth'
        elif yoy_growth > 0.25:  # >25%
            yoy_eps_growth_level = 'Standard Growth'
        else:
            yoy_eps_growth_level = 'Moderate Growth'
        
        # Create message
        message = (
            f"YoY EPS growth is {yoy_growth:+.1%}, which exceeds the +25% threshold."
            if is_pass
            else f"YoY EPS growth is {yoy_growth:+.1%}, failing to meet the +25% threshold."
        )

        details[metric_key] = {
            "pass": is_pass,
            "current_quarter_eps": current_eps,
            "previous_year_eps": previous_year_eps,
            "yoy_growth": f"{yoy_growth:+.1%}",
            "yoy_eps_growth_level": yoy_eps_growth_level,
            "message": message
        }
        
    except (ZeroDivisionError, IndexError, KeyError, TypeError):
        details.update(failed_check(metric_key, "An error occurred during calculation.",
                                    earnings = earnings))

def check_positive_recent_earnings(financial_data, details):
    """
    Check if the company's Earnings Per Share (EPS) for the last fiscal year
    and the most recent quarter are both positive.
    
    Args:
        financial_data (dict): Financial data containing annual and quarterly earnings.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'has_positive_recent_earnings' key of the details dictionary.
    """
    metric_key = 'has_positive_recent_earnings'
    try:
        # Get annual and quarterly earnings data
        annual_earnings = financial_data.get('annual_earnings', [])
        quarterly_earnings = financial_data.get('quarterly_earnings', [])
        
        # Check if we have sufficient data
        if not annual_earnings or not quarterly_earnings:
            details.update(failed_check(metric_key, "Missing EPS value in earnings data.",
                                        annual_qtrs=len(annual_earnings),
                                        quarterly_qtrs=len(quarterly_earnings)))
            return
        
        # Get the most recent annual EPS (first item in the list)
        annual_eps = annual_earnings[0].get('Earnings')
        
        # Get the most recent quarterly EPS (first item in the list)
        quarterly_eps = quarterly_earnings[0].get('Earnings')
        
        # Check if both EPS values are positive
        is_pass = (
            annual_eps is not None and annual_eps > 0 and
            quarterly_eps is not None and quarterly_eps > 0
        )
        message = (
            f"Annual EPS ({annual_eps}) and Quarterly EPS ({quarterly_eps}) are both positive."
            if is_pass
            else f"Either Annual EPS ({annual_eps}) or Quarterly EPS ({quarterly_eps}) is not positive."
        )

        details[metric_key] = {
            "pass": is_pass,
            "annual_eps": annual_eps,
            "quarterly_eps": quarterly_eps,
            "message": message
        }

    except (IndexError, KeyError, TypeError):
        details['has_positive_recent_earnings'] = False

def check_outperforms_in_rally(stock_data, sp500_data, details):
    """
    Check if the stock outperforms the S&P 500 by more than 1.5x during a defined market rally period.
    
    The system identifies the start of a market rally in the S&P 500 and then compares the performance
    of both the stock and S&P 500 over the next 20 trading days. The stock must show > 1.5x the market's gain.
    
    PS: Data of price history is in order of oldest-to-newest.
    Args:
        stock_data (list): List of stock price data dictionaries. 
        sp500_data (list): List of S&P 500 price data dictionaries.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'outperforms_in_rally' key of the details dictionary.
    """
    metric_key = 'outperforms_in_rally'
    try:
        # Check if we have sufficient data
        if not stock_data or not sp500_data or len(stock_data) < 21 or len(sp500_data) < 21:
            details.update(failed_check(metric_key, "Insufficient stock or S&P 500 data (requires >=21 data points).",
                                        stock_days=len(stock_data), sp500_days=len(sp500_data)))
            return
        
        # Define parameters
        rally_threshold = 0.1  # 10% increase to identify rally start
        performance_period = 20  # 20 trading days for performance comparison
        
        # Look for a rally in the most recent data (last 180 days)
        lookback_period = min(180, len(sp500_data))
        
        # Find the start of a market rally (10% increase over 10 days)
        rally_start_idx = None
        
        # Look for a 10% increase over a 10-day period in recent data
        search_start = max(0, len(sp500_data) - lookback_period)
        search_end = len(sp500_data) - performance_period - 10
        
        for i in range(search_start, search_end):
            start_price = sp500_data[i]['close']
            # Check 10-day increase
            if i + 10 < len(sp500_data):
                end_price = sp500_data[i + 10]['close']
                if end_price >= start_price * (1 + rally_threshold):
                    rally_start_idx = i  # Rally starts at the beginning of the 10-day period
                    break
        
        # If still no rally found, we can't make a determination
        if rally_start_idx is None:
            details.update(failed_check(metric_key, "No recent market rally detected to measure against."))
            return
        
        # Define the performance comparison period (next 20 trading days)
        performance_end_idx = min(len(sp500_data) - 1, rally_start_idx + performance_period)
        
        # Get S&P 500 performance over the period
        sp500_start_price = sp500_data[rally_start_idx]['close']
        sp500_end_price = sp500_data[performance_end_idx]['close']
        sp500_performance = (sp500_end_price - sp500_start_price) / sp500_start_price
        
        # Make sure there's a positive rally (market going up)
        if sp500_performance <= 0:
            details.update(failed_check(metric_key, "Market performance during rally period was not positive.",
                                        sp500_performance=f"{sp500_performance:.2%}"))
            return
        
        # Find corresponding stock data points
        rally_start_date = sp500_data[rally_start_idx]['formatted_date']
        
        # Find the stock data point that matches or is closest to the rally start date
        stock_start_idx = None
        for i, data_point in enumerate(stock_data):
            if data_point['formatted_date'] >= rally_start_date:
                stock_start_idx = i
                break
        
        # If we can't find a matching date, use the closest available data
        if stock_start_idx is None:
            # Use the same relative position in the stock data
            relative_position = rally_start_idx / len(sp500_data)
            stock_start_idx = int(relative_position * len(stock_data))
            stock_start_idx = max(0, min(stock_start_idx, len(stock_data) - performance_period - 1))
        
        # Find the end index for stock data (20 trading days after start)
        stock_end_idx = min(len(stock_data) - 1, stock_start_idx + performance_period)
        
        # Ensure we have valid indices
        if stock_start_idx >= len(stock_data) or stock_end_idx >= len(stock_data) or stock_start_idx < 0:
            details.update(failed_check(metric_key, "Invalid stock data indices for performance period."))
            return
        
        # Calculate stock performance over the same period
        stock_start_price = stock_data[stock_start_idx]['close']
        stock_end_price = stock_data[stock_end_idx]['close']
        stock_performance = (stock_end_price - stock_start_price) / stock_start_price
        
        # Check if stock outperforms S&P 500 by more than 1.5x
        is_pass = stock_performance > (sp500_performance * 1.5)
        message = (
            f"Stock gained {stock_performance:.1%} vs S&P 500's {sp500_performance:.1%} during the rally, exceeding the 1.5x threshold."
            if is_pass
            else f"Stock gained {stock_performance:.1%} vs S&P 500's {sp500_performance:.1%}, failing to meet the 1.5x threshold."
        )
        
        details[metric_key] = {
            "pass": is_pass,
            "stock_performance": f"{stock_performance:.1%}",
            "sp500_performance": f"{sp500_performance:.1%}",
            "required_outperformance": "1.5x",
            "message": message
        }

    except Exception as e:
        # Handle any errors gracefully
        details.update(failed_check(metric_key, f"An unexpected error occurred: {e}"))

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


def evaluate_market_trend_impact(stock_data, index_data, market_trend_context, details):
    """
    Evaluate the stock's behavior relative to the market trend context.

    PS: Data of price history is in order of oldest-to-newest.
    Args:
        stock_data (list): List of stock price data dictionaries.
        index_data (dict): Dictionary containing market data for all three indices.
        market_trend_context (str): The market trend context determined by check_market_trend_context.
        details (dict): A dictionary to store the result.

    Returns:
        None: The results are stored in the details dictionary.
    """
    metric_key = 'market_trend_impact'
    try:
        # Initialize evaluation results
        shallow_decline = False
        new_52_week_high = False
        recent_breakout = False
        sub_results = {}

        # Fetch market trend data from data-service
        market_trends_url = f"{DATA_SERVICE_URL}/market-trends"
        market_trends_response = requests.get(market_trends_url, timeout=10)
        if market_trends_response.status_code != 200:
            raise Exception("Failed to fetch market trend data")

        market_trends_data = market_trends_response.json()
        recent_trends_statuses = [trend['status'] for trend in market_trends_data]
        recent_trends = recent_trends_statuses[-8:]

        # Determine if the market is in a recovery phase
        is_recovery_phase = (
            market_trend_context in ['Neutral', 'Bullish'] and
            any(trend == 'Bearish' for trend in recent_trends)
        )

        if market_trend_context == 'Bearish':
            # Shallow Decline Check
            # A stock's correction from its 52-week high must not be more than 2.5 times the current correction of the S&P 500 (SPY)
            if stock_data and '^GSPC' in index_data:
                sp500_data = index_data['^GSPC']
                sp500_high = sp500_data.get('high_52_week')
                sp500_current = sp500_data.get('current_price')
                sp500_decline = ((sp500_high - sp500_current) / sp500_high) if sp500_high and sp500_current else 0

                # Find stock's 52-week high and current price
                if len(stock_data) >= 252:  # Approximately 1 year of trading days
                    stock_high = max(day['high'] for day in stock_data[-252:])
                    stock_current = stock_data[-1]['close']
                    stock_decline = ((stock_high - stock_current) / stock_high) if stock_high else 0

                    # Check if stock's decline is not more than 2.5 times the S&P 500's decline
                    if sp500_decline > 0 and stock_decline <= (sp500_decline * 2.5):
                        shallow_decline = True

            sub_results['shallow_decline'] = {
                "pass": shallow_decline,
                "message": "Stock decline is shallow relative to S&P 500." if shallow_decline else "Stock decline exceeds threshold relative to S&P 500."
            }

        elif market_trend_context in ['Neutral', 'Bullish']:
            # New High Check
            # Check if the stock is among the first to reach a new 52-week high
            if stock_data and len(stock_data) >= 252:
                stock_high = max(day['high'] for day in stock_data[-252:-1])  # High excluding today
                current_price = stock_data[-1]['close']

                # Check if current price is a new 52-week high
                if current_price > stock_high:
                    new_52_week_high = True

            sub_results['new_52_week_high'] = {
                "pass": new_52_week_high,
                "message": "Stock reached a new 52-week high." if new_52_week_high else "Stock did not reach a new 52-week high."
            }

            # Breakout Check During Market Recovery
            if is_recovery_phase and stock_data and len(stock_data) >= 20:
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

        is_pass = all(sub['pass'] for sub in sub_results.values()) if sub_results else False
        message = f"Market trend impact evaluated in {market_trend_context} context."

        details[metric_key] = {
            "pass": is_pass,
            "market_trend_context": market_trend_context,
            "is_recovery_phase": is_recovery_phase,
            "sub_results": sub_results,
            "message": message
        }

    except Exception as e:
        # Handle any errors gracefully
        details.update(failed_check(metric_key, f"An unexpected error occurred: {str(e)}"))

def check_accelerating_growth(financial_data, details):
    """
    Check if the quarter-over-quarter growth rates are strictly increasing for
    Earnings, Sales, and Net Margin over the last 4 quarters.
    Requires at least 4 quarters of data to calculate three distinct QoQ growth rates.
    Checks if GrowthRate3 > GrowthRate2 > GrowthRate1 for each metric.
    """
    metric_key = 'has_accelerating_growth'
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        financials = financial_data.get('quarterly_financials', [])
        
        # Need at least 4 quarters to calculate 3 QoQ growth rates
        if len(earnings) < 4 or len(financials) < 4:
            details.update(failed_check(metric_key, "Insufficient data (requires >= 4 quarters of earnings and financials).", 
                                        earnings_qtrs=len(earnings), financials_qtrs=len(financials)))
            return

        def calculate_qoq_growth_rates(data, key1, key2=None):
            """Calculates and checks for 3 accelerating QoQ growth rates."""
            rates = []
            for i in range(3):
                # Indices are in reverse chronological order: 0=Q4, 1=Q3, 2=Q2, 3=Q1
                # We calculate (Newer - Older) / abs(Older)
                # Newest growth: (data[0] - data[1]) -> Q4 vs Q3
                # Middle growth: (data[1] - data[2]) -> Q3 vs Q2
                # Oldest growth: (data[2] - data[3]) -> Q2 vs Q1
                
                # Use index i for the newer period, i+1 for the older period
                new_period = data[i]
                old_period = data[i+1]

                if key2: # For margin = key1 / key2 (e.g., Net Income / Revenue)
                    new_val = new_period.get(key1) / new_period.get(key2)
                    old_val = old_period.get(key1) / old_period.get(key2)
                else: # For direct values (e.g., Earnings, Revenue)
                    new_val = new_period.get(key1)
                    old_val = old_period.get(key1)

                # Ensure values are valid for calculation
                if old_val is None or new_val is None or old_val == 0:
                     return {"pass": False, "rates": [], "message": f"Cannot calculate growth for {key1} due to zero/null base."}
                
                rates.append((new_val - old_val) / abs(old_val))
            
            # Check for strictly increasing growth: Newest > Middle > Oldest
            is_accelerating = rates[0] > rates[1] > rates[2]
            message = f"Growth rates [{', '.join([f'{r:.1%}' for r in rates])}] are {'accelerating' if is_accelerating else 'not accelerating'}."
            return {"pass": is_accelerating, "rates": [f'{r:.1%}' for r in rates], "message": message}

        # Check for acceleration across all three key metrics
        earnings_accelerating = calculate_qoq_growth_rates(earnings, 'Earnings')
        revenue_accelerating = calculate_qoq_growth_rates(earnings, 'Revenue')
        margin_accelerating = calculate_qoq_growth_rates(financials, 'Net Income', 'Total Revenue')

        is_pass = earnings_accelerating['pass'] and revenue_accelerating['pass'] and margin_accelerating['pass']
        
        details[metric_key] = {
            "pass": is_pass,
            "message": "Passes if Earnings, Revenue, and Margin all show accelerating quarter-over-quarter growth." if is_pass else "One or more metrics failed to show accelerating growth.",
            "earnings": earnings_accelerating,
            "revenue": revenue_accelerating,
            "margin": margin_accelerating
        }

    except (KeyError, TypeError, IndexError, ZeroDivisionError, AttributeError) as e:
        # Gracefully handle any data or calculation errors
        details.update(failed_check(metric_key, f"An unexpected error occurred: {e}"))


def check_consecutive_quarterly_growth(financial_data, details):
    """
    Checks if the Quarter-over-Quarter (QoQ) EPS growth has been >20%
    for the last 4 consecutive quarters. Requires at least 5 quarters of data.
    Fails if any of the last four quarters do not show >20% QoQ EPS growth.
    Categorizes the average growth level of the last four quarters.
    """
    metric_key = 'has_consecutive_quarterly_growth'
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        
        # Require at least 5 quarters of data to calculate 4 QoQ growth rates.
        if len(earnings) < 5:
            details.update(failed_check(metric_key, "Insufficient data (requires >= 5 quarters).",
                                        quarters_found=len(earnings)))
            return

        # Calculate the last 4 QoQ growth rates
        qoq_growth_rates = []
        # We need the last 5 earnings reports to get the last 4 growth rates.
        recent_earnings = earnings[:5]

        for i in range(len(recent_earnings) - 1):
            current_eps = recent_earnings[i].get('Earnings')
            next_eps = recent_earnings[i+1].get('Earnings')

            # Handle missing data, or negative/zero base EPS
            if current_eps is None or next_eps is None or next_eps <= 0:
                qoq_growth_rates.append(0)  # Assign 0 growth to avoid errors and ensure failure
                continue
            
            growth = (current_eps - next_eps) / abs(next_eps)
            qoq_growth_rates.append(growth)

        # Check that ALL of the last 4 quarters have >20% QoQ EPS growth
        is_pass = all(rate > 0.20 for rate in qoq_growth_rates)
        
        # Determine growth level based on the average of the last 4 quarters' growth
        if qoq_growth_rates:
            avg_growth = sum(qoq_growth_rates) / len(qoq_growth_rates)
            if avg_growth > 0.45:
                level = 'Exceptional Growth'
            elif avg_growth > 0.35:
                level = 'High Growth'
            elif avg_growth > 0.20:
                level = 'Standard Growth'
            else:
                level = 'Moderate Growth'

        message = (
            f"Passes with {level} growth. All 4 recent quarters show >20% QoQ EPS growth."
            if is_pass
            else "Fails. Not all of the last 4 quarters show >20% QoQ EPS growth."
        )

        details[metric_key] = {
            "pass": is_pass,
            "growth_level": f"{level}",
            "average_qoq_growth": f"{avg_growth:.1%}",
            "quarterly_growth_rates": [f"{r:.1%}" for r in qoq_growth_rates],
            "message": message
        }

    except (KeyError, TypeError, IndexError, ZeroDivisionError):
        details.update(failed_check(metric_key, "An unexpected error occurred during calculation."))

def check_industry_leadership(ticker):
    """
    Analyzes a company's industry peers and ranks them based on revenue and market cap.

    Args:
        ticker (str): The stock ticker symbol of the company to analyze.

    Returns:
        dict: A JSON object containing the ticker's rank and industry details,
              or an error message if data cannot be fetched or processed.
    """
    try:
        # 1. Call GET /industry/peers/<ticker> to get industry name and peer list
        peers_url = f"{DATA_SERVICE_URL}/industry/peers/{ticker}"
        peers_response = requests.get(peers_url, timeout=10)

        if peers_response.status_code != 200:
            return {"error": f"Could not fetch industry peers for {ticker}", "status_code": 500}

        peers_data = peers_response.json()
        industry_name = peers_data.get("industry")
        peer_tickers = peers_data.get("peers", [])

        if not industry_name:
            return {"error": f"No industry data found for {ticker}"}
        
        # Include the original ticker in the batch request
        # Even if peer_tickers is empty, we still want to process the original ticker
        all_tickers = list(set(peer_tickers + [ticker]))

        # Include the original ticker in the batch request
        all_tickers = list(set(peer_tickers + [ticker]))

        # 2. Call POST /financials/core/batch with the entire list of peer tickers
        batch_financials_url = f"{DATA_SERVICE_URL}/financials/core/batch"
        batch_response = requests.post(batch_financials_url, json={"tickers": all_tickers, "metrics": ["revenue", "marketCap", "netIncome"]}, timeout=40)

        if batch_response.status_code != 200:
            return {"error": f"Could not fetch batch financial data", "status_code": 500}

        batch_financial_data = batch_response.json().get("success", {})

        # 3. Filter out any peers with incomplete data and prepare for DataFrame
        processed_data = []
        for ticker_symbol, data in batch_financial_data.items():
            # Ensure data is valid and annual_earnings is a non-empty list
            if data and isinstance(data.get('annual_earnings'), list) and data['annual_earnings']:
                most_recent_annual = data['annual_earnings'][0]
                revenue = most_recent_annual.get('Revenue')
                net_income = most_recent_annual.get('Net Income')
                market_cap = data.get('marketCap')

                # Ensure all required metrics are present and not None
                if revenue is not None and net_income is not None and market_cap is not None:
                    processed_data.append({
                        'ticker': ticker_symbol,
                        'revenue': revenue,
                        'marketCap': market_cap,
                        'netIncome': net_income
                    })

        if not processed_data:
            return {"error": "No complete financial data available for ranking after filtering."}

        # Create a pandas DataFrame
        df = pd.DataFrame(processed_data)

        # Rank by revenue, market cap, and net income (descending)
        # method='min' assigns the lowest rank in case of ties
        df['revenue_rank'] = df['revenue'].rank(ascending=False, method='min')
        df['market_cap_rank'] = df['marketCap'].rank(ascending=False, method='min')
        df['earnings_rank'] = df['netIncome'].rank(ascending=False, method='min')

        # Combine ranks (lower combined rank is better)
        df['combined_rank'] = df['revenue_rank'] + df['market_cap_rank'] + df['earnings_rank']

        # Sort by combined rank to get the final ranking
        df = df.sort_values(by='combined_rank').reset_index(drop=True)

        # Find the rank of the original ticker
        ticker_rank_info = df[df['ticker'] == ticker]

        if not ticker_rank_info.empty:
            # Add 1 because pandas ranks are 0-indexed if reset_index is used without drop=True,
            # but rank() itself is 1-indexed. combined_rank is already a sum of 1-indexed ranks.
            # We want the position in the sorted DataFrame, which is 0-indexed.
            # So, if the first item is rank 1, its index is 0.
            # The rank should be its position + 1.
            final_rank = ticker_rank_info.index[0] + 1
        else:
            final_rank = None # Should not happen if original ticker was included in all_tickers

        # Convert numpy.int64 to Python int
        final_rank = int(final_rank) if final_rank is not None else None
        df['combined_rank'] = df['combined_rank'].astype(int)

        return {
            "ticker": ticker,
            "industry": industry_name,
            "rank": final_rank,
            "total_peers_ranked": len(df),
            "ranked_peers_data": df.to_dict(orient='records') # Optional: include full ranked data
        }

    except requests.exceptions.Timeout:
        return {"error": "Request to data service timed out."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Network or service error: {e}"}
    except Exception as e:
        print(f"Error in check_industry_leadership for {ticker}: {e}")
        return {"error": f"An unexpected error occurred: {e}"}