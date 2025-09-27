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
from pydantic import ValidationError, TypeAdapter
import logging
from typing import List
from shared.contracts import (
    ScreeningJobResult,
    FinalCandidate,
    IndustryDiversity,
    VCPAnalysisBatchItem,
    LeadershipProfileBatch
)

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
            'leadership_survivors': None,
            'ticker_status': None
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
                self.collections['ticker_status'] = self.db['ticker_status']

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
            self.collections['leadership_survivors'],
            self.collections['ticker_status'],
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
    """Runs VCP analysis on trend survivors using the batch endpoint."""
    if not tickers:
        logger.info(f"Job {job_id}: Skipping VCP analysis, no trend survivors.")
        return []
    
    logger.info(f"Job {job_id}: Sending {len(tickers)} trend survivors to analysis-service for batch VCP screening.")
    
    final_candidates = []
    try:
        # Use 'fast' mode for VCP analysis to quickly filter out non-viable candidates
        # without consuming excessive resources on detailed, long-running analysis.
        resp = requests.post(
            f"{ANALYSIS_SERVICE_URL}/analyze/batch",
            json={"tickers": tickers, "mode": "fast"},
            timeout=1200,
        )
        if resp.status_code == 200:
            # Enforce the data contract for the VCP analysis batch result.
            try:
                vcp_survivors = TypeAdapter(List[VCPAnalysisBatchItem]).validate_python(resp.json())
                logger.info(f"Job {job_id}: Stage 2 (VCP Screen) passed: {len(vcp_survivors)} tickers.")
                return vcp_survivors
            except (requests.exceptions.JSONDecodeError, ValidationError) as e:
                logger.warning(
                    f"Job {job_id}: Could not decode or validate JSON from analysis-service against VCPAnalysisBatchItem contract. Error: {e}",
                    exc_info=True
                )
                return []
        else:
            logger.error(f"Job {job_id}: VCP analysis batch request failed with status {resp.status_code}. Details: {resp.text}")
            return []
    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Could not connect to analysis-service for batch VCP.", exc_info=True)
        return []

