# backend-services/scheduler-service/app.py
import os
import requests
import uuid
import shortuuid
from datetime import datetime, timezone
from flask import Flask, jsonify
from pymongo import MongoClient, errors

app = Flask(__name__)

# --- Configuration ---
PORT = int(os.getenv("PORT", 3004))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
TICKER_SERVICE_URL = os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001")
SCREENING_SERVICE_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")
LEADERSHIP_SERVICE_URL = os.getenv("LEADERSHIP_SERVICE_URL", "http://leadership-service:3005")
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
# --- Database Setup ---
client = None
results_collection = None
jobs_collection = None

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
        print("MongoDB connection successful.")
        return results_collection, jobs_collection
    except errors.ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
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
            print(f"Warning: Job {job_id}: Could not decode JSON from ticker-service: {e}. Skipping ticker fetching.")
            return [], None

        if not isinstance(tickers, list):
            print(f"Warning: Job {job_id}: Ticker service returned non-list format. Skipping ticker fetching.")
            return [], None
        print(f"Job {job_id}: Fetched {len(tickers)} total tickers.")
        return tickers, None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Job {job_id}: Failed to connect to ticker-service: {e}")
        return None, ({"error": "Failed to connect to ticker-service", "details": str(e)}, 503)

def _run_trend_screening(job_id, tickers):
    """Runs trend screening on a list of tickers."""
    if not tickers:
        print(f"Job {job_id}: Skipping trend screen, no tickers to process.")
        return [], None
    try:
        resp = requests.post(f"{SCREENING_SERVICE_URL}/screen/batch", json={"tickers": tickers}, timeout=5999)
        resp.raise_for_status()
        # Gracefully handle malformed JSON from a downstream service to prevent job failure.
        try:
            trend_survivors = resp.json()
        except requests.exceptions.JSONDecodeError as e:
            print(f"Warning: Job {job_id}: Could not decode JSON from screening-service: {e}. Skipping trend screening.")
            return [], None

        print(f"Job {job_id}: Stage 1 (Trend Screen) passed: {len(trend_survivors)} tickers.")
        return trend_survivors, None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Job {job_id}: Failed to connect to screening-service: {e}")
        return None, ({"error": "Failed to connect to screening-service", "details": str(e)}, 503)

def _run_vcp_analysis(job_id, tickers):
    """Runs VCP analysis on trend survivors."""
    if not tickers:
        print(f"Job {job_id}: Skipping VCP analysis, no trend survivors.")
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
                except requests.exceptions.JSONDecodeError as e:
                    print(f"Warning: Job {job_id}: Could not decode JSON for ticker {ticker}: {e}. Skipping.")
                    continue

                if isinstance(result, dict) and result.get("vcp_pass"):
                    final_candidates.append(result)
        except requests.exceptions.RequestException as e:
            print(f"Warning: Job {job_id}: Could not analyze ticker {ticker}: {e}. Skipping.")
            continue
    print(f"Job {job_id}: Stage 2 (VCP Screen) passed: {len(final_candidates)} tickers.")
    return final_candidates

# backend-services/scheduler-service/app.py

def _store_results(job_id, candidates, funnel_summary):
    """Stores candidate results and the job summary in the database."""
    results_coll, jobs_coll = get_db_collections()
    
    # boolean check to compare with None.
    if jobs_coll is None:
        print(f"ERROR: Job {job_id}: Database collection 'screening_jobs' is not available.")
        return False, ({"error": "Database 'screening_jobs' client not available"}, 500)

    try:
        jobs_coll.update_one({"job_id": job_id}, {"$set": funnel_summary}, upsert=True)
        print(f"Job {job_id}: Successfully logged job summary.")
    except errors.PyMongoError as e:
        print(f"ERROR: Job {job_id}: Failed to write job summary to database: {e}")
        return False, ({"error": "Failed to write job summary to database", "details": str(e)}, 500)

    if not candidates:
        print(f"Job {job_id}: No final candidates to store.")
        return True, None

    # boolean check to compare with None.
    if results_coll is None:
        print(f"ERROR: Job {job_id}: Database collection 'screening_results' is not available.")
        return False, ({"error": "Database 'screening_results' client not available"}, 500)

    try:
        processed_time = datetime.now(timezone.utc)
        for candidate in candidates:
            candidate['job_id'] = job_id
            candidate['processed_at'] = processed_time
        
        results_coll.insert_many(candidates)
        print(f"Job {job_id}: Inserted {len(candidates)} documents into the database.")
        return True, None
    except errors.PyMongoError as e:
        print(f"ERROR: Job {job_id}: Failed to write candidate results to database: {e}")
        return False, ({"error": "Failed to write candidate results to database", "details": str(e)}, 500)

# --- Orchestration Logic ---
def run_screening_pipeline():
    """
    Orchestrates the multi-stage screening process.
    Fetches all tickers, runs trend screening, then VCP analysis on survivors.
    """
    # Generate a human-readable and chronological job ID
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime('%Y%m%d-%H%M%S')
    unique_part = shortuuid.uuid()[:8]
    job_id = f"{timestamp_str}-{unique_part}"
    print(f"Starting screening job ID: {job_id}")

    # 1. Get all available tickers from the ticker service.
    all_tickers, error = _get_all_tickers(job_id)
    if error:
        return error
    print(f"Job {job_id}: Funnel: Fetched {len(all_tickers)} total tickers.")

    # 2. Run Stage 1 Trend Screening on the fetched tickers.
    trend_survivors, error = _run_trend_screening(job_id, all_tickers)
    if error:
        return error
    print(f"Job {job_id}: Funnel: After trend screening, {len(trend_survivors)} tickers remain.")

    # 3. Run Stage 2 VCP Analysis on the tickers that survived trend screening.
    final_candidates = _run_vcp_analysis(job_id, trend_survivors)
    print(f"Job {job_id}: Funnel: After VCP analysis, {len(final_candidates)} final candidates found.")
    
    # 4. Prepare and store results and summary
    job_summary = {
        "job_id": job_id,
        "processed_at": now,
        "total_tickers_fetched": len(all_tickers),
        "trend_screen_survivors_count": len(trend_survivors),
        "final_candidates_count": len(final_candidates)
    }

    success, error_info = _store_results(job_id, final_candidates, job_summary)
    if not success:
        return error_info

    # 5. Return a success response with job details.
    print(f"Screening job {job_id} completed successfully.")
    return {
        "message": "Screening job completed successfully.",
        **job_summary # Unpack the summary into the response
    }, 200

# --- API Endpoint ---
@app.route('/jobs/screening/start', methods=['POST'])
def start_screening_job_endpoint():
    result, status_code = run_screening_pipeline()
    return jsonify(result), status_code

if __name__ == '__main__':
    get_db_collections() # Initialize DB connection on startup
    app.run(host='0.0.0.0', port=PORT)