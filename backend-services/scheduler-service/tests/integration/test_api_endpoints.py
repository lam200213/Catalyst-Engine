# backend-services/scheduler-service/tests/integration/test_api_endpoints.py

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch, Mock, call
from shared.contracts import JobType, ScreeningJobRunRecord, JobStatus

# Try importing the real Celery/Kombu exception. 
# If not available (e.g. in a minimal test env), define a dummy to allow tests to run.
try:
    from kombu.exceptions import OperationalError
except ImportError:
    class OperationalError(Exception):
        pass

# -----------------------------------------------------------------------------
# Test Utilities & Custom Assertions
# -----------------------------------------------------------------------------

def parse_json_or_fail(response):
    """
    Helper to safely parse JSON from a response.
    Fails the test with a clear message if the response is HTML (e.g., Flask 404/500 default).
    """
    if response.content_type != "application/json":
        pytest.fail(
            f"Expected JSON response but got {response.content_type}. "
            f"Status: {response.status_code}. "
            f"Body snippet: {response.data[:200]}"
        )
    return json.loads(response.data)

def assert_valid_async_response(response, expected_job_id):
    """
    Validates the strict API Contract for Async Triggers (202 Accepted).
    Rules:
    1. Status must be 202.
    2. Payload must contain exact keys: {job_id, status, message}.
    3. job_id must match the expected (DB-generated) ID.
    4. status must be 'PENDING'.
    """
    assert response.status_code == 202, f"Expected 202 Accepted, got {response.status_code}"
    data = parse_json_or_fail(response)
    
    # 1. Check Data Integrity
    assert data['job_id'] == expected_job_id, f"Expected job_id {expected_job_id}, got {data['job_id']}"
    assert data.get('status') == 'PENDING', f"Expected status PENDING, got {data.get('status')}"
    assert "queued" in data.get('message', '').lower()
    
    # 2. Check Schema Strictness (No extra keys allowed)
    allowed_keys = {"job_id", "status", "message"}
    assert set(data.keys()) == allowed_keys, f"Response keys mismatch. Expected {allowed_keys}, got {set(data.keys())}"

def assert_valid_error_response(response, expected_codes):
    """
    Validates the strict API Contract for Errors.
    Rules:
    1. Status code must be in the expected list.
    2. Payload must be JSON and contain an 'error' key.
    """
    if not isinstance(expected_codes, list):
        expected_codes = [expected_codes]
        
    assert response.status_code in expected_codes, \
        f"Expected status in {expected_codes}, got {response.status_code}"
    
    data = parse_json_or_fail(response)
    assert "error" in data, "Error response must contain an 'error' key"
    assert len(data["error"]) > 0, "Error message should not be empty"

# -----------------------------------------------------------------------------
# Test Configuration & Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_app_dependencies():
    """
    Patches dependencies within app.py to isolate the controller logic.
    
    TDD STRATEGY:
    1. Patch 'app.run_full_pipeline' (Legacy) with create=True.
       This prevents AttributeError if app.py has already removed this import,
       making the test suite resilient during refactoring.
    2. Patch 'app.job_service' etc. with create=True.
       This allows testing against the current app.py state while guiding
       implementation of new dependencies.
    """
    with patch("app.run_full_pipeline", create=True) as mock_legacy_pipeline, \
         patch("app.job_service", create=True) as mock_js, \
         patch("app.enqueue_full_pipeline", create=True) as mock_enqueue, \
         patch("app.refresh_watchlist_task", create=True) as mock_refresh:
        
        # 1. Setup New Logic Mocks (The Target Behavior)
        # Default behavior: Success
        mock_js.create_job.return_value = "new-api-uuid-123"
        
        mock_async = Mock()
        mock_async.id = "celery-task-id" 
        mock_enqueue.return_value = mock_async
        mock_refresh.delay.return_value = mock_async

        # 2. Setup Legacy Logic Mock (To be deprecated)
        mock_legacy_pipeline.delay.return_value = mock_async
        
        yield {
            "job_service": mock_js,
            "enqueue_pipeline": mock_enqueue,
            "refresh_task": mock_refresh,
            "legacy_pipeline": mock_legacy_pipeline
        }

# -----------------------------------------------------------------------------
# Step 4.1: Trigger Endpoints (Async, Resilience, Contracts)
# -----------------------------------------------------------------------------

