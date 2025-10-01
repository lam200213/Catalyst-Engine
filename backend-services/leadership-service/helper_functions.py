#backend-services/leadership-service/helper_functions.py
import json
from pydantic import ValidationError, TypeAdapter
from typing import List
import logging

from checks import financial_health_checks, market_relative_checks, industry_peer_checks
from data_fetcher import fetch_index_data, fetch_market_trends
from shared.contracts import CoreFinancials, PriceDataItem

logger = logging.getLogger(__name__)

def validate_data_contract(data, validator, ticker_for_log, contract_name):
    """
    Validates data against a Pydantic model/validator. Adheres to DRY principle.
    Returns serialized data on success, None on failure.
    """
    try:
        # Handle lists via TypeAdapter
        if isinstance(validator, TypeAdapter):
            validated_items = validator.validate_python(data)
            return [item.model_dump(by_alias=True) for item in validated_items]
        # Handle single objects via model_validate
        else:
            return validator.model_validate(data).model_dump(by_alias=True)
    except ValidationError as e:
        logger.error(f"Contract violation for {contract_name} for {ticker_for_log}: {e}")
        return None

def fetch_general_data_for_analysis():   
    # Fetch historical price data
    index_data = fetch_index_data()
    if not index_data:
        logger.error(f"Failed to fetch index data")
        return {'error': 'Failed to fetch index data', 'status': 503}

    # Fetch market trends data
    n_days = 365
    market_trends_data, error = fetch_market_trends(n_days)
    if error:
        logger.error(f"Failed to fetch market trends data: {error[0]}")
        return {'error': error[0], 'status': error[1]}

    return index_data, market_trends_data

# helper function to perform leadership analysis
def analyze_ticker_leadership(ticker, index_data, market_trends_data, financial_data, stock_data, peers_data, all_financial_data):
    """
    Analyzes a single ticker for leadership criteria.
    Returns a dictionary with the analysis result, or an error dictionary.
    """
    # data validation
    if not stock_data:
        logger.error(f"Missing price data for {ticker} in analysis function.")
        return {'ticker': ticker, 'error': 'Missing price data for analysis', 'status': 400}

    if not financial_data:
        logger.error(f"Missing financial data for {ticker} in analysis function.")
        return {'ticker': ticker, 'error': 'Missing financial data for analysis', 'status': 400}

    # --- DEBUGGING BLOCK ---
    # Print the exact data received to the container's logs
    print("--- LEADERSHIP-SERVICE DEBUG ---", flush=True)
    print(f"Data received from data-service for {ticker}:", flush=True)
    # # Use json.dumps for pretty-printing the dictionary
    print(json.dumps(financial_data, indent=2), flush=True)
    print("--- END DEBUG ---", flush=True)
    # --- END DEBUGGING BLOCK ---

    # Run all leadership checks
    results = {} # used to create a clean, top-level summary of the pass/fail status for "each" major criterion
    details = {} # used as a data aggregator to collect "all" the rich, detailed information from each individual check function.
    
    try:
        financial_health_checks.check_is_small_to_mid_cap(financial_data, details)
        results['is_small_to_mid_cap'] = details.get('is_small_to_mid_cap', False)
        
        financial_health_checks.check_is_early_stage(financial_data, details)
        results['is_recent_ipo'] = details.get('is_recent_ipo', False)
        
        financial_health_checks.check_has_limited_float(financial_data, details)
        results['has_limited_float'] = details.get('has_limited_float', False)
        
        financial_health_checks.check_accelerating_growth(financial_data, details)
        results['has_accelerating_growth'] = details.get('has_accelerating_growth', False)
        
        financial_health_checks.check_yoy_eps_growth(financial_data, details)
        results['has_strong_yoy_eps_growth'] = details.get('has_strong_yoy_eps_growth', False)
        
        financial_health_checks.check_consecutive_quarterly_growth(financial_data, details)
        results['has_consecutive_quarterly_growth'] = details.get('has_consecutive_quarterly_growth', False)
        
        financial_health_checks.check_positive_recent_earnings(financial_data, details)
        results['has_positive_recent_earnings'] = details.get('has_positive_recent_earnings', False)
        
        market_relative_checks.evaluate_market_trend_impact(stock_data, index_data, market_trends_data, details)

        # Assign the nested result to its own key, ie: shallow_decline, new_52_week_high, recent_breakout
        results['market_trend_impact'] = details.get('market_trend_impact', {})
        
        industry_peer_checks.analyze_industry_leadership(ticker, peers_data, all_financial_data, details)
        results['is_industry_leader'] = details.get('is_industry_leader', {"pass": False, "message": "Check failed to run."})

        core_criteria = [
            'is_small_to_mid_cap', 'is_recent_ipo', 'has_limited_float',
            'has_accelerating_growth', 'has_strong_yoy_eps_growth',
            'has_consecutive_quarterly_growth', 'has_positive_recent_earnings', 'is_industry_leader', 'market_trend_impact'
        ]
        passes_check = all(check_pass(results.get(key)) for key in core_criteria)

    except Exception as e:
        logger.error(f"Error running leadership checks for {ticker}: {e}")
        return {'ticker': ticker, 'error': 'An internal error occurred during checks', 'status': 500}

    # for detailed logging of failed checks.
    print(f"--- Leadership Analysis Details for {ticker} ---")
    for metric, result in results.items():
        if isinstance(result, dict): # Ensure we're looking at a metric result
            passed = result.get('pass', True)
            message = result.get('message')
            
            if not passed and message:
                print(f"[FAIL] {metric}: {message}")
            elif passed and message: # Optional: log success messages too
                print(f"[PASS] {metric}: {message}")
    print("-------------------------------------------------")

    industry_check_result = results.get('is_industry_leader', {})
    # Ensure the result is a dict before trying to get a key from it.
    industry_name = industry_check_result.get('industry') if isinstance(industry_check_result, dict) else None

    return {
        'ticker': ticker,
        'passes': passes_check,
        'details': results,
        'industry': industry_name,
    }

def check_pass(result_item):
    """Helper function to safely check the 'pass' status from either a dictionary or a direct boolean."""
    if isinstance(result_item, bool):
        return result_item
    if isinstance(result_item, dict):
        return result_item.get('pass', False)
    return False