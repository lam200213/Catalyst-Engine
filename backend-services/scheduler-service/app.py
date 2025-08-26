# backend-services/scheduler-service/app.py
import os
import requests
import time 
import shortuuid
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import requests
from flask import Flask, jsonify
from pymongo import MongoClient, errors
import logging

app = Flask(__name__)

# --- Configuration ---
PORT = int(os.getenv("PORT", 3004))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
TICKER_SERVICE_URL = os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001")
SCREENING_SERVICE_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")
LEADERSHIP_SERVICE_URL = os.getenv("LEADERSHIP_SERVICE_URL", "http://leadership-service:3005")
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
SCHEDULER_TIME = os.getenv("SCHEDULER_TIME", "16:00")
# --- Database Setup ---
client = None
results_collection = None
jobs_collection = None
# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_db_collections():
    """Initializes database connection and returns all relevant collections."""
    global client, results_collection, jobs_collection
    if results_collection is not None and jobs_collection is not None:
        return results_collection, jobs_collection

    try:
        client = MongoClient(MONGO_URI)
        db = client.stock_analysis
        results_collection = db.screening_results
        jobs_collection = db.screening_jobs
        client.admin.command('ping')
        logger.info("MongoDB connection successful.")
        return results_collection, jobs_collection
    except errors.ConnectionFailure as e:
        logger.error(f"MongoDB connection failed: {e}")
        client = None
        results_collection = None
        jobs_collection = None
        return None, None

# --- Helper Functions ---
def _get_all_tickers(job_id):
    """Fetches all tickers from the ticker service."""
    try:
        resp = requests.get(f"{TICKER_SERVICE_URL}/tickers", timeout=15)
        resp.raise_for_status()
        # Gracefully handle malformed JSON from a downstream service to prevent job failure.
        try:
            tickers = resp.json()
        except requests.exceptions.JSONDecodeError as e:
            logger.warning(f"Job {job_id}: Could not decode JSON from ticker-service. Skipping ticker fetching.", exc_info=True)
            return [], None

        if not isinstance(tickers, list):
            logger.warning(f"Job {job_id}: Ticker service returned non-list format. Skipping ticker fetching.")
            return [], None
        logger.info(f"Job {job_id}: Fetched {len(tickers)} total tickers.")
        return tickers, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Job {job_id}: Failed to connect to ticker-service.", exc_info=True)
        return None, ({"error": "Failed to connect to ticker-service", "details": str(e)}, 503)

def _run_trend_screening(job_id, tickers):
    """Runs trend screening on a list of tickers."""
    if not tickers:
        logger.info(f"Job {job_id}: Skipping trend screen, no tickers to process.")
        return [], None
    try:
        resp = requests.post(f"{SCREENING_SERVICE_URL}/screen/batch", json={"tickers": tickers}, timeout=5999)
        resp.raise_for_status()
        # Gracefully handle malformed JSON from a downstream service to prevent job failure.
        try:
            trend_survivors = resp.json()
        except requests.exceptions.JSONDecodeError:
            logger.warning(f"Job {job_id}: Could not decode JSON from screening-service. Skipping trend screening.", exc_info=True)
            return [], None

        logger.info(f"Job {job_id}: Stage 1 (Trend Screen) passed: {len(trend_survivors)} tickers.")
        return trend_survivors, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Job {job_id}: Failed to connect to screening-service.", exc_info=True)
        return None, ({"error": "Failed to connect to screening-service", "details": str(e)}, 503)

def _run_vcp_analysis(job_id, tickers):
    """Runs VCP analysis on trend survivors."""
    if not tickers:
        logger.info(f"Job {job_id}: Skipping VCP analysis, no trend survivors.")
        return []
    
    final_candidates = []
    for ticker in tickers:
        try:
            # Use 'fast' mode for VCP analysis to quickly filter out non-viable candidates
            # without consuming excessive resources on detailed, long-running analysis.
            resp = requests.get(
                f"{ANALYSIS_SERVICE_URL}/analyze/{ticker}",
                params={'mode': 'fast'},
                timeout=60
            )
            if resp.status_code == 200:
                # Gracefully handle malformed JSON from a downstream service to prevent job failure.
                try:
                    result = resp.json()
                except requests.exceptions.JSONDecodeError:
                    logger.warning(f"Job {job_id}: Could not decode JSON for ticker {ticker}. Skipping.", exc_info=True)
                    continue

                if isinstance(result, dict) and result.get("vcp_pass"):
                    final_candidates.append(result)
        except requests.exceptions.RequestException:
            logger.warning(f"Job {job_id}: Could not analyze ticker {ticker}. Skipping.", exc_info=True)
            continue
    logger.info(f"Job {job_id}: Stage 2 (VCP Screen) passed: {len(final_candidates)} tickers.")
    return final_candidates