def test_post_screening_start_order_of_operations(client, mock_app_dependencies):
    """
    SDD Task 3.1: Strict verification that DB persistence occurs BEFORE Celery enqueue.
    """
    # Arrange
    mock_js = mock_app_dependencies["job_service"]
    mock_enqueue = mock_app_dependencies["enqueue_pipeline"]
    mock_legacy = mock_app_dependencies["legacy_pipeline"]
    
    expected_job_id = "new-api-uuid-123"
    mock_js.create_job.return_value = expected_job_id
    
    manager = Mock()
    manager.attach_mock(mock_js, 'job_service')
    manager.attach_mock(mock_enqueue, 'enqueue')

    # Input Payload
    payload = {"use_vcp_freshness_check": True}
    
    # Expected Options (Payload + Default values applied by Pydantic in app.py)
    # Since ScreeningRunOptions has mode='full' by default, the app will pass this downstream.
    expected_options = {"use_vcp_freshness_check": True, "mode": "full"}

    # Act
    response = client.post(
        "/jobs/screening/start",
        data=json.dumps(payload),
        content_type='application/json'
    )

    # Assert 1: Strict Response Contract
    assert_valid_async_response(response, expected_job_id)

    # Assert 2: Strict Order of Operations (DB -> Queue)
    expected_calls = [
        call.job_service.create_job(
            job_type=JobType.SCREENING,
            options=expected_options, # Updated to match Pydantic normalization
            trigger_source="API"
        ),
        call.enqueue(
            job_id=expected_job_id,  # Must pass the API-generated ID
            options=expected_options # Updated to match Pydantic normalization
        )
    ]
    manager.assert_has_calls(expected_calls, any_order=False)

    # Assert 3: Legacy code should NOT be called
    mock_legacy.delay.assert_not_called()


def test_post_screening_distinct_ids(client, mock_app_dependencies):
    """
    Requirement: Each request must generate a unique job_id.
    """
    mock_js = mock_app_dependencies["job_service"]
    mock_js.create_job.side_effect = ["uuid-1", "uuid-2"]

    resp1 = client.post("/jobs/screening/start", json={})
    resp2 = client.post("/jobs/screening/start", json={})

    assert_valid_async_response(resp1, "uuid-1")
    assert_valid_async_response(resp2, "uuid-2")


def test_post_screening_start_db_failure(client, mock_app_dependencies):
    """
    Security/Resilience: If DB creation fails, return 500 and do NOT enqueue.
    """
    mock_js = mock_app_dependencies["job_service"]
    mock_enqueue = mock_app_dependencies["enqueue_pipeline"]
    
    mock_js.create_job.side_effect = Exception("Mongo Connection Failure")

    response = client.post("/jobs/screening/start", json={})

    assert_valid_error_response(response, 500)
    
    data = parse_json_or_fail(response)
    # Security: Ensure raw exception details are stripped
    assert "Mongo Connection Failure" not in data.get("error", "")
    
    mock_enqueue.assert_not_called()


def test_post_screening_start_broker_failure(client, mock_app_dependencies):
    """
    Resilience: If Celery enqueue fails (OperationalError), return 503.
    """
    mock_js = mock_app_dependencies["job_service"]
    mock_enqueue = mock_app_dependencies["enqueue_pipeline"]
    
    mock_js.create_job.return_value = "uuid-123"
    mock_enqueue.side_effect = OperationalError("Connection refused")

    response = client.post("/jobs/screening/start", json={})

    assert_valid_error_response(response, 503)
    
    data = parse_json_or_fail(response)
    assert "Service Unavailable" in data.get("error", "") or "Failed" in data.get("error", "")


def test_post_screening_malformed_json(client, mock_app_dependencies):
    """
    Validation: Broken JSON syntax should result in 400 Bad Request with error envelope.
    """
    response = client.post(
        "/jobs/screening/start", 
        data="[Invalid JSON}", 
        content_type='application/json'
    )
    assert_valid_error_response(response, 400)


def test_post_screening_option_type_mismatch(client, mock_app_dependencies):
    """
    Validation: Wrong value types (e.g. string vs bool) -> 400/422 with error envelope.
    """
    bad_payload = {"use_vcp_freshness_check": "true"} # String is not Bool

    response = client.post(
        "/jobs/screening/start", 
        data=json.dumps(bad_payload), 
        content_type='application/json'
    )
    assert_valid_error_response(response, [400, 422])


def test_post_screening_unknown_option(client, mock_app_dependencies):
    """
    Validation: Extra/Unknown fields -> 400/422 with error envelope.
    """
    bad_payload = {"unexpected_field_xyz": 123}

    response = client.post(
        "/jobs/screening/start", 
        data=json.dumps(bad_payload), 
        content_type='application/json'
    )
    assert_valid_error_response(response, [400, 422])


def test_post_watchlist_refresh_happy_path(client, mock_app_dependencies):
    """
    SDD Task 3.1: Trigger Watchlist Refresh.
    """
    # Arrange
    mock_js = mock_app_dependencies["job_service"]
    mock_refresh = mock_app_dependencies["refresh_task"]
    
    expected_job_id = "refresh-uuid-999"
    mock_js.create_job.return_value = expected_job_id

    # Act
    response = client.post("/jobs/watchlist/refresh")

    # Assert 1: Use shared helper to ensure strict contract consistency
    assert_valid_async_response(response, expected_job_id)

    # Assert 2: Logic checks
    mock_js.create_job.assert_called_once_with(
        job_type=JobType.WATCHLIST_REFRESH,
        options={},
        trigger_source="API"
    )
    
    mock_refresh.delay.assert_called_once_with(
        job_id=expected_job_id
    )

