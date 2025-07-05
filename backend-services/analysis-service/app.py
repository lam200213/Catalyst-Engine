# backend-services/analysis-service/app.py
import os
import json
from flask import Flask, jsonify
from flask.json.provider import JSONProvider
import requests
import numpy as np


app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3003))

# Define constants from algoParas in cookStock.py
COUNTER_THRESHOLD = 5 # Used for finding local highs/lows (5 consecutive non-new highs/lows)
PIVOT_PRICE_PERC = 0.2 # For is_pivot_good, max correction percentage
PRICE_POSITION_LOW = 0.66 # For price_strategy, current price position relative to 1-year low/high

# Add the custom JSON provider to handle NumPy types
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

class CustomJSONProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, **kwargs, cls=NumpyJSONEncoder)
    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)

app.json = CustomJSONProvider(app)

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
    return prices, dates, sorted_data # Return original sorted data for historicalData

def find_one_contraction(prices, start_index):
    """
    Finds a single volatility contraction pattern (VCP) from a given start index.
    It searches for a local high (peak) followed by a local low (trough) within rolling 5-day windows.
    Returns (high_idx, high_price, low_idx, low_price) or None if no contraction is found.
    """
    if start_index < 0 or start_index >= len(prices):
        return None

    # --- Find Local High (Peak) ---
    local_highest_price = -float('inf')
    local_highest_idx = -1
    no_new_high_count = 0

    # Iterate from start_index to find a peak
    # A peak is found when 5 consecutive 5-day windows do not produce a new high
    for i in range(start_index, len(prices)):
        # Define a 5-day window starting from current index 'i'
        window_end = min(i + 5, len(prices))
        if i >= window_end: # Not enough data for a 5-day window
            break

        window_prices = prices[i : window_end]
        if not window_prices:
            continue

        current_window_high = max(window_prices)
        # Get the relative index of the highest price within this window, then convert to global index
        current_window_high_relative_idx = window_prices.index(current_window_high)
        current_window_high_global_idx = i + current_window_high_relative_idx

        if current_window_high > local_highest_price:
            local_highest_price = current_window_high
            local_highest_idx = current_window_high_global_idx
            no_new_high_count = 0 # Reset counter if a new high is found
        else:
            no_new_high_count += 1 # Increment if no new high in this window
        
        if no_new_high_count >= COUNTER_THRESHOLD:
            # Found a peak: 5 consecutive windows without a new high
            break
    
    # If we didn't find a peak (counter didn't reach threshold) or no high was set
    if no_new_high_count < COUNTER_THRESHOLD or local_highest_idx == -1:
        return None

    # --- Find Local Low (Trough) ---
    # Start searching for the low from the local_highest_idx
    local_lowest_price = float('inf')
    local_lowest_idx = -1
    no_new_low_count = 0

    # Iterate from the local_highest_idx to find a trough
    # A trough is found when 5 consecutive 5-day windows do not produce a new low
    for j in range(local_highest_idx, len(prices)):
        window_end = min(j + 5, len(prices))
        if j >= window_end: break

        window_prices = prices[j : window_end]
        if not window_prices: continue

        current_window_low = min(window_prices)
        # Get the relative index of the lowest price within this window, then convert to global index
        current_window_low_relative_idx = window_prices.index(current_window_low)
        current_window_low_global_idx = j + current_window_low_relative_idx

        if current_window_low < local_lowest_price:
            local_lowest_price = current_window_low
            local_lowest_idx = current_window_low_global_idx
            no_new_low_count = 0 # Reset counter if a new low is found
        else:
            no_new_low_count += 1 # Increment if no new low in this window
        
        if no_new_low_count >= COUNTER_THRESHOLD:
            # Found a trough: 5 consecutive windows without a new low
            break
    
    # If we didn't find a trough or no low was set
    if no_new_low_count < COUNTER_THRESHOLD or local_lowest_idx == -1:
        return None

    # Ensure the high point comes before the low point in terms of index
    # And that the high and low prices are distinct
    if local_highest_idx >= local_lowest_idx or local_highest_price == local_lowest_price:
        return None

    return (local_highest_idx, local_highest_price, local_lowest_idx, local_lowest_price)

