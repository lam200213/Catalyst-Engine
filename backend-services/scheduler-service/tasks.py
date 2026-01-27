# backend-services/scheduler-service/tasks.py

import os
import logging
import requests
import time
from datetime import datetime, timezone
from typing import List, Tuple, Any, Optional, Dict

from celery import chain
from pydantic import ValidationError, TypeAdapter

# Import Shared Contracts & Services
from shared.contracts import (
    ScreeningJobResult,
    FinalCandidate,
    IndustryDiversity,
    VCPAnalysisBatchItem,
    LeadershipProfileBatch,
    JobStatus
)
from celery_app import celery
from services.progress_emitter import emit_progress

# Importing the module allows tests to patch 'tasks.job_service' reliably
import services.job_service as job_service
from db import get_db_collections

logger = logging.getLogger(__name__)

# --- Configuration ---
TICKER_SERVICE_URL = os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001")
SCREENING_SERVICE_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")
LEADERSHIP_SERVICE_URL = os.getenv("LEADERSHIP_SERVICE_URL", "http://leadership-service:3005")
MONITORING_SERVICE_URL = os.getenv("MONITORING_SERVICE_URL", "http://monitoring-service:3006")

# --- Helper Functions (Private / Testable) ---

def _get_all_tickers(job_id: str) -> Tuple[List[str], Any]:
    try:
        resp = requests.get(f"{TICKER_SERVICE_URL}/tickers", timeout=15)
        resp.raise_for_status()
        tickers = resp.json()
        if not isinstance(tickers, list):
            return [], "Invalid format"
        return tickers, None
    except Exception as e:
        logger.error(f"Job {job_id}: Failed to fetch tickers: {e}")
        return [], str(e)

def _run_trend_screening(job_id: str, tickers: List[str]) -> Tuple[List[str], Any]:
    if not tickers:
        return [], None
    try:
        resp = requests.post(f"{SCREENING_SERVICE_URL}/screen/batch", json={"tickers": tickers}, timeout=5999)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        logger.error(f"Job {job_id}: Trend screen failed: {e}")
        return [], str(e)

def _run_vcp_analysis(job_id: str, tickers: List[str]) -> List[VCPAnalysisBatchItem]:
    if not tickers:
        return []
    try:
        # Note: 'mode': 'fast' is hardcoded here for analysis, but this only affects the VCP step,
        # not the number of tickers sent TO this step.
        resp = requests.post(
            f"{ANALYSIS_SERVICE_URL}/analyze/batch",
            json={"tickers": tickers, "mode": "fast"},
            timeout=1200,
        )
        if resp.status_code == 200:
            return TypeAdapter(List[VCPAnalysisBatchItem]).validate_python(resp.json())
        return []
    except Exception as e:
        logger.error(f"Job {job_id}: VCP analysis failed: {e}")
        return []

def _run_leadership_screening(job_id: str, vcp_survivors: List[VCPAnalysisBatchItem]) -> Tuple[List[FinalCandidate], int]:
    if not vcp_survivors:
        return [], 0
    
    tickers = [c.ticker for c in vcp_survivors]
    try:
        resp = requests.post(
            f"{LEADERSHIP_SERVICE_URL}/leadership/batch",
            json={"tickers": tickers},
            timeout=3600
        )
        resp.raise_for_status()
        
        batch_result = LeadershipProfileBatch.model_validate_json(resp.content)
        leadership_map = {item.ticker: item.model_dump() for item in batch_result.passing_candidates}
        
        final_candidates = []
        for vcp_item in vcp_survivors:
            if vcp_item.ticker in leadership_map:
                final = FinalCandidate(
                    ticker=vcp_item.ticker,
                    vcp_pass=vcp_item.vcp_pass,
                    vcpFootprint=vcp_item.vcpFootprint,
                    leadership_results=leadership_map[vcp_item.ticker]
                )
                final_candidates.append(final)
                
        return final_candidates, batch_result.unique_industries_count
    except Exception as e:
        logger.error(f"Job {job_id}: Leadership screen failed: {e}")
        return [], 0

