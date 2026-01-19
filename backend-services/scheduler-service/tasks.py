# backend-services/scheduler-service/tasks.py

import os
import time
import logging
from datetime import datetime, timezone

import requests
import shortuuid
from pymongo import errors
from pydantic import ValidationError

from shared.contracts import (
    ScreeningJobResult,
    FinalCandidate,
    IndustryDiversity,
    VCPAnalysisBatchItem,
    LeadershipProfileBatch,
)

from celery_app import celery
from db import get_db_collections


logger = logging.getLogger(__name__)

TICKER_SERVICE_URL = os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001")
SCREENING_SERVICE_URL = os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003")
LEADERSHIP_SERVICE_URL = os.getenv("LEADERSHIP_SERVICE_URL", "http://leadership-service:3005")


def _get_all_tickers(job_id: str):
    try:
        resp = requests.get(f"{TICKER_SERVICE_URL}/tickers", timeout=15)
        resp.raise_for_status()

        try:
            tickers = resp.json()
        except requests.exceptions.JSONDecodeError:
            logger.warning(
                f"Job {job_id}: Could not decode JSON from ticker-service. Skipping ticker fetching.",
                exc_info=True,
            )
            return list(), None

        if not isinstance(tickers, list):
            logger.warning(f"Job {job_id}: Ticker service returned non-list format. Skipping ticker fetching.")
            return list(), None

        logger.info(f"Job {job_id}: Fetched {len(tickers)} total tickers.")
        return tickers, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Job {job_id}: Failed to connect to ticker-service.", exc_info=True)
        return None, ({"error": "Failed to connect to ticker-service", "details": str(e)}, 503)


def _filter_delisted_tickers(job_id: str, tickers):
    _, _, _, _, _, ticker_status_coll = get_db_collections()
    if ticker_status_coll is None:
        logger.warning(f"Job {job_id}: ticker_status collection not available. Proceeding unfiltered.")
        return tickers

    try:
        delisted_docs = ticker_status_coll.find({"status": "delisted"}, {"ticker": 1, "_id": 0})
        delisted_set = set()
        for doc in delisted_docs:
            if isinstance(doc, dict) and doc.get("ticker"):
                delisted_set.add(doc.get("ticker"))

        if not delisted_set:
            return tickers

        active = list()
        for t in tickers:
            if t not in delisted_set:
                active.append(t)

        logger.info(
            f"Job {job_id}: Pre-screening filter removed {len(tickers) - len(active)} delisted tickers. "
            f"Proceeding with {len(active)} active tickers."
        )
        return active
    except errors.PyMongoError as e:
        logger.error(f"Job {job_id}: Failed to query delisted tickers. Proceeding unfiltered. Error: {e}")
        return tickers


def _run_trend_screening(job_id: str, tickers):
    if not tickers:
        logger.info(f"Job {job_id}: Skipping trend screen, no tickers to process.")
        return list(), None

    try:
        resp = requests.post(
            f"{SCREENING_SERVICE_URL}/screen/batch",
            json={"tickers": tickers},
            timeout=5999,
        )
        resp.raise_for_status()

        try:
            trend_survivors = resp.json()
        except requests.exceptions.JSONDecodeError:
            logger.warning(
                f"Job {job_id}: Could not decode JSON from screening-service. Skipping trend screening.",
                exc_info=True,
            )
            return list(), None

        if not isinstance(trend_survivors, list):
            logger.warning(f"Job {job_id}: screening-service returned non-list survivors. Treating as empty.")
            return list(), None

        logger.info(f"Job {job_id}: Stage 1 (Trend Screen) passed: {len(trend_survivors)} tickers.")
        return trend_survivors, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Job {job_id}: Failed to connect to screening-service.", exc_info=True)
        return None, ({"error": "Failed to connect to screening-service", "details": str(e)}, 503)


