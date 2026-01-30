# backend-services/scheduler-service/services/job_service.py

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pymongo import DESCENDING, InsertOne
from pymongo.errors import PyMongoError
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)

from db import get_db_collections
from shared.contracts import JobStatus, JobType, ScreeningJobRunRecord

def create_job(
    job_type: JobType, 
    options: Optional[Dict[str, Any]] = None,
    trigger_source: Optional[str] = None,
    parent_job_id: Optional[str] = None
) -> str:
    """
    Creates a new job record with PENDING status.
    
    Args:
        job_type: Enum indicating the type of job (SCREENING, WATCHLIST_REFRESH).
        options: Configuration dictionary for the job.
        trigger_source: Origin of the job (API, CRON, etc.).
        parent_job_id: ID of the parent job if part of a chain.

    Returns:
        str: The generated UUID v4 job_id.
    """
    job_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    
    # Construct the document ensuring Enums are converted to values (str)
    job_doc = {
        "job_id": job_id,
        "job_type": job_type.value if hasattr(job_type, 'value') else job_type,
        "status": JobStatus.PENDING.value,
        "created_at": now_utc,
        "options": options or {},
        "progress_log": [],
        "progress_snapshot": None,
        "results": None,
        "result_summary": None
    }

    # Add optional orchestration fields if present
    if trigger_source:
        job_doc["trigger_source"] = trigger_source
    if parent_job_id:
        job_doc["parent_job_id"] = parent_job_id

    _, jobs_col, _, _, _, _ = get_db_collections()
    jobs_col.insert_one(job_doc)
    
    return job_id

def start_job(job_id: str) -> None:
    """
    Transitions a job to RUNNING and records the start time.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    jobs_col.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": JobStatus.RUNNING.value,
                "started_at": datetime.now(timezone.utc)
            }
        }
    )

def update_job_progress(
    job_id: str,
    step_current: int,
    step_total: int,
    step_name: str,
    message: str,
    job_type: JobType,
    status: JobStatus = JobStatus.RUNNING
) -> None:
    """
    Updates the job's progress snapshot and appends to the rolling log.
    Enforces a max log size of 100 entries using MongoDB $slice.
    """
    now_utc = datetime.now(timezone.utc)
    
    # Snapshot overwrites the previous state for O(1) read access
    snapshot = {
        "job_id": job_id,
        "job_type": job_type.value if hasattr(job_type, 'value') else job_type,
        "status": status.value if hasattr(status, 'value') else status,
        "step_current": step_current,
        "step_total": step_total,
        "step_name": step_name,
        "message": message,
        "updated_at": now_utc
    }
    
    # Log entry is appended to history
    log_entry = {
        "step": step_current,
        "name": step_name,
        "message": message,
        "timestamp": now_utc
    }

    _, jobs_col, _, _, _, _ = get_db_collections()
    
    jobs_col.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "progress_snapshot": snapshot,
                # Optionally update status here if provided, though typically start/complete handle transitions
                "status": status.value if hasattr(status, 'value') else status
            },
            "$push": {
                "progress_log": {
                    "$each": [log_entry],
                    "$slice": -100  # Keep only the last 100 entries
                }
            }
        }
    )

def complete_job(
    job_id: str, 
    results: Optional[Dict[str, Any]] = None, 
    summary: Optional[Dict[str, Any]] = None,
    final_candidates_objs: Optional[List[Any]] = None  # Latest Add: specific arg for detailed objects
) -> None:
    """
    Transitions job to SUCCESS, persists results, and performs fan-out persistence.
    
    Refactored for Week 10:
    1. 'results' (in job doc): Stores lightweight lists of tickers (strings) for debugging.
    2. 'screening_results' (collection): Stores detailed FinalCandidate objects for analytics.
    """
    results_col, jobs_col, _, _, _, _ = get_db_collections()
    
    # Fetch started_at to calculate total duration
    job = jobs_col.find_one({"job_id": job_id}, {"started_at": 1})
    
    now_utc = datetime.now(timezone.utc)
    started_at = job.get("started_at") if job else None
    
    total_time = 0.0
    if started_at:
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        total_time = (now_utc - started_at).total_seconds()

    # Fan-out Persistence to screening_results ---
    if final_candidates_objs and results_col is not None:
        try:
            bulk_ops = []
            for candidate in final_candidates_objs:
                # Ensure the object is a dict (handle Pydantic models)
                candidate_dict = candidate.model_dump() if hasattr(candidate, 'model_dump') else candidate
                
                # Enrich with Metadata for Indexing
                doc = {
                    "job_id": job_id,
                    "processed_at": now_utc,
                    "ticker": candidate_dict.get("ticker"),
                    "data": candidate_dict # Nest the detailed metrics
                }
                bulk_ops.append(InsertOne(doc))
            
            if bulk_ops:
                results_col.bulk_write(bulk_ops)
                logger.info(f"Persisted {len(bulk_ops)} final candidates to screening_results.")
        except Exception as e:
            logger.error(f"Failed to fan-out persistence for job {job_id}: {e}")
            # We do NOT fail the job here; the data is in the summary backup if needed.

    update_fields = {
        "status": JobStatus.SUCCESS.value,
        "completed_at": now_utc,
        "total_process_time": total_time,
        "result_summary": summary,
        "results": results  # Lightweight strings only
    }

    jobs_col.update_one(
        {"job_id": job_id},
        {"$set": update_fields}
    )

def fail_job(job_id: str, error_message: str, error_step: Optional[str] = None) -> None:
    """
    Transitions job to FAILED and records error details.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    jobs_col.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": JobStatus.FAILED.value,
                "completed_at": datetime.now(timezone.utc),
                "error_message": error_message,
                "error_step": error_step
            }
        }
    )

def get_job_history(limit: int = 20, skip: int = 0) -> List[ScreeningJobRunRecord]:
    """
    Retrieves a paginated list of job records, converted to Pydantic models.
    Resilient to schema validation errors.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    cursor = jobs_col.find({})\
        .sort("created_at", DESCENDING)\
        .skip(skip)\
        .limit(limit)
    
    history = []
    for doc in cursor:
        try:
            # Attempt to convert to strict contract
            history.append(ScreeningJobRunRecord(**doc))
        except ValidationError as e:
            # Log the corruption but DO NOT crash the request
            job_id = doc.get("job_id", "unknown")
            logger.warning(f"Skipping corrupt job record {job_id}: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error parsing job: {e}")
            continue
            
    return history

def get_job_detail(job_id: str) -> Optional[ScreeningJobRunRecord]:
    """
    Retrieves a single full job record by ID.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    doc = jobs_col.find_one({"job_id": job_id})
    if not doc:
        return None
        
    return ScreeningJobRunRecord(**doc)