import requests
import pandas as pd

# Constants for market cap ranges (in USD)
MIN_MARKET_CAP = 300_000_000      # $300M
MAX_MARKET_CAP = 10_000_000_000    # $10B

# Constants for float percentage threshold
LIMITED_FLOAT_THRESHOLD = 0.20    # 20%

# Constants for time periods
RECENT_IPO_YEARS = 10              # Last 10 years

def check_is_small_to_mid_cap(financial_data, details):
    """
    Check if the company has a market capitalization between a specified lower and upper bound.
    
    Args:
        financial_data (dict): Financial data containing 'marketCap' key.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'is_small_to_mid_cap' key of the details dictionary.
    """
    try:
        market_cap = financial_data.get('marketCap')
        
        # Handle missing or None market cap
        if market_cap is None:
            details['is_small_to_mid_cap'] = False
            return
        
        # Check if market cap is within the specified range
        details['is_small_to_mid_cap'] = MIN_MARKET_CAP <= market_cap <= MAX_MARKET_CAP
        
    except (TypeError, ValueError):
        details['is_small_to_mid_cap'] = False

def check_is_early_stage(financial_data, details):
    """
    Check if the company's Initial Public Offering (IPO) was within a recent timeframe.
    
    Args:
        financial_data (dict): Financial data containing 'ipoDate' key (string in format "YYYY-MM-DD").
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'is_recent_ipo' key of the details dictionary.
    """
    from datetime import datetime
    
    try:
        ipo_date_str = financial_data.get('ipoDate')
        
        # Handle missing or None IPO date
        if not ipo_date_str:
            details['is_recent_ipo'] = False
            return
        
        # Parse the IPO date string
        ipo_date = datetime.strptime(ipo_date_str, '%Y-%m-%d')
        
        # Calculate the difference in years
        current_date = datetime.now()
        years_since_ipo = (current_date - ipo_date).days / 365.25
        
        # Check if IPO was within the recent timeframe
        details['is_recent_ipo'] = years_since_ipo <= RECENT_IPO_YEARS
        
    except (ValueError, TypeError):
        details['is_recent_ipo'] = False

def check_has_limited_float(financial_data, details):
    """
    Check if the company has a relatively small number of shares available for public trading.
    
    Args:
        financial_data (dict): Financial data containing 'sharesOutstanding' and 'floatShares' keys.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'has_limited_float' key of the details dictionary.
    """
    try:
        shares_outstanding = financial_data.get('sharesOutstanding')
        float_shares = financial_data.get('floatShares')
        
        # Handle missing or None values
        if shares_outstanding is None or float_shares is None or shares_outstanding <= 0:
            details['has_limited_float'] = False
            return
        
        # Calculate the float percentage
        float_percentage = float_shares / shares_outstanding
        
        # Check if the float percentage is below the threshold
        details['has_limited_float'] = float_percentage <= LIMITED_FLOAT_THRESHOLD
        
    except (TypeError, ValueError, ZeroDivisionError):
        details['has_limited_float'] = False

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
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        
        # Require at least 5 quarters of data
        if len(earnings) < 5:
            details['has_strong_yoy_eps_growth'] = False
            details['yoy_eps_growth_level'] = 'Insufficient Data'
            return
        
        # Most recent quarter (index -1) and same quarter from previous year (index -5)
        current_eps = earnings[-1]['Earnings']
        previous_year_eps = earnings[-5]['Earnings']
        
        # Handle division by zero or negative numbers
        if previous_year_eps <= 0:
            details['has_strong_yoy_eps_growth'] = False
            details['yoy_eps_growth_level'] = 'Negative/Zero Base'
            return
        
        # Calculate YoY growth percentage
        yoy_growth = (current_eps - previous_year_eps) / previous_year_eps
        
        # Determine growth level
        if yoy_growth > 0.45:  # >45%
            details['yoy_eps_growth_level'] = 'Exceptional Growth'
        elif yoy_growth > 0.35:  # >35%
            details['yoy_eps_growth_level'] = 'High Growth'
        elif yoy_growth > 0.25:  # >25%
            details['yoy_eps_growth_level'] = 'Standard Growth'
        else:
            details['yoy_eps_growth_level'] = 'Moderate Growth'
        
        details['has_strong_yoy_eps_growth'] = yoy_growth > 0.25  # 25%
        
    except (ZeroDivisionError, IndexError, KeyError, TypeError):
        details['has_strong_yoy_eps_growth'] = False
        details['yoy_eps_growth_level'] = 'Error'

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
    try:
        # Get annual and quarterly earnings data
        annual_earnings = financial_data.get('annual_earnings', [])
        quarterly_earnings = financial_data.get('quarterly_earnings', [])
        
        # Check if we have sufficient data
        if not annual_earnings or not quarterly_earnings:
            details['has_positive_recent_earnings'] = False
            return
        
        # Get the most recent annual EPS (first item in the list)
        annual_eps = annual_earnings[0].get('Earnings')
        
        # Get the most recent quarterly EPS (last item in the list)
        quarterly_eps = quarterly_earnings[-1].get('Earnings')
        
        # Check if both EPS values are positive
        details['has_positive_recent_earnings'] = (
            annual_eps is not None and annual_eps > 0 and
            quarterly_eps is not None and quarterly_eps > 0
        )
    except (IndexError, KeyError, TypeError):
        details['has_positive_recent_earnings'] = False