def _run_leadership_screening(job_id, vcp_survivors):
    """Run leadership screening on VCP survivors, passing in the current market trend."""
    if not vcp_survivors:
        logger.info(f"Job {job_id}: Skipping leadership screening, no VCP survivors.")
        return [], 0

    # Extract just the ticker symbols to send in the request
    vcp_tickers = [candidate.ticker for candidate in vcp_survivors]
    if not vcp_tickers:
        logger.warning(f"Job {job_id}: No valid tickers found in VCP survivors list.")
        return [], 0

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
        
        # Enforce the data contract for the leadership screening batch result.
        try:
            result = LeadershipProfileBatch.model_validate_json(resp.content)
            passing_candidates_details = result.passing_candidates
            unique_industries_count = result.unique_industries_count
        except (requests.exceptions.JSONDecodeError, ValidationError) as e:
            logger.error(
                f"Job {job_id}: Could not decode or validate JSON from leadership-service against LeadershipProfileBatch contract. Error: {e}",
                exc_info=True
            )
            return [], 0

        # Create a dictionary for quick lookup of leadership results by ticker
        leadership_results_map = {item.ticker: item.model_dump() for item in passing_candidates_details}
        
        # Integrate the leadership results back into the original vcp_survivors data structure
        final_candidates = []
        for candidate in vcp_survivors:
            if candidate.ticker in leadership_results_map:
                # Create a FinalCandidate instance, ensuring the data structure is correct.
                enriched_candidate = FinalCandidate(
                    ticker=candidate.ticker,
                    vcp_pass=candidate.vcp_pass,
                    vcpFootprint=candidate.vcpFootprint,
                    leadership_results=leadership_results_map[candidate.ticker]
                )
                final_candidates.append(enriched_candidate)
        
        logger.info(f"Job {job_id}: Stage 3 (Leadership Screen) passed: {len(final_candidates)} tickers.")
        return final_candidates, unique_industries_count

    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Failed to connect to leadership-service for batch screening.", exc_info=True)
        return [], 0 # Return empty list on failure to prevent entire job from crashing, Return 0 for industry count on error

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
    results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll, _ = get_db_collections()
    
    # Centralized check if any collection object is None.
    collections_list = [results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll]
    if any(coll is None for coll in collections_list):
        logger.error(f"Job {job_id}: Database connection failed or collections are missing. Aborting result storage.")
        return False, ({"error": "Database client not available or collections missing"}, 500)
    
    # 1. Store the job summary document.
    try:
        # Use the Pydantic model's dump method for a consistent, validated structure.
        jobs_coll.update_one({"job_id": job_id}, {"$set": summary_doc.model_dump()}, upsert=True)
        logger.info(f"Job {job_id}: Successfully logged job summary.")
    except errors.PyMongoError as e: 
        logger.exception(f"Job {job_id}: Failed to write job summary to database.")
        return False, ({"error": "Failed to write job summary to database", "details": str(e)}, 500)
        
    # 2. Store each survivor list in its dedicated collection.
    if not store_stage_survivors(job_id, trend_coll, trend_survivors, "trend"): return False, ({"error": "DB error"}, 500)

    # VCP survivors are Pydantic models, so we access attributes with dot notation.
    vcp_tickers = [item.ticker for item in vcp_survivors if item.ticker]
    if not store_stage_survivors(job_id, vcp_coll, vcp_tickers, "VCP"): return False, ({"error": "DB error"}, 500)

    # Leadership survivors are also models (`FinalCandidate`), so we use dot notation here too.
    leadership_tickers = [item.ticker for item in leadership_survivors if item.ticker]
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
        # Explicitly add the job_id to each candidate document.
        # Convert Pydantic models to dictionaries for MongoDB insertion.
        candidates_to_insert = [
            {**candidate.model_dump(), 'job_id': job_id, 'processed_at': processed_time}
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
    
    # 1. Get all available tickers from the ticker service.
    all_tickers, error = _get_all_tickers(job_id)
    # all_tickers = ['AAPL', 'MSFT', 'NVDA', 'JPM', 'DE', 'GOOGL', 'AMZN', 'TSLA', 'META', 'BRK.B', 'UNH', 'JNJ', 'XOM', 'V', 'PG', 'MA', 'HD', 'CVX', 'ABBV', 'LLY', 'AVGO', 'PEP', 'KO', 'COST', 'MRK', 'BAC', 'WMT', 'PFE', 'TMO', 'DIS', 'ABT', 'VZ', 'ADBE', 'CMCSA', 'CSCO', 'DHR', 'ACN', 'NFLX', 'NKE', 'MCD', 'WFC', 'LIN', 'PM', 'RTX', 'TXN', 'BMY', 'HON', 'UPS', 'IBM', 'AMGN', 'QCOM', 'COP', 'CAT', 'AMD', 'INTU', 'SPGI', 'BA', 'GS', 'PLD', 'SBUX', 'MS', 'BLK', 'MDT', 'AMT', 'GE', 'ISRG', 'LOW', 'SCHW', 'AXP', 'ELV', 'NOW', 'BKNG', 'LMT', 'ADI', 'TJX', 'DE', 'C', 'GILD', 'MMM', 'ZTS', 'SYK', 'CB', 'CI', 'MO', 'T', 'SO', 'DUK', 'MMC', 'PNC', 'USB', 'CL', 'BDX', 'NEE', 'APD', 'EOG', 'ICE', 'FISV', 'SLB', 'EQIX', 'NOC', 'ATVI', 'EMR', 'HUM', 'ITW', 'SHW', 'PGR', 'MCK', 'ETN', 'GD', 'PSA', 'AON', 'F', 'ORCL']
    if error:
        return error
    
    # Pre-filter the master ticker list to remove known delisted stocks.
    _, _, _, _, _, ticker_status_coll = get_db_collections()
    active_tickers = all_tickers
    if ticker_status_coll is not None:
        try:
            delisted_docs = ticker_status_coll.find({"status": "delisted"}, {"ticker": 1, "_id": 0})
            delisted_set = {doc['ticker'] for doc in delisted_docs}
            
            if delisted_set:
                original_count = len(all_tickers)
                all_tickers_set = set(all_tickers)
                active_tickers_set = all_tickers_set - delisted_set
                active_tickers = list(active_tickers_set)
                logger.info(
                    f"Job {job_id}: Pre-screening filter removed {original_count - len(active_tickers)} delisted tickers. "
                    f"Proceeding with {len(active_tickers)} active tickers."
                )
        except errors.PyMongoError as e:
            logger.error(f"Job {job_id}: Failed to query for delisted tickers. Proceeding with unfiltered list. Error: {e}")
    else:
        logger.warning(f"Job {job_id}: Ticker status collection not available. Screening all fetched tickers.")


    print(f"Job {job_id}: Funnel: Fetched {len(all_tickers)} total tickers.")
    
    # 2. Run Stage 1 Trend Screening on the fetched tickers.
    trend_survivors, error = _run_trend_screening(job_id, active_tickers)
    if error:
        return error
    logger.info(f"Job {job_id}: Funnel: After trend screening, {len(trend_survivors)} tickers remain.")
    
    # 3. Run Stage 2 VCP Analysis on the tickers that survived trend screening.
    vcp_survivors = _run_vcp_analysis(job_id, trend_survivors)
    logger.info(f"Job {job_id}: Funnel: After VCP analysis, {len(vcp_survivors)} VCP survivors found.")
    
    # 4. Run Stage 3 Leadership Screening on VCP survivors
    leadership_survivors, unique_industries_count = _run_leadership_screening(job_id, vcp_survivors)
    logger.info(f"Job {job_id}: Funnel: After leadership screening, {len(leadership_survivors)} final candidates found.")
    
    # 5. Prepare and store results and summary
    final_candidates = leadership_survivors

    end_time = time.time()
    total_process_time = round(end_time - start_time, 2)

    # Use the ScreeningJobResult contract to build the summary document, ensuring
    # data consistency and validation. This is the single source of truth for the job result structure.
    try:
        job_summary = ScreeningJobResult(
            job_id=job_id,
            processed_at=now,
            total_process_time=total_process_time,
            total_tickers_fetched=len(all_tickers),
            trend_screen_survivors_count=len(trend_survivors),
            vcp_survivors_count=len(vcp_survivors),
            final_candidates_count=len(final_candidates),
            industry_diversity=IndustryDiversity(
                unique_industries_count=unique_industries_count
            ),
            final_candidates=final_candidates,
        )
    except ValidationError as e:
        logger.error(f"Job {job_id}: Failed to create final job summary due to validation error: {e}")
        return {"error": "Internal data validation failed when creating job summary.", "details": str(e)}, 500
    
    # debug
    vcp_survivor_tickers = [item.ticker for item in vcp_survivors]
    logger.info(f"Job {job_id}: Funnel: vcp_survivors: {vcp_survivor_tickers}")
    
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
    
    # 6. Return a success response with job details.

    response_data = job_summary.model_dump()
    response_data.pop('trend_survivors', None)

    logger.info(f"Screening job {job_id} completed successfully.")
    return {
        "message": "Screening job completed successfully.",
        **response_data
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