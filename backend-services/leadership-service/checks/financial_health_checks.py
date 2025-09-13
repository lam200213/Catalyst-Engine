# backend-services/leadership-service/checks/financial_health_checks.py
# contain all functions related to the company's intrinsic fundamentals.

import logging
import pandas as pd
from datetime import datetime
from .utils import failed_check

# Get a logger that's a child of the app.logger, so it inherits the file handler
logger = logging.getLogger('app.logic')

# Constants for market cap ranges (in USD)
MIN_MARKET_CAP = 300_000_000      # $300M
MAX_MARKET_CAP = 10_000_000_000    # $10B

# Constants for float share classification
LOW_FLOAT_SHARES = 10_000_000      # Under 10 million shares
MEDIUM_FLOAT_SHARES = 100_000_000  # Between 10 million and 100 million shares

# Constants for time periods
RECENT_IPO_YEARS = 10              # Last 10 years

DATA_SERVICE_URL = "http://data-service:3001"

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

                # --- Graceful handling of zero division ---
                try:
                    if key2: # For margin = key1 / key2 (e.g., Net Income / Revenue)
                        new_denominator = new_period.get(key2)
                        old_denominator = old_period.get(key2)
                        if new_denominator in [0, None] or old_denominator in [0, None]:
                            return {"pass": False, "rates": [], "message": f"Cannot calculate {metric_name} growth because revenue was zero."}
                        new_val = new_period.get(key1) / new_denominator
                        old_val = old_period.get(key1) / old_denominator
                    else: # For direct values like Earnings or Revenue
                        new_val = new_period.get(key1)
                        old_val = old_period.get(key1)

                    if old_val is None or new_val is None:
                        return {"pass": False, "rates": [], "message": f"Cannot calculate {metric_name} growth due to missing data."}
                    
                    if old_val == 0:
                        # This is the specific business reason for the failure.
                        return {"pass": False, "rates": [], "message": f"Cannot calculate {metric_name} growth because the base value was zero."}
                    
                    rates.append((new_val - old_val) / abs(old_val))

                except (TypeError, KeyError):
                     return {"pass": False, "rates": [], "message": f"Missing data points for {metric_name} calculation."}
                except ZeroDivisionError as e:
                    # This is the technical log for the developer.
                    logging.error(f"DEV LOG: ZeroDivisionError for {metric_name}: {e}")
                    return {"pass": False, "rates": [], "message": f"Cannot calculate {metric_name} growth because a denominator was zero."}
            
            # --- End of graceful handling ---
            
            # Check for strictly increasing growth: Newest > Middle > Oldest
            is_accelerating = rates[0] > rates[1] > rates[2]
            message = f"Growth rates [{', '.join([f'{r:.1%}' for r in rates])}] are {'accelerating' if is_accelerating else 'not accelerating'}."
            return {"pass": is_accelerating, "rates": [f'{r:.1%}' for r in rates], "message": message}

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
