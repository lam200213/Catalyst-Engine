# backend-services/leadership-service/app.py
# responsible for handling API routing and HTTP request/response logic
import time
import threading
from flask import Flask, jsonify, request
import os
import re # regex import for input validation
import logging 
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from checks import industry_peer_checks
from pydantic import ValidationError, TypeAdapter
from typing import List
from shared.contracts import CoreFinancials, PriceDataItem, LeadershipProfileSingle, LeadershipProfileBatch, LeadershipProfileForBatch
from data_fetcher import (
    fetch_financial_data,
    fetch_price_data,
    fetch_batch_financials,
    fetch_batch_price_data,
    fetch_peer_data,
)
from helper_functions import (
    validate_data_contract,
    fetch_general_data_for_analysis,
    analyze_ticker_leadership,
)
app = Flask(__name__)

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 5000))

# --- Thread-local storage for context ---
_thread_local = threading.local()

# --- Custom Logging Filter ---
class TickerContextFilter(logging.Filter):
    """
    This filter injects the ticker symbol from thread-local storage into log records.
    """
    def filter(self, record):
        # Get the ticker from the thread-local storage, default to 'N/A' if not set
        record.ticker = getattr(_thread_local, 'ticker', 'N/A')
        return True

# --- Structured Logging Setup ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    log_directory = "/app/logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # The filename is now specific to the service and in a dedicated folder.
    log_file = os.path.join(log_directory, "leadership_service.log")

    # Create a filter instance to add ticker context to logs
    ticker_filter = TickerContextFilter()

    # Create a rotating file handler to prevent log files from growing too large
    # It will create up to 5 backup files of 5MB each.
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.addFilter(ticker_filter) # Add filter to handler

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.addFilter(ticker_filter) # Add filter to handler

    # Define the log format to include the new 'ticker' field
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(ticker)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)

    # --- Centralized Configuration for All Service Loggers ---
    # This ensures that any module using logging.getLogger(__name__) will use the same handlers and format,
    # directing all logs to the service's dedicated log file. This approach is thread-safe and does
    # not rely on Flask's application context, which is unavailable in background threads.
    loggers_to_configure = [
        app.logger,  # The main Flask app logger
        logging.getLogger('data_fetcher'),
        logging.getLogger('helper_functions'),
        logging.getLogger('checks.financial_health_checks'),
        logging.getLogger('checks.market_relative_checks'),
        logging.getLogger('checks.industry_peer_checks'),
        logging.getLogger('checks.utils')
    ]

    for logger in loggers_to_configure:
        # Clear any existing handlers to prevent duplicate log entries
        logger.handlers.clear()
        
        # Add the shared handlers configured above
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Set the log level
        logger.setLevel(log_level)
        
        # Prevent log messages from propagating to the root logger, which might have its own handlers
        logger.propagate = False

setup_logging(app)
# --- End of Logging Setup ---

@app.route('/leadership/<path:ticker>', methods=['GET'])
def leadership_analysis(ticker):
    """Main endpoint for leadership screening analysis"""
    start_time = time.time()
    
    # Set ticker context for logging in this thread
    _thread_local.ticker = ticker

    try:
        start_time = time.time()

        # Input validation to prevent path traversal
        if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()) or '../' in ticker:
            return jsonify({'error': 'Invalid ticker format'}), 400
        
        # Robustly handle mixed return types (tuple on success, dict on error).
        common_data = fetch_general_data_for_analysis()
        if isinstance(common_data, dict) and 'error' in common_data:
            return jsonify({'error': common_data['error']}), common_data.get('status', 503)
        index_data, market_trends_data = common_data

        financial_data_raw, status_code = fetch_financial_data(ticker)
        if not financial_data_raw:
            return jsonify({'error': f"Failed to fetch financial data for {ticker}"}), status_code

        stock_data_raw, status_code  = fetch_price_data(ticker)
        if not stock_data_raw:
            return jsonify({'error': f"Failed to fetch price data for {ticker}"}), status_code

        peers_data_raw, peer_error = fetch_peer_data(ticker)
        if peer_error:
            app.logger.warning(f"Could not fetch peer data for {ticker}: {peer_error[0]}. Proceeding without industry check.")
            peers_data_raw = {}  # Use an empty dict to signal failure downstream

        # Fetch financials for the ticker and all its peers
        all_related_tickers = [ticker] + peers_data_raw.get('peers', [])
        all_financial_data_raw, fin_error = fetch_batch_financials(list(set(all_related_tickers)))
        if fin_error:
            return jsonify({'error': fin_error[0]}), fin_error[1]

        # Validate incoming data against contracts using the centralized helper
        PriceDataValidator = TypeAdapter(List[PriceDataItem])
        financial_data = validate_data_contract(financial_data_raw, CoreFinancials, ticker, "CoreFinancials")
        stock_data = validate_data_contract(stock_data_raw, PriceDataValidator, ticker, "PriceData")

        all_financial_data = {}
        for t, data in all_financial_data_raw.get('success', {}).items():
            validated_data = validate_data_contract(data, CoreFinancials, t, "CoreFinancials")
            if validated_data:
                all_financial_data[t] = validated_data

        if not financial_data or not stock_data:
            return jsonify({
                "error": "Invalid data structure received from upstream data-service.",
            }), 502

        # Call the leadership analysis function with all data
        analysis_result = analyze_ticker_leadership(
            ticker, index_data, market_trends_data,
            financial_data, stock_data, peers_data_raw, all_financial_data
        )
        
        if 'error' in analysis_result:
                status_code = analysis_result.get('status', 500)
                return jsonify({'error': analysis_result['error']}), status_code

        execution_time = time.time() - start_time
        analysis_result['metadata'] = {'execution_time': round(execution_time, 3)}

        # Validate the final output against its own contract before sending
        try:
            validated_response = LeadershipProfileSingle.model_validate(analysis_result)
            return jsonify(validated_response.model_dump())
        except ValidationError as e:
            app.logger.critical(f"Output contract violation for LeadershipProfileSingle for {ticker}: {e}")
            return jsonify({"error": "An internal error occurred while generating the response."}), 500

    finally:
        # Clean up the ticker context to prevent bleeding into other requests
        if hasattr(_thread_local, 'ticker'):
            del _thread_local.ticker

