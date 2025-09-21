# backend-services/leadership-service/checks/financial_health_checks.py
# contain all functions related to the company's intrinsic fundamentals.

import logging
import pandas as pd
from datetime import datetime
import numpy as np
from .utils import failed_check

# Get a logger that's a child of the app.logger, so it inherits the file handler
logger = logging.getLogger(__name__)

# Constants for market cap ranges (in USD)
MIN_MARKET_CAP = 300_000_000      # $300M
MAX_MARKET_CAP = 10_000_000_000    # $10B

# Constants for float share classification
LOW_FLOAT_SHARES = 10_000_000      # Under 10 million shares
MEDIUM_FLOAT_SHARES = 100_000_000  # Between 10 million and 100 million shares

# Constants for time periods
RECENT_IPO_YEARS = 10              # Last 10 years

DATA_SERVICE_URL = "http://data-service:3001"

# Helper function
def calculate_growth_rate(current, previous, max_cap=10.0):
    """
    Safely computes a growth rate, handling edge cases.
    
    Computes (current – previous) / abs(previous), and handles:
      • None or non-numeric inputs → returns {'rate': 0.0, 'capped': False}
      • previous = 0 → returns capped rate if current is positive
      • infinite or excessively large rates → caps the rate to max_cap
      
    Returns:
        dict: A dictionary containing {'rate': float, 'capped': bool}.
    """
    result = {'rate': 0.0, 'capped': False}
    try:
        # Ensure inputs are numeric and not None
        if not all(isinstance(v, (int, float)) for v in [current, previous]):
            logger.debug(f"Non-numeric or None input: current={current}, previous={previous}")
            return result

        # Handle the zero-denominator case
        if previous == 0:
            if current > 0:
                logger.warning(f"Previous value is 0, current is {current}. Capping growth.")
                result.update(rate=max_cap, capped=True)
            # If current is also 0 or negative, growth is 0.0
            return result
            
        # Standard calculation using absolute for the denominator
        # This correctly handles growth from a negative base
        raw_rate = (current - previous) / abs(previous)

        # Cap infinite or overly large rates
        if not np.isfinite(raw_rate) or raw_rate > max_cap:
            logger.info(f"Raw rate {raw_rate:.2f} exceeds cap of {max_cap}. Capping.")
            result.update(rate=max_cap, capped=True)
        else:
            result['rate'] = raw_rate

    except Exception as e:
        logger.error(f"Error in calculate_growth_rate(current={current}, previous={previous}): {e}", exc_info=True)
        # Return default value on any unexpected error
        result = {'rate': 0.0, 'capped': False}
        
    return result