# -----------------------------------------------------------------------------
# Step 4.2: History Endpoints (Structure Verification)
# -----------------------------------------------------------------------------

def test_get_history_list_structure(client, mock_app_dependencies):
    """
    SDD Task 3.2: Verify History List Structure.
    """
    mock_js = mock_app_dependencies["job_service"]
    
    # FIX: Use Pydantic model instead of dict, because app.py calls .model_dump()
    mock_record = ScreeningJobRunRecord(
        job_id="job-1",
        job_type=JobType.SCREENING,
        status="SUCCESS",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        result_summary={"vcp_survivors_count": 5}
    )
    mock_js.get_job_history.return_value = [mock_record]

    response = client.get("/jobs/screening/history?limit=10")

    assert response.status_code == 200
    data = parse_json_or_fail(response)
    
    assert "jobs" in data
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_id"] == "job-1"
    
    # Assert call includes default skip=0 parameter
    mock_js.get_job_history.assert_called_once_with(limit=10, skip=0)

# -----------------------------------------------------------------------------
# Step 4.2: History Endpoints (Structure & Data)
# -----------------------------------------------------------------------------

def test_get_history_list_structure(client, mock_app_dependencies):
    """
    SDD Task 3.2: Verify History List returns correct schema and metadata.
    """
    # Arrange
    mock_js = mock_app_dependencies["job_service"]
    
    # Mock data strictly adhering to ScreeningJobRunRecord
    mock_records = [
        ScreeningJobRunRecord(
            job_id="job-1",
            job_type=JobType.SCREENING,
            status=JobStatus.SUCCESS,
            created_at=datetime.now(timezone.utc),
            result_summary={"vcp_survivors_count": 5}
        )
    ]
    mock_js.get_job_history.return_value = mock_records

    # Act
    response = client.get("/jobs/screening/history")

    # Assert
    assert response.status_code == 200
    data = parse_json_or_fail(response)
    
    # Verify Top Level Structure
    assert "jobs" in data
    assert "metadata" in data
    assert data["metadata"]["count"] == 1
    
    # Verify Item Structure
    assert data["jobs"][0]["job_id"] == "job-1"
    assert data["jobs"][0]["status"] == "SUCCESS"
    
    # Verify default pagination args
    mock_js.get_job_history.assert_called_once_with(limit=20, skip=0)

def test_get_history_list_pagination(client, mock_app_dependencies):
    """
    SDD Task 3.2: Verify pagination parameters are passed to service.
    """
    mock_js = mock_app_dependencies["job_service"]
    mock_js.get_job_history.return_value = []

    # Act
    client.get("/jobs/screening/history?limit=5&skip=10")

    # Assert
    mock_js.get_job_history.assert_called_once_with(limit=5, skip=10)

def test_get_history_list_invalid_params(client, mock_app_dependencies):
    """
    Edge Case: Invalid pagination parameters should return 400 Bad Request.
    """
    # Act: Send string where int is expected
    response = client.get("/jobs/screening/history?limit=invalid")

    # Assert
    assert_valid_error_response(response, 400)

def test_get_history_detail_found(client, mock_app_dependencies):
    """
    SDD Task 3.2: Verify History Detail Structure.
    """
    mock_js = mock_app_dependencies["job_service"]
    job_id = "job-123"
    
    # FIX: Use Pydantic model
    mock_detail = ScreeningJobRunRecord(
        job_id=job_id,
        job_type=JobType.SCREENING,
        status=JobStatus.SUCCESS,
        created_at=datetime.now(timezone.utc),
        results={"vcp_survivors": ["AAPL"]}
    )
    mock_js.get_job_detail.return_value = mock_detail

    response = client.get(f"/jobs/screening/history/{job_id}")

    assert response.status_code == 200
    data = parse_json_or_fail(response)
    assert data["job_id"] == job_id
    assert "results" in data
    assert data["results"]["vcp_survivors"] == ["AAPL"]

def test_get_history_detail_not_found(client, mock_app_dependencies):
    """
    SDD Task 3.2: Verify History Detail 404 behavior.
    """
    # Arrange
    mock_js = mock_app_dependencies["job_service"]
    job_id = "job-999-missing"
    
    mock_js.get_job_detail.return_value = None

    # Act
    response = client.get(f"/jobs/screening/history/{job_id}")

    # Assert
    assert_valid_error_response(response, 404)
    data = parse_json_or_fail(response)
    assert "not found" in data["error"].lower()