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
import traceback 
from pydantic import BaseModel, ValidationError, TypeAdapter
from typing import List, Dict
from shared.contracts import PriceDataItem

app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3002))
CHUNK_SIZE = 75 # Number of tickers to process at once for batch processing

class BatchResponse(BaseModel):
    success: Dict[str, List[PriceDataItem]]
    failed: List[str]

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

# Endpoint to screen a single ticker
@app.route('/screen/<ticker>')
def screen_ticker_endpoint(ticker):
    try:
        ticker = ticker.upper()
        # Fetch historical price data from data-service
        data_service_url = f"{DATA_SERVICE_URL}/price/{ticker}"
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
            PriceDataValidator = TypeAdapter(List[PriceDataItem])
            PriceDataValidator.validate_json(hist_resp.content)
            historical_data = hist_resp.json()
        except ValidationError as e:
            app.logger.error(f"Data contract violation from data-service for {ticker}: {e}")
            return jsonify({
                "error": "Invalid data structure received from upstream data-service.",
                "details": str(e)
            }), 502
        except requests.exceptions.JSONDecodeError:
            # Centralized error handling
            return jsonify({
                "error": "Invalid JSON response from data-service.",
                "details": hist_resp.text
            }), 502

        # debug
        print(f"[SINGLE] Received {len(historical_data)} data points for {ticker}", flush=True)
        result = apply_screening_criteria(ticker, historical_data)
        return jsonify({"ticker": ticker, **result})

    except requests.exceptions.RequestException as e:
        # This catches network errors connecting to data-service
        return jsonify({"error": "Error connecting to the data-service.", "details": str(e)}), 503
    except Exception as e:
        # This catches other unexpected errors within the screening-service
        return jsonify({"error": "An internal error occurred in the screening-service.", "details": str(e)}), 500

# Endpoint to screen a batch of tickers
def _process_chunk(chunk):
    """
    Helper function to process a single chunk of tickers.
    Returns a list of tickers that passed the screening.
    """
    passing_in_chunk = []
    try:
        # 1. Fetch data for the entire chunk from the data-service's batch endpoint
        data_service_url = f"{DATA_SERVICE_URL}/price/batch"
        resp = requests.post(data_service_url, json={"tickers": chunk, "source": "yfinance"}, timeout=120)
        
        if resp.status_code != 200:
            print(f"Warning: Chunk failed with status {resp.status_code}. Details: {resp.text}")
            return []

        try:
            # This is the idiomatic way for a BaseModel, avoiding the TypeAdapter error.
            validated_response = BatchResponse.model_validate_json(resp.content)
            batch_data = validated_response.model_dump() # Convert to dict for existing logic
        except (ValidationError, json.JSONDecodeError) as e:
            # If the data structure from the data-service is invalid, log the error and fail the chunk.
            print(f"Warning: Batch data contract violation from data-service. Error: {e}. Response: {resp.text[:500]}")
            return []
        
        successful_data = batch_data.get('success', {})
        failed_tickers = batch_data.get('failed', [])

        if failed_tickers:
            print(f"Warning: Data could not be fetched for the following tickers: {failed_tickers}")

        # 2. Apply screening logic to the successfully fetched data
        # The data is already fetched, so this part is just CPU-bound.
        for ticker, historical_data in successful_data.items():
            result = apply_screening_criteria(ticker, historical_data)
            if result.get("passes", False):
                passing_in_chunk.append(ticker)
                
    except requests.exceptions.RequestException as e:
        print(f"Warning: Request for chunk failed: {e}")
        error_details = traceback.format_exc()
        print(f"--- ERROR PROCESSING CHUNK ---\nTickers: {chunk}\nError: {e}\nTraceback:\n{error_details}\n--", flush=True)
    except Exception as e:
        print(f"Warning: Unexpected error processing chunk: {e}")
        error_details = traceback.format_exc()
        print(f"--- ERROR PROCESSING CHUNK ---\nTickers: {chunk}\nError: {e}\nTraceback:\n{error_details}\n--", flush=True)
        
    return passing_in_chunk

@app.route('/screen/batch', methods=['POST'])
def screen_batch_endpoint():
    """
    Receives a list of tickers, splits them into chunks, processes each
    chunk against the data-service's batch endpoint, and returns a final
    list of tickers that pass all screening criteria.
    """
    try:
        data = request.get_json()
        if not data or 'tickers' not in data or not isinstance(data['tickers'], list):
            return jsonify({"error": "Invalid request body. 'tickers' array is required."}), 400

        incoming_tickers = data['tickers']
        passing_tickers = []
        
        # Split the incoming tickers into chunks of CHUNK_SIZE
        ticker_chunks = [incoming_tickers[i:i + CHUNK_SIZE] for i in range(0, len(incoming_tickers), CHUNK_SIZE)]

        with ThreadPoolExecutor() as executor:
            # Submit each chunk to be processed in parallel
            future_to_chunk = {executor.submit(_process_chunk, chunk) for chunk in ticker_chunks}
            
            for future in future_to_chunk:
                passing_tickers.extend(future.result())

        return jsonify(passing_tickers), 200

    except Exception as e:
        print(f"An internal error occurred in the batch screening endpoint: {e}")
        return jsonify({"error": "An internal error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    is_debug = os.environ.get('FLASK_DEBUG', '0').lower() in ['true', '1', 't']
    app.run(host='0.0.0.0', port=PORT, debug=is_debug)