@app.route('/leadership/batch', methods=['POST'])
def leadership_batch_analysis():
    """Endpoint for batch leadership screening"""
    start_time = time.time()
    payload = request.get_json()
    if not payload or 'tickers' not in payload:
        return jsonify({"error": "Invalid request payload. 'tickers' is required."}), 400

    tickers = payload['tickers']
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
        return jsonify({"error": "'tickers' must be a list of strings."}), 400

    app.logger.info(f"Starting batch leadership analysis for {len(tickers)} tickers.")

     # --- 1. Sanitize Tickers ---
    sanitized_tickers = [
        t for t in tickers if re.match(r'^[A-Z0-9\.\-\^]+$', t.upper()) and '../' not in t
    ]
    if not sanitized_tickers:
        return jsonify({'passing_candidates': [], 'metadata': {'total_processed': len(tickers), 'total_passed': 0, 'execution_time': 0}}), 200

    # --- 2. Fetch Common and Price Data ---
    app.logger.info("Fetching general market and trend data...")
    # Robustly handle mixed return types (tuple on success, dict on error).
    common_data = fetch_general_data_for_analysis()
    if isinstance(common_data, dict) and 'error' in common_data:
        return jsonify({'error': common_data['error']}), common_data.get('status', 503)
    index_data, market_trends_data = common_data

    app.logger.info(f"Fetching batch price data for {len(sanitized_tickers)} tickers...")
    all_price_data, price_error = fetch_batch_price_data(sanitized_tickers)
    if price_error:
        return jsonify({"error": price_error[0]}), price_error[1]

    # --- 3. Efficiently Fetch All Peer and Financial Data ---
    all_tickers_for_financials = set(sanitized_tickers)
    peers_map = {} # To store peer data for each candidate

    # Fetch peer lists in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(fetch_peer_data, ticker): ticker for ticker in sanitized_tickers}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                peers_data, error = future.result()
                if not error and peers_data and 'peers' in peers_data:
                    peers_map[ticker] = peers_data
                    all_tickers_for_financials.update(peers_data['peers'])
                elif error:
                    app.logger.warning(f"Could not fetch peer data for {ticker}: {error[0]}")
            except Exception as exc:
                app.logger.error(f"Generated an exception while fetching peers for {ticker}: {exc}")

    # Single batch call for all financials (candidates + all unique peers)
    app.logger.info(f"Fetching batch financials for {len(all_tickers_for_financials)} unique tickers...")
    all_financial_data_raw, financial_error = fetch_batch_financials(list(all_tickers_for_financials))
    if financial_error:
        return jsonify({"error": financial_error[0]}), financial_error[1]

    # --- 4. Validate All Fetched Data ---

    # Validate all successfully fetched data using the centralized helper
    PriceDataValidator = TypeAdapter(List[PriceDataItem])
    successful_financials = {}
    for ticker, data in all_financial_data_raw.get('success', {}).items():
        validated_data = validate_data_contract(data, CoreFinancials, ticker, "CoreFinancials")
        if validated_data:
            successful_financials[ticker] = validated_data

    successful_prices = {}
    for ticker, data in all_price_data.get('success', {}).items():
        validated_data = validate_data_contract(data, PriceDataValidator, ticker, "PriceData")
        if validated_data:
            successful_prices[ticker] = validated_data

    # --- 5. Prepare Analysis Tasks (CPU-Bound) ---
    analysis_tasks = []
    for ticker in sanitized_tickers:
        if ticker not in successful_prices:
            app.logger.warning(f"Skipping {ticker} from analysis due to missing price data.")
            continue
            
        if ticker not in successful_financials:
            app.logger.warning(f"Skipping {ticker} from analysis due to missing financial data.")
            continue

        # A ticker is viable if we have its own price and financial data. Peer data is optional.
        if ticker in successful_prices and ticker in successful_financials:
            task = {
                "ticker": ticker,
                "financial_data": successful_financials[ticker],
                "stock_data": successful_prices[ticker],
                "peers_data": peers_map.get(ticker, {}) # Pass peer data if available, otherwise pass an empty dict
            }
            analysis_tasks.append(task)

    # --- 6. Execute Analysis in Parallel ---
    passing_candidates = []
    unique_industries = set()

    # Use a ThreadPoolExecutor to run the I/O-bound analysis tasks in parallel.
    # The number of workers is set to 10 to balance performance without overwhelming downstream services.
    # logs from each thread are tagged with the correct ticker.
    if analysis_tasks:
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Use functools.partial to pass the pre-fetched market data to the worker function.
            analysis_func = partial(analyze_ticker_leadership, index_data=index_data, market_trends_data=market_trends_data, all_financial_data=successful_financials)

            def worker_with_context(task):
                """Sets and clears the ticker in thread-local storage for logging."""
                _thread_local.ticker = task['ticker']
                try:
                    # Unpack the task dictionary to call the analysis function
                    result = analysis_func(
                        ticker=task['ticker'],
                        financial_data=task['financial_data'],
                        stock_data=task['stock_data'],
                        peers_data=task['peers_data']
                    )
                finally:
                    # Ensure the context is cleared after the task is done
                    if hasattr(_thread_local, 'ticker'):
                        del _thread_local.ticker
                return result

            # map() efficiently applies the wrapper function to each task
            results_iterator = executor.map(worker_with_context, analysis_tasks)
            for result in results_iterator:
                # We only care about tickers that pass the screening and have no errors.
                if 'error' not in result and result.get('passes', False):
                    # Construct the leaner object for the batch response
                    # This ensures the output conforms to the LeadershipProfileForBatch contract.
                    candidate_for_batch = {
                        "ticker": result.get("ticker"),
                        "passes": result.get("passes"),
                        "leadership_summary": result.get("leadership_summary"),
                        "profile_details": result.get("profile_details"),
                        "industry": result.get("industry")
                    }
                    passing_candidates.append(candidate_for_batch)
                    
                    if result.get('industry'):
                        unique_industries.add(result['industry'])

    execution_time = time.time() - start_time
    app.logger.info(f"Batch leadership analysis completed in {execution_time:.2f}s. Found {len(passing_candidates)} passing candidates.")
    
    response = {
        'passing_candidates': passing_candidates,
        'unique_industries_count': len(unique_industries),
        'metadata': {
            'total_processed': len(tickers),
            'total_passed': len(passing_candidates),
            'execution_time': round(execution_time, 3)
        }
    }
    
    # Validate the final output against its own contract before sending
    try:
        validated_response = LeadershipProfileBatch.model_validate(response)
        return jsonify(validated_response.model_dump(by_alias=True))
    except ValidationError as e:
        app.logger.critical(f"Output contract violation for LeadershipProfileBatch: {e}")
        return jsonify({"error": "An internal error occurred while generating the batch response."}), 500

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
    if not re.match(r'^[A-Z0-9\.\-\^]+$', ticker.upper()) or '../' in ticker:
        return jsonify({'error': 'Invalid ticker format'}), 400

    # Create a dictionary to hold the results for this specific request.
    details = {}

    peers_data_raw, error = fetch_peer_data(ticker)
    if error:
        return jsonify({'error': f"Upstream error: {error[0]}"}), 502

    all_tickers = [ticker] + peers_data_raw.get("peers", [])
    batch_financials, error = fetch_batch_financials(list(set(all_tickers)))
    if error:
        return jsonify({'error': f"Upstream error fetching batch financials: {error[0]}"}), 502
    
    all_financial_data = batch_financials.get("success", {})

    industry_peer_checks.analyze_industry_leadership(ticker, peers_data_raw, all_financial_data, details)
    result = details.get('is_industry_leader')

    if not result or result.get("pass") is None:
        # This handles cases where the check failed internally (e.g., data fetching error)
        return jsonify({"error": result.get("message", "Failed to perform industry analysis.")}), 500

    return jsonify(result), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
