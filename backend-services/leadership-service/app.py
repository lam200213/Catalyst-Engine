import time
import requests
from flask import Flask, request, jsonify
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

# Data service URL from environment or default
DATA_SERVICE_URL = "http://data-service:3001"

def fetch_financial_data(ticker):
    """Fetch financial data from data service"""
    try:
        # Fetch core financial data
        financials_url = f"{DATA_SERVICE_URL}/financials/core/{ticker}"
        financials_response = requests.get(financials_url, timeout=10)
        
        if financials_response.status_code != 200:
            return None
            
        financial_data = financials_response.json()
        return financial_data
    except Exception as e:
        print(f"Error fetching financial data for {ticker}: {e}")
        return None

def fetch_price_data(ticker):
    """Fetch price data from data service"""
    try:
        # Fetch stock price data
        stock_url = f"{DATA_SERVICE_URL}/data/{ticker}"
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

@app.route('/leadership/<ticker>', methods=['GET'])
def leadership_analysis(ticker):
    """Main endpoint for leadership screening analysis"""
    start_time = time.time()
    
    # Validate ticker parameter
    if not ticker or not isinstance(ticker, str):
        return jsonify({'error': 'Invalid ticker parameter'}), 400
    
    # Fetch all required data
    financial_data = fetch_financial_data(ticker)
    if not financial_data:
        return jsonify({'error': 'Unable to fetch financial data'}), 503
    
    stock_data = fetch_price_data(ticker)
    if stock_data is None:
        return jsonify({'error': 'Failed to fetch price data due to a connection or service error'}), 503
    
    index_data = fetch_index_data()
    
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
        sp500_data = index_data  # Now contains the S&P 500 core financial data
        check_outperforms_in_rally(stock_data, sp500_data.get('^GSPC', []), details)
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
    
    # Prepare response
    response = {
        'ticker': ticker,
        'results': results,
        'metadata': {
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)