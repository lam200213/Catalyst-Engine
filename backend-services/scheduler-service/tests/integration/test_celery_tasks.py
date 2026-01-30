# backend-services/scheduler-service/tests/integration/test_celery_tasks.py

import pytest
import json
from unittest.mock import MagicMock, call, ANY
from requests import HTTPError

from shared.contracts import (
    JobProgressEvent,
    JobStatus,
    VCPAnalysisBatchItem,
    LeadershipProfileBatch,
    FinalCandidate
)

# --- Local Helper (Specific to this test file) ---

def _coerce_progress_event(call_obj):
    """
    Normalizes emit_progress calls into a dict for easy assertion.
    """
    args, kwargs = call_obj
    
    if args and hasattr(args[0], 'model_dump'):
        return args[0].model_dump()
        
    if "event" in kwargs and hasattr(kwargs["event"], 'model_dump'):
        return kwargs["event"].model_dump()

    if len(args) >= 5:
        return {
            "job_id": args[0],
            "message": args[1],
            "step_current": args[2],
            "step_total": args[3],
            "step_name": args[4],
            "status": kwargs.get("status")
        }

    return {
        "job_id": kwargs.get("job_id"),
        "step_name": kwargs.get("step_name"),
        "status": kwargs.get("status"),
        "message": kwargs.get("message")
    }

def assert_progress_steps(mock_emit, job_id, expected_steps):
    """Verifies that specific step_names were emitted for the given job_id."""
    emitted_steps = []
    for c in mock_emit.call_args_list:
        ev = _coerce_progress_event(c)
        if ev.get("job_id") == job_id:
            emitted_steps.append(ev.get("step_name"))
    
    missing = [s for s in expected_steps if s not in emitted_steps]
    assert not missing, f"Missing progress steps: {missing}. Found: {emitted_steps}"

# --- Tests ---

def test_enqueue_full_pipeline_creates_chain(mock_job_service):
    """
    Verifies US-4: The pipeline MUST be orchestrated as a Celery Chain.
    1. run_full_pipeline (Parent)
    2. refresh_watchlist_task (Child, dependent)
    """
    # Import inside test to ensure patched env vars (from conftest) apply
    from tasks import enqueue_full_pipeline
    from unittest.mock import patch

    job_id = "job-chain-001"
    options = {"mode": "fast"}
    
    with patch("tasks.chain") as mock_chain:
        mock_workflow = MagicMock()
        mock_chain.return_value = mock_workflow
        
        # Patch the signatures (.s()) of the tasks within the tasks module
        with patch("tasks.run_full_pipeline") as mock_run_task, \
             patch("tasks.refresh_watchlist_task") as mock_refresh_task:
            
            enqueue_full_pipeline(job_id=job_id, options=options)
            
            # Assert Chain Creation
            mock_chain.assert_called_once()
            
            # Assert Task 1: Pipeline (Parent)
            mock_run_task.s.assert_called_once_with(job_id=job_id, options=options)
            
            # Assert Task 2: Refresh (Child)
            expected_child_id = f"{job_id}-refresh"
            mock_refresh_task.si.assert_called_once_with(
                job_id=expected_child_id, 
                parent_job_id=job_id
            )
            
            # Assert Execution
            mock_workflow.apply_async.assert_called_once()


