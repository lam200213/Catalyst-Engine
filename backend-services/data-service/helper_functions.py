# data-service/helper_functions.py
import logging

# A consistent structure for failure responses
def failed_check(metric, message, **kwargs):
    # Log the technical failure for developers
    logging.warning(f"Check failed for metric '{metric}': {message} | Details: {kwargs}")
    return {metric: {"pass": False, "message": message, **kwargs}}

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
