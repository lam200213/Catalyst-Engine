# backend-services/scheduler-service/app.py

import os
import logging
import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Generator

from flask import Flask, jsonify, request, Response, stream_with_context
from pydantic import BaseModel, ConfigDict, ValidationError, StrictBool
from kombu.exceptions import OperationalError

# Import services and tasks
import services.job_service as job_service
from tasks import enqueue_full_pipeline, refresh_watchlist_task
from shared.contracts import (
    JobType, 
    JobStatus, 
    JobProgressEvent, 
    JobCompleteEvent, 
    JobErrorEvent,
    ScreeningJobRunRecord
)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.getenv("PORT", 3004))


# --- Input Validation Models ---

class ScreeningRunOptions(BaseModel):
    """
    Strict validation for screening job options.
    Uses StrictBool to satisfy test_post_screening_option_type_mismatch
    and forbids extra fields for test_post_screening_unknown_option.
    """
    use_vcp_freshness_check: Optional[StrictBool] = False
    mode: Optional[str] = "full"
    
    # Forbid extra fields to ensure strict contract compliance
    model_config = ConfigDict(extra="forbid")


# --- Helper: SSE Generator ---

def _sse_generator(job_id: str) -> Generator[str, None, None]:
    """
    Polls the database for job updates and yields SSE-compliant events.
    Strictly follows Week 10 SDD requirements:
    - Deduplicates events based on timestamps.
    - Emits heartbeats every 15s.
    - Maps DB state to canonical Pydantic events (JobProgressEvent, etc.).
    - Prioritizes progress emission over terminal state to handle fast jobs.
    - Handles polymorphic summary extraction for Screening vs. Watchlist jobs.
    """
    last_updated_at = None
    last_heartbeat = time.time()
    
    # Yield immediate event to flush headers and prevent Gateway/Client timeouts
    yield ": connected\n\n"
    
    # Loop indefinitely; relying on client disconnect or terminal state to break
    while True:
        try:
            job: Optional[ScreeningJobRunRecord] = job_service.get_job_detail(job_id)
            
            # 1. Handle Job Not Found
            if not job:
                error_event = JobErrorEvent(
                    job_id=job_id,
                    job_type="SCREENING", # Default/fallback
                    status="FAILED",
                    error_message=f"Job {job_id} not found",
                    completed_at=datetime.now(timezone.utc)
                )
                yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
                break

            status = job.status
            now = time.time()

            # --- Process Progress Snapshot FIRST (Race Condition Fix) ---
            snapshot = job.progress_snapshot
            if snapshot:
                # Deduplication logic: Check if timestamp has changed
                current_updated_at = str(snapshot.get('updated_at'))
                
                if current_updated_at != last_updated_at:
                    try:
                        # Map snapshot to strict contract
                        progress_event = JobProgressEvent(
                            job_id=job.job_id,
                            job_type=job.job_type,
                            status=job.status,
                            step_current=snapshot.get('step_current', 0),
                            step_total=snapshot.get('step_total', 0),
                            step_name=snapshot.get('step_name', 'unknown'),
                            message=snapshot.get('message', ''),
                            updated_at=snapshot.get('updated_at')
                        )
                        yield f"event: progress\ndata: {progress_event.model_dump_json()}\n\n"
                        last_updated_at = current_updated_at
                    except ValidationError as ve:
                        logger.error(f"Invalid progress snapshot for {job_id}: {ve}")
                    except Exception as e:
                        logger.warning(f"Error processing snapshot for {job_id}: {e}")

            # --- Handle Terminal States (SUCCESS/FAILED) ---
            if status == JobStatus.SUCCESS.value:
                # Polymorphic Extraction based on JobType
                # We must extract specific keys based on the job type to satisfy the test expectations
                # and avoid Pydantic validation errors from complex objects.
                
                full_summary = job.result_summary if job.result_summary else {}
                summary_counts = {}

                # CASE A: Watchlist Refresh Job
                if job.job_type == JobType.WATCHLIST_REFRESH or job.job_type == JobType.WATCHLIST_REFRESH.value:
                    summary_counts = {
                        "updated_items": int(full_summary.get("updated_items", 0)),
                        "archived_items": int(full_summary.get("archived_items", 0)),
                        "failed_items": int(full_summary.get("failed_items", 0))
                    }

                # CASE B: Screening Job (Default)
                else:
                    summary_counts = {
                        "total_tickers_fetched": int(full_summary.get("total_tickers_fetched", 0)),
                        "trend_screen_survivors_count": int(full_summary.get("trend_screen_survivors_count", 0)),
                        "vcp_survivors_count": int(full_summary.get("vcp_survivors_count", 0)),
                        "final_candidates_count": int(full_summary.get("final_candidates_count", 0))
                    }
                    # Handle nested industry diversity if present
                    industry_diversity = full_summary.get("industry_diversity", {})
                    if isinstance(industry_diversity, dict):
                        summary_counts["unique_industries_count"] = int(industry_diversity.get("unique_industries_count", 0))

                complete_event = JobCompleteEvent(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status="SUCCESS",
                    completed_at=job.completed_at or datetime.now(timezone.utc),
                    summary_counts=summary_counts
                )
                yield f"event: complete\ndata: {complete_event.model_dump_json()}\n\n"
                break
            
            elif status == JobStatus.FAILED.value:
                error_event = JobErrorEvent(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status="FAILED",
                    error_message=job.error_message or "Unknown error",
                    completed_at=job.completed_at or datetime.now(timezone.utc)
                )
                yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
                break

            # Heartbeat (Every 15s)
            if now - last_heartbeat >= 15.0:
                yield ": ping\n\n"
                last_heartbeat = now

            # Polling interval
            time.sleep(1.0)

        except Exception as e:
            logger.error(f"SSE Stream Error for {job_id}: {e}")
            # Try to emit an error event before closing if possible
            try:
                err = JobErrorEvent(
                    job_id=job_id,
                    job_type="UNKNOWN",
                    status="FAILED",
                    error_message=f"Internal Stream Error: {str(e)}",
                    completed_at=datetime.now(timezone.utc)
                )
                yield f"event: error\ndata: {err.model_dump_json()}\n\n"
            except:
                pass
            break

