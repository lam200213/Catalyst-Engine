# backend-services/scheduler-service/tests/unit/test_job_service.py

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pymongo.errors import PyMongoError

from shared.contracts import JobProgressEvent, JobStatus, JobType, ScreeningJobRunRecord

# In true TDD Red phase, these imports should fail loudly (do not skip).
from services.job_service import (
    complete_job,
    create_job,
    fail_job,
    get_job_history,
    start_job,
    update_job_progress,
)


@pytest.mark.unit
class TestJobService:
    def test_create_job_returns_valid_uuid_and_persists_pending_record(
        self, mock_db_collections, mock_jobs_collection
    ):
        """
        Week 10 requirements:
        - create_job returns a valid RFC 4122 UUID string.
        - Persists a ScreeningJobRunRecord-like document:
          job_id, job_type, status, created_at (UTC), options.
        - Supports additional optional fields (trigger_source, parent_job_id) additively.
        """
        options = {"use_vcp_freshness_check": True}
        trigger_source = "API"
        parent_job_id = "parent-job-123"

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            job_id = create_job(
                job_type=JobType.SCREENING,
                options=options,
                trigger_source=trigger_source,
                parent_job_id=parent_job_id,
            )

        assert isinstance(job_id, str)
        parsed = uuid.UUID(job_id)
        assert str(parsed) == job_id

        mock_jobs_collection.insert_one.assert_called_once()
        doc = mock_jobs_collection.insert_one.call_args[0][0]

        assert doc["job_id"] == job_id
        assert doc["job_type"] == JobType.SCREENING.value
        assert doc["status"] == JobStatus.PENDING.value
        assert doc["options"] == options

        assert "created_at" in doc
        assert isinstance(doc["created_at"], datetime)
        assert doc["created_at"].tzinfo == timezone.utc

        # Optional Week 10 linkage fields (allowed even if not yet in contracts model)
        assert doc.get("trigger_source") == trigger_source
        assert doc.get("parent_job_id") == parent_job_id

        # Recommended defaults for a durable record (not strictly required by contract,
        # but helps ensure consistent DB shape).
        assert "progress_log" in doc
        assert isinstance(doc["progress_log"], list)

    def test_create_job_raises_on_db_error(self, mock_db_collections, mock_jobs_collection):
        mock_jobs_collection.insert_one.side_effect = PyMongoError("DB down")

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            with pytest.raises(PyMongoError):
                create_job(job_type=JobType.SCREENING, options={})

    def test_start_job_sets_running_and_started_at_utc(self, mock_db_collections, mock_jobs_collection):
        job_id = str(uuid.uuid4())

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            start_job(job_id)

        mock_jobs_collection.update_one.assert_called_once()
        filter_doc, update_doc = mock_jobs_collection.update_one.call_args[0][0:2]

        assert filter_doc == {"job_id": job_id}
        assert "$set" in update_doc
        assert update_doc["$set"]["status"] == JobStatus.RUNNING.value
        assert isinstance(update_doc["$set"]["started_at"], datetime)
        assert update_doc["$set"]["started_at"].tzinfo == timezone.utc

        # Ensure additive update semantics (no full document replacement)
        assert "job_id" not in update_doc
        assert "status" not in update_doc

    def test_update_job_progress_persists_snapshot_and_bounded_log(
        self, mock_db_collections, mock_jobs_collection
    ):
        """
        Week 10 requirements:
        - progress_snapshot must be compatible with JobProgressEvent schema.
        - progress_log must be appended with a bounded size of 100 (Mongo $slice -100).
        - Update must be additive ($set + $push), not a full replacement.
        """
        job_id = str(uuid.uuid4())

        step_current = 2
        step_total = 5
        step_name = "trend_screening"
        message = "Trend screen started"

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            update_job_progress(
                job_id=job_id,
                step_current=step_current,
                step_total=step_total,
                step_name=step_name,
                message=message,
                job_type=JobType.SCREENING,
                status=JobStatus.RUNNING,
            )

        mock_jobs_collection.update_one.assert_called_once()
        filter_doc, update_doc = mock_jobs_collection.update_one.call_args[0][0:2]

        assert filter_doc == {"job_id": job_id}
        assert "$set" in update_doc
        assert "$push" in update_doc

        snapshot = update_doc["$set"]["progress_snapshot"]

        # Enforce JobProgressEvent compatibility (keys and basic types)
        required_keys = (
            "job_id",
            "job_type",
            "status",
            "step_current",
            "step_total",
            "step_name",
            "message",
            "updated_at",
        )
        for k in required_keys:
            assert k in snapshot

        assert snapshot["job_id"] == job_id
        assert snapshot["job_type"] == JobType.SCREENING.value
        assert snapshot["status"] == JobStatus.RUNNING.value
        assert snapshot["step_current"] == step_current
        assert snapshot["step_total"] == step_total
        assert snapshot["step_name"] == step_name
        assert snapshot["message"] == message
        assert isinstance(snapshot["updated_at"], datetime)
        assert snapshot["updated_at"].tzinfo == timezone.utc

        # Validate it can instantiate JobProgressEvent without schema mismatch
        JobProgressEvent(**snapshot)

        # Bounded log ($push with $each + $slice)
        log_push = update_doc["$push"]["progress_log"]
        assert "$each" in log_push
        assert "$slice" in log_push
        assert log_push["$slice"] == -100
        assert isinstance(log_push["$each"], list)
        assert len(log_push["$each"]) == 1
        assert isinstance(log_push["$each"][0], dict)

        # Ensure additive update semantics
        assert "progress_snapshot" not in update_doc
        assert "progress_log" not in update_doc

    def test_complete_job_sets_success_and_calculates_total_process_time_deterministically(
        self, mock_db_collections, mock_jobs_collection
    ):
        """
        Week 10 requirements:
        - complete_job sets status SUCCESS and completed_at.
        - Calculates total_process_time = completed_at - started_at (seconds).
        - Split persistence:
          - results payload stored in results
          - metrics stored in result_summary
        """
        job_id = str(uuid.uuid4())

        started_at = datetime(2026, 1, 19, 12, 0, 0, tzinfo=timezone.utc)
        fixed_now = started_at + timedelta(seconds=37.5)

        mock_jobs_collection.find_one.return_value = {"job_id": job_id, "started_at": started_at}

        results_payload = {
            "trend_survivors": ["AAPL", "MSFT"],
            "vcp_survivors": ["AAPL"],
            "final_candidates": ["AAPL"],
        }
        summary_payload = {
            "total_tickers_fetched": 200,
            "trend_screen_survivors_count": 2,
            "vcp_survivors_count": 1,
            "final_candidates_count": 1,
            "industry_diversity": {"unique_industries_count": 1},
        }

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            with patch("services.job_service.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_now
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

                complete_job(job_id=job_id, results=results_payload, summary=summary_payload)

        mock_jobs_collection.find_one.assert_called_once()
        args, kwargs = mock_jobs_collection.find_one.call_args
        assert args[0] == {"job_id": job_id}
        # projection can be optional, but if present should include started_at
        if len(args) > 1:
            assert args[1] == {"started_at": 1}

        filter_doc, update_doc = mock_jobs_collection.update_one.call_args[0][0:2]
        assert filter_doc == {"job_id": job_id}
        assert "$set" in update_doc

        set_doc = update_doc["$set"]
        assert set_doc["status"] == JobStatus.SUCCESS.value
        assert isinstance(set_doc["completed_at"], datetime)
        assert set_doc["completed_at"].tzinfo == timezone.utc

        assert set_doc["results"] == results_payload
        assert set_doc["result_summary"] == summary_payload

        assert "total_process_time" in set_doc
        assert set_doc["total_process_time"] == pytest.approx(37.5, rel=1e-6)

    def test_fail_job_sets_failed_and_persists_error_fields(
        self, mock_db_collections, mock_jobs_collection
    ):
        """
        Week 10 requirements:
        - fail_job sets status FAILED
        - persists error_message and error_step
        - sets completed_at
        """
        job_id = str(uuid.uuid4())
        error_message = "Downstream service timeout"
        error_step = "vcp_analysis"

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            fail_job(job_id=job_id, error_message=error_message, error_step=error_step)

        mock_jobs_collection.update_one.assert_called_once()
        filter_doc, update_doc = mock_jobs_collection.update_one.call_args[0][0:2]

        assert filter_doc == {"job_id": job_id}
        assert "$set" in update_doc

        set_doc = update_doc["$set"]
        assert set_doc["status"] == JobStatus.FAILED.value
        assert set_doc["error_message"] == error_message
        assert set_doc["error_step"] == error_step
        assert isinstance(set_doc["completed_at"], datetime)
        assert set_doc["completed_at"].tzinfo == timezone.utc

    def test_get_job_history_defaults_and_sorting(self, mock_db_collections, mock_jobs_collection):
        """
        Week 10 requirement:
        - Default pagination: skip=0, limit=20
        - Sorting: created_at desc
        """
        mock_cursor = MagicMock()
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(tuple())

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            get_job_history()

        mock_jobs_collection.find.assert_called_once()
        mock_cursor.sort.assert_called_once_with("created_at", -1)
        mock_cursor.skip.assert_called_once_with(0)
        mock_cursor.limit.assert_called_once_with(20)

    def test_get_job_history_custom_pagination(self, mock_db_collections, mock_jobs_collection):
        mock_cursor = MagicMock()
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter(tuple())

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            get_job_history(limit=50, skip=10)

        mock_cursor.skip.assert_called_once_with(10)
        mock_cursor.limit.assert_called_once_with(50)

    def test_get_job_history_returns_screening_job_run_record_models(
        self, mock_db_collections, mock_jobs_collection
    ):
        """
        Week 10 requirement:
        - Return ScreeningJobRunRecord models (not raw dicts).
        - Types must validate per contracts.py (status is a string).
        """
        raw_doc = {
            "job_id": "job-abc-123",
            "job_type": JobType.SCREENING.value,
            "status": JobStatus.SUCCESS.value,
            "created_at": datetime(2026, 1, 19, 12, 0, 0, tzinfo=timezone.utc),
            "options": {},
            "progress_snapshot": None,
            "progress_log": [],
            "results": None,
            "result_summary": {"total_tickers_fetched": 100},
        }

        mock_cursor = MagicMock()
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter((raw_doc,))

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            history = get_job_history()

        assert isinstance(history, list)
        assert len(history) == 1

        record = history[0]
        assert isinstance(record, ScreeningJobRunRecord)
        assert record.job_id == "job-abc-123"
        assert record.job_type == JobType.SCREENING.value
        assert record.status == JobStatus.SUCCESS.value
        assert record.result_summary["total_tickers_fetched"] == 100

    def test_update_job_progress_does_not_replace_existing_document(self, mock_db_collections, mock_jobs_collection):
        """
        Week 10 schema-compatibility requirement:
        Updates must be additive ($set/$push) and must not delete unknown/legacy fields.
        This test ensures we never send a full replacement document to update_one.
        """
        job_id = str(uuid.uuid4())

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            update_job_progress(
                job_id=job_id,
                step_current=1,
                step_total=4,
                step_name="fetch_tickers",
                message="Starting",
                job_type=JobType.SCREENING,
                status=JobStatus.RUNNING,
            )

        _, update_doc = mock_jobs_collection.update_one.call_args[0][0:2]
        assert "$set" in update_doc
        assert "$push" in update_doc
        assert len(update_doc.keys()) == 2