def test_run_full_pipeline_success_end_to_end(
    mock_requests, 
    mock_db_session, 
    mock_job_service, 
    mock_emit_progress,
    assert_requests_have_timeouts
):
    """
    Verifies the Happy Path for the main pipeline task.
    Flow: Tickers -> Trend -> VCP -> Leadership -> Batch Add -> Complete.
    
    Corrected Data Contracts for Leadership and Results.
    """
    from tasks import run_full_pipeline
    
    job_id = "job-happy-path-1"
    
    # 1. Setup DB: Ensure no delisted tickers block the flow
    mock_db_session['ticker_status'].find.return_value = []

    # 2. Mock External Service Responses
    mock_requests.get.return_value.json.return_value = ["AAPL", "NVDA", "MSFT"]
    mock_requests.get.return_value.status_code = 200

    def post_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        
        if "screening-service" in url:
            # Internal Screening Service returns {"passing_tickers": [...]} 
            # OR simple list depending on internal contract. 
            # API_REFERENCE says: Produces {"passing_tickers": TickerList}
            mock_resp.json.return_value = {"passing_tickers": ["AAPL", "NVDA"]}
            
        elif "analysis-service" in url:
            # VCP Screen (Batch) - Adheres to VCPAnalysisBatchItem
            mock_resp.json.return_value = [
                {"ticker": "AAPL", "vcp_pass": True, "vcpFootprint": "10D 5.2%"},
                {"ticker": "NVDA", "vcp_pass": True, "vcpFootprint": "5D 2.0%"}
            ]
            
        elif "leadership-service" in url:
            # Leadership Screen - Adheres to LeadershipProfileBatch
            # Corrected: 'passes' is the field name in LeadershipProfileForBatch, not 'pass'
            resp_data = {
                "passing_candidates": [
                    {
                        "ticker": "AAPL", 
                        "passes": True,  # Corrected from 'pass'
                        "leadership_summary": {
                            "qualified_profiles": ["Market Leader"], 
                            "message": "Ok"
                        },
                        "profile_details": {
                            "explosive_grower": {"pass": True, "passed_checks": 4, "total_checks": 4},
                            "market_favorite": {"pass": False, "passed_checks": 1, "total_checks": 3},
                             "high_potential_setup": {"pass": False, "passed_checks": 1, "total_checks": 3}
                        },
                        "industry": "Tech"
                    }
                ],
                "unique_industries_count": 1,
                "metadata": {
                    "total_processed": 2, 
                    "total_passed": 1, 
                    "execution_time": 0.1
                }
            }
            mock_resp.json.return_value = resp_data
            mock_resp.content = json.dumps(resp_data).encode('utf-8')

        elif "monitoring-service" in url and "batch/add" in url:
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"message": "Added", "added": 1, "skipped": 0}
            
        else:
            raise ValueError(f"Test encountered unmocked URL: {url}")
            
        return mock_resp

    mock_requests.post.side_effect = post_side_effect

    # 3. Execute
    run_full_pipeline(job_id=job_id, options={})

    # 4. Assert Progress Steps
    expected_steps = [
        "fetch_tickers", 
        "trend_screening", 
        "vcp_analysis", 
        "leadership_screening", 
        "persist_results",
        "complete"
    ]
    assert_progress_steps(mock_emit_progress, job_id, expected_steps)

    # 5. Assert Logic & Data Contracts
    # Check monitoring service call payload
    monitor_call = [c for c in mock_requests.post.call_args_list 
                   if "monitoring-service" in c[0][0] and "batch/add" in c[0][0]][0]
    
    # Verify only the passing candidate (AAPL) was sent
    assert monitor_call[1]['json']['tickers'] == ["AAPL"] 
    
    # 6. Assert Security (Timeouts)
    assert_requests_have_timeouts(mock_requests.get)
    assert_requests_have_timeouts(mock_requests.post)

    # 7. Assert Completion
    mock_job_service.complete_job.assert_called_once()
    _, kwargs = mock_job_service.complete_job.call_args
    
    # Corrected Result Assertion:
    # Based on Week 10 SDD 'Split Persistence', 'results' stores the raw lists of survivors
    # and 'result_summary' stores the metrics/complex objects.
    # We check 'results' for the simple string list of survivors.
    assert "leadership_survivors" in kwargs['results']
    assert "AAPL" in kwargs['results']['leadership_survivors']
    assert kwargs['job_id'] == job_id


