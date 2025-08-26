import time
import json
from flask import Flask, jsonify, request
import os
import re # regex import for input validation
import logging 
from leadership_logic import (
    check_accelerating_growth,
    check_yoy_eps_growth,
    check_consecutive_quarterly_growth,
    check_positive_recent_earnings,
    check_is_small_to_mid_cap,
    check_is_early_stage,
    check_has_limited_float,
    check_outperforms_in_rally,
    check_market_trend_context,
    evaluate_market_trend_impact,
    check_industry_leadership
)
from data_fetcher import (
    fetch_financial_data,
    fetch_price_data,
    fetch_index_data,
    fetch_peer_data,
    fetch_batch_financials,
    fetch_market_trends
)
app = Flask(__name__)

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 5000))

# --- Structured Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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
    market_trends_data, error = fetch_market_trends()
    if error:
        app.logger.error(f"Failed to fetch market trends data: {error[0]}")
        return {'ticker': ticker, 'error': error[0], 'status': error[1]}

    # --- Industry Peer Data Fetching ---
    peers_data, error = fetch_peer_data(ticker)
    if error:
        app.logger.error(f"Failed to fetch peer data for {ticker}: {error[0]}")
        return {'ticker': ticker, 'error': error[0], 'status': error[1]}

    raw_peer_tickers = peers_data.get("peers", [])
    if not raw_peer_tickers:
        app.logger.warning(f"No peer data found for {ticker}")
        # Proceeding without peer analysis is better than failing the whole request
        batch_financial_data = {}
    else:
        peer_tickers = [t.strip().replace('/', '-') for t in raw_peer_tickers if t]
        all_tickers = list(set(peer_tickers + [ticker]))
        batch_financials, error = fetch_batch_financials(all_tickers)
        if error:
            app.logger.error(f"Failed to fetch batch financials: {error[0]}")
            return {'ticker': ticker, 'error': error[0], 'status': error[1]}
        # The 'success' key contains the dictionary of results
        batch_financial_data = batch_financials.get("success", {})
    # --- End of Industry Peer Data Fetching ---

    # Run all leadership checks
    results = {} # used to create a clean, top-level summary of the pass/fail status for "each" major criterion
    details = {} # used as a data aggregator to collect "all" the rich, detailed information from each individual check function.
    
    try:
        check_is_small_to_mid_cap(financial_data, details)
        results['is_small_to_mid_cap'] = details.get('is_small_to_mid_cap', False)
        
        check_is_early_stage(financial_data, details)
        results['is_recent_ipo'] = details.get('is_recent_ipo', False)
        
        check_has_limited_float(financial_data, details)
        results['has_limited_float'] = details.get('has_limited_float', False)
        
        check_accelerating_growth(financial_data, details)
        results['has_accelerating_growth'] = details.get('has_accelerating_growth', False)
        
        check_yoy_eps_growth(financial_data, details)
        results['has_strong_yoy_eps_growth'] = details.get('has_strong_yoy_eps_growth', False)
        
        check_consecutive_quarterly_growth(financial_data, details)
        results['has_consecutive_quarterly_growth'] = details.get('has_consecutive_quarterly_growth', False)
        
        check_positive_recent_earnings(financial_data, details)
        results['has_positive_recent_earnings'] = details.get('has_positive_recent_earnings', False)
        
        check_outperforms_in_rally(stock_data, sp500_price_data, details)
        results['outperforms_in_rally'] = details.get('outperforms_in_rally', False)
        
        leadership_result = check_industry_leadership(ticker, peers_data, batch_financial_data)
        if "rank" in leadership_result and leadership_result['rank'] is not None:
            results['is_industry_leader'] = leadership_result['rank'] <= 3
            details['industry_leadership_details'] = leadership_result
        else:
            results['is_industry_leader'] = False
            details['industry_leadership_details'] = leadership_result
        
        check_market_trend_context(index_data, details)
        results['market_trend_context'] = details.get('market_trend_context', 'Unknown')
        
        # The key 'market_trend_context' now holds a dictionary, so we extract the string trend from it.
        market_trend_context_str = details.get('market_trend_context', {}).get('trend', 'Unknown')
        evaluate_market_trend_impact(stock_data, index_data, market_trend_context_str, market_trends_data, details)
        # Assign the nested result to its own key, ie: shallow_decline, new_52_week_high, recent_breakout
        results['market_trend_impact'] = details.get('market_trend_impact', {})
        
        
        core_criteria = [
            'is_small_to_mid_cap', 'is_recent_ipo', 'has_limited_float',
            'has_accelerating_growth', 'has_strong_yoy_eps_growth',
            'has_consecutive_quarterly_growth', 'has_positive_recent_earnings', 'is_industry_leader'
        ]
        passes_check = all(check_pass(results.get(key)) for key in core_criteria)

        # Conditionally check market context criteria
        market_trend_impact_details = results.get('market_trend_impact', {})
        market_trend_context_str = results.get('market_trend_context')
        if market_trend_context_str == 'Bearish':
            shallow_decline_passed = market_trend_impact_details.get('sub_results', {}).get('shallow_decline', {}).get('pass', False)
            passes_check = passes_check and shallow_decline_passed
        elif market_trend_context_str in ['Bullish', 'Neutral']:
            # In a recovery, a breakout OR a new high is a good sign
            is_in_recovery = "Bearish" in details.get('recent_trends', [])
            breakout_passed = market_trend_impact_details.get('sub_results', {}).get('recent_breakout', {}).get('pass', False)
            new_high_passed = market_trend_impact_details.get('sub_results', {}).get('new_52_week_high', {}).get('pass', False)
            if is_in_recovery:
                passes_check = passes_check and (breakout_passed or new_high_passed)
            else: # In a standard bull/neutral market, look for a new high
                passes_check = passes_check and new_high_passed

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
    
    for ticker in tickers:
        # Sanitize each ticker
        if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()) or '../' in ticker:
            app.logger.warning(f"Skipping invalid ticker format in batch: {ticker}")
            continue

        result = _analyze_ticker_leadership(ticker)
        
        # We only care about tickers that pass the screening in a batch job
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
    
    result = check_industry_leadership(ticker)
    
    if "error" in result:
        status_code = result.get("status_code", 500)
        return jsonify({"error": result["error"]}), status_code
    return jsonify(result), 200

@app.route('/market-trend/current', methods=['GET'])
def current_market_trend():
    """Endpoint to get the current market trend"""
    try:
        index_data = fetch_index_data()
        details = {}
        check_market_trend_context(index_data, details)
        trend = details.get('market_trend_context', 'Unknown')
        return jsonify({'status': trend}), 200
    except Exception as e:
        print(f"Error fetching market trend: {e}")
        return jsonify({'error': 'Error fetching market trend'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