def _count_unique_industries(job_id, vcp_survivors):
    """Count unique industries from VCP survivors."""
    if not vcp_survivors:
        logger.info(f"Job {job_id}: No VCP survivors to process for industry counting.")
        return 0
    
    unique_industries = set()
    for candidate in vcp_survivors:
        ticker = candidate.get('ticker')
        if not ticker:
            continue
            
        try:
            # Call the data service to get industry information
            resp = requests.get(f"{DATA_SERVICE_URL}/industry/peers/{ticker}", timeout=30)
            if resp.status_code == 200:
                try:
                    industry_data = resp.json()
                    industry = industry_data.get('industry')
                    if industry:
                        unique_industries.add(industry)
                except requests.exceptions.JSONDecodeError:
                    logger.warning(f"Job {job_id}: Could not decode JSON for industry data of {ticker}. Skipping.", exc_info=True)
                    continue
        except requests.exceptions.RequestException:
            logger.warning(f"Job {job_id}: Could not fetch industry data for {ticker}. Skipping.", exc_info=True)
            continue
    
    unique_count = len(unique_industries)
    logger.info(f"Job {job_id}: Counted {unique_count} unique industries from {len(vcp_survivors)} VCP survivors.")
    return unique_count

def _get_current_market_trend(job_id):
    """Fetches the current market trend from the leadership service."""
    try:
        resp = requests.get(f"{LEADERSHIP_SERVICE_URL}/market-trend/current", timeout=30)
        resp.raise_for_status()
        trend_data = resp.json()
        current_trend = trend_data.get('status', 'Unknown')
        logger.info(f"Job {job_id}: Successfully fetched current market trend: {current_trend}")
        return current_trend
    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Could not fetch current market trend. Defaulting to 'Unknown'.", exc_info=True)
        return "Unknown" # Default to a neutral state on failure

def _run_leadership_screening(job_id, vcp_survivors, market_trend):
    """Run leadership screening on VCP survivors, passing in the current market trend."""
    if not vcp_survivors:
        logger.info(f"Job {job_id}: Skipping leadership screening, no VCP survivors.")
        return []

    # Extract just the ticker symbols to send in the request
    vcp_tickers = [candidate.get('ticker') for candidate in vcp_survivors if candidate.get('ticker')]
    if not vcp_tickers:
        logger.warning(f"Job {job_id}: No valid tickers found in VCP survivors list.")
        return []

    logger.info(f"Job {job_id}: Sending {len(vcp_tickers)} tickers to leadership-service for batch screening.")
    try:
        # Pass the pre-fetched market_trend to the batch endpoint for efficiency.
        payload = {
            "tickers": vcp_tickers,
            "market_trend": market_trend
        }
        resp = requests.post(
            f"{LEADERSHIP_SERVICE_URL}/leadership/batch",
            json=payload,
            timeout=3000  # Allow a long timeout for batch processing
        )
        resp.raise_for_status()
        
        # Handle JSON decoding errors gracefully
        try:
            result = resp.json()
            passing_candidates_details = result.get('passing_candidates', [])
        except requests.exceptions.JSONDecodeError:
            logger.error(f"Job {job_id}: Could not decode JSON from leadership-service batch endpoint.", exc_info=True)
            return []

        # Create a dictionary for quick lookup of leadership results by ticker
        leadership_results_map = {item['ticker']: item['details'] for item in passing_candidates_details}
        
        # Integrate the leadership results back into the original vcp_survivors data structure
        final_candidates = []
        for candidate in vcp_survivors:
            ticker = candidate.get('ticker')
            if ticker in leadership_results_map:
                # Create a new dictionary to prevent side effects from modifying the original `candidate` object.
                # This ensures data integrity by isolating the data destined for the final candidates list.
                enriched_candidate = {
                    **candidate,
                    'leadership_results': leadership_results_map[ticker]
                }
                final_candidates.append(enriched_candidate)
        
        logger.info(f"Job {job_id}: Stage 3 (Leadership Screen) passed: {len(final_candidates)} tickers.")
        return final_candidates

    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Failed to connect to leadership-service for batch screening.", exc_info=True)
        return [] # Return empty list on failure to prevent entire job from crashing

