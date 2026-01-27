# backend-services/scheduler-service/tests/integration/test_sse_streaming.py

import pytest
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Import contracts for strict validation (Contract Lock)
from shared.contracts import (
    JobStatus, 
    JobProgressEvent, 
    JobCompleteEvent, 
    JobErrorEvent,
    JobType,
    ScreeningJobRunRecord
)

# --- Local Fixtures ---
# Note: client and mock_clock are now imported from conftest.py automatically

@pytest.fixture
def mock_job_service_get_detail():
    """
    Patches the job_service.get_job_detail function.
    """
    with patch("services.job_service.get_job_detail") as mock_get:
        yield mock_get

# --- Helper Functions ---
# helper to skip SSE comments like ": connected" / ": ping"
def next_named_event(event_iterator):
    while True:
        obj = next(event_iterator)  # may raise StopIteration as usual
        if 'event' in obj:
            return obj

# --- Tests ---

def test_sse_headers_strict(client, mock_job_service_get_detail, mock_clock):
    """
    SDD Task 3.3 / Week 10 Step 5.1
    Verifies NFRs: strict headers to prevent buffering in proxies/gateways.
    """
    job_id = "test-header-job"
    
    # Setup: Immediate success to close stream
    mock_job_service_get_detail.return_value = MagicMock(
        job_id=job_id,
        status=JobStatus.SUCCESS.value,
        result_summary={},
        completed_at=datetime.now(timezone.utc)
    )

    response = client.get(f"/jobs/screening/stream/{job_id}")

    # 1. Assert Status Code
    assert response.status_code == 200

    # 2. Assert Strict Headers
    assert "text/event-stream" in response.headers["Content-Type"]
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Accel-Buffering"] == "no"

def test_generator_polling_logic(client, mock_job_service_get_detail, mock_clock, sse_parser):
    """
    SDD Task 3.3: Verify full lifecycle, de-duplication, strict timestamp format,
    and DATA MAPPING (result_summary -> summary_counts).
    
    Scenario:
    1. PENDING (No emit)
    2. RUNNING Step 1 (Emit)
    3. RUNNING Step 1 Duplicate (No Emit - Dedup check)
    4. RUNNING Step 2 (Emit - Timestamp changed)
    5. SUCCESS (Emit Complete with Summary & Close)
    """
    job_id = "lifecycle-job"
    job_type = JobType.SCREENING.value
    now = datetime.now(timezone.utc)
    later = now + timedelta(seconds=10) # Distinct timestamp for step 2
    
    # Define States
    state_pending = MagicMock(
        job_id=job_id, job_type=job_type, status=JobStatus.PENDING.value,
        progress_snapshot=None, updated_at=now
    )
    
    state_step_1 = MagicMock(
        job_id=job_id, job_type=job_type, status=JobStatus.RUNNING.value,
        progress_snapshot={
            "job_id": job_id, "job_type": job_type, "status": "RUNNING",
            "step_current": 1, "step_total": 5, "step_name": "init", 
            "message": "Init", "updated_at": now.isoformat() 
        }
    )
    
    # Same state as step 1 -> Should trigger dedup
    state_step_1_dup = state_step_1 
    
    state_step_2 = MagicMock(
        job_id=job_id, job_type=job_type, status=JobStatus.RUNNING.value,
        progress_snapshot={
             "job_id": job_id, "job_type": job_type, "status": "RUNNING",
            "step_current": 2, "step_total": 5, "step_name": "process", 
            "message": "Processing", "updated_at": later.isoformat() # Distinct time
        }
    )

    # SUCCESS STATE: Contains DB-style 'result_summary'
    # App must map this to 'summary_counts' in the SSE payload
    state_success = MagicMock(
        job_id=job_id, job_type=job_type, status=JobStatus.SUCCESS.value,
        completed_at=later,
        result_summary={"final_candidates_count": 10, "vcp_survivors_count": 20},
        progress_snapshot=None 
    )

    # Side Effect Sequence
    mock_job_service_get_detail.side_effect = [
        state_pending,      # Call 1: Pending (Wait)
        state_step_1,       # Call 2: New State -> Emit Progress (Step 1)
        state_step_1_dup,   # Call 3: Duplicate -> Skip (Dedup Logic)
        state_step_2,       # Call 4: New State -> Emit Progress (Step 2)
        state_success,      # Call 5: Terminal -> Emit Complete
        state_success,      # Call 6: Should not be reached if termination works
    ]

    response = client.get(f"/jobs/screening/stream/{job_id}")
    
    event_iterator = sse_parser(response.response)
    data_events = []
    
    try:
        # Event 1: Step 1
        # Use next_named_event to skip initial ": connected" comment
        e1 = next_named_event(event_iterator)
        data_events.append(e1)
        assert e1['event'] == 'progress'
        assert e1['data']['step_current'] == 1
        
        # Event 2: Step 2
        e2 = next_named_event(event_iterator)
        data_events.append(e2)
        assert e2['event'] == 'progress'
        assert e2['data']['step_current'] == 2
        
        # Event 3: Complete
        e3 = next_named_event(event_iterator)
        data_events.append(e3)
        assert e3['event'] == 'complete'
        assert e3['data']['status'] == 'SUCCESS'
        
        # --- KEY ASSERTION: Contract Mapping ---
        # The app must map DB `result_summary` to SSE `summary_counts`
        assert e3['data']['summary_counts']['final_candidates_count'] == 10
        assert e3['data']['summary_counts']['vcp_survivors_count'] == 20
        
    except StopIteration:
        pytest.fail("Stream ended prematurely. Expected 3 distinct events.")
        
    # Verify Stream Termination
    with pytest.raises(StopIteration):
        next(event_iterator)

    # Contract Validation
    try:
        JobProgressEvent.model_validate(data_events[0]['data'])
        JobProgressEvent.model_validate(data_events[1]['data'])
        JobCompleteEvent.model_validate(data_events[2]['data'])
    except Exception as e:
        pytest.fail(f"Event failed contract validation: {e}")