def test_pipeline_invokes_batch_add(
    mock_requests,
    mock_db_session,
    mock_job_service,
    mock_emit_progress
):
    """
    Step 3.2 / Task 2.1 Verification: 
    Strict Ordering & Payload Test: Verifies that 'Batch Add' happens BEFORE 
    job completion AND sends the correct survivors.
    """
    from tasks import run_full_pipeline
    job_id = "job-ordering-check"
    
    # 1. Setup Mocks with Manager for strict ordering
    manager = MagicMock()
    manager.attach_mock(mock_requests.post, 'post')
    manager.attach_mock(mock_job_service.complete_job, 'complete_job')

    # 2. Setup standard responses
    mock_requests.get.return_value.json.return_value = ["A"]
    
    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        
        if "screening" in url: 
            resp.json.return_value = {"passing_tickers": ["A"]}
        elif "analysis" in url: 
            resp.json.return_value = [{"ticker": "A", "vcp_pass": True, "vcpFootprint": "Ok"}]
        elif "leadership" in url:
            # Corrected: Use 'passes' not 'pass'
            resp_data = {
                "passing_candidates": [{
                    "ticker": "A", 
                    "passes": True, 
                    "leadership_summary": {"qualified_profiles": ["X"], "message": "Y"}, 
                    "profile_details": {"explosive_grower": {"pass": True, "passed_checks": 1, "total_checks": 1}},
                    "industry": "Tech"
                }],
                "unique_industries_count": 0, 
                "metadata": {"total_processed": 1, "total_passed": 1, "execution_time": 0.1}
            }
            resp.json.return_value = resp_data
            resp.content = json.dumps(resp_data).encode('utf-8')
        elif "batch/add" in url:
            resp.status_code = 201
            resp.json.return_value = {}
        else:
            raise ValueError(f"Test encountered unmocked URL: {url}")
            
        return resp
    
    mock_requests.post.side_effect = side_effect
    
    # 3. Execute
    run_full_pipeline(job_id=job_id)
    
    # 4. Verify Ordering via Manager
    monitoring_url = "http://monitoring-service:3006/monitor/internal/watchlist/batch/add"
    
    # Extract calls
    calls = manager.mock_calls
    monitor_idx = -1
    complete_idx = -1
    sent_payload = None

    for i, c in enumerate(calls):
        # Inspect call to monitoring service
        if "post" in str(c) and monitoring_url in str(c):
            monitor_idx = i
            # Capture payload
            if 'json' in c.kwargs:
                sent_payload = c.kwargs['json']

        if "complete_job" in str(c):
            complete_idx = i
            
    # Assertions
    assert monitor_idx != -1, "Monitoring Batch Add was NOT called."
    assert complete_idx != -1, "Job completion was NOT called."
    assert monitor_idx < complete_idx, "VIOLATION: Job marked complete BEFORE batch add finished."
    
    # Payload Assertion
    assert sent_payload is not None, "Batch Add called without JSON payload"
    assert sent_payload.get("tickers") == ["A"], f"Batch Add sent incorrect tickers: {sent_payload}"


def test_refresh_watchlist_task_success(
    mock_requests, 
    mock_job_service, 
    mock_emit_progress,
    assert_requests_have_timeouts
):
    """
    Verifies refresh_watchlist_task calls the internal orchestrator endpoint.
    Verifies timeout and return values.
    """
    from tasks import refresh_watchlist_task
    
    job_id = "job-refresh-1"
    
    # Mock Monitoring Service Response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"message": "ok"}'
    mock_resp.json.return_value = {
        "message": "Done",
        "updated_items": 5,
        "archived_items": 1,
        "failed_items": 0
    }
    mock_requests.post.return_value = mock_resp

    result = refresh_watchlist_task(job_id=job_id)

    # Assert Call
    expected_url = "http://monitoring-service:3006/monitor/internal/watchlist/refresh-status"
    
    mock_requests.post.assert_called_once()
    args, kwargs = mock_requests.post.call_args
    assert args[0] == expected_url
    
    assert_requests_have_timeouts(mock_requests.post)

    # Assert Completion
    mock_job_service.complete_job.assert_called_once()
    assert result['updated_items'] == 5


