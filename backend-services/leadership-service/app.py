import time
import json
from flask import Flask, jsonify, request
import os
import re # regex import for input validation
import logging 
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from checks import financial_health_checks
from checks import market_relative_checks
from checks import industry_peer_checks

from data_fetcher import (
    fetch_financial_data,
    fetch_price_data,
    fetch_index_data,
    fetch_market_trends
)
app = Flask(__name__)

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 5000))

# --- Structured Logging Setup ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    # Create a rotating file handler to prevent log files from growing too large
    # It will create up to 5 backup files of 5MB each.
    file_handler = RotatingFileHandler(
        'leadership_analysis.log', 
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Define the log format
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)

    # Add handlers to the app's logger
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    
    # Prevent the root logger from handling messages again
    app.logger.propagate = False

setup_logging(app)
# --- End of Logging Setup ---

# helper function to perform leadership analysis
def _analyze_ticker_leadership(ticker):
    """
    Analyzes a single ticker for leadership criteria.
    Returns a dictionary with the analysis result, or an error dictionary.
    """
    # data fetching and error handling
    financial_data, status = fetch_financial_data(ticker)
    if not financial_data:
        app.logger.error(f"Failed to fetch financial data for {ticker}. Status: {status}")
        return {'ticker': ticker, 'error': 'Failed to fetch financial data', 'status': status}

    # --- DEBUGGING BLOCK ---
    # Print the exact data received to the container's logs
    print("--- LEADERSHIP-SERVICE DEBUG ---", flush=True)
    print(f"Data received from data-service for {ticker}:", flush=True)
    # # Use json.dumps for pretty-printing the dictionary
    print(json.dumps(financial_data, indent=2), flush=True)
    print("--- END DEBUG ---", flush=True)
    # --- END DEBUGGING BLOCK ---

    # Fetch price data
    stock_data = fetch_price_data(ticker)
    if stock_data is None:
        app.logger.error(f"Failed to fetch price data for {ticker}")
        return {'ticker': ticker, 'error': 'Failed to fetch price data', 'status': 503}

    # Fetch historical price data for S&P 500 for the rally check
    index_data = fetch_index_data()
    sp500_price_data = fetch_price_data('^GSPC')
    if sp500_price_data is None:
        app.logger.error(f"Failed to fetch S&P 500 price data for rally analysis")
        return {'ticker': ticker, 'error': 'Failed to fetch S&P 500 price data', 'status': 503}

    # Fetch market trends data
    n_days = 365
    market_trends_data, error = fetch_market_trends(n_days)
    if error:
        app.logger.error(f"Failed to fetch market trends data: {error[0]}")
        return {'ticker': ticker, 'error': error[0], 'status': error[1]}

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
        # The key 'market_trend_context' holds a dictionary, so we extract the string trend from it.
        results['market_trend_context'] = details.get('market_trend_context', {})
        # Assign the nested result to its own key, ie: shallow_decline, new_52_week_high, recent_breakout
        results['market_trend_impact'] = details.get('market_trend_impact', {})
        
        industry_peer_checks.get_and_check_industry_leadership(ticker, details)
        results['is_industry_leader'] = details.get('is_industry_leader', {"pass": False, "message": "Check failed to run."})

        core_criteria = [
            'is_small_to_mid_cap', 'is_recent_ipo', 'has_limited_float',
            'has_accelerating_growth', 'has_strong_yoy_eps_growth',
            'has_consecutive_quarterly_growth', 'has_positive_recent_earnings', 'is_industry_leader', 'market_trend_impact'
        ]
        passes_check = all(check_pass(results.get(key)) for key in core_criteria)

    except Exception as e:
        app.logger.error(f"Error running leadership checks for {ticker}: {e}")
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

    return {
        'ticker': ticker,
        'passes': passes_check,
        'details': results,
    }

# helper function to safely check the 'pass' status from either a dictionary or a direct boolean.
def check_pass(result_item):
    if isinstance(result_item, bool):
        return result_item
    if isinstance(result_item, dict):
        return result_item.get('pass', False)
    return False

@app.route('/leadership/<path:ticker>', methods=['GET'])
def leadership_analysis(ticker):
    """Main endpoint for leadership screening analysis"""
    start_time = time.time()
    
    # Input validation to prevent path traversal
    if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()) or '../' in ticker:
        return jsonify({'error': 'Invalid ticker format'}), 400
    
    analysis_result = _analyze_ticker_leadership(ticker)
    if 'error' in analysis_result:
            status_code = analysis_result.get('status', 500)
            return jsonify({'error': analysis_result['error']}), status_code

    execution_time = time.time() - start_time
    analysis_result['metadata'] = {'execution_time': round(execution_time, 3)}

    return jsonify(analysis_result)

@app.route('/leadership/batch', methods=['POST'])
def leadership_batch_analysis():
    """Endpoint for batch leadership screening"""
    start_time = time.time()
    payload = request.get_json()
    if not payload or 'tickers' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' is required."}), 400

    tickers = payload['tickers']
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
        return jsonify({"error": "'tickers' must be a list of strings."}), 400

    tickers = payload['tickers']
    app.logger.info(f"Starting batch leadership analysis for {len(tickers)} tickers.")
    
    passing_candidates = []
    # Sanitize tickers before processing
    sanitized_tickers = [
        t for t in tickers if re.match(r'^[A-Z0-9\.\-\^]+$', t.upper()) and '../' not in t
    ]

    # Use a ThreadPoolExecutor to run the I/O-bound analysis tasks in parallel.
    # The number of workers is set to 10 to balance performance without overwhelming downstream services.
    with ThreadPoolExecutor(max_workers=10) as executor:
        # map() efficiently applies the function to each ticker and returns results as they complete.
        results_iterator = executor.map(_analyze_ticker_leadership, sanitized_tickers)
        
        for result in results_iterator:
            # We only care about tickers that pass the screening and have no errors.
            if 'error' not in result and result.get('passes', False):
                passing_candidates.append(result)

    execution_time = time.time() - start_time
    app.logger.info(f"Batch leadership analysis completed in {execution_time:.2f}s. Found {len(passing_candidates)} passing candidates.")
    
    response = {
        'passing_candidates': passing_candidates,
        'metadata': {
            'total_processed': len(tickers),
            'total_passed': len(passing_candidates),
            'execution_time': round(execution_time, 3)
        }
    }
    
    return jsonify(response)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/leadership/industry_rank/<ticker>', methods=['GET'])
def industry_rank_analysis(ticker):
    """
    API endpoint to get the industry rank of a given ticker.
    """
    if not ticker or not isinstance(ticker, str):
        return jsonify({'error': 'Invalid ticker parameter'}), 400
    if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()) or '../' in ticker:
        return jsonify({'error': 'Invalid ticker format'}), 400

    # Create a dictionary to hold the results for this specific request.
    details = {}

    industry_peer_checks.get_and_check_industry_leadership(ticker, details)
    result = details.get('is_industry_leader')

    if not result or result.get("pass") is None:
        # This handles cases where the check failed internally (e.g., data fetching error)
        return jsonify({"error": result.get("message", "Failed to perform industry analysis.")}), 500

    return jsonify(result), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