def _run_vcp_analysis(job_id: str, tickers):
    if not tickers:
        logger.info(f"Job {job_id}: Skipping VCP analysis, no trend survivors.")
        return list()

    logger.info(f"Job {job_id}: Sending {len(tickers)} trend survivors to analysis-service for batch VCP screening.")

    try:
        resp = requests.post(
            f"{ANALYSIS_SERVICE_URL}/analyze/batch",
            json={"tickers": tickers, "mode": "fast"},
            timeout=1200,
        )

        if resp.status_code != 200:
            logger.error(
                f"Job {job_id}: VCP analysis batch request failed with status {resp.status_code}. Details: {resp.text}"
            )
            return list()

        try:
            raw = resp.json()
        except requests.exceptions.JSONDecodeError:
            logger.warning(
                f"Job {job_id}: Could not decode JSON from analysis-service. Treating VCP survivors as empty.",
                exc_info=True,
            )
            return list()

        survivors = list()
        if isinstance(raw, list):
            for item in raw:
                try:
                    survivors.append(VCPAnalysisBatchItem.model_validate(item))
                except ValidationError:
                    continue

        logger.info(f"Job {job_id}: Stage 2 (VCP Screen) passed: {len(survivors)} tickers.")
        return survivors
    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Could not connect to analysis-service for batch VCP.", exc_info=True)
        return list()


def _run_leadership_screening(job_id: str, vcp_survivors):
    if not vcp_survivors:
        logger.info(f"Job {job_id}: Skipping leadership screening, no VCP survivors.")
        return list(), 0

    vcp_tickers = list()
    for candidate in vcp_survivors:
        if getattr(candidate, "ticker", None):
            vcp_tickers.append(candidate.ticker)

    if not vcp_tickers:
        logger.warning(f"Job {job_id}: No valid tickers found in VCP survivors list.")
        return list(), 0

    logger.info(f"Job {job_id}: Sending {len(vcp_tickers)} tickers to leadership-service for batch screening.")

    try:
        resp = requests.post(
            f"{LEADERSHIP_SERVICE_URL}/leadership/batch",
            json={"tickers": vcp_tickers},
            timeout=3600,
        )
        resp.raise_for_status()

        try:
            result = LeadershipProfileBatch.model_validate_json(resp.content)
        except ValidationError as e:
            logger.error(
                f"Job {job_id}: Could not validate JSON from leadership-service against LeadershipProfileBatch. Error: {e}",
                exc_info=True,
            )
            return list(), 0

        leadership_results_map = dict()
        for item in result.passing_candidates:
            leadership_results_map[item.ticker] = item.model_dump()

        final_candidates = list()
        for candidate in vcp_survivors:
            if candidate.ticker in leadership_results_map:
                final_candidates.append(
                    FinalCandidate(
                        ticker=candidate.ticker,
                        vcp_pass=candidate.vcp_pass,
                        vcpFootprint=candidate.vcpFootprint,
                        leadership_results=leadership_results_map.get(candidate.ticker),
                    )
                )

        logger.info(f"Job {job_id}: Stage 3 (Leadership Screen) passed: {len(final_candidates)} tickers.")
        return final_candidates, result.unique_industries_count
    except requests.exceptions.RequestException:
        logger.error(f"Job {job_id}: Failed to connect to leadership-service for batch screening.", exc_info=True)
        return list(), 0


def _store_stage_survivors(job_id: str, collection, survivors, stage_name: str) -> bool:
    if collection is None:
        logger.error(f"Job {job_id}: Cannot store {stage_name} survivors, DB collection not available.")
        return False

    if not survivors:
        logger.info(f"Job {job_id}: No {stage_name} survivors to store.")
        return True

    try:
        docs = list()
        for ticker in survivors:
            docs.append({"job_id": job_id, "ticker": ticker})

        if docs:
            collection.insert_many(docs)

        logger.info(f"Job {job_id}: Inserted {len(docs)} {stage_name} survivors.")
        return True
    except errors.PyMongoError:
        logger.exception(f"Job {job_id}: Failed to write {stage_name} survivors to database.")
        return False


