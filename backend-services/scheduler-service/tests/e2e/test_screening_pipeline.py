# backend-services/scheduler-service/tests/e2e/test_screening_pipeline.py

import pytest
import json
import time
from shared.contracts import (
    JobProgressEvent, 
    JobCompleteEvent, 
    JobStatus
)

@pytest.mark.e2e
def test_gateway_proxy_streaming_behavior(gateway_base_url, api_session, sse_parser):
    """
    Verifies the full Screening Pipeline via the API Gateway.
    Focus: Async 202 -> SSE Stream (No Buffering) -> Final History
    Uses robust incremental parsing to handle network fragmentation.
    """

    # 1. Trigger the Job
    # We use 'fast' mode (if supported by app.py) or just standard run
    start_url = f"{gateway_base_url}/jobs/screening/start"
    payload = {"mode": "fast", "use_vcp_freshness_check": True}

    print(f"[E2E] Starting job via {start_url}")
    start_resp = api_session.post(start_url, json=payload, timeout=5)

    assert start_resp.status_code == 202, f"Job start failed: {start_resp.text}"
    job_id = start_resp.json().get("job_id")
    assert job_id, "Job ID not returned"

    # 2. Stream Progress (SSE)
    stream_url = f"{gateway_base_url}/jobs/screening/stream/{job_id}"
    print(f"[E2E] Connecting to stream: {stream_url}")

    progress_events = []
    complete_event = None

    # Measure time to first byte/event
    req_start = time.time()

    with api_session.get(stream_url, stream=True, timeout=60) as response:
        # A. Verify Protocol Headers
        assert response.headers.get("Content-Type") == "text/event-stream"
        assert response.headers.get("Cache-Control") == "no-cache"
        
        # B. Consume Stream using robust fixture
        # sse_parser handles buffering across chunks automatically
        event_iterator = sse_parser(response.iter_content(chunk_size=None))

        for item in event_iterator:
            # Skip comments/heartbeats
            if 'event' not in item:
                continue

            event_type = item['event']
            data = item['data']

            if event_type == 'progress':
                try:
                    evt = JobProgressEvent(**data)
                    progress_events.append(evt)
                except Exception as e:
                    pytest.fail(f"Progress contract mismatch: {e}")

            elif event_type == 'complete':
                try:
                    complete_event = JobCompleteEvent(**data)
                    # [CRITICAL FIX] Break loop immediately on completion.
                    # Do not wait for server to close connection, as it might keep 
                    # the socket open for heartbeats or timeouts.
                    break 
                except Exception as e:
                    pytest.fail(f"Complete contract mismatch: {e}")

            elif event_type == 'error':
                pytest.fail(f"Job failed with error: {data}")

    # 3. Assertions
    assert len(progress_events) > 0, "No progress events received (Stream might be buffered or job failed silently)"
    assert complete_event is not None, "Stream ended without 'complete' event"
    assert complete_event.status == "SUCCESS"
    assert complete_event.job_id == job_id

    # 4. Verify Persistence (History)
    history_url = f"{gateway_base_url}/jobs/screening/history/{job_id}"
    hist_resp = api_session.get(history_url)
    assert hist_resp.status_code == 200
    
    hist_data = hist_resp.json()
    assert hist_data['status'] == "SUCCESS"
    assert 'results' in hist_data, "Detailed results not persisted"
    assert 'result_summary' in hist_data, "Summary not persisted"

@pytest.mark.e2e
def test_job_not_found_stream(gateway_base_url, api_session, sse_parser):
    """Ensure accessing a non-existent stream returns an error event, not 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    url = f"{gateway_base_url}/jobs/screening/stream/{fake_id}"
    
    with api_session.get(url, stream=True, timeout=5) as response:
        assert response.status_code == 200
        
        # Use valid parser here too
        iterator = sse_parser(response.iter_content(chunk_size=None))
        
        events = []
        for item in iterator:
            if 'event' in item:
                events.append(item)
                # Break on error to avoid hanging
                if item['event'] == 'error':
                    break
        
        assert len(events) > 0
        assert events[0]['event'] == 'error'
        assert "not found" in str(events[0]['data']).lower()