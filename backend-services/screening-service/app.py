# backend-services/screening-service/app.py
import os
from flask import Flask, jsonify
import requests
import numpy as np
import json
from flask.json.provider import JSONProvider

app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3002))

# This class teaches Flask's JSON encoder how to handle NumPy's specific data types.
class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NumpyJSONEncoder, self).default(obj)

# This class applies our custom encoder to the Flask app.
class CustomJSONProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, **kwargs, cls=NumpyJSONEncoder)
    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)

# Register the custom JSON provider with our Flask app instance.
app.json = CustomJSONProvider(app)

def extract_close_prices(historical_data):
    """
    Extracts a list of closing prices, handling both Finnhub's dictionary-of-lists
    format and yfinance's list-of-dictionaries format.
    """
    if not historical_data:
        return []
    
    # Handle yfinance format (list of dicts)
    if isinstance(historical_data, list):
        return [item['close'] for item in historical_data if 'close' in item and item['close'] is not None]
        
    # Handle Finnhub format (dict of lists)
    if isinstance(historical_data, dict) and 'c' in historical_data and historical_data['c'] is not None:
        return [price for price in historical_data['c'] if price is not None]
        
    return []

def calculate_sma(prices, period):
    """
    Calculates the Simple Moving Average (SMA) for a given period.
    Handles insufficient data by returning None.
    """
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def apply_screening_criteria(ticker, historical_data):
    """
    Applies the 7 SEPA screening criteria based on Mark Minervini's method.
    """
    close_prices = extract_close_prices(historical_data)
    
    details = {}
    values = {}
    all_passes = True

    if not close_prices:
        return {"passes": False, "details": {}, "values": {}, "reason": "Insufficient historical price data."}

    current_price = close_prices[-1]
    values['current_price'] = current_price

    # Calculate MAs
    ma_50 = calculate_sma(close_prices, 50)
    ma_150 = calculate_sma(close_prices, 150)
    ma_200 = calculate_sma(close_prices, 200)

    values['ma_50'] = ma_50
    values['ma_150'] = ma_150
    values['ma_200'] = ma_200

    # Criterion 1: Current Price > MA(150) & MA(200)
    crit1_pass = (ma_150 is not None and current_price > ma_150) and \
                 (ma_200 is not None and current_price > ma_200)
    details['current_price_above_ma150_ma200'] = crit1_pass
    all_passes = all_passes and crit1_pass

    # Criterion 2: MA(150) > MA(200)
    crit2_pass = (ma_150 is not None and ma_200 is not None and ma_150 > ma_200)
    details['ma150_above_ma200'] = crit2_pass
    all_passes = all_passes and crit2_pass

    # Criterion 3: MA(200) is trending up for at least one month. (approx 20 trading days)
    # Need at least 200 + 20 = 220 data points for this.
    crit3_pass = False
    if len(close_prices) >= 220:
        ma_200_start_month = calculate_sma(close_prices[:-20], 200)
        if ma_200 is not None and ma_200_start_month is not None:
            crit3_pass = ma_200 > ma_200_start_month
    details['ma200_trending_up'] = crit3_pass
    all_passes = all_passes and crit3_pass

    # Criterion 4: MA(50) > MA(150) & MA(200)
    crit4_pass = (ma_50 is not None and ma_150 is not None and ma_200 is not None and \
                  ma_50 > ma_150 and ma_50 > ma_200)
    details['ma50_above_ma150_ma200'] = crit4_pass
    all_passes = all_passes and crit4_pass

    # Criterion 5: Current Price > MA(50)
    crit5_pass = (ma_50 is not None and current_price > ma_50)
    details['current_price_above_ma50'] = crit5_pass
    all_passes = all_passes and crit5_pass

    # Criterion 6: Current Price is at least 30% above its 52-week low.
    crit6_pass = False
    # Assuming 252 trading days in a year for 52-week low/high
    if len(close_prices) >= 252:
        low_52_week = np.min(close_prices[-252:])
        values['low_52_week'] = low_52_week
        crit6_pass = current_price >= (low_52_week * 1.30)
    details['price_30_percent_above_52_week_low'] = crit6_pass
    all_passes = all_passes and crit6_pass

    # Criterion 7: Current price is within 25% of its 52-week high.
    crit7_pass = False
    if len(close_prices) >= 252:
        high_52_week = np.max(close_prices[-252:])
        values['high_52_week'] = high_52_week
        crit7_pass = current_price >= (high_52_week * 0.75)
    details['price_within_25_percent_of_52_week_high'] = crit7_pass
    all_passes = all_passes and crit7_pass

    return {
        "passes": all_passes,
        "details": details,
        "values": values
    }

@app.route('/screen/<ticker>')
def screen_ticker_endpoint(ticker): # Removed async
    try:
        ticker = ticker.upper()
        # Fetch historical price data from data-service
        data_service_url = f"{DATA_SERVICE_URL}/data/{ticker}"
        hist_resp = requests.get(data_service_url)

        # Explicitly check for non-200 status codes from data-service
        print(f"Data service response status code: {hist_resp.status_code}")
        print(f"Data service response text: {hist_resp.text}")
        if hist_resp.status_code == 404:
            try:
                error_details = hist_resp.json().get('error', hist_resp.text)
            except requests.exceptions.JSONDecodeError:
                error_details = hist_resp.text
            return jsonify({
                "error": "Invalid or non-existent ticker: " + ticker,
                "details": error_details
            }), 502 # Return 502 Bad Gateway for invalid tickers
        elif hist_resp.status_code != 200:
            try:
                error_details = hist_resp.json().get('error', hist_resp.text)
            except requests.exceptions.JSONDecodeError:
                error_details = hist_resp.text
            return jsonify({
                "error": "Failed to retrieve data from data-service.",
                "dependency_status_code": hist_resp.status_code,
                "dependency_error": error_details
            }), 502 # Return 502 Bad Gateway for other data-service errors

        try:
            historical_data = hist_resp.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({
                "error": "Invalid JSON response from data-service.",
                "dependency_status_code": hist_resp.status_code,
                "dependency_response": hist_resp.text
            }), 502

        result = apply_screening_criteria(ticker, historical_data)
        return jsonify({"ticker": ticker, **result})

    except requests.exceptions.RequestException as e:
        # This catches network errors connecting to data-service
        return jsonify({"error": "Error connecting to the data-service.", "details": str(e)}), 503
    except Exception as e:
        # This catches other unexpected errors within the screening-service
        return jsonify({"error": "An internal error occurred in the screening-service.", "details": str(e)}), 500

if __name__ == '__main__':
    is_debug = os.environ.get('FLASK_DEBUG', '0').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=PORT, debug=is_debug)