def test_refresh_watchlist_task_failure_propagates_to_parent(
    mock_requests, 
    mock_job_service, 
    mock_emit_progress
):
    """
    Verifies US-4 Failure Semantics:
    If refresh_watchlist_task fails:
    1. Parent job must be marked as FAILED.
    2. Parent job must NOT be marked as SUCCESS (mutually exclusive).
    """
    from tasks import refresh_watchlist_task
    
    job_id = "child-refresh-job"
    parent_id = "parent-screening-job"
    
    # Mock Failure (500 Error)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = HTTPError("500 Internal Error")
    mock_requests.post.return_value = mock_resp

    # Expect exception
    with pytest.raises(HTTPError):
        refresh_watchlist_task(job_id=job_id, parent_job_id=parent_id)

    # Assert Failure Propagation
    # We expect fail_job to be called TWICE: once for child, once for parent
    assert mock_job_service.fail_job.call_count >= 2
    
    # Verify Parent Fail Call
    parent_calls = [
        c for c in mock_job_service.fail_job.call_args_list 
        if c.kwargs.get('job_id') == parent_id
    ]
    assert len(parent_calls) == 1, "Parent job was NOT failed."
    assert "refresh_watchlist_task" in parent_calls[0].kwargs.get("error_step", "")

    # Verify State Exclusivity (No Zombie Jobs)
    # The parent job should NEVER be marked complete if it was failed
    complete_calls_for_parent = [
        c for c in mock_job_service.complete_job.call_args_list
        if c.kwargs.get('job_id') == parent_id
    ]
    assert len(complete_calls_for_parent) == 0, "Parent job was marked COMPLETE after failure!"

def test_run_full_pipeline_passes_detailed_objects_to_complete_job(
    mock_requests, 
    mock_db_session, 
    mock_job_service, 
    mock_emit_progress,
    assert_requests_have_timeouts
):
    """
    Verifies that run_full_pipeline constructs valid FinalCandidate objects 
    (containing VCP footprint + Leadership results) and passes them to 
    job_service.complete_job for fan-out persistence.
    """
    from tasks import run_full_pipeline
    
    job_id = "job-split-persistence-check"
    
    # 1. Mock External Service Responses (Condensed for brevity)
    mock_requests.get.return_value.json.return_value = ["AAPL"] # Ticker Service
    
    def post_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        
        if "screening-service" in url:
            mock_resp.json.return_value = {"passing_tickers": ["AAPL"]}
        elif "analysis-service" in url:
            # VCP Result
            mock_resp.json.return_value = [
                {"ticker": "AAPL", "vcp_pass": True, "vcpFootprint": "10D 5%"}
            ]
        elif "leadership-service" in url:
            # Leadership Result
            resp_data = {
                "passing_candidates": [{
                    "ticker": "AAPL", 
                    "passes": True, 
                    "leadership_summary": {"qualified_profiles": ["Leader"], "message": "OK"}, 
                    "profile_details": {"explosive_grower": {"pass": True, "passed_checks": 1, "total_checks": 1}},
                    "industry": "Tech"
                }],
                "unique_industries_count": 1,
                "metadata": {"total_processed": 1, "total_passed": 1, "execution_time": 0.1}
            }
            mock_resp.json.return_value = resp_data
            mock_resp.content = json.dumps(resp_data).encode('utf-8')
        elif "batch/add" in url:
            mock_resp.status_code = 201
            
        return mock_resp

    mock_requests.post.side_effect = post_side_effect

    # 2. Execute
    run_full_pipeline(job_id=job_id, options={})

    # 3. Assertions
    mock_job_service.complete_job.assert_called_once()
    _, kwargs = mock_job_service.complete_job.call_args
    
    # A. Check Lightweight Results (Strings)
    assert "final_candidates" in kwargs['results']
    assert kwargs['results']['final_candidates'] == ["AAPL"]
    
    # B. Check Detailed Objects (Fan-Out Data)
    assert "final_candidates_objs" in kwargs
    detailed_objs = kwargs['final_candidates_objs']
    
    assert len(detailed_objs) == 1
    candidate = detailed_objs[0]
    
    # Verify Object Structure (Must be FinalCandidate model or compatible)
    assert isinstance(candidate, FinalCandidate)
    assert candidate.ticker == "AAPL"
    assert candidate.vcpFootprint == "10D 5%" # Came from Analysis
    assert candidate.leadership_results["ticker"] == "AAPL" # Came from Leadership