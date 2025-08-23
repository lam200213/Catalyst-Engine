import time
import requests
import json
from flask import Flask, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import re # regex import for input validation
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
app = Flask(__name__)

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 5000))

# --- Create a shared requests Session for connection pooling and retries ---
session = requests.Session()

# Define the retry strategy
retry_strategy = Retry(
    total=3,  # Total number of retries
    backoff_factor=1,  # Wait 1s, 2s, 4s between retries
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
    allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
)

# Mount the retry strategy to the session
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)
# --- End of shared session configuration ---

# --- Helper functions for data fetching ---
def fetch_financial_data(ticker):
    """
    Fetch financial data from data service, handling errors gracefully.
    Returns a tuple of (data, status_code).
    """
    try:
        financials_url = f"{DATA_SERVICE_URL}/financials/core/{ticker}"
        financials_response = session.get(financials_url, timeout=10)
        
        financials_response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            
        return financials_response.json(), 200
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Could not fetch financial data for {ticker}: {e}")
        return None, getattr(e.response, 'status_code', 503)

def fetch_price_data(ticker):
    """Fetch price data from data service"""
    try:
        # Fetch stock price data
        stock_url = f"{DATA_SERVICE_URL}/price/{ticker}"
        stock_response = session.get(stock_url, timeout=10) 
        stock_response.raise_for_status()
            
        stock_data = stock_response.json()
        return stock_data
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching price data for {ticker} after retries: {e}")
        return None

def fetch_index_data():
    """Fetch major index data from data service"""
    # Fetch data for all three major indices for market trend context
    indices = ['^GSPC', '^DJI', '^IXIC']
    index_data = {}
    for index in indices:
        try:
            url = f"{DATA_SERVICE_URL}/financials/core/{index}"
            response = session.get(url, timeout=10)
            response.raise_for_status()
            index_data[index] = response.json()
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error fetching index data for {index} after retries: {e}")
            index_data[index] = {}
            
    return index_data

