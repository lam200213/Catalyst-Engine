import time
import requests
import json
from flask import Flask, jsonify
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

def fetch_financial_data(ticker):
    """
    Fetch financial data from data service, handling errors gracefully.
    Returns a tuple of (data, status_code).
    """
    try:
        financials_url = f"{DATA_SERVICE_URL}/financials/core/{ticker}"
        financials_response = requests.get(financials_url, timeout=10)
        
        if financials_response.status_code != 200:
            return None, financials_response.status_code
            
        return financials_response.json(), 200
    except requests.exceptions.RequestException as e:
        print(f"Error fetching financial data for {ticker}: {e}")
        return None, 503 # Service Unavailable

def fetch_price_data(ticker):
    """Fetch price data from data service"""
    try:
        # Fetch stock price data
        stock_url = f"{DATA_SERVICE_URL}/price/{ticker}"
        stock_response = requests.get(stock_url, timeout=10)
        
        if stock_response.status_code != 200:
            return None
            
        stock_data = stock_response.json()
        return stock_data
    except Exception as e:
        print(f"Error fetching price data for {ticker}: {e}")
        return None

def fetch_index_data():
    """Fetch major index data from data service"""
    try:
        # Fetch data for all three major indices for market trend context
        indices = ['^GSPC', '^DJI', 'QQQ']
        index_data = {}
        
        for index in indices:
            url = f"{DATA_SERVICE_URL}/financials/core/{index}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                index_data[index] = response.json()
            else:
                index_data[index] = {}
                
        return index_data
    except Exception as e:
        print(f"Error fetching index data: {e}")
        return {}

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
        results['yoy_eps_growth_level'] = details.get('yoy_eps_growth_level', 'Unknown')
        
        # Consecutive quarterly growth check
        check_consecutive_quarterly_growth(financial_data, details)
        results['has_consecutive_quarterly_growth'] = details.get('has_consecutive_quarterly_growth', False)
        results['consecutive_quarterly_growth_level'] = details.get('consecutive_quarterly_growth_level', 'Unknown')
        
        # Positive recent earnings check
        check_positive_recent_earnings(financial_data, details)
        results['has_positive_recent_earnings'] = details.get('has_positive_recent_earnings', False)
        
        # Outperforms in rally check
        check_outperforms_in_rally(stock_data, sp500_price_data, details)
        results['outperforms_in_rally'] = details.get('outperforms_in_rally', False)
        
        # Market trend context check
        check_market_trend_context(index_data, details)
        results['market_trend_context'] = details.get('market_trend_context', 'Unknown')
        
        # Evaluate market trend impact
        market_trend_context = details.get('market_trend_context', 'Unknown')
        evaluate_market_trend_impact(stock_data, index_data, market_trend_context, details)
        results['shallow_decline'] = details.get('shallow_decline', False)
        results['new_52_week_high'] = details.get('new_52_week_high', False)
        results['recent_breakout'] = details.get('recent_breakout', False)
        
    except Exception as e:
        print(f"Error running leadership checks: {e}")
        return jsonify({'error': 'Error running leadership checks'}), 500
    
    # Calculate execution time
    execution_time = time.time() - start_time
    # Define core criteria that must always pass
    core_criteria = [
        'is_small_to_mid_cap', 'is_recent_ipo', 'has_limited_float',
        'has_accelerating_growth', 'has_strong_yoy_eps_growth',
        'has_consecutive_quarterly_growth', 'has_positive_recent_earnings',
        'outperforms_in_rally'
    ]

    # Check if all core criteria pass
    passes_check = all(results.get(key, False) for key in core_criteria)

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
    
    # Prepare response
    response = {
        'ticker': ticker,
        'passes': passes_check,
        'details': results, # Rename 'results' to 'details' for consistency with plan
        'metadata': {
            'execution_time': round(execution_time, 3)
        }
    }

    # Check industry leadership
    leadership_result = check_industry_leadership(ticker)
    if "rank" in leadership_result and leadership_result['rank'] is not None:
        response['details']['is_industry_leader'] = leadership_result['rank'] <= 3
    
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
