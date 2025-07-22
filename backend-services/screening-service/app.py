# backend-services/screening-service/app.py
# Applies the seven quantitative SEPA screening criteria 
import os
from flask import Flask, jsonify, request
import requests
import numpy as np
import json
from flask.json.provider import JSONProvider
from concurrent.futures import ThreadPoolExecutor
from screening_logic import apply_screening_criteria

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

@app.route('/screen/<ticker>')
def screen_ticker_endpoint(ticker):
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

def _process_ticker(ticker):
    """
    Helper function to process a single ticker.
    Encapsulates data fetching and screening logic.
    Returns the ticker if it passes, otherwise None.
    """
    try:
        # 1. Fetch data for the ticker
        data_service_url = f"{DATA_SERVICE_URL}/data/{ticker.upper()}"
        hist_resp = requests.get(data_service_url)
        
        # Skip this ticker if data fetching fails
        if hist_resp.status_code != 200:
            print(f"Skipping {ticker}: Failed to get data (status {hist_resp.status_code})")
            return None
        
        historical_data = hist_resp.json()
        
        # 2. Apply screening logic
        result = apply_screening_criteria(ticker, historical_data)
        
        # 3. Return ticker if it passes
        if result.get("passes", False):
            return ticker
            
    except requests.exceptions.RequestException as e:
        print(f"Skipping {ticker} due to connection error: {e}")
    except Exception as e:
        print(f"Skipping {ticker} due to an unexpected error during its processing: {e}")
    
    return None

@app.route('/screen/batch', methods=['POST'])
def screen_batch_endpoint():
    """
    Receives a list of tickers and returns a sub-list containing only
    the tickers that pass all screening criteria.
    """
    try:
        data = request.get_json()
        if not data or 'tickers' not in data or not isinstance(data['tickers'], list):
            return jsonify({"error": "Invalid request body. 'tickers' array is required."}), 400

        incoming_tickers = data['tickers']
        passing_tickers = []
        
        with ThreadPoolExecutor() as executor:
            # Submit all tickers to the executor
            future_to_ticker = {executor.submit(_process_ticker, ticker) for ticker in incoming_tickers}
            
            for future in future_to_ticker:
                result = future.result()
                if result:
                    passing_tickers.append(result)

        return jsonify(passing_tickers), 200

    except Exception as e:
        print(f"An internal error occurred in the batch screening endpoint: {e}")
        return jsonify({"error": "An internal error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    is_debug = os.environ.get('FLASK_DEBUG', '0').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=PORT, debug=is_debug)