def _store_results(job_id, summary_doc, candidates_doc):
    """Stores the job summary and candidate results in their respective collections."""
    results_coll, jobs_coll = get_db_collections()
    
    if jobs_coll is None:
        logger.error(f"Job {job_id}: Database collection 'screening_jobs' is not available.")
        return False, ({"error": "Database 'screening_jobs' client not available"}, 500)
    
    # 1. Store the job summary document.
    try:
        jobs_coll.update_one({"job_id": job_id}, {"$set": summary_doc}, upsert=True)
        logger.info(f"Job {job_id}: Successfully logged job summary.")
    except errors.PyMongoError:
        logger.exception(f"Job {job_id}: Failed to write job summary to database.")
        return False, ({"error": "Failed to write job summary to database"}, 500)
        
    # 2. Store the candidate results if any exist.
    if not candidates_doc:
        logger.info(f"Job {job_id}: No final candidates to store.")
        return True, None

    if results_coll is None:
        logger.error(f"Job {job_id}: Database collection 'screening_results' is not available.")
        return False, ({"error": "Database 'screening_results' client not available"}, 500)

    try:
        processed_time = datetime.now(timezone.utc)
        # The crucial step: explicitly add the job_id to each candidate document.
        candidates_to_insert = [
            {**candidate, 'job_id': job_id, 'processed_at': processed_time}
            for candidate in candidates_doc
        ]
        
        if candidates_to_insert:
            results_coll.insert_many(candidates_to_insert)
            logger.info(f"Job {job_id}: Inserted {len(candidates_to_insert)} documents into the results database.")
        return True, None
    except errors.PyMongoError:
        logger.exception(f"Job {job_id}: Failed to write candidate results to database.")
        return False, ({"error": "Failed to write candidate results to database", "details": str(e)}, 500)