def _store_results(job_id: str, summary_doc, trend_survivors, vcp_survivors, leadership_survivors, final_candidates):
    results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll, _ = get_db_collections()
    if any(coll is None for coll in (results_coll, jobs_coll, trend_coll, vcp_coll, leadership_coll)):
        return False, ({"error": "Database client not available or collections missing"}, 500)

    try:
        jobs_coll.update_one({"job_id": job_id}, {"$set": summary_doc.model_dump()}, upsert=True)
    except errors.PyMongoError as e:
        logger.exception(f"Job {job_id}: Failed to write job summary to database.")
        return False, ({"error": "Failed to write job summary to database", "details": str(e)}, 500)

    if not _store_stage_survivors(job_id, trend_coll, trend_survivors, "trend"):
        return False, ({"error": "DB error"}, 500)

    vcp_tickers = list()
    for item in vcp_survivors:
        if getattr(item, "ticker", None):
            vcp_tickers.append(item.ticker)

    if not _store_stage_survivors(job_id, vcp_coll, vcp_tickers, "vcp"):
        return False, ({"error": "DB error"}, 500)

    leadership_tickers = list()
    for item in leadership_survivors:
        if getattr(item, "ticker", None):
            leadership_tickers.append(item.ticker)

    if not _store_stage_survivors(job_id, leadership_coll, leadership_tickers, "leadership"):
        return False, ({"error": "DB error"}, 500)

    if not final_candidates:
        return True, None

    try:
        processed_time = datetime.now(timezone.utc)
        docs = list()
        for candidate in final_candidates:
            d = candidate.model_dump()
            d["job_id"] = job_id
            d["processed_at"] = processed_time
            docs.append(d)

        if docs:
            results_coll.insert_many(docs)

        return True, None
    except errors.PyMongoError as e:
        logger.exception(f"Job {job_id}: Failed to write candidate results to database.")
        return False, ({"error": "Failed to write candidate results to database", "details": str(e)}, 500)


def run_screening_pipeline():
    start_time = time.time()

    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d-%H%M%S")
    unique_part = shortuuid.uuid()[:8]
    job_id = f"{timestamp_str}-{unique_part}"

    logger.info(f"Starting screening job ID: {job_id}")

    all_tickers, error = _get_all_tickers(job_id)
    if error:
        return error

    active_tickers = _filter_delisted_tickers(job_id, all_tickers)

    trend_survivors, error = _run_trend_screening(job_id, active_tickers)
    if error:
        return error

    vcp_survivors = _run_vcp_analysis(job_id, trend_survivors)
    leadership_survivors, unique_industries_count = _run_leadership_screening(job_id, vcp_survivors)

    end_time = time.time()
    total_process_time = round(end_time - start_time, 2)

    try:
        job_summary = ScreeningJobResult(
            job_id=job_id,
            processed_at=now,
            total_process_time=total_process_time,
            total_tickers_fetched=len(all_tickers),
            trend_screen_survivors_count=len(trend_survivors),
            vcp_survivors_count=len(vcp_survivors),
            final_candidates_count=len(leadership_survivors),
            industry_diversity=IndustryDiversity(unique_industries_count=unique_industries_count),
            final_candidates=leadership_survivors,
        )
    except ValidationError as e:
        logger.error(f"Job {job_id}: Failed to create job summary due to validation error: {e}")
        return ({"error": "Internal data validation failed when creating job summary.", "details": str(e)}, 500)

    success, error_info = _store_results(
        job_id=job_id,
        summary_doc=job_summary,
        trend_survivors=trend_survivors,
        vcp_survivors=vcp_survivors,
        leadership_survivors=leadership_survivors,
        final_candidates=leadership_survivors,
    )
    if not success:
        return error_info

    response_data = job_summary.model_dump()
    logger.info(f"Screening job {job_id} completed successfully.")

    return ({"message": "Screening job completed successfully.", **response_data}, 200)


@celery.task(name="scheduler.run_screening_pipeline_task")
def run_screening_pipeline_task():
    result, status_code = run_screening_pipeline()
    return {"status_code": status_code, "result": result}
