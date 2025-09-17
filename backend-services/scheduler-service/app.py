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
SCHEDULER_TIME = os.getenv("SCHEDULER_TIME", "05:00")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Database Setup ---
class DatabaseManager:
    """Singleton-like manager for MongoDB connection and collections."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.client = None
        self.db = None
        self.collections = {
            'results': None,
            'jobs': None,
            'trend_survivors': None,
            'vcp_survivors': None,
            'leadership_survivors': None
        }

    def connect(self):
        """Establishes the connection if not already connected."""
        if self.client is not None and all(coll is not None for coll in self.collections.values()):
            return True  # Already connected

        # Implement retry logic for database connection
        max_retries = 3
        retry_delay = 5  # seconds
        for attempt in range(max_retries):
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000) 
                self.client.admin.command('ping') # Verify connection

                self.db = self.client['stock_analysis']  # Use the DB name here
                self.collections['results'] = self.db['screening_results']
                self.collections['jobs'] = self.db['screening_jobs']
                self.collections['trend_survivors'] = self.db['trend_survivors']
                self.collections['vcp_survivors'] = self.db['vcp_survivors']
                self.collections['leadership_survivors'] = self.db['leadership_survivors']

                logger.info("MongoDB connection successful.")
                return True
            except errors.ConnectionFailure as e:
                logger.error(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("All MongoDB connection attempts failed.")
                    self._reset()  # Reset on final failure
                    return False
        return False # Should not be reached, but for safety

    def _reset(self):
        """Resets the connection and collections on failure."""
        self.client = None
        self.db = None
        for key in self.collections:
            self.collections[key] = None

    def get_collections(self):
        """Returns the collections if connected, else attempts to connect and returns them."""
        if not self.connect():
            return (None,) * len(self.collections)  # Return None for each collection to match original signature
        return (
            self.collections['results'],
            self.collections['jobs'],
            self.collections['trend_survivors'],
            self.collections['vcp_survivors'],
            self.collections['leadership_survivors']
        )

def get_db_collections():
    db_manager = DatabaseManager()
    return db_manager.get_collections()

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

def _run_leadership_screening(job_id, vcp_survivors):
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
        }
        resp = requests.post(
            f"{LEADERSHIP_SERVICE_URL}/leadership/batch",
            json=payload,
            timeout=3600  # Allow a long timeout for batch processing
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

# Function to store a list of documents for a specific stage
def store_stage_survivors(job_id, collection, survivors, stage_name):
    
    if collection is None:
        logger.error(f"Job {job_id}: Cannot store {stage_name} survivors, database collection is not available.")
        return False
    
    if not survivors:
        logger.info(f"Job {job_id}: No {stage_name} survivors to store.")
        return True
    try:
        # Structure documents with job_id for linking
        docs_to_insert = [{"job_id": job_id, "ticker": ticker} for ticker in survivors]
        if docs_to_insert:
            collection.insert_many(docs_to_insert)
            logger.info(f"Job {job_id}: Inserted {len(docs_to_insert)} {stage_name} survivors.")
        return True
    except errors.PyMongoError as e:
        logger.exception(f"Job {job_id}: Failed to write {stage_name} survivors to database.")
        return False

def _store_results(job_id, summary_doc, trend_survivors, vcp_survivors, leadership_survivors, final_candidates):
    """Stores the job summary and detailed survivor lists in their respective collections."""
    results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll = get_db_collections()
    
    # Centralized check if any collection object is None.
    collections_list = [results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll]
    if any(coll is None for coll in collections_list):
        logger.error(f"Job {job_id}: Database connection failed or collections are missing. Aborting result storage.")
        return False, ({"error": "Database client not available or collections missing"}, 500)
    
    # 1. Store the job summary document.
    try:
        jobs_coll.update_one({"job_id": job_id}, {"$set": summary_doc}, upsert=True)
        logger.info(f"Job {job_id}: Successfully logged job summary.")
    except errors.PyMongoError as e: 
        logger.exception(f"Job {job_id}: Failed to write job summary to database.")
        return False, ({"error": "Failed to write job summary to database", "details": str(e)}, 500)
        
    # 2. Store each survivor list in its dedicated collection.
    if not store_stage_survivors(job_id, trend_coll, trend_survivors, "trend"): return False, ({"error": "DB error"}, 500)

    # VCP survivors are dicts, so we extract tickers
    vcp_tickers = [item.get('ticker') for item in vcp_survivors if item.get('ticker')]
    if not store_stage_survivors(job_id, vcp_coll, vcp_tickers, "VCP"): return False, ({"error": "DB error"}, 500)

    leadership_tickers = [item.get('ticker') for item in leadership_survivors if item.get('ticker')]
    if not store_stage_survivors(job_id, leadership_coll, leadership_tickers, "leadership"): return False, ({"error": "DB error"}, 500)

    # 3. Store the final candidate results
    if not final_candidates:
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
            for candidate in final_candidates
        ]
        
        if candidates_to_insert:
            results_coll.insert_many(candidates_to_insert)
            logger.info(f"Job {job_id}: Inserted {len(candidates_to_insert)} documents into the results database.")
        return True, None
    except errors.PyMongoError:
        logger.exception(f"Job {job_id}: Failed to write candidate results to database.")
        return False, ({"error": "Failed to write candidate results to database", "details": str(e)}, 500)
# --- Scheduled Job ---
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
    print(f"Job {job_id}: Funnel: Fetched {len(all_tickers)} total tickers.")
    
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

    # 5. Run Stage 3 Leadership Screening on VCP survivors
    leadership_survivors = _run_leadership_screening(job_id, vcp_survivors)
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
        "industry_diversity": {
            "unique_industries_count": unique_industries_count
        },
        "final_candidates_count": len(final_candidates),
        # Store only ticker lists in the summary to keep it lightweight.
        "vcp_survivors": [item.get('ticker') for item in vcp_survivors],
        "leadership_survivors": [item.get('ticker') for item in final_candidates],
        "final_candidates": final_candidates,
    }
    
    success, error_info = _store_results(
        job_id,
        job_summary,
        trend_survivors,
        vcp_survivors,
        leadership_survivors,
        final_candidates
    )
    if not success:
        return error_info
    
    # 7. Return a success response with job details.

    excluded_keys = {"trend_survivors"}

    # Create a filtered copy of job_summary
    filtered_result = {k: v for k, v in job_summary.items() if k not in excluded_keys}

    logger.info(f"Screening job {job_id} completed successfully.")
    return {
        "message": "Screening job completed successfully.",
        **filtered_result, # Unpack the summary into the response
        "unique_industries_count": unique_industries_count,
    }, 200

# Initialize the scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Schedule the job to run daily at the configured time
scheduler.add_job(
    run_screening_pipeline,
    CronTrigger(hour=int(SCHEDULER_TIME.split(':')[0]), minute=int(SCHEDULER_TIME.split(':')[1]))
)

# --- API Endpoint ---
@app.route('/jobs/screening/start', methods=['POST'])
def start_screening_job_endpoint():
    result, status_code = run_screening_pipeline()
    return jsonify(result), status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)