# backend-services/analysis-service/app.py
import os
import json
from flask import Flask, jsonify, request
from flask.json.provider import JSONProvider
import requests
import numpy as np
import vcp_logic
from vcp_logic import run_vcp_screening, _calculate_volume_trend


app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3003))

# --- Constants ---
# For VCP detection: number of consecutive windows without a new high/low to define a peak/trough.
COUNTER_THRESHOLD = 5


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


# --- VCP (Volatility Contraction Pattern) Logic ---

# --- VCP Pattern Detection ---

def find_one_contraction(prices, start_index):
    """
    Finds a single volatility contraction pattern (VCP) from a given start index.
    It searches for a local high (peak) followed by a local low (trough).
    A peak/trough is identified when a new high/low is not found for `COUNTER_THRESHOLD` consecutive 5-day windows.
    
    Returns:
        tuple: (high_idx, high_price, low_idx, low_price) or None if no contraction is found.
    """
    if start_index < 0 or start_index >= len(prices):
        return None

    # --- Find Local High (Peak) ---
    local_highest_price = -float('inf')
    local_highest_idx = -1
    no_new_high_count = 0

    # Iterate from start_index to find a peak
    for i in range(start_index, len(prices)):
        window_end = min(i + 5, len(prices))
        if i >= window_end: break

        window_prices = prices[i : window_end]
        if not window_prices: continue

        current_window_high = max(window_prices)
        current_window_high_relative_idx = window_prices.index(current_window_high)
        current_window_high_global_idx = i + current_window_high_relative_idx

        if current_window_high > local_highest_price:
            local_highest_price = current_window_high
            local_highest_idx = current_window_high_global_idx
            no_new_high_count = 0
        else:
            no_new_high_count += 1
        
        if no_new_high_count >= COUNTER_THRESHOLD:
            break
    
    if no_new_high_count < COUNTER_THRESHOLD or local_highest_idx == -1:
        return None

    # --- Find Local Low (Trough) ---
    local_lowest_price = float('inf')
    local_lowest_idx = -1
    no_new_low_count = 0

    # Iterate from the local_highest_idx to find a trough
    for j in range(local_highest_idx, len(prices)):
        window_end = min(j + 5, len(prices))
        if j >= window_end: break

        window_prices = prices[j : window_end]
        if not window_prices: continue

        current_window_low = min(window_prices)
        current_window_low_relative_idx = window_prices.index(current_window_low)
        current_window_low_global_idx = j + current_window_low_relative_idx

        if current_window_low < local_lowest_price:
            local_lowest_price = current_window_low
            local_lowest_idx = current_window_low_global_idx
            no_new_low_count = 0
        else:
            no_new_low_count += 1
        
        if no_new_low_count >= COUNTER_THRESHOLD:
            break
    
    if no_new_low_count < COUNTER_THRESHOLD or local_lowest_idx == -1:
        return None

    if local_highest_idx >= local_lowest_idx or local_highest_price == local_lowest_price:
        return None

    return (local_highest_idx, local_highest_price, local_lowest_idx, local_lowest_price)

def find_volatility_contraction_pattern(prices):
    """
    Main function to detect VCPs by iteratively calling find_one_contraction.
    Collects all detected contractions to form the complete pattern.
    """
    contractions = []
    start_index = 0
    while start_index < len(prices):
        result = find_one_contraction(prices, start_index)
        if result:
            contractions.append(result)
            # Advance start_index past the found contraction's low point to search for the next one.
            start_index = result[2] + 1
        else:
            # If no more contractions are found, advance by one to avoid an infinite loop.
            start_index += 1
    return contractions

# --- Data Preparation and Utility Functions ---

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
        hist_resp = requests.get(f"{DATA_SERVICE_URL}/data/{ticker}")
        
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

        # 2. Prepare data for analysis
        raw_historical_data = hist_resp.json()
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

if __name__ == '__main__':
    print("Analysis Service started.")
    app.run(host='0.0.0.0', port=PORT)