def find_volatility_contraction_pattern(prices):
    """
    Main function to detect VCPs by iteratively calling find_one_contraction.
    Collects all detected contractions.
    """
    contractions = []
    start_index = 0
    # Loop until we run out of data to search for contractions
    while start_index < len(prices):
        result = find_one_contraction(prices, start_index)
        if result:
            contractions.append(result)
            # Advance start_index past the found contraction's lowest point
            # This ensures we search for the next contraction after the current one ends.
            # result is (high_idx, high_price, low_idx, low_price)
            start_index = result[2] + 1 # Advance past the low_idx
        else:
            # If no contraction found from current start_index, advance by one day
            # This prevents infinite loops if find_one_contraction always returns None
            start_index += 1
    return contractions

# Helper function to calculate a moving average series
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

@app.route('/')
def index():
    return "Analysis Service is running."

@app.route('/analyze/<ticker>')
def analyze_ticker_endpoint(ticker):
    print(f"Received analysis request for ticker: {ticker}")
    try:
        ticker = ticker.upper()
        # Fetch historical data from data-service
        hist_resp = requests.get(f"{DATA_SERVICE_URL}/data/{ticker}")
        
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

        raw_historical_data = hist_resp.json()

        prices, dates, historical_data_sorted = prepare_historical_data(raw_historical_data)

        # Handle empty price data gracefully
        if not prices:
            return jsonify({"error": f"No price data available for {ticker} to analyze."}), 404

        # Extract volumes for pivot calculation
        volumes = [item.get('volume', 0) for item in historical_data_sorted]

        vcp_results = find_volatility_contraction_pattern(prices)

        # Calculate moving averages
        ma_20_series = calculate_sma_series(prices, dates, 20)
        ma_50_series = calculate_sma_series(prices, dates, 50)
        ma_150_series = calculate_sma_series(prices, dates, 150)
        ma_200_series = calculate_sma_series(prices, dates, 200)

        # Format the JSON Response (Step 4)
        vcp_lines, buy_points, sell_points = [], [], []
        low_volume_pivot_date = None

        if vcp_results:
            last_high_price = vcp_results[-1][1]
            last_low_price = vcp_results[-1][3]
            for high_idx, high_price, low_idx, low_price in vcp_results:
                vcp_lines.extend([{"time": dates[high_idx], "value": high_price}, {"time": dates[low_idx], "value": low_price}])
            buy_points.append({"value": last_high_price * 1.01})
            sell_points.append({"value": last_low_price * 0.99})

            # Find the low volume pivot date
            last_contraction_high_idx, _, last_contraction_low_idx, _ = vcp_results[-1]
            if last_contraction_high_idx < len(volumes) and last_contraction_low_idx < len(volumes):
                contraction_volumes = volumes[last_contraction_high_idx : last_contraction_low_idx + 1]
                if contraction_volumes:
                    min_volume_local_idx = np.argmin(contraction_volumes)
                    min_volume_global_idx = last_contraction_high_idx + min_volume_local_idx
                    low_volume_pivot_date = dates[min_volume_global_idx]
            

        return jsonify({
            "ticker": ticker,
            "analysis": {
                "detected": bool(vcp_results),
                "message": "VCP analysis complete." if vcp_results else "No VCP detected.",
                "vcpLines": vcp_lines,
                "buyPoints": buy_points,
                "sellPoints": sell_points,
                "ma20": ma_20_series,
                "ma50": ma_50_series,
                "ma150": ma_150_series,
                "ma200": ma_200_series,
                "lowVolumePivotDate": low_volume_pivot_date
            },
            "historicalData": historical_data_sorted
        })
    except requests.exceptions.RequestException as e:
        print(f"Connection error to data-service: {e}")
        return jsonify({"error": "Service unavailable: data-service", "details": str(e)}), 503
    except Exception as e:
        print(f"Unhandled exception in analyze_ticker_endpoint: {e}")
        return jsonify({"error": "An internal error occurred in the analysis service."}), 500

if __name__ == '__main__':
    print("Analysis Service started.")
    app.run(host='0.0.0.0', port=PORT)