# --- Routes ---

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


@app.route("/jobs/screening/start", methods=["POST"])
def start_screening_job_endpoint():
    """
    Starts a full screening pipeline.
    SDD Task 3.1: Async Endpoints
    """
    # 1. Validation
    raw_data = request.get_json(silent=True)
    if raw_data is None:
        if request.data and request.data.strip():
             return jsonify({"error": "Malformed JSON"}), 400
        raw_data = {}

    try:
        options = ScreeningRunOptions(**raw_data)
    except ValidationError as e:
        return jsonify({"error": "Validation Error", "details": e.errors()}), 400

    # 2. DB Persistence (Order of Operations: DB first)
    try:
        job_id = job_service.create_job(
            job_type=JobType.SCREENING,
            options=options.model_dump(),
            trigger_source="API"
        )
    except Exception as e:
        logger.error(f"Failed to create job in DB: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

    # 3. Enqueue Task (Celery)
    try:
        # [Critical] Ensure options are passed to Celery so 'mode' is respected
        enqueue_full_pipeline(job_id=job_id, options=options.model_dump())
    except OperationalError as e:
        logger.error(f"Broker connection failed for job {job_id}: {e}")
        job_service.fail_job(job_id, "Failed to enqueue task: Broker unavailable", "enqueue")
        return jsonify({"error": "Service Unavailable - Message Broker Failed"}), 503
    except Exception as e:
        logger.error(f"Failed to enqueue job {job_id}: {e}")
        job_service.fail_job(job_id, f"Failed to enqueue task: {str(e)}", "enqueue")
        return jsonify({"error": "Failed to queue job"}), 500

    # 4. Success Response
    return jsonify({
        "message": "Batch screening job successfully queued.",
        "job_id": job_id,
        "status": "PENDING"
    }), 202


@app.route("/jobs/watchlist/refresh", methods=["POST"])
def start_watchlist_refresh_endpoint():
    """
    Triggers a watchlist health check.
    """
    try:
        job_id = job_service.create_job(
            job_type=JobType.WATCHLIST_REFRESH,
            options={},
            trigger_source="API"
        )
        
        refresh_watchlist_task.delay(job_id=job_id)
        
        return jsonify({
            "message": "Watchlist refresh job successfully queued.",
            "job_id": job_id,
            "status": "PENDING"
        }), 202
        
    except Exception as e:
        logger.error(f"Failed to trigger watchlist refresh: {e}")
        return jsonify({"error": "Failed to queue job"}), 500


@app.route("/jobs/screening/history", methods=["GET"])
def get_job_history_endpoint():
    """
    Retrieves paginated job history.
    SDD Task 3.2: History
    """
    # 1. Parse Pagination (ISOLATED)
    try:
        limit = int(request.args.get("limit", 20))
        skip = int(request.args.get("skip", 0))
    except ValueError:
        return jsonify({"error": "Invalid pagination parameters"}), 400

    # 2. Fetch Data (Separate Try Block)
    try:
        history = job_service.get_job_history(limit=limit, skip=skip)
        # Use mode='json' to handle datetime serialization automatically
        history_data = [job.model_dump(mode="json") for job in history]
        
        return jsonify({
            "jobs": history_data,
            "metadata": {"count": len(history_data), "limit": limit, "skip": skip}
        }), 200
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@app.route("/jobs/screening/history/<job_id>", methods=["GET"])
def get_job_detail_endpoint(job_id):
    """
    Retrieves detailed job record.
    """
    try:
        job = job_service.get_job_detail(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
            
        return jsonify(job.model_dump(mode="json")), 200
    except Exception as e:
        logger.error(f"Error fetching job detail {job_id}: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


# --- Streaming Routes ---

@app.route("/jobs/screening/stream/<job_id>", methods=["GET"])
def stream_screening_job_progress(job_id):
    """
    Streams progress for a screening job using SSE.
    """
    # Added X-Accel-Buffering: no to prevent Nginx/Reverse Proxies from buffering chunks
    return Response(
        stream_with_context(_sse_generator(job_id)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

@app.route("/jobs/watchlist/stream/<job_id>", methods=["GET"])
def stream_watchlist_job_progress(job_id):
    """
    Streams progress for a watchlist refresh job using SSE.
    """
    return Response(
        stream_with_context(_sse_generator(job_id)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)