#backend-services/leadership-service/helper_functions.py
import json
from pydantic import ValidationError, TypeAdapter
import logging

from checks import financial_health_checks, market_relative_checks, industry_peer_checks
from data_fetcher import fetch_index_data, fetch_market_trends

logger = logging.getLogger(__name__)

LEADERSHIP_PROFILES = {
    "Explosive Grower": [
        'has_accelerating_growth',
        'has_strong_yoy_eps_growth',
        'has_consecutive_quarterly_growth',
        'has_positive_recent_earnings'
    ],
    "High Potential Setup": [
        'is_small_to_mid_cap',
        'is_recent_ipo',
        'has_limited_float'
    ],
    "Market Favorite": [
        'is_industry_leader',
        'market_trend_impact'
    ]
}

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

    # --- Step 1: Run all individual checks ---
    results = {} # 'results' is the single source for collecting all check outputs.

    try:
        # Each check function populates the `results` dict directly with its rich output.
        financial_health_checks.check_is_small_to_mid_cap(financial_data, results)
        financial_health_checks.check_is_early_stage(financial_data, results)
        financial_health_checks.check_has_limited_float(financial_data, results)
        financial_health_checks.check_accelerating_growth(financial_data, results)
        financial_health_checks.check_yoy_eps_growth(financial_data, results)
        financial_health_checks.check_consecutive_quarterly_growth(financial_data, results)
        financial_health_checks.check_positive_recent_earnings(financial_data, results)
        market_relative_checks.evaluate_market_trend_impact(stock_data, index_data, market_trends_data, results)
        industry_peer_checks.analyze_industry_leadership(ticker, peers_data, all_financial_data, results)
    except Exception as e:
        logger.error(f"Error running leadership checks for {ticker}: {e}")
        return {'ticker': ticker, 'error': 'An internal error occurred during checks', 'status': 500}

    # --- Step 2: Evaluate Leadership Profiles based on check results ---
    profile_eval = {}
    for profile_name, checks in LEADERSHIP_PROFILES.items():
        passed_count = sum(1 for check_key in checks if check_pass(results.get(check_key)))
        total_count = len(checks)
        profile_eval[profile_name] = {
            "passed": passed_count,
            "total": total_count,
            "is_primary_pass": passed_count == total_count and total_count > 0
        }

    # --- Step 3: Apply the two-tiered passing logic ---
    primary_pass_profiles = [name for name, eval_data in profile_eval.items() if eval_data["is_primary_pass"]]
    passes_overall = False
    summary_message = "Fails to qualify. Does not meet the criteria for any leadership profile."

    if primary_pass_profiles:
        # Primary condition met. Now check the supporting condition.
        has_all_supporting_passes = True
        for profile_name, eval_data in profile_eval.items():
            if profile_name not in primary_pass_profiles:
                if eval_data["passed"] == 0: # Must pass at least one check
                    has_all_supporting_passes = False
                    break  # No need to check further

        if has_all_supporting_passes:
            passes_overall = True
            profile_names = ", ".join(primary_pass_profiles)
            summary_message = f"Qualifies as a {profile_names} with supporting characteristics in other profiles."
        else:
            profile_names = ", ".join(primary_pass_profiles)
            summary_message = f"Fails to qualify. While passing the '{profile_names}' profile, it lacked supporting characteristics in other areas."

    # --- Step 4: Construct the final response object ---
    profile_details_for_contract = {
        name.lower().replace(" ", "_"): {
            "pass": eval_data["is_primary_pass"],
            "passed_checks": eval_data["passed"],
            "total_checks": eval_data["total"]
        }
        for name, eval_data in profile_eval.items()
    }

    leadership_summary_for_contract = {
        "qualified_profiles": primary_pass_profiles,
        "message": summary_message
    }

    industry_check_result = results.get('is_industry_leader', {})
    industry_name = industry_check_result.get('industry') if isinstance(industry_check_result, dict) else None

    return {
        'ticker': ticker,
        'passes': passes_overall,
        'leadership_summary': leadership_summary_for_contract,
        'profile_details': profile_details_for_contract,
        'details': results,
        'industry': industry_name,
    }
    # --- End of logic ---

def check_pass(result_item):
    """Helper function to safely check the 'pass' status from either a dictionary or a direct boolean."""
    if isinstance(result_item, bool):
        return result_item
    if isinstance(result_item, dict):
        return result_item.get('pass', False)
    return False