# --- Scheduled Job ---
def store_daily_market_trend():
    try:
        # Fetch the current market trend from the leadership-service
        trend_response = requests.get(f"{LEADERSHIP_SERVICE_URL}/market-trend/current", timeout=15)
        trend_response.raise_for_status()
        trend_data = trend_response.json()

        # Prepare the data to be stored in the data-service
        trend_status = trend_data.get('status')
        if not trend_status:
            logger.error("Failed to get market trend status from leadership-service")
            return

        # Store the trend data in the data-service
        store_response = requests.post(
            f"{DATA_SERVICE_URL}/market-trend",
            json={'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'status': trend_status},
            timeout=15
        )
        store_response.raise_for_status()
        logger.info("Successfully stored market trend status in data-service")

    except requests.exceptions.RequestException:
        logger.exception("Failed to store market trend status.")

# Initialize the scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Schedule the job to run daily at the configured time
scheduler.add_job(
    store_daily_market_trend,
    CronTrigger(hour=int(SCHEDULER_TIME.split(':')[0]), minute=int(SCHEDULER_TIME.split(':')[1]))
)

# --- Orchestration Logic ---
def run_screening_pipeline():
    """
    Orchestrates the multi-stage screening process.
    Fetches all tickers, runs trend screening, then VCP analysis on survivors,
    followed by leadership screening.
    """
    start_time = time.time()
    # Generate a human-readable and chronological job ID
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime('%Y%m%d-%H%M%S')
    unique_part = shortuuid.uuid()[:8]
    job_id = f"{timestamp_str}-{unique_part}"
    logger.info(f"Starting screening job ID: {job_id}")

    final_candidates = []
    
    # 1. Get all available tickers from the ticker service.
    # all_tickers, error = _get_all_tickers(job_id)
    all_tickers = ['AAPL', 'MSFT', 'NVDA', 'JPM', 'DE', 'GOOGL', 'AMZN', 'TSLA', 'META', 'BRK.B', 'UNH', 'JNJ', 'XOM', 'V', 'PG', 'MA', 'HD', 'CVX', 'ABBV', 'LLY', 'AVGO', 'PEP', 'KO', 'COST', 'MRK', 'BAC', 'WMT', 'PFE', 'TMO', 'DIS', 'ABT', 'VZ', 'ADBE', 'CMCSA', 'CSCO', 'DHR', 'ACN', 'NFLX', 'NKE', 'MCD', 'WFC', 'LIN', 'PM', 'RTX', 'TXN', 'BMY', 'HON', 'UPS', 'IBM', 'AMGN', 'QCOM', 'COP', 'CAT', 'AMD', 'INTU', 'SPGI', 'BA', 'GS', 'PLD', 'SBUX', 'MS', 'BLK', 'MDT', 'AMT', 'GE', 'ISRG', 'LOW', 'SCHW', 'AXP', 'ELV', 'NOW', 'BKNG', 'LMT', 'ADI', 'TJX', 'DE', 'C', 'GILD', 'MMM', 'ZTS', 'SYK', 'CB', 'CI', 'MO', 'T', 'SO', 'DUK', 'MMC', 'PNC', 'USB', 'CL', 'BDX', 'NEE', 'APD', 'EOG', 'ICE', 'FISV', 'SLB', 'EQIX', 'NOC', 'ATVI', 'EMR', 'HUM', 'ITW', 'SHW', 'PGR', 'MCK', 'ETN', 'GD', 'PSA', 'AON', 'F', 'ORCL']
    # if error:
    #     return error
    # print(f"Job {job_id}: Funnel: Fetched {len(all_tickers)} total tickers.")
    
    # 2. Run Stage 1 Trend Screening on the fetched tickers.
    trend_survivors, error = _run_trend_screening(job_id, all_tickers)
    if error:
        return error
    logger.info(f"Job {job_id}: Funnel: After trend screening, {len(trend_survivors)} tickers remain.")
    
    # 3. Run Stage 2 VCP Analysis on the tickers that survived trend screening.
    vcp_survivors = _run_vcp_analysis(job_id, trend_survivors)
    logger.info(f"Job {job_id}: Funnel: After VCP analysis, {len(vcp_survivors)} VCP survivors found.")
    
    # 4. Run "How to Count Unique Industries" task
    unique_industries_count = _count_unique_industries(job_id, vcp_survivors)

    # 5a. Determine current market trend once for the entire batch.
    current_market_trend = _get_current_market_trend(job_id)

    # 5b. Run Stage 3 Leadership Screening on VCP survivors
    leadership_survivors = _run_leadership_screening(job_id, vcp_survivors, current_market_trend)
    logger.info(f"Job {job_id}: Funnel: After leadership screening, {len(leadership_survivors)} final candidates found.")
    
    # 6. Prepare and store results and summary
    final_candidates = leadership_survivors

    end_time = time.time()
    total_process_time = round(end_time - start_time, 2)

    job_summary = {
        "job_id": job_id,
        "processed_at": now,
        "total_process_time": total_process_time,
        "total_tickers_fetched": len(all_tickers),
        "trend_screen_survivors_count": len(trend_survivors),
        "vcp_survivors_count": len(vcp_survivors),
        "unique_industries_count": unique_industries_count,
        "final_candidates_count": len(final_candidates),
        "trend_survivors": trend_survivors,
        "vcp_survivors": vcp_survivors,
        "leadership_survivors": leadership_survivors,
        # Store only ticker lists in the summary to keep it lightweight.
        # "vcp_survivors": [item.get('ticker') for item in vcp_survivors],
        # "leadership_survivors": [item.get('ticker') for item in final_candidates],
        "final_candidates": final_candidates,
    }
    
    success, error_info = _store_results(job_id, job_summary, final_candidates)
    if not success:
        return error_info
    
    # 7. Return a success response with job details.

    excluded_keys = {"trend_survivors"}
    job_summary['vcp_survivors'] = [item['ticker'] for item in job_summary['vcp_survivors']]
    job_summary['leadership_survivors'] = [item['ticker'] for item in job_summary['leadership_survivors']]

    # Create a filtered copy of job_summary
    filtered_result = {k: v for k, v in job_summary.items() if k not in excluded_keys}

    logger.info(f"Screening job {job_id} completed successfully.")
    return {
        "message": "Screening job completed successfully.",
        **filtered_result, # Unpack the summary into the response
        "unique_industries_count": unique_industries_count,
    }, 200

# --- API Endpoint ---
@app.route('/jobs/screening/start', methods=['POST'])
def start_screening_job_endpoint():
    result, status_code = run_screening_pipeline()
    return jsonify(result), status_code

if __name__ == '__main__':
    get_db_collections() # Initialize DB connection on startup
    app.run(host='0.0.0.0', port=PORT)