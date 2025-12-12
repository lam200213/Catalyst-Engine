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
from vcp_logic import (
    find_volatility_contraction_pattern,
    run_vcp_screening,
    _calculate_volume_trend,
    check_pivot_freshness,      
    get_vcp_footprint,
    is_pivot_good,          
    check_pullback_setup, 
    PIVOT_PRICE_PERC,              
)
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

# --- Centralized Executor ---
# Using a ThreadPoolExecutor for concurrent VCP analysis in the batch endpoint
executor = ThreadPoolExecutor(max_workers=10)

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
    Filters out any data points where 'close' price is null or missing.
    Expected input format: [{'formatted_date': 'YYYY-MM-DD', 'close': X.X, ...}]
    """
    if not historical_data:
        return [], [], []

    # Filter out entries with no 'close' price and then sort chronologically
    valid_data = [item for item in historical_data if item.get('close') is not None]
    if not valid_data:
        return [], [], []
        
    sorted_data = sorted(valid_data, key=lambda x: x['formatted_date'])
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

def _build_chart_data(prices, dates, volumes, historical_data_sorted, vcp_results, vcp_pass_status, vcp_details):
    """
    Helper to construct the full VCPChartData object.
    Used by both single and batch endpoints to ensure consistent chart visualization.
    """
    # 1. Calculate Moving Averages
    ma_20_series = calculate_sma_series(prices, dates, 20)
    ma_50_series = calculate_sma_series(prices, dates, 50)
    ma_150_series = calculate_sma_series(prices, dates, 150)
    ma_200_series = calculate_sma_series(prices, dates, 200)

    # 2. Derive Rejection Reason if failed
    rejection_reason = None
    if not vcp_pass_status and vcp_results and isinstance(vcp_details, dict):
        reasons = []
        # Map internal boolean checks to human-readable reasons
        if not vcp_details.get("is_pivot_good", True): reasons.append("Bad Pivot")
        if not vcp_details.get("is_correction_deep", True): reasons.append("Deep Base")
        if not vcp_details.get("is_demand_dry", True): reasons.append("Vol Trend Up")
        if not vcp_details.get("is_volume_dry_at_pivot", True): reasons.append("No Dry Up")
        
        rejection_reason = ", ".join(reasons) if reasons else "Structure Invalid"

    # 3. Assemble base chart data
    chart_data = {
        "detected": bool(vcp_results),
        "message": "VCP analysis complete." if vcp_results else "No VCP detected.",
        "vcpLines": [], # Gone: Deprecated
        "vcpContractions": [], 
        "pivotPrice": None,
        "vcp_pass": vcp_pass_status,       
        "rejection_reason": rejection_reason, 
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

    # 4. Populate VCP-specifics (Contractions, Pivot, etc.)
    if vcp_results:
        # Determine which set of contractions to use for visualization logic
        # We prioritize the 'filtered_contractions' (sanitized SEPA base) if available.
        target_contractions = vcp_results
        if vcp_details and "filtered_contractions" in vcp_details and vcp_details["filtered_contractions"]:
            target_contractions = vcp_details["filtered_contractions"]

        # Construct the new vcpContractions list for the chart using the TARGET set
        contraction_items = []
        for high_idx, high_price, low_idx, low_price in target_contractions:
            if high_price > 0:
                depth = (high_price - low_price) / high_price
            else:
                depth = 0.0
                
            contraction_items.append({
                "start_date": dates[high_idx],
                "start_price": float(high_price),
                "end_date": dates[low_idx],
                "end_price": float(low_price),
                "depth_percent": float(depth)
            })
        chart_data["vcpContractions"] = contraction_items

        # Define Pivot, Buy/Sell Points based on the LAST contraction of the FILTERED set
        last_contraction = target_contractions[-1]
        last_high_idx = int(last_contraction[0])
        last_high_price = float(last_contraction[1])
        last_low_idx = int(last_contraction[2])
        last_low_price = float(last_contraction[3])

        chart_data["pivotPrice"] = last_high_price
        chart_data["buyPoints"] = [{"value": last_high_price * 1.01}]
        chart_data["sellPoints"] = [{"value": last_low_price * 0.99}]

        # Identify the date of the lowest volume within the LAST filtered contraction
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
    
    return chart_data

def _process_ticker_analysis(ticker, historical_data, mode):
    """
    Helper function to run VCP analysis for a single ticker with its data.
    Designed for parallel execution in the batch endpoint.

    Returns a result dict if VCP passes, OR if mode='full' (returns full chart data).
    If mode='fast' and VCP fails, returns None (to filter out non-candidates).

    Fields:
    - ticker
    - vcp_pass
    - vcpFootprint
    - is_pivot_good
    - has_pivot
    - is_at_pivot
    - has_pullback_setup
    - pivot_price
    - pattern_age_days
    """
    try:
        prices, dates, historical_data_sorted = prepare_historical_data(historical_data)
        if not prices:
            return None

        volumes = [item.get("volume", 0) for item in historical_data_sorted]

        # Core VCP detection
        vcp_results = find_volatility_contraction_pattern(prices)
        vcp_pass_status, vcp_footprint_string, details = run_vcp_screening(
            vcp_results, prices, volumes, mode
        )

        # In 'fast' mode, we filter out failures to save bandwidth/processing
        if mode == 'fast' and not vcp_pass_status:
            return None

        # Build basic result
        result = {
            "ticker": ticker,
            "vcp_pass": vcp_pass_status,
            "vcpFootprint": vcp_footprint_string,
        }

        # If 'full' mode, we ALWAYS attach the rich chart data, even if it failed VCP.
        # This allows the frontend to render the chart and explain WHY it failed.
        if mode == 'full':
            result["chart_data"] = _build_chart_data(
                prices, dates, volumes, historical_data_sorted, 
                vcp_results, vcp_pass_status, details
            )
            # Map details if present
            if isinstance(details, dict):
                mapped = _build_vcp_details_response(details)
                if mapped:
                    result["vcp_details"] = mapped

        # Add lightweight fields for screening context
        has_pivot = bool(vcp_results)
        result["has_pivot"] = has_pivot

        pivot_price = None
        pattern_age_days = None
        is_at_pivot = False

        if has_pivot:
            # Prefer filtered contractions for pivot calculation if available
            target_contractions = vcp_results
            if isinstance(details, dict) and details.get("filtered_contractions"):
                target_contractions = details["filtered_contractions"]

            last_high_idx, last_high_price, last_low_idx, _ = target_contractions[-1]
            pivot_price = float(last_high_price)
            # mirror freshness notion: days since pivot low
            pattern_age_days = int((len(prices) - 1) - int(last_low_idx))

            current_price = float(prices[-1])
            if pivot_price > 0.0:
                rel_dist = abs(current_price - pivot_price) / pivot_price
                # treat within PIVOT_PRICE_PERC band of pivot high as "at pivot"
                is_at_pivot = rel_dist <= PIVOT_PRICE_PERC

        result["pivot_price"] = pivot_price
        result["pattern_age_days"] = pattern_age_days
        result["is_at_pivot"] = is_at_pivot

        # Use detailed is_pivot_good if available; otherwise recompute
        if isinstance(details, dict) and "is_pivot_good" in details:
            is_pivot_good_flag = bool(details.get("is_pivot_good"))
        else:
            is_pivot_good_flag = is_pivot_good(vcp_results, float(prices[-1])) if has_pivot else False

        result["is_pivot_good"] = is_pivot_good_flag

        # Full Pullback (PB) Setup Logic
        # Identifies if stock is in a constructive post-breakout position
        # ie this stock is in a strong, extended position where a future pullback would be buyable
        has_pullback_setup = False
        if has_pivot and pivot_price and pattern_age_days is not None:
            has_pullback_setup = check_pullback_setup(
                prices=prices, 
                volumes=volumes, 
                pivot_price=pivot_price, 
                vcp_passed=vcp_pass_status,
                is_pivot_good=is_pivot_good_flag,
                pattern_age_days=pattern_age_days
            )
        
        result["has_pullback_setup"] = has_pullback_setup

        return result

    except Exception:
        return None

# helper for freshness analysis (mirrors _process_ticker_analysis)
def _process_ticker_freshness_analysis(ticker: str, historical_data: list[dict]) -> dict | None:
    """
    Runs VCP 'fast' screening and pivot freshness for a single ticker.
    Returns a result dict if freshness passes; otherwise None.
    """
    try:
        prices, _, sorted_data = prepare_historical_data(historical_data)
        if not prices:
            return None

        vcp_results = find_volatility_contraction_pattern(prices)
        volumes = [item.get('volume', 0) for item in sorted_data]

        # Gate on VCP fast screen to ensure valid VCP candidate first
        vcp_pass, footprint_str, _ = run_vcp_screening(vcp_results, prices, volumes, mode='fast')
        if not vcp_pass:
            return None

        freshness = check_pivot_freshness(vcp_results, prices)
        if not freshness.get("passes"):
            return None

        # Ensure vcpFootprint present even if screening computed it already
        if not footprint_str:
            _, footprint_str = get_vcp_footprint(vcp_results)

        return {
            "ticker": ticker,
            "passes_freshness_check": True,
            "vcp_detected": bool(vcp_results),
            "days_since_pivot": freshness.get("days_since_pivot"),
            "message": freshness.get("message", ""),
            "vcpFootprint": footprint_str
        }
    except Exception:
        # Fail-soft to keep batch processing resilient
        return None

def _build_vcp_details_response(vcp_details_raw: dict | None) -> dict | None:
    """
    Maps the flat vcp_details dict from vcp_logic into the nested
    VCPDetails shape expected by shared.contracts:
        {
          "pivot_validation": {"pass": bool, "message": str},
          "volume_validation": {"pass": bool, "message": str}
        }
    """
    if not isinstance(vcp_details_raw, dict) or not vcp_details_raw:
        return None

    is_pivot_good = bool(vcp_details_raw.get("is_pivot_good", False))
    is_vol_dry = bool(vcp_details_raw.get("is_volume_dry_at_pivot", False))
    vol_ratio = vcp_details_raw.get("volume_dry_up_ratio", None)

    # Pivot validation message
    if is_pivot_good:
        pivot_msg = "Pivot check passed: final contraction depth and location are within the acceptable band."
    else:
        pivot_msg = "Pivot check failed: final contraction is too deep or price is not positioned correctly near the pivot low."

    # Volume validation message, incorporating the ratio when available
    if vol_ratio is not None:
        ratio_str = f"{vol_ratio:.2f}x"
        if is_vol_dry:
            volume_msg = f"Volume at the pivot is {ratio_str} the 50-day average (dry-up confirmed)."
        else:
            volume_msg = f"Volume at the pivot is {ratio_str} the 50-day average (not sufficiently dry)."
    else:
        volume_msg = (
            "Pivot volume dry-up detected."
            if is_vol_dry
            else "Insufficient volume data to evaluate pivot dry-up."
        )

    return {
        "pivot_validation": {
            "pass": is_pivot_good,
            "message": pivot_msg,
        },
        "volume_validation": {
            "pass": is_vol_dry,
            "message": volume_msg,
        },
    }

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

        # 4. Use helper to build complete chart data (DRY)
        chart_data = _build_chart_data(
            prices, dates, volumes, historical_data_sorted, 
            vcp_results, vcp_pass_status, vcp_details
        )

        # 5. Return the final JSON response
        response_payload = {
            "ticker": ticker,
            "vcp_pass": vcp_pass_status,
            "vcpFootprint": vcp_footprint_string,
            "chart_data": chart_data,
        }
        # Only include details if in full mode, and map them to contract shape
        if mode == 'full':
            mapped_details = _build_vcp_details_response(vcp_details)
            if mapped_details is not None:
                response_payload["vcp_details"] = mapped_details
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
        payload = request.get_json(silent=True)
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
                # Exception for market indices to bypass strict validation
                # Matches pattern in helper_functions.py requested by user
                if ticker.startswith('^') or ticker in ['SPY', 'QQQ', 'DIA']:
                     if not isinstance(data, list):
                         app.logger.warning(f"Index data for {ticker} is not a list: {type(data)}")
                         continue
                else:
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

@app.route('/analyze/freshness/batch', methods=['POST'])
def analyze_freshness_batch_endpoint():
    """
    Screens a batch of tickers and returns only those with fresh, actionable VCP setups.
    - Validates input payload.
    - Fetches raw price data in a single call to data-service.
    - Processes each ticker concurrently.
    - Returns only passers (those that pass both VCP fast screen and freshness).
    """
    try:
        payload = request.get_json(silent=True)
        if not payload or 'tickers' not in payload or not isinstance(payload['tickers'], list):
            return jsonify({"error": "Invalid request. 'tickers' array is required."}), 400

        tickers = payload['tickers']
        if not tickers:
            return jsonify([]), 200

        # Fetch historical data for all tickers
        try:
            data_resp = requests.post(
                f"{DATA_SERVICE_URL}/price/batch",
                json={"tickers": tickers, "source": "yfinance"},
                timeout=120
            )
            if data_resp.status_code != 200:
                return jsonify({"error": "Failed to retrieve batch data"}), 502

            # Parse upstream JSON safely
            raw_batch = data_resp.json()
            success_map = raw_batch.get('success', {})
        except requests.exceptions.RequestException as e:
            return jsonify({"error": "Error connecting to data-service.", "details": str(e)}), 503
        except ValueError:
            # JSON decode error
            return jsonify({"error": "Invalid JSON response from data-service"}), 502

        # Validate each ticker’s data against contract, then process concurrently
        passing = []
        future_to_ticker = {}
        PriceDataValidator = TypeAdapter(List[PriceDataItem])

        for tkr, raw_list in success_map.items():
            try:
                # Validate before submitting for processing
                PriceDataValidator.validate_python(raw_list)
                fut = executor.submit(_process_ticker_freshness_analysis, tkr, raw_list)
                future_to_ticker[fut] = tkr
            except ValidationError as ve:
                app.logger.warning(f"Contract violation in freshness batch for {tkr}: {ve}")
                continue

        for fut in as_completed(future_to_ticker):
            try:
                result = fut.result()
                if result:
                    passing.append(result)
            except Exception as exc:
                app.logger.error(f"Error processing {future_to_ticker[fut]} in freshness batch: {exc}")

        return jsonify(passing), 200

    except Exception as e:
        app.logger.error(f"Unhandled exception in freshness batch endpoint: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == '__main__':
    print("Analysis Service started.")
    app.run(host='0.0.0.0', port=PORT)