def test_heartbeat_ping_format(client, mock_job_service_get_detail, mock_clock, sse_parser):
    """
    SDD Requirement: "Sends a heartbeat comment (e.g., : ping) every 15s."
    Strictly verifies the emitted line is a pure comment.
    """
    job_id = "heartbeat-job"
    
    state_running = MagicMock(
        job_id=job_id, job_type="SCREENING", status=JobStatus.RUNNING.value,
        progress_snapshot={"updated_at": "static"}
    )
    
    # Simulate enough loops to trigger heartbeat logic (15s)
    side_effects = [state_running] * 20
    side_effects.append(MagicMock(status=JobStatus.SUCCESS.value, result_summary={}))
    
    mock_job_service_get_detail.side_effect = side_effects

    response = client.get(f"/jobs/screening/stream/{job_id}")
    
    event_iterator = sse_parser(response.response)
    pings = []
    
    for event_obj in event_iterator:
        if 'comment' in event_obj and 'ping' in event_obj['comment']:
            pings.append(event_obj)
            
    assert len(pings) >= 1, "Expected at least one heartbeat ping"
    
    # Strict Format Check
    ping = pings[0]
    assert ping['comment'] == "ping"
    assert set(ping.keys()) == {'comment'}, f"Heartbeat must NOT contain event/data keys. Got: {ping.keys()}"

def test_error_handling_job_failed(client, mock_job_service_get_detail, mock_clock, sse_parser):
    """
    Verify emission of JobErrorEvent when job status is FAILED.
    """
    job_id = "failed-job"
    job_type = "SCREENING"
    now = datetime.now(timezone.utc)
    
    state_failed = MagicMock(
        job_id=job_id, 
        job_type=job_type, 
        status=JobStatus.FAILED.value,
        error_message="Critical DB failure",
        completed_at=now,
        progress_snapshot=None
    )
    
    mock_job_service_get_detail.return_value = state_failed
    
    response = client.get(f"/jobs/screening/stream/{job_id}")
    event_iterator = sse_parser(response.response)
    
    try:
        # Use next_named_event to skip initial ": connected" comment
        e1 = next_named_event(event_iterator)
        assert e1['event'] == 'error'
        
        # Contract Validation
        err_event = JobErrorEvent.model_validate(e1['data'])
        assert err_event.status == "FAILED"
        assert err_event.error_message == "Critical DB failure"
        assert err_event.job_id == job_id
        
        with pytest.raises(StopIteration):
            next(event_iterator)
            
    except StopIteration:
        pytest.fail("Stream ended without emitting error event.")

def test_error_handling_job_not_found(client, mock_job_service_get_detail, mock_clock, sse_parser):
    """
    Verify correct behavior when job ID does not exist.
    Must emit synthetic error event matching JobErrorEvent contract.
    """
    job_id = "missing-id"
    mock_job_service_get_detail.return_value = None
    
    response = client.get(f"/jobs/screening/stream/{job_id}")
    event_iterator = sse_parser(response.response)
    
    try:
        # Use next_named_event to skip initial ": connected" comment
        e1 = next_named_event(event_iterator)
        assert e1['event'] == 'error'
        
        payload = e1['data']
        assert payload['status'] == "FAILED"
        assert "not found" in payload['error_message'].lower()
        
        # Strict Contract Validation for Synthetic Error
        # App must inject the requested job_id even if DB didn't return it
        err_event = JobErrorEvent.model_validate(payload)
        assert err_event.job_id == job_id
        # Expect default 'SCREENING' if not known, or whatever the route defaults to
        assert err_event.job_type == "SCREENING"
        
        with pytest.raises(StopIteration):
            next(event_iterator)
            
    except StopIteration:
        pytest.fail("Stream ended without emitting error event.")