# Functions for financial statements (like check_yoy_eps_growth) expect newest-to-oldest data, 
# while functions for price history expect oldest-to-newest, due to the data properties.

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
    Checks if the company has a low or medium float based on the absolute number of shares.

    - Low Float: < 10 million shares
    - Medium Float: 10 million to 100 million shares
    - High Float: > 100 million shares

    The check passes if the float is 'low' or 'medium'.

    Args:
        financial_data (dict): A dictionary containing 'floatShares'.
        details (dict): A dictionary to store the result.
    """
    metric_key = 'has_limited_float'

    try:
        float_shares = financial_data.get('floatShares')
        
        # Handle missing or None values
        if float_shares is None:
            details.update(failed_check(metric_key, "Float shares data not available.", 
                                        float_shares=float_shares))
            return
        
        # Classify the float
        if float_shares < LOW_FLOAT_SHARES:
            classification = "Low"
        elif float_shares <= MEDIUM_FLOAT_SHARES:
            classification = "Medium"
        else:
            classification = "High"

        # Check if the float percentage is below high
        is_pass = classification in ["Low", "Medium"]
        
        message = (
            f"Passes. Float is '{classification}' with {float_shares:,.0f} shares."
            if is_pass
            else f"Fails. Float is '{classification}' with {float_shares:,.0f} shares, which is considered high."
        )
        
        details[metric_key] = {
            "pass": is_pass,
            "float_shares": float_shares,
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
        current_quarter_eps = earnings[0]['Earnings']
        previous_year_eps = earnings[4]['Earnings']
        
        # Calculate YoY growth percentage
        growth_info = calculate_growth_rate(current_quarter_eps, previous_year_eps)
        yoy_growth = growth_info['rate']

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
            "current_quarter_eps": current_quarter_eps,
            "previous_year_eps": previous_year_eps,
            "yoy_growth": f"{yoy_growth:+.1%}",
            "yoy_eps_growth_level": yoy_eps_growth_level,
            "is_capped": growth_info['capped'],
            "message": message
        }
        
    except (IndexError, KeyError, TypeError) as e: 
        logger.error(f"Error in {metric_key}: {e}", exc_info=True)
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
        
        # Check that values are numeric before comparison
        annual_eps_is_positive = isinstance(annual_eps, (int, float)) and annual_eps > 0
        quarterly_eps_is_positive = isinstance(quarterly_eps, (int, float)) and quarterly_eps > 0

        is_pass = annual_eps_is_positive and quarterly_eps_is_positive

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

        def calculate_qoq_growth_rates(data, metric_name, key1, key2=None):
            """Calculates and checks for 3 accelerating QoQ growth rates."""
            # Store the full rate objects, not just the rate value
            rate_objects = [] 
            for i in range(3):
                # Indices are in reverse chronological order: 0=Q4, 1=Q3, 2=Q2, 3=Q1
                # We calculate 3 rates: Q4vQ3, Q3vQ2, Q2vQ1 (newest to oldest)
                
                # Use index i for the newer period, i+1 for the older period
                new_period, old_period = data[i], data[i+1]

                # --- Graceful handling of zero division ---
                try:
                    if key2: # For margin = key1 / key2 (e.g., Net Income / Revenue)
                        num_new, den_new = new_period.get(key1), new_period.get(key2) # den for denominator
                        num_old, den_old = old_period.get(key1), old_period.get(key2)
                        if None in (num_new, den_new, num_old, den_old) or 0 in (den_new, den_old):
                            rate_objects.append({'rate': 0.0, 'capped': False}) # Incalculable, treat as zero growth
                            continue
                        new_val, old_val = num_new / den_new, num_old / den_old
                    else: # Direct value (e.g., Earnings, Revenue)
                        new_val, old_val = new_period.get(key1), old_period.get(key1)
                        if new_val is None or old_val is None:
                           rate_objects.append({'rate': 0.0, 'capped': False}) # Missing data, treat as zero growth
                           continue
                        
                except (TypeError, KeyError) as e:
                    logger.error(f"Error extracting {metric_name} values: {e}", exc_info=True)
                    rate_objects.append({'rate': 0.0, 'capped': False})
                    continue
                
                # Delegate the core calculation
                growth_info = calculate_growth_rate(new_val, old_val)
                rate_objects.append(growth_info)

            # --- End of graceful handling ---

            # Filter out capped rates before the acceleration check
            # The comparison should only happen on organic, non-extraordinary growth figures.
            uncapped_rates = [info['rate'] for info in rate_objects if not info['capped']]

            # Check for strictly increasing growth on the *uncapped* values.
            # Need at least two uncapped points to check for acceleration.
            is_accelerating = False
            if len(uncapped_rates) >= 2:
                # Comparison is [Newest > Middle > Oldest]
                is_accelerating = all(uncapped_rates[i] > uncapped_rates[i+1] for i in range(len(uncapped_rates)-1))

            # Format human-readable strings, flagging capped values
            pct_strs = [f"{info['rate']:.1%}{' (CAPPED)' if info['capped'] else ''}" for info in rate_objects]
            
            msg = f"{metric_name} rates [{', '.join(pct_strs)}] are {'accelerating' if is_accelerating else 'not accelerating'}."
            if len(uncapped_rates) < len(rate_objects):
                msg += " Capped values were excluded from the acceleration check."

            return {
                "pass": is_accelerating, 
                "rates_formatted": pct_strs, 
                "rates_data": rate_objects, # Return the raw objects
                "message": msg
            }

        # --- Main Logic ---
        # Check for acceleration across all three key metrics
        earnings_accelerating = calculate_qoq_growth_rates(earnings, 'Earnings', 'Earnings')
        revenue_accelerating = calculate_qoq_growth_rates(earnings, 'Revenue', 'Revenue')
        margin_accelerating = calculate_qoq_growth_rates(financials, 'Net Margin', 'Net Income', 'Total Revenue')

        is_pass = earnings_accelerating['pass'] and revenue_accelerating['pass'] and margin_accelerating['pass']
        message = "All metrics (Earnings, Revenue, Margin) show accelerating quarter-over-quarter growth." if is_pass else "One or more metrics failed to show accelerating growth."
        
        details[metric_key] = {
            "pass": is_pass,
            "message": message,
            "earnings": earnings_accelerating,
            "revenue": revenue_accelerating,
            "margin": margin_accelerating
        }

    except (KeyError, TypeError, IndexError, ZeroDivisionError, AttributeError) as e:
        # Gracefully handle any data or calculation errors
        logging.error(f"DEV LOG: Unhandled exception in check_accelerating_growth: {e}", exc_info=True)
        details.update(failed_check(metric_key, "An unexpected error occurred during analysis."))


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
        qoq_growth_infos = []

        for i in range(len(recent_earnings) - 1):
            current_eps = recent_earnings[i].get('Earnings')
            previous_eps = recent_earnings[i+1].get('Earnings')

            qoq_growth_infos.append(calculate_growth_rate(current_eps, previous_eps))

        qoq_growth_rates = [info['rate'] for info in qoq_growth_infos]

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
            "quarterly_growth_rates": [f"{info['rate']:.1%}{' (CAPPED)' if info['capped'] else ''}" for info in qoq_growth_infos],
            "rates_data": qoq_growth_infos,
            "message": message
        }

    except Exception as e: 
        logger.error(f"Error in {metric_key}: {e}", exc_info=True)
        details.update(failed_check(metric_key, "An unexpected error occurred during calculation."))