def check_outperforms_in_rally(stock_data, sp500_data, details):
    """
    Check if the stock outperforms the S&P 500 by more than 1.5x during a defined market rally period.
    
    The system identifies the start of a market rally in the S&P 500 and then compares the performance
    of both the stock and S&P 500 over the next 20 trading days. The stock must show > 1.5x the market's gain.
    
    Args:
        stock_data (list): List of stock price data dictionaries.
        sp500_data (list): List of S&P 500 price data dictionaries.
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'outperforms_in_rally' key of the details dictionary.
    """
    try:
        # Check if we have sufficient data
        if not stock_data or not sp500_data or len(stock_data) < 21 or len(sp500_data) < 21:
            details['outperforms_in_rally'] = False
            return
        
        # Define parameters
        rally_threshold = 0.05  # 5% increase to identify rally start
        performance_period = 20  # 20 trading days for performance comparison
        
        # Look for a rally in the most recent data (last 90 days)
        lookback_period = min(90, len(sp500_data))
        
        # Find the start of a market rally (5% increase over 3 days)
        rally_start_idx = None
        
        # Look for a 5% increase over a 3-day period in recent data
        search_start = max(0, len(sp500_data) - lookback_period)
        search_end = len(sp500_data) - performance_period - 3
        
        for i in range(search_start, search_end):
            start_price = sp500_data[i]['close']
            # Check 3-day increase
            if i + 3 < len(sp500_data):
                end_price = sp500_data[i + 3]['close']
                if end_price >= start_price * (1 + rally_threshold):
                    rally_start_idx = i  # Rally starts at the beginning of the 3-day period
                    break
        
        # If still no rally found, we can't make a determination
        if rally_start_idx is None:
            details['outperforms_in_rally'] = False
            return
        
        # Define the performance comparison period (next 20 trading days)
        performance_end_idx = min(len(sp500_data) - 1, rally_start_idx + performance_period)
        
        # Ensure we have enough data for the full performance period
        if performance_end_idx - rally_start_idx < 10:  # Need at least 10 days for meaningful comparison
            details['outperforms_in_rally'] = False
            return
        
        # Get S&P 500 performance over the period
        sp500_start_price = sp500_data[rally_start_idx]['close']
        sp500_end_price = sp500_data[performance_end_idx]['close']
        sp500_performance = (sp500_end_price - sp500_start_price) / sp500_start_price
        
        # Make sure there's a positive rally (market going up)
        if sp500_performance <= 0:
            details['outperforms_in_rally'] = False
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
            details['outperforms_in_rally'] = False
            return
        
        # Calculate stock performance over the same period
        stock_start_price = stock_data[stock_start_idx]['close']
        stock_end_price = stock_data[stock_end_idx]['close']
        stock_performance = (stock_end_price - stock_start_price) / stock_start_price
        
        # Check if stock outperforms S&P 500 by more than 1.5x
        details['outperforms_in_rally'] = stock_performance > (sp500_performance * 1.5)
        
    except Exception as e:
        # Handle any errors gracefully
        details['outperforms_in_rally'] = False

