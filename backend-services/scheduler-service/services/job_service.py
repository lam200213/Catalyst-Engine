# backend-services/scheduler-service/services/job_service.py

import logging
import shortuuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from db import get_db_collections
from shared.contracts import ScreeningJobRunRecord, JobStatus, JobType

logger = logging.getLogger(__name__)

def create_job(job_type: str = JobType.SCREENING, options: Optional[Dict[str, Any]] = None) -> str:
    """
    Creates a new job record in MongoDB with PENDING status.
    Returns the generated job_id.
    """
    # 1. Access DB
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    # 2. Generate ID and Timestamp
    job_id = shortuuid.uuid()
    now = datetime.now(timezone.utc)
    
    # 3. Create Contract Model
    # options default to empty dict if None
    job_record = ScreeningJobRunRecord(
        job_id=job_id,
        job_type=job_type,
        status=JobStatus.PENDING,
        created_at=now,
        options=options or {}
    )
    
    # 4. Persist to MongoDB
    # model_dump() keeps datetime objects which Mongo handles natively/efficiently
    try:
        jobs_col.insert_one(job_record.model_dump())
        logger.info(f"Created new {job_type} job: {job_id}")
        return job_id
    except Exception as e:
        logger.error(f"Failed to persist new job {job_id}: {e}")
        raise e

def get_job_history(limit: int = 20, skip: int = 0) -> List[ScreeningJobRunRecord]:
    """
    Retrieves a paginated list of past job runs, sorted by most recent.
    Returns a list of Pydantic models.
    """
    _, jobs_col, _, _, _, _ = get_db_collections()
    
    cursor = jobs_col.find({}).sort("created_at", -1).skip(skip).limit(limit)
    
    history = []
    for doc in cursor:
        try:
            # Convert raw Mongo doc back to Pydantic model
            record = ScreeningJobRunRecord.model_validate(doc)
            history.append(record)
        except Exception as e:
            logger.warning(f"Skipping malformed job record in history: {e}")
            continue
            
    return history