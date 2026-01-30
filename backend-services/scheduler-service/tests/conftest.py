# backend-services/scheduler-service/tests/conftest.py

import sys
import os
import pytest
import time
import json
from unittest.mock import MagicMock, patch
from bson import ObjectId
import requests

# Ensure the app and shared modules are in the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# --- Environment Configuration ---
def pytest_configure(config):
    """Register custom markers to avoid warnings."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated, no containers).")
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (service integration; may use DB/network mocks).",
    )
    config.addinivalue_line("markers", "e2e: End-to-end integration tests requiring running containers.")

def pytest_collection_modifyitems(config, items):
    # auto-tag tests by folder so `-m unit|integration|e2e` works consistently
    for item in items:
        path = str(item.fspath)
        if f"{os.sep}e2e{os.sep}" in path:
            item.add_marker(pytest.mark.e2e)
        elif f"{os.sep}integration{os.sep}" in path:
            item.add_marker(pytest.mark.integration)
        elif (f"{os.sep}unit{os.sep}" in path) or (f"{os.sep}unittest{os.sep}" in path):
            item.add_marker(pytest.mark.unit)

@pytest.fixture(autouse=True)
def celery_test_mode_env(monkeypatch, request):
    """
    Apply Celery eager mode ONLY for integration/e2e tests.
    """
    test_path = str(request.fspath)
    is_integration_test = f"{os.sep}integration{os.sep}" in test_path
    is_e2e_test = f"{os.sep}e2e{os.sep}" in test_path

    if not is_integration_test and not is_e2e_test:
        return

    if is_e2e_test and os.getenv("E2E_CELERY_EAGER", "0") != "1":
        return

    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "True")
    monkeypatch.setenv("CELERY_TASK_EAGER_PROPAGATES", "True")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "memory://")

@pytest.fixture(autouse=True)
def baseline_service_url_env(monkeypatch, request):
    """
    Sets baseline service URLs for integration tests to prevent import errors.
    """
    test_path = str(request.fspath)
    is_integration_test = f"{os.sep}integration{os.sep}" in test_path
    
    if not is_integration_test:
        return

    defaults = {
        "MONITORING_SERVICE_URL": "http://monitoring-service:3006",
        "TICKER_SERVICE_URL": "http://ticker-service:5001",
        "SCREENING_SERVICE_URL": "http://screening-service:3002",
        "ANALYSIS_SERVICE_URL": "http://analysis-service:3003",
        "LEADERSHIP_SERVICE_URL": "http://leadership-service:3005",
    }

    for key, val in defaults.items():
        if key not in os.environ:
            monkeypatch.setenv(key, val)

@pytest.fixture(scope="session")
def gateway_base_url():
    """
    Resolves the API Gateway URL. 
    Defaults to 'http://api-gateway:3000' which is the correct internal Docker DNS.
    Falls back to env var 'API_GATEWAY_URL' if set.
    """
    # 1. Check Explicit Env Var
    url = os.getenv("API_GATEWAY_URL")
    
    # 2. Default to Docker Service Name (Standard for inter-service communication)
    if not url:
        url = "http://api-gateway:3000"
        
    return url.rstrip('/')

@pytest.fixture(scope="session")
def api_session(gateway_base_url):
    """
    Creates a requests Session and verifies Gateway connectivity.
    Retries for up to 30s to allow services to warm up.
    """
    session = requests.Session()
    
    # Use a known existing endpoint that exercises the Gateway -> Scheduler path.
    health_check_url = f"{gateway_base_url}/jobs/screening/history"
    
    # FIX: Provide BOTH limit and skip to satisfy strict validation
    health_check_params = {"limit": 1, "skip": 0}
    
    print(f"\n[Fixture] Waiting for Gateway at {health_check_url}...")
    
    deadline = time.time() + 30
    connected = False
    
    while time.time() < deadline:
        try:
            # We send params to satisfy the 'Invalid pagination parameters' validation
            resp = session.get(health_check_url, params=health_check_params, timeout=2)
            
            # 200 OK means Gateway routed to Scheduler successfully AND Scheduler accepted args
            if resp.status_code == 200:
                connected = True
                break
            
            print(f"[Wait] Gateway reachable but returned {resp.status_code}. Retrying...")
            
        except requests.RequestException:
            # Connection refused means Gateway is down
            pass
        
        time.sleep(1)
        
    if not connected:
        # Try one last time to get the error for the failure message
        try:
            resp = session.get(health_check_url, params=health_check_params, timeout=2)
            pytest.fail(f"Gateway reachable but returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            pytest.fail(f"Could not connect to API Gateway at {gateway_base_url} after 30s. "
                        f"Ensure docker-compose up is running.")
        
    return session

# --- Flask & Time Fixtures (Required for SSE Tests) ---

@pytest.fixture
def client():
    """
    Returns the Flask test client. 
    Used by integration tests (especially SSE) to make requests to the application.
    """
    from app import app
    app.testing = True
    return app.test_client()

@pytest.fixture
def mock_clock():
    """
    Patches time.time and time.sleep to allow deterministic testing of 
    time-dependent logic (like heartbeats) without actual delays.
    """
    class MockClock:
        def __init__(self):
            self.current_time = 1700000000.0  # Arbitrary fixed start time
        
        def time(self):
            return self.current_time
        
        def sleep(self, seconds):
            self.current_time += seconds

    clock = MockClock()
    
    with patch("time.time", side_effect=clock.time), \
         patch("time.sleep", side_effect=clock.sleep):
        yield clock

# --- Database & Service Mocks (Required for Task/Unit Tests) ---

@pytest.fixture
def mock_db_collections():
    """
    Creates a tuple of MagicMocks representing the database collections.
    Used by unit tests (test_job_service.py) to patch services manually.
    Structure: (results, jobs, trend, vcp, leadership, status)
    """
    mock_results = MagicMock(name="results")
    mock_jobs = MagicMock(name="jobs")
    mock_trend = MagicMock(name="trend")
    mock_vcp = MagicMock(name="vcp")
    mock_leadership = MagicMock(name="leadership")
    mock_status = MagicMock(name="status")

    # Setup standard mongo return values
    mock_insert_result = MagicMock()
    mock_insert_result.inserted_id = ObjectId()
    mock_jobs.insert_one.return_value = mock_insert_result
    
    # Defaults
    mock_status.find.return_value = [] 

    return (mock_results, mock_jobs, mock_trend, mock_vcp, mock_leadership, mock_status)

@pytest.fixture
def mock_jobs_collection(mock_db_collections):
    """Convenience fixture to access the jobs collection mock directly."""
    return mock_db_collections[1]

@pytest.fixture
def mock_db_session():
    """
    Patches tasks.get_db_collections globally for integration tests (test_celery_tasks.py).
    Returns a dictionary for easy access to specific collection mocks.
    """
    with patch("tasks.get_db_collections") as mock_get_db:
        # Create mocks
        results_col = MagicMock(name="results_col")
        jobs_col = MagicMock(name="jobs_col")
        trend_col = MagicMock(name="trend_col")
        vcp_col = MagicMock(name="vcp_col")
        leadership_col = MagicMock(name="leadership_col")
        status_col = MagicMock(name="status_col")

        # Configure default behaviors
        jobs_col.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        status_col.find.return_value = [] 

        # Return the tuple expected by the application
        mock_get_db.return_value = (
            results_col, 
            jobs_col, 
            trend_col, 
            vcp_col, 
            leadership_col, 
            status_col
        )

        yield {
            "results": results_col,
            "jobs": jobs_col,
            "trend": trend_col,
            "vcp": vcp_col,
            "leadership": leadership_col,
            "ticker_status": status_col,
            "get_db_mock": mock_get_db 
        }

@pytest.fixture
def mock_requests():
    """
    Patches tasks.requests to prevent accidental network calls.
    """
    with patch("tasks.requests") as mock_req:
        yield mock_req

@pytest.fixture
def mock_job_service():
    """
    Patches tasks.job_service to prevent DB writes during task logic tests.
    """
    with patch("tasks.job_service") as mock_js:
        yield mock_js

@pytest.fixture
def mock_emit_progress():
    """
    Patches tasks.emit_progress so integration tests can assert progress emissions.
    """
    with patch("tasks.emit_progress") as mock_emit:
        yield mock_emit

# --- Shared Helpers ---
def _incremental_sse_parser(response_iterator):
    """
    Parses SSE stream incrementally.
    Yields parsed events (and comments/heartbeats) one by one.
    """
    buffer = ""
    for chunk in response_iterator:
        if isinstance(chunk, bytes):
            buffer += chunk.decode('utf-8')
        else:
            buffer += chunk
        
        while '\n\n' in buffer:
            block, buffer = buffer.split('\n\n', 1)
            lines = block.split('\n')
            
            event = {}
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # Capture comments (heartbeats)
                if line.startswith(":"):
                    event["comment"] = line[1:].strip()
                elif line.startswith("event:"):
                    event['event'] = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    try:
                        event['data'] = json.loads(data_str)
                    except json.JSONDecodeError:
                        event['data'] = data_str
            
            # Yield if we found content (event OR comment)
            if event:
                yield event
@pytest.fixture
def sse_parser():
    """
    Fixture that provides the robust incremental SSE parser.
    """
    return _incremental_sse_parser

def _assert_requests_have_timeouts(mock_requests_method):
    """
    Verifies that all calls to a mocked requests method included a 'timeout' argument.
    """
    for call_args in mock_requests_method.call_args_list:
        args, kwargs = call_args
        assert "timeout" in kwargs, (
            f"SECURITY FAILURE: Outbound call to {args[0] if args else '<unknown>'} "
            f"is missing a 'timeout' argument."
        )

@pytest.fixture
def assert_requests_have_timeouts():
    return _assert_requests_have_timeouts