def check_market_trend_context(index_data, details):
    """
    Determine the market trend context based on all three major indices (SPY, DIA, QQQ) technical indicators.
    
    Args:
        index_data (dict): Dictionary containing market data for all three indices including:
                          '^GSPC', '^DJI', 'QQQ' each with 'current_price', 'sma_50', 'sma_200', 'high_52_week', 'low_52_week'
        details (dict): A dictionary to store the result.
        
    Returns:
        None: The result is stored in the 'market_trend_context' key of the details dictionary.
    """
    try:
        # Define the three major indices
        indices = ['^GSPC', '^DJI', 'QQQ']
        
        # Check if we have data for all three indices
        if not index_data or not all(index in index_data for index in indices):
            details['market_trend_context'] = 'Unknown'
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
                details['market_trend_context'] = 'Unknown'
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
            details['market_trend_context'] = 'Bullish'
        elif bearish_count == 3:
            # All three indices are bearish (below their 50-day SMA)
            details['market_trend_context'] = 'Bearish'
        else:
            # Mixed signals
            details['market_trend_context'] = 'Neutral'
        
    except Exception as e:
        # Handle any errors gracefully
        details['market_trend_context'] = 'Unknown'


def evaluate_market_trend_impact(stock_data, index_data, market_trend_context, details):
    """
    Evaluate the stock's behavior relative to the market trend context.

    Args:
        stock_data (list): List of stock price data dictionaries.
        index_data (dict): Dictionary containing market data for all three indices.
        market_trend_context (str): The market trend context determined by check_market_trend_context.
        details (dict): A dictionary to store the result.

    Returns:
        None: The results are stored in the details dictionary.
    """
    try:
        # Initialize evaluation results
        details['shallow_decline'] = False
        details['new_52_week_high'] = False
        details['recent_breakout'] = False

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
                        details['shallow_decline'] = True

        elif market_trend_context in ['Neutral', 'Bullish']:
            # New High Check
            # Check if the stock is among the first to reach a new 52-week high
            if stock_data and len(stock_data) >= 252:
                stock_high = max(day['high'] for day in stock_data[-252:-1])  # High excluding today
                current_price = stock_data[-1]['close']

                # Check if current price is a new 52-week high
                if current_price > stock_high:
                    details['new_52_week_high'] = True

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
                        details['recent_breakout'] = True

    except Exception as e:
        # Handle any errors gracefully
        details['shallow_decline'] = False
        details['new_52_week_high'] = False
        details['recent_breakout'] = False

def _calculate_rolling_average_growth(quarterly_data, key):
    """
    Calculates QoQ growth rates and then a two-quarter rolling average.
    
    Args:
        quarterly_data (list): List of dictionaries with quarterly results.
        key (str): The key for the value to analyze (e.g., 'Earnings', 'Revenue').

    Returns:
        list: A list of the two-quarter rolling average growth rates.
    """
    if not quarterly_data or len(quarterly_data) < 2:
        return []

    growth_rates = []
    for i in range(1, len(quarterly_data)):
        current_val = quarterly_data[i].get(key)
        prev_val = quarterly_data[i-1].get(key)
        
        if current_val is None or prev_val is None or prev_val == 0:
            growth_rates.append(0)  # Handle missing data or division by zero
            continue
            
        growth = (current_val - prev_val) / abs(prev_val)
        growth_rates.append(growth)

    if len(growth_rates) < 2:
        return []

    rolling_averages = []
    for i in range(1, len(growth_rates)):
        avg = (growth_rates[i] + growth_rates[i-1]) / 2
        rolling_averages.append(avg)
        
    return rolling_averages


def check_accelerating_growth(financial_data, details):
    """
    Check if the quarter-over-quarter growth rates are strictly increasing for
    Earnings, Sales, and Net Margin over the last 4 quarters.
    Requires at least 4 quarters of data to calculate three distinct QoQ growth rates.
    Checks if GrowthRate3 > GrowthRate2 > GrowthRate1 for each metric.
    """
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        financials = financial_data.get('quarterly_financials', [])
        
        # Need at least 4 quarters to calculate 3 QoQ growth rates
        if len(earnings) < 4 or len(financials) < 4:
            details['has_accelerating_growth'] = False
            return

        def calculate_qoq_growth_rates(data, key1, key2=None):
            """Calculate 3 QoQ growth rates from 4 quarters of data"""
            growth_rates = []
            for i in range(1, 4):  # Calculate 3 growth rates from 4 quarters
                if key2:  # For margin calculation (Net Income / Total Revenue)
                    current_val = data[-(4-i)][key1] / data[-(4-i)][key2]
                    prev_val = data[-(4-(i-1))][key1] / data[-(4-(i-1))][key2]
                else:  # For direct value calculation (Earnings, Revenue)
                    current_val = data[-(4-i)][key1]
                    prev_val = data[-(4-(i-1))][key1]
                
                if prev_val == 0:
                    return None
                
                growth_rate = (current_val - prev_val) / abs(prev_val)
                growth_rates.append(growth_rate)
            return growth_rates

        # Calculate QoQ growth rates for Earnings
        earnings_growth_rates = calculate_qoq_growth_rates(earnings, 'Earnings')
        if earnings_growth_rates is None:
            details['has_accelerating_growth'] = False
            return

        # Check if Earnings growth rates are strictly increasing
        earnings_accelerating = (earnings_growth_rates[2] > earnings_growth_rates[1] >
                              earnings_growth_rates[0])

        # Calculate QoQ growth rates for Revenue (Sales)
        revenue_growth_rates = calculate_qoq_growth_rates(earnings, 'Revenue')
        if revenue_growth_rates is None:
            details['has_accelerating_growth'] = False
            return

        # Check if Revenue growth rates are strictly increasing
        revenue_accelerating = (revenue_growth_rates[2] > revenue_growth_rates[1] >
                             revenue_growth_rates[0])

        # Calculate QoQ growth rates for Net Margin
        margin_growth_rates = calculate_qoq_growth_rates(financials, 'Net Income', 'Total Revenue')
        if margin_growth_rates is None:
            details['has_accelerating_growth'] = False
            return

        # Check if Net Margin growth rates are strictly increasing
        margin_accelerating = (margin_growth_rates[2] > margin_growth_rates[1] >
                            margin_growth_rates[0])
        
        details['has_accelerating_growth'] = (earnings_accelerating and
                                           revenue_accelerating and
                                           margin_accelerating)
        
    except (KeyError, TypeError, IndexError, ZeroDivisionError):
        details['has_accelerating_growth'] = False


