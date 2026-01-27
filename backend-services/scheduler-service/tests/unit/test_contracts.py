# backend-services/scheduler-service/tests/unit/test_contracts.py
# Contracts existence + SSE snake_case enforcement

import json
import re
from datetime import datetime, timezone
from pydantic import BaseModel

def _model_dump(m):
    return m.model_dump() if hasattr(m, "model_dump") else m.dict()

def _model_dump_json(m):
    return m.model_dump_json() if hasattr(m, "model_dump_json") else m.json()

def test_contracts_export_new_models():
    """
    Red test: fail until these Week 10 models exist in shared/contracts.py.
    """
    from shared.contracts import JobProgressEvent, ScreeningJobRunRecord  # noqa: F401
    assert issubclass(JobProgressEvent, BaseModel)
    assert issubclass(ScreeningJobRunRecord, BaseModel)

def test_job_progress_event_serializes_snake_case_keys():
    """
    Red test: SSE payload JSON must use canonical snake_case field names per Week 10 SDD.
    Ref: SDD Stage 3 "Canonical Naming"
    """
    from shared.contracts import JobProgressEvent

    # Using snake_case arguments as required by SDD
    event = JobProgressEvent(
        job_id="job-123",           
        job_type="SCREENING",       
        status="RUNNING",
        step_current=1,             
        step_total=4,               
        step_name="trend",
        message="Trend screening started",
        updated_at=datetime(2026, 1, 18, 12, 0, 0, tzinfo=timezone.utc), 
    )

    payload = json.loads(_model_dump_json(event))
    
    # Corrected Expected Keys (Snake Case)
    expected_keys = {
        "job_id", 
        "job_type", 
        "status", 
        "step_current", 
        "step_total", 
        "step_name", 
        "message", 
        "updated_at"
    }
    assert set(payload.keys()) == expected_keys
    assert isinstance(payload["job_id"], str)

def test_job_progress_event_datetime_uses_z_suffix():
    """
    Red test: datetime must serialize as ...Z (UTC) for strict SSE compliance.
    """
    from shared.contracts import JobProgressEvent

    event = JobProgressEvent(
        job_id="job-456",
        job_type="SCREENING",
        status="RUNNING",
        step_current=2,
        step_total=4,
        step_name="vcp",
        message="VCP screening started",
        updated_at=datetime(2026, 1, 18, 13, 0, 0, tzinfo=timezone.utc),
    )

    payload = json.loads(_model_dump_json(event))
    # Check the updated_at field specifically
    assert payload["updated_at"].endswith("Z")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", payload["updated_at"])

def test_screening_job_run_record_minimum_creation_shape():
    """
    Red test: fail until ScreeningJobRunRecord exists.
    """
    from shared.contracts import ScreeningJobRunRecord

    record = ScreeningJobRunRecord(
        job_id="job-789",
        job_type="SCREENING",
        status="PENDING",
        created_at=datetime(2026, 1, 18, 14, 0, 0, tzinfo=timezone.utc),
        options={"use_vcp_freshness_check": True},
    )

    data = _model_dump(record)
    assert data["job_id"] == "job-789"
    assert data["status"] == "PENDING"
    assert "created_at" in data