def _batch_add_to_watchlist(job_id: str, tickers: List[str]) -> None:
    """
    Step 5: Calls Monitoring Service to batch add final survivors to the watchlist.
    This corresponds to the 'Re-introduction' step in the SDD.
    """
    if not tickers:
        return

    try:
        # Internal endpoint expects {"tickers": [...]}
        resp = requests.post(
            f"{MONITORING_SERVICE_URL}/monitor/internal/watchlist/batch/add",
            json={"tickers": tickers},
            timeout=30 
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Job {job_id}: Failed to batch add survivors to watchlist: {e}")
        raise e

# --- Celery Tasks ---

@celery.task(bind=True, name="scheduler.refresh_watchlist_task")
def refresh_watchlist_task(self, job_id: Optional[str] = None, parent_job_id: Optional[str] = None):
    """
    Triggers the Monitoring Service to refresh watchlist statuses.
    """
    job_id = job_id or self.request.id or "auto-refresh"
    emit_progress(job_id, "Starting watchlist refresh...", 0, 1, "watchlist_refresh")
    
    try:
        # Added timeout=300 to satisfy security/NFR test requirements
        resp = requests.post(
            f"{MONITORING_SERVICE_URL}/monitor/internal/watchlist/refresh-status",
            timeout=300
        )
        resp.raise_for_status()
        
        if not resp.content:
             raise ValueError("Empty response from monitoring service")
             
        data = resp.json()
        
        job_service.complete_job(
            job_id=job_id,
            summary=data
        )
        
        emit_progress(job_id, "Watchlist refresh complete.", 1, 1, "complete", status=JobStatus.SUCCESS)
        return data
        
    except Exception as e:
        logger.error(f"Job {job_id}: Watchlist refresh failed: {e}")
        error_msg = str(e)
        
        job_service.fail_job(job_id=job_id, error_message=error_msg, error_step="refresh")
        
        if parent_job_id:
            logger.error(f"Marking parent job {parent_job_id} failed due to child failure.")
            job_service.fail_job(
                job_id=parent_job_id,
                error_message=f"Child task refresh failed: {error_msg}",
                error_step="refresh_watchlist_task"
            )
            
        emit_progress(job_id, f"Watchlist refresh failed: {e}", 1, 1, "error", status=JobStatus.FAILED)
        raise e

@celery.task(
    bind=True, 
    name="scheduler.run_full_pipeline",
    # Soft Limit: 100 mins (6000s) - Worker raises SoftTimeLimitExceeded, allowing cleanup
    soft_time_limit=6000,
    # Hard Limit: 110 mins (6600s) - Worker sends SIGKILL
    time_limit=6600
)
def run_full_pipeline(self, job_id: Optional[str] = None, options: Optional[Dict[str, Any]] = None):
    """
    The main screening pipeline.
    Respects options['mode']='fast' to enable rapid E2E testing.
    """
    job_id = job_id or self.request.id
    start_time = time.time()
    options = options or {}
    
    try:
        # 1. Fetch Tickers
        emit_progress(job_id, "Fetching tickers from Ticker Service...", 5, 100, "fetch_tickers")
        all_tickers, error = _get_all_tickers(job_id)
        if error:
            raise Exception(f"Failed to fetch tickers: {error}")
            
        # 1b. Filter Delisted
        _, _, _, _, _, ticker_status_coll = get_db_collections()
        active_tickers = all_tickers
        if ticker_status_coll is not None:
            try:
                delisted_docs = ticker_status_coll.find({"status": "delisted"}, {"ticker": 1, "_id": 0})
                delisted_set = {doc['ticker'] for doc in delisted_docs}
                if delisted_set:
                    active_set = set(all_tickers) - delisted_set
                    active_tickers = list(active_set)
                    logger.info(f"Job {job_id}: Filtered {len(delisted_set)} delisted tickers. {len(active_tickers)} remaining.")
            except Exception as db_e:
                logger.warning(f"Job {job_id}: Failed to filter delisted tickers: {db_e}")

        # --- Fast Mode Implementation ---
        # If mode is 'fast', slice the list to the first 50 tickers.
        if options.get("mode") == "fast":
            logger.info(f"Job {job_id}: FAST MODE enabled. Limiting analysis to first 50 tickers.")
            active_tickers = active_tickers[:50]
        # -------------------------------------

        emit_progress(job_id, f"Fetched {len(all_tickers)} tickers ({len(active_tickers)} active).", 10, 100, "fetch_tickers")

        # 2. Trend Screening
        emit_progress(job_id, "Running Trend Screening...", 20, 100, "trend_screening")
        trend_survivors_raw, error = _run_trend_screening(job_id, active_tickers)
        if error:
             raise Exception(f"Trend screening failed: {error}")
        
        trend_survivors = []
        if trend_survivors_raw:
            trend_survivors = [t['ticker'] if isinstance(t, dict) else t for t in trend_survivors_raw]

        # 3. VCP Analysis
        emit_progress(job_id, f"Running VCP Analysis on {len(trend_survivors)} survivors...", 40, 100, "vcp_analysis")
        
        # Filter results to only include PASSING items
        vcp_analysis_results = _run_vcp_analysis(job_id, trend_survivors)
        vcp_survivors_objs = [item for item in vcp_analysis_results if item.vcp_pass]
        vcp_survivors = [item.ticker for item in vcp_survivors_objs]

        # 4. Leadership Screening
        emit_progress(job_id, f"Running Leadership Screening on {len(vcp_survivors)} candidates...", 70, 100, "leadership_screening")
        final_candidates_objs, unique_industries = _run_leadership_screening(job_id, vcp_survivors_objs)
        final_candidates = [item.ticker for item in final_candidates_objs]

        # 5. Batch Add to Watchlist (Monitoring Service Integration)
        emit_progress(job_id, f"Adding {len(final_candidates)} survivors to watchlist...", 80, 100, "persist_results")
        _batch_add_to_watchlist(job_id, final_candidates)

        # 6. Persist Results
        emit_progress(job_id, "Finalizing results...", 90, 100, "persist_results")
        
        total_time = round(time.time() - start_time, 2)
        
        summary = ScreeningJobResult(
            job_id=job_id,
            processed_at=datetime.now(timezone.utc),
            total_process_time=total_time,
            total_tickers_fetched=len(all_tickers),
            trend_screen_survivors_count=len(trend_survivors),
            vcp_survivors_count=len(vcp_survivors),
            final_candidates_count=len(final_candidates),
            industry_diversity=IndustryDiversity(unique_industries_count=unique_industries),
            final_candidates=final_candidates_objs
        )
        
        results_payload = {
            "trend_survivors": trend_survivors,
            "vcp_survivors": vcp_survivors,
            "final_candidates": final_candidates,
            "leadership_survivors": final_candidates
        }

        job_service.complete_job(
            job_id=job_id,
            results=results_payload,
            summary=summary.model_dump()
        )
        
        emit_progress(
            job_id, 
            f"Job completed successfully. Found {len(final_candidates)} candidates.", 
            100, 100, "complete", 
            status=JobStatus.SUCCESS
        )
        
        return summary.model_dump()

    except Exception as e:
        logger.error(f"Job {job_id}: Pipeline failed: {e}", exc_info=True)
        job_service.fail_job(
            job_id=job_id,
            error_message=str(e),
            error_step="pipeline_execution"
        )
        emit_progress(job_id, f"Job failed: {e}", 0, 100, "failed", status=JobStatus.FAILED)
        raise e

def enqueue_full_pipeline(job_id: str, options: Optional[Dict[str, Any]] = None):
    """
    Orchestrates the pipeline + watchlist refresh chain.
    """
    workflow = chain(
        run_full_pipeline.s(job_id=job_id, options=options),
        refresh_watchlist_task.si(job_id=f"{job_id}-refresh", parent_job_id=job_id)
    )
    return workflow.apply_async()