def fetch_peer_data(ticker):
    """Fetches industry and peer list from the data-service."""
    try:
        peers_url = f"{DATA_SERVICE_URL}/industry/peers/{ticker}"
        response = session.get(peers_url, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch industry peers for {ticker}", status_code)

def fetch_batch_financials(tickers):
    """Fetches core financial data for a list of tickers in a single batch."""
    try:
        batch_url = f"{DATA_SERVICE_URL}/financials/core/batch"
        payload = {"tickers": tickers, "metrics": ["revenue", "marketCap", "netIncome"]}
        response = session.post(batch_url, json=payload, timeout=40)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch batch financial data", status_code)
    
def fetch_market_trends():
    """Fetches historical market trend data."""
    try:
        trends_url = f"{DATA_SERVICE_URL}/market-trends"
        response = session.get(trends_url, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch market trends data", status_code)

# --- End of helper functions ---

@app.route('/leadership/<path:ticker>', methods=['GET'])
def leadership_analysis(ticker):
    """Main endpoint for leadership screening analysis"""
    start_time = time.time()
    
    # Input validation to prevent path traversal
    if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()):
        return jsonify({'error': 'Invalid ticker format'}), 400
    
    # Additional check for path traversal
    if '../' in ticker:
        return jsonify({'error': 'Invalid ticker format'}), 400
    
    # Refactored data fetching and error handling
    financial_data, status = fetch_financial_data(ticker)
    if not financial_data:
        if status == 503:
            return jsonify({'error': 'Service unavailable: data-service'}), 503
        else:
            return jsonify({'error': f'Failed to fetch data from data-service (status {status})'}), 502

    # --- DEBUGGING BLOCK ---
    # Print the exact data received to the container's logs
    print("--- LEADERSHIP-SERVICE DEBUG ---", flush=True)
    print(f"Data received from data-service for {ticker}:", flush=True)
    # # Use json.dumps for pretty-printing the dictionary
    print(json.dumps(financial_data, indent=2), flush=True)
    print("--- END DEBUG ---", flush=True)
    # --- END DEBUGGING BLOCK ---

    stock_data = fetch_price_data(ticker)
    if stock_data is None:
        return jsonify({'error': 'Failed to fetch price data due to a connection or service error'}), 503
    
    index_data = fetch_index_data()

    # Fetch historical price data for S&P 500 for the rally check
    sp500_price_data = fetch_price_data('^GSPC')
    if sp500_price_data is None:
        return jsonify({'error': 'Failed to fetch S&P 500 price data for rally analysis'}), 503
    
    # --- Industry Peer Data Fetching ---
    peers_data, error = fetch_peer_data(ticker)
    if error:
        return jsonify({'error': error[0]}), error[1]

    raw_peer_tickers = peers_data.get("peers", [])
    if not raw_peer_tickers:
        return jsonify({'error': f"No peer data found for {ticker}"}), 404

    peer_tickers = [t.strip().replace('/', '-') for t in raw_peer_tickers if t]
    all_tickers = list(set(peer_tickers + [ticker]))

    batch_financials, error = fetch_batch_financials(all_tickers)
    if error:
        return jsonify({'error': error[0]}), error[1]
    
    # The 'success' key contains the dictionary of results
    batch_financial_data = batch_financials.get("success", {})
    # --- End of Industry Peer Data Fetching ---

    # Fetch market trends data 
    market_trends_data, error = fetch_market_trends()
    if error:
        return jsonify({'error': error[0]}), error[1]

    # Run all leadership checks
    results = {}
    details = {}
    
    # Run all checks and collect results
    try:
        # Market cap check
        check_is_small_to_mid_cap(financial_data, details)
        results['is_small_to_mid_cap'] = details.get('is_small_to_mid_cap', False)
        
        # Early stage check
        check_is_early_stage(financial_data, details)
        results['is_recent_ipo'] = details.get('is_recent_ipo', False)
        
        # Limited float check
        check_has_limited_float(financial_data, details)
        results['has_limited_float'] = details.get('has_limited_float', False)
        
        # Accelerating growth check
        check_accelerating_growth(financial_data, details)
        results['has_accelerating_growth'] = details.get('has_accelerating_growth', False)
        
        # YoY EPS growth check
        check_yoy_eps_growth(financial_data, details)
        results['has_strong_yoy_eps_growth'] = details.get('has_strong_yoy_eps_growth', False)
        
        # Consecutive quarterly growth check
        check_consecutive_quarterly_growth(financial_data, details)
        results['has_consecutive_quarterly_growth'] = details.get('has_consecutive_quarterly_growth', False)
        
        # Positive recent earnings check
        check_positive_recent_earnings(financial_data, details)
        results['has_positive_recent_earnings'] = details.get('has_positive_recent_earnings', False)
        
        # Outperforms in rally check
        check_outperforms_in_rally(stock_data, sp500_price_data, details)
        results['outperforms_in_rally'] = details.get('outperforms_in_rally', False)
        
        # Check industry leadership
        leadership_result = check_industry_leadership(ticker, peers_data, batch_financial_data)
        if "rank" in leadership_result and leadership_result['rank'] is not None:
            results['is_industry_leader'] = leadership_result['rank'] <= 3
            details['industry_leadership_details'] = leadership_result
        else:
            results['is_industry_leader'] = False
            details['industry_leadership_details'] = leadership_result 
        
        # Market trend context check
        check_market_trend_context(index_data, details)
        results['market_trend_context'] = details.get('market_trend_context', 'Unknown')
        
        # Evaluate market trend impact
        market_trend_context = details.get('market_trend_context', 'Unknown')
        evaluate_market_trend_impact(stock_data, index_data, market_trend_context, market_trends_data, details)
        results['shallow_decline'] = details.get('shallow_decline', False)
        results['new_52_week_high'] = details.get('new_52_week_high', False)
        results['recent_breakout'] = details.get('recent_breakout', False)
        
        # Conditionally check market context criteria
        market_context = results.get('market_trend_context')
        if market_context == 'Bearish':
            passes_check = passes_check and results.get('shallow_decline', False)
        elif market_context in ['Bullish', 'Neutral']:
            # In a recovery, a breakout OR a new high is a good sign
            is_in_recovery = "Bearish" in details.get('recent_trends', [])
            if is_in_recovery:
                passes_check = passes_check and (results.get('recent_breakout', False) or results.get('new_52_week_high', False))
            else: # In a standard bull/neutral market, look for a new high
                passes_check = passes_check and results.get('new_52_week_high', False)

    except Exception as e:
        app.logger.error(f"Error running leadership checks for {ticker}: {e}")
        return jsonify({'error': 'Error running leadership checks'}), 500
    
    # Calculate execution time
    execution_time = time.time() - start_time
    # Define core criteria that must always pass
    core_criteria = [
        'is_small_to_mid_cap', 'is_recent_ipo', 'has_limited_float',
        'has_accelerating_growth', 'has_strong_yoy_eps_growth',
        'has_consecutive_quarterly_growth', 'has_positive_recent_earnings',
    ]

    # Check if all core criteria pass
    passes_check = all(details.get(key, {}).get('pass', False) for key in core_criteria)

    # Prepare response
    response = {
        'ticker': ticker,
        'passes': passes_check,
        'details': results, # Rename 'results' to 'details' for consistency with plan
        'metadata': {
            'execution_time': round(execution_time, 3)
        }
    }

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
