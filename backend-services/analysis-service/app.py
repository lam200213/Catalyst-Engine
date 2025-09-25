# backend-services/analysis-service/app.py
# Performs the detailed Volatility Contraction Pattern (VCP) analysis
import os
import json
from flask import Flask, jsonify, request
from flask.json.provider import JSONProvider
import requests
import numpy as np
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from vcp_logic import find_volatility_contraction_pattern, run_vcp_screening, _calculate_volume_trend
from pydantic import ValidationError, TypeAdapter
from typing import List
from shared.contracts import PriceDataItem

app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3003))


# --- Flask App Initialization and Custom JSON Encoding ---

# Add the custom JSON provider to handle NumPy types, which are not natively serializable.
class NumpyJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle NumPy data types."""
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

class CustomJSONProvider(JSONProvider):
    """Custom JSON provider that uses the NumPy-aware encoder."""
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, **kwargs, cls=NumpyJSONEncoder)
    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)

app.json = CustomJSONProvider(app)

# --- Data Preparation and Utility Functions ---

def _validate_and_parse_price_data(response, ticker_for_log):
    """
    Validates the price data response from the data-service against the contract.
    Returns parsed data on success, or (None, error_response_tuple) on failure.
    This function helps enforce the PriceDataItem contract and follows DRY principle.
    """
    try:
        # Pydantic's TypeAdapter is efficient for validating lists of models
        PriceDataValidator = TypeAdapter(List[PriceDataItem])
        # .validate_json is faster as it works directly on bytes
        validated_data = PriceDataValidator.validate_json(response.content)
        # Pydantic models are returned, convert them back to dicts for the existing logic
        return [item.model_dump() for item in validated_data], None
    except ValidationError as e:
        app.logger.error(f"Data contract violation from data-service for {ticker_for_log}: {e}")
        error_payload = {
            "error": "Invalid data structure received from upstream data-service.",
            "details": str(e)
        }
        return None, (jsonify(error_payload), 502)
    except json.JSONDecodeError:
        error_payload = {
            "error": "Invalid JSON response from data-service.",
            "details": response.text
        }
        return None, (jsonify(error_payload), 502)

def prepare_historical_data(historical_data):
    """
    Transforms data-service response into sorted lists of close prices and dates.
    Expected input format: [{'formatted_date': 'YYYY-MM-DD', 'close': X.X, ...}]
    """
    if not historical_data:
        return [], [], []

    # Sort data by date to ensure chronological order
    sorted_data = sorted(historical_data, key=lambda x: x['formatted_date'])
    prices = [item['close'] for item in sorted_data]
    dates = [item['formatted_date'] for item in sorted_data]
    return prices, dates, sorted_data

def calculate_sma_series(prices, dates, period):
    """
    Calculates a continuous Simple Moving Average series.
    Returns a list of dictionaries formatted for lightweight-charts.
    """
    if len(prices) < period:
        return []
    
    sma_values = []
    # Use a rolling window to calculate SMA for each point where possible
    rolling_sma = np.convolve(prices, np.ones(period), 'valid') / period
    
    # The result of 'valid' convolution is shorter, so we align it with the original dates
    # SMA values start from the 'period-1'-th index of the original data
    for i in range(len(rolling_sma)):
        date_index = period - 1 + i
        sma_values.append({
            "time": dates[date_index],
            "value": rolling_sma[i]
        })
        
    return sma_values

# Using a ThreadPoolExecutor for concurrent VCP analysis in the batch endpoint
executor = ThreadPoolExecutor(max_workers=10)

def _process_ticker_analysis(ticker, historical_data, mode):
    """
    Helper function to run VCP analysis for a single ticker with its data.
    Designed for parallel execution in the batch endpoint.
    Returns a result dict if VCP passes, otherwise None.
    """
    try:
        prices, _, historical_data_sorted = prepare_historical_data(historical_data)
        if not prices:
            return None

        volumes = [item.get('volume', 0) for item in historical_data_sorted]

        # Run VCP analysis using the 'fast' mode logic for efficiency
        vcp_results = find_volatility_contraction_pattern(prices)
        vcp_pass_status, vcp_footprint_string, _ = run_vcp_screening(vcp_results, prices, volumes, mode)

        if vcp_pass_status:
            return {
                "ticker": ticker,
                "vcp_pass": vcp_pass_status,
                "vcpFootprint": vcp_footprint_string,
            }
        return None
    except Exception:
        # Log the exception if needed, but return None to not crash the batch
        return None

# --- API Endpoints ---

@app.route('/')
def index():
    """Health check endpoint."""
    return "Analysis Service is running."

@app.route('/analyze/<ticker>')
def analyze_ticker_endpoint(ticker):
    """
    Main endpoint to perform VCP analysis on a given stock ticker.
    Supports two modes:
    - 'full' (default): Returns a detailed breakdown of all VCP checks.
    - 'fast': Halts on the first failure and returns a lean response.
    """
    mode = request.args.get('mode', 'full') # Read the mode parameter
    print(f"Received analysis request for ticker: {ticker}, mode: {mode}")
    try:
        ticker = ticker.upper()
        # 1. Fetch historical data from the data-service
        hist_resp = requests.get(f"{DATA_SERVICE_URL}/price/{ticker}")
        
        if hist_resp.status_code != 200:
            try:
                error_details = hist_resp.json().get('error', hist_resp.text)
            except requests.exceptions.JSONDecodeError:
                error_details = hist_resp.text
            
            error_message = "Failed to retrieve data from data-service."
            if hist_resp.status_code == 404:
                error_message = f"Invalid or non-existent ticker: {ticker}"

            return jsonify({
                "error": error_message,
                "dependency_status_code": hist_resp.status_code,
                "details": error_details
            }), 502 # 502 Bad Gateway for dependency errors

        # 1.5. Validate data contract before processing using the DRY helper function
        raw_historical_data, error_response = _validate_and_parse_price_data(hist_resp, ticker)
        if error_response:
            return error_response

        # 2. Prepare data for analysis
        prices, dates, historical_data_sorted = prepare_historical_data(raw_historical_data)

        if not prices:
            return jsonify({"error": f"No price data available for {ticker} to analyze."}), 404

        volumes = [item.get('volume', 0) for item in historical_data_sorted]

        # 3. Run VCP analysis
        vcp_results = find_volatility_contraction_pattern(prices)
        vcp_pass_status, vcp_footprint_string, vcp_details = run_vcp_screening(vcp_results, prices, volumes, mode)

        # 4. Calculate Moving Averages for charting
        ma_20_series = calculate_sma_series(prices, dates, 20)
        ma_50_series = calculate_sma_series(prices, dates, 50)
        ma_150_series = calculate_sma_series(prices, dates, 150)
        ma_200_series = calculate_sma_series(prices, dates, 200)

        # 5. Assemble chart data for the frontend
        chart_data = {
            "detected": bool(vcp_results),
            "message": "VCP analysis complete." if vcp_results else "No VCP detected.",
            "vcpLines": [],
            "buyPoints": [],
            "sellPoints": [],
            "lowVolumePivotDate": None,
            "volumeTrendLine": [],
            "ma20": ma_20_series,
            "ma50": ma_50_series,
            "ma150": ma_150_series,
            "ma200": ma_200_series,
            "historicalData": historical_data_sorted
        }

        if vcp_results:
            # Generate lines connecting highs and lows for charting the VCP
            vcp_lines = []
            for high_idx, high_price, low_idx, low_price in vcp_results:
                vcp_lines.extend([
                    {"time": dates[high_idx], "value": high_price},
                    {"time": dates[low_idx], "value": low_price}
                ])
            chart_data["vcpLines"] = vcp_lines

            # Define potential buy/sell points based on the last contraction
            last_high_price = vcp_results[-1][1]
            last_low_price = vcp_results[-1][3]
            chart_data["buyPoints"] = [{"value": last_high_price * 1.01}]
            chart_data["sellPoints"] = [{"value": last_low_price * 0.99}]

            # Identify the date of the lowest volume within the last contraction
            last_high_idx, _, last_low_idx, _ = vcp_results[-1]
            if last_high_idx < len(volumes) and last_low_idx < len(volumes):
                contraction_volumes = volumes[last_high_idx : last_low_idx + 1]
                if contraction_volumes:
                    min_vol_local_idx = np.argmin(contraction_volumes)
                    min_vol_global_idx = last_high_idx + min_vol_local_idx
                    chart_data["lowVolumePivotDate"] = dates[min_vol_global_idx]
                
                # Calculate the volume trend line for the last contraction for charting
                if len(contraction_volumes) > 1:
                    slope, intercept = _calculate_volume_trend(contraction_volumes)
                    start_point = {"time": dates[last_high_idx], "value": intercept}
                    end_point_val = slope * (len(contraction_volumes) - 1) + intercept
                    end_point = {"time": dates[last_low_idx], "value": end_point_val}
                    chart_data["volumeTrendLine"] = [start_point, end_point]

        # 6. Return the final JSON response
        response_payload = {
            "ticker": ticker,
            "vcp_pass": vcp_pass_status,
            "vcpFootprint": vcp_footprint_string,
            "chart_data": chart_data,
        }
        # Only include details if in full mode
        if mode == 'full':
            response_payload["vcp_details"] = vcp_details

        return jsonify(response_payload)
    
    except requests.exceptions.RequestException as e:
        print(f"Connection error to data-service: {e}")
        return jsonify({"error": "Service unavailable: data-service", "details": str(e)}), 503
    except Exception as e:
        print(f"Unhandled exception in analyze_ticker_endpoint: {e}")
        return jsonify({"error": "An internal error occurred in the analysis service."}), 500

@app.route('/analyze/batch', methods=['POST'])
def analyze_batch_endpoint():
    """
    Analyzes a batch of tickers for VCP.
    Fetches all price data in a single batch call and then processes in parallel.
    'mode' can be passed in the JSON payload. Defaults to 'fast'.
    """
    try:
        payload = request.get_json()
        if not payload or 'tickers' not in payload or not isinstance(payload['tickers'], list):
            return jsonify({"error": "Invalid request. 'tickers' array is required."}), 400

        mode = payload.get('mode', 'fast')
        tickers = payload['tickers']
        if not tickers:
            return jsonify([]), 200

        # 1. Fetch all historical data in a single batch request
        try:
            data_resp = requests.post(
                f"{DATA_SERVICE_URL}/price/batch",
                json={"tickers": tickers, "source": "yfinance"},
                timeout=120
            )
            if data_resp.status_code != 200:
                return jsonify({
                    "error": "Failed to retrieve batch data from data-service.",
                    "details": data_resp.text
                }), 502
            
            try:
                raw_batch_data = data_resp.json()
                successful_data = raw_batch_data.get('success', {})
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON response from data-service", "details": data_resp.text}), 502
            
        except requests.exceptions.RequestException as e:
            return jsonify({"error": "Error connecting to data-service.", "details": str(e)}), 503

        # 2. Process each ticker's data in parallel
        passing_candidates = []

        # Pydantic validator for validating the price data list for each ticker
        PriceDataValidator = TypeAdapter(List[PriceDataItem])

        # Use the executor to submit analysis tasks
        future_to_ticker = {}
        for ticker, data in successful_data.items():
            try:
                # Validate the data for each ticker against the contract before processing
                PriceDataValidator.validate_python(data)
                future = executor.submit(_process_ticker_analysis, ticker, data, mode)
                future_to_ticker[future] = ticker
            except ValidationError as e:
                # Log the contract violation and skip this ticker to maintain batch resilience
                app.logger.warning(f"Contract violation for {ticker} in batch, skipping. Details: {e}")
                continue
        
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    passing_candidates.append(result)
            except Exception as exc:
                # Log the specific ticker that failed and continue with the batch
                print(f"Ticker '{ticker}' generated an exception during batch analysis: {exc}")

        return jsonify(passing_candidates), 200

    except Exception as e:
        print(f"An internal error occurred in the batch screening endpoint: {e}")
        return jsonify({"error": "An internal error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    print("Analysis Service started.")
    app.run(host='0.0.0.0', port=PORT)