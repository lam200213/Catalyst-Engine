# backend-services/scheduler-service/services/progress_emitter.py

import logging
from datetime import datetime, timezone
from typing import Optional

from db import get_db_collections
from shared.contracts import JobStatus

logger = logging.getLogger(__name__)

def emit_progress(
    job_id: str,
    message: str,
    step_current: int,
    step_total: int,
    step_name: str,
    status: Optional[str] = None
) -> None:
    """
    Updates the job status and appends a log entry in a single atomic MongoDB operation.
    
    Features:
    - Atomicity: Uses $set (state) and $push (log) in one call.
    - Capping: Uses $slice to keep only the last 100 log entries to prevent document bloat.
    - Consistency: Always updates 'updated_at' to the current UTC time.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    now = datetime.now(timezone.utc)
    
    # 1. Build the $set fields (State Snapshot)
    set_fields = {
        "updated_at": now,
        "step_current": step_current,
        "step_total": step_total,
        "step_name": step_name
    }
    
    # Update status if explicitly provided (e.g., transition to SUCCESS)
    # OR if it's currently just running (default behavior for progress updates)
    if status:
        set_fields["status"] = status
        # If the job is finishing, mark the completion time
        if status in [JobStatus.SUCCESS, JobStatus.FAILED]:
            set_fields["completed_at"] = now
    elif status is None:
        # Default to RUNNING if not specified, to ensure "PENDING" moves to "RUNNING"
        set_fields["status"] = JobStatus.RUNNING

    # 2. Build the $push fields (Log History)
    # We use $each and $slice to append and cap in one go.
    log_entry = {
        "timestamp": now,
        "message": message,
        "step": step_current,
        "step_name": step_name
    }

    try:
        jobs_col.update_one(
            {"job_id": job_id},
            {
                "$set": set_fields,
                "$push": {
                    "progress_log": {
                        "$each": [log_entry],
                        "$slice": -100  # Keep only the last 100 entries (Negative slice keeps tail)
                    }
                }
            }
        )
    except Exception as e:
        # We log but do not raise, as progress emission failure shouldn't crash the pipeline
        logger.error(f"Failed to emit progress for job {job_id}: {e}")