def test_watchlist_stream_endpoint(client, mock_job_service_get_detail, mock_clock, sse_parser):
    """
    Verify the watchlist stream endpoint AND JobType consistency.
    """
    job_id = "wl-job"
    # Ensure Mock returns the CORRECT job_type for a watchlist job
    mock_job_service_get_detail.return_value = MagicMock(
        job_id=job_id,
        job_type=JobType.WATCHLIST_REFRESH.value, # Strict Enum Value
        status=JobStatus.SUCCESS.value,
        result_summary={"updated_items": 5, "archived_items": 1},
        completed_at=datetime.now(timezone.utc)
    )
    
    response = client.get(f"/jobs/watchlist/stream/{job_id}")
    
    # 1. Headers Check
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["Content-Type"]
    
    # 2. Content Check
    event_iterator = sse_parser(response.response)
    
    # Use next_named_event to skip initial ": connected" comment
    e1 = next_named_event(event_iterator)
    
    assert e1['event'] == 'complete'
    
    # --- KEY ASSERTION: JobType Safety ---
    # The emitted event must correctly identify as WATCHLIST_REFRESH
    assert e1['data']['job_type'] == JobType.WATCHLIST_REFRESH.value
    
    # Verify Data Mapping
    assert e1['data']['summary_counts']['updated_items'] == 5
    assert e1['data']['summary_counts']['archived_items'] == 1
    
    with pytest.raises(StopIteration):
        next(event_iterator)

def test_fast_job_race_condition(client, mock_job_service_get_detail, sse_parser):
    """
    Verifies that if a job transitions from PENDING -> RUNNING -> SUCCESS 
    faster than the SSE poll interval, the stream still emits the final 
    progress event before the complete event.
    """
    job_id = "fast-race-job"
    
    # Shared mutable state to simulate DB updates
    job_state = {
        "status": JobStatus.PENDING.value,
        "progress_snapshot": None,
        "result_summary": None
    }

    def get_job_side_effect(jid):
        # Return a fresh model instance based on current shared state
        return ScreeningJobRunRecord(
            job_id=jid,
            job_type=JobType.SCREENING,
            status=job_state["status"],
            created_at=datetime.now(timezone.utc),
            progress_snapshot=job_state["progress_snapshot"],
            result_summary=job_state["result_summary"]
        )

    mock_job_service_get_detail.side_effect = get_job_side_effect

    # Background thread to simulate rapid job execution
    def background_job_runner():
        time.sleep(0.1)
        # Step 1: Running with progress
        job_state["status"] = JobStatus.RUNNING.value
        job_state["progress_snapshot"] = {
            "updated_at": datetime.now(timezone.utc),
            "step_current": 100,
            "step_total": 100,
            "step_name": "finalizing",
            "message": "Almost done"
        }
        
        time.sleep(0.1)
        # Step 2: Success immediately after
        job_state["status"] = JobStatus.SUCCESS.value
        job_state["result_summary"] = {
            "total_tickers_fetched": 10,
            "final_candidates_count": 5
        }

    # Start the "job"
    runner_thread = threading.Thread(target=background_job_runner)
    runner_thread.start()

    # Consume the stream
    # Note: We patch time.sleep in app.py to speed up the test execution if needed,
    # but here we rely on the background thread being fast enough.
    with patch("app.time.sleep", return_value=None):  # Make poll loop instant
        response = client.get(f"/jobs/screening/stream/{job_id}")
        assert response.status_code == 200
        
        iterator = sse_parser(response.response)
        
        # We expect:
        # 1. : connected (skipped by helper)
        # 2. event: progress (The critical missing piece)
        # 3. event: complete
        
        events_received = []
        try:
            while True:
                evt = next_named_event(iterator)
                if not evt: break
                events_received.append(evt)
                if evt['event'] == 'complete' or evt['event'] == 'error':
                    break
        except StopIteration:
            pass

    runner_thread.join()

    # Assertions
    event_types = [e['event'] for e in events_received]
    
    # Diagnostic print
    print(f"Events received: {event_types}")

    assert 'error' not in event_types, f"Stream failed with error: {events_received[-1]}"
    assert 'progress' in event_types, "Failed to capture progress event in fast job scenario"
    assert 'complete' in event_types, "Failed to capture complete event"
    
    # Verify order: Progress MUST come before Complete
    progress_idx = event_types.index('progress')
    complete_idx = event_types.index('complete')
    assert progress_idx < complete_idx, "Progress event appeared after completion"