def check_consecutive_quarterly_growth(financial_data, details):
    """
    Check if the 2Q rolling average growth for EPS has been >20%
    for the last 4 consecutive quarters.
    Requires at least 6 quarters of data to produce 4 rolling average figures.
    Fails if even one of the last four quarters does not show >20% EPS growth.
    Also categorizes the growth level similar to YoY EPS growth.
    """
    try:
        earnings = financial_data.get('quarterly_earnings', [])
        
        if len(earnings) < 6:
            details['has_consecutive_quarterly_growth'] = False
            details['consecutive_quarterly_growth_level'] = 'Insufficient Data'
            return

        # Check smoothed EPS growth
        eps_rolling_avg = _calculate_rolling_average_growth(earnings, 'Earnings')
        
        # Check that we have at least 4 rolling average figures
        if len(eps_rolling_avg) < 4:
            details['has_consecutive_quarterly_growth'] = False
            details['consecutive_quarterly_growth_level'] = 'Insufficient Data'
            return
        
        # Get the average of the last 4 quarters' growth rates
        recent_growth_rates = eps_rolling_avg[-4:]
        avg_growth = sum(recent_growth_rates) / len(recent_growth_rates)
        
        # Determine growth level
        if avg_growth > 0.45:  # >45%
            details['consecutive_quarterly_growth_level'] = 'Exceptional Growth'
        elif avg_growth > 0.35:  # >35%
            details['consecutive_quarterly_growth_level'] = 'High Growth'
        elif avg_growth > 0.20:  # >20%
            details['consecutive_quarterly_growth_level'] = 'Standard Growth'
        else:
            details['consecutive_quarterly_growth_level'] = 'Moderate Growth'
        
        # Check that ALL of the last 4 quarters have >20% EPS growth
        # If ANY quarter has <=20% growth, the function should fail
        details['has_consecutive_quarterly_growth'] = all(avg > 0.20 for avg in recent_growth_rates)
        
    except (KeyError, TypeError, IndexError):
        details['has_consecutive_quarterly_growth'] = False
        details['consecutive_quarterly_growth_level'] = 'Error'


DATA_SERVICE_URL = "http://data-service:3001"

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
        batch_response = requests.post(batch_financials_url, json={"tickers": all_tickers, "metrics": ["revenue", "marketCap", "netIncome"]}, timeout=30)

        if batch_response.status_code != 200:
            return {"error": f"Could not fetch batch financial data", "status_code": 500}

        batch_financial_data = batch_response.json().get("success", {})

        # 3. Filter out any peers with incomplete data and prepare for DataFrame
        processed_data = []
        for ticker_symbol, data in batch_financial_data.items():
            # Ensure 'revenue', 'marketCap', and 'netIncome' are present and not None
            if data and data.get('totalRevenue') is not None and data.get('marketCap') is not None and data.get('netIncome') is not None:
                processed_data.append({
                    'ticker': ticker_symbol,
                    'revenue': data['totalRevenue'],
                    'marketCap': data['marketCap'],
                    'netIncome': data['netIncome']
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