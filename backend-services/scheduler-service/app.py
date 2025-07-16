# backend-services/scheduler-service/app.py
import os
import requests
import uuid
from datetime import datetime, timezone
from flask import Flask, jsonify
from pymongo import MongoClient, errors

app = Flask(__name__)

# --- Configuration ---
PORT = int(os.getenv("PORT", 3004))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/")
TICKER_SERVICE_URL = os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5000")
SCREENING_SERVICE_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")

# --- Database Setup ---
client = None
results_collection = None

def get_db_collection():
    """Initializes database connection and returns the results collection."""
    global client, results_collection
    if results_collection is not None:
        return results_collection

    try:
        client = MongoClient(MONGO_URI)
        db = client.stock_analysis
        results_collection = db.screening_results
        client.admin.command('ping')
        print("MongoDB connection successful.")
        return results_collection
    except errors.ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        client = None
        results_collection = None
        return None

# --- Helper Functions ---
def _get_all_tickers(job_id):
    """Fetches all tickers from the ticker service."""
    try:
        resp = requests.get(f"{TICKER_SERVICE_URL}/tickers", timeout=15)
        resp.raise_for_status()
        tickers = resp.json()
        if not isinstance(tickers, list):
            print(f"Warning: Job {job_id}: Ticker service returned non-list format.")
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
        resp = requests.post(f"{SCREENING_SERVICE_URL}/screen/batch", json={"tickers": tickers}, timeout=300)
        resp.raise_for_status()
        survivors = resp.json()
        print(f"Job {job_id}: Stage 1 (Trend Screen) passed: {len(survivors)} tickers.")
        return survivors, None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Job {job_id}: Failed to connect to screening-service: {e}")
        return None, ({"error": "Failed to connect to screening-service", "details": str(e)}, 503)

def _run_vcp_analysis(job_id, tickers):
    """Runs VCP analysis on trend survivors."""
    if not tickers:
        print(f"Job {job_id}: Skipping VCP analysis, no trend survivors.")
        return []
    
    vcp_survivors = []
    for ticker in tickers:
        try:
            resp = requests.get(f"{ANALYSIS_SERVICE_URL}/analyze/{ticker}", timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                if isinstance(result, dict) and result.get("vcp_pass"):
                    result['job_id'] = job_id
                    result['processed_at'] = datetime.now(timezone.utc)
                    vcp_survivors.append(result)
        except requests.exceptions.RequestException as e:
            print(f"Warning: Job {job_id}: Could not analyze ticker {ticker}: {e}. Skipping.")
            continue
    print(f"Job {job_id}: Stage 2 (VCP Screen) passed: {len(vcp_survivors)} tickers.")
    return vcp_survivors

def _store_results(job_id, results):
    """Stores analysis results in the database."""
    if not results:
        return None
    
    collection = get_db_collection()
    if collection is None:
        return {"error": "Database client not available"}, 500
        
    try:
        collection.insert_many(results)
        print(f"Job {job_id}: Inserted {len(results)} results into MongoDB.")
        return None
    except errors.PyMongoError as e:
        print(f"ERROR: Job {job_id}: Failed to write results to database: {e}")
        return {"error": "Failed to write to database", "details": str(e)}, 500

# --- Orchestration Logic ---
def run_screening_pipeline():
    job_id = str(uuid.uuid4())
    print(f"Starting screening job ID: {job_id}")

    all_tickers, error = _get_all_tickers(job_id)
    if error:
        return error

    trend_survivors, error = _run_trend_screening(job_id, all_tickers)
    if error:
        return error

    vcp_survivors = _run_vcp_analysis(job_id, trend_survivors)

    error_info = _store_results(job_id, vcp_survivors)
    if error_info:
        return error_info

    return {
        "message": "Screening job completed successfully.",
        "job_id": job_id,
        "total_tickers_fetched": len(all_tickers),
        "trend_screen_survivors": len(trend_survivors),
        "final_candidates_count": len(vcp_survivors)
    }, 200

# --- API Endpoint ---
@app.route('/jobs/screening/start', methods=['POST'])
def start_screening_job_endpoint():
    result, status_code = run_screening_pipeline()
    return jsonify(result), status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)