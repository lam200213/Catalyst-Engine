# backend-services/scheduler-service/tests/unit/test_job_service.py

import pytest
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone
from shared.contracts import JobStatus, JobType, ScreeningJobRunRecord

# Note: These imports will fail until the implementation (Green phase) is complete.
# This confirms the "Red" state of TDD.
try:
    from services.job_service import create_job, get_job_history
except ImportError:
    pass # Expected in Red phase

@pytest.mark.unit
class TestJobService:

    def test_create_job_returns_valid_uuid_and_pending_status(self, mock_db_collections, mock_jobs_collection):
        """
        Requirements:
        1. Returns a string UUID.
        2. Inserts a record into the 'jobs' collection.
        3. Sets status to PENDING and created_at to UTC.
        """
        # Arrange
        options = {"use_vcp_freshness": True}
        
        # Patch the database accessor in the service module
        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            
            # Act
            job_id = create_job(job_type=JobType.SCREENING, options=options)
            
            # Assert - Output
            assert isinstance(job_id, str)
            assert len(job_id) > 5  # Ensure it's not empty or trivial
            
            # Assert - Persistence (verify business logic)
            mock_jobs_collection.insert_one.assert_called_once()
            call_args = mock_jobs_collection.insert_one.call_args[0][0]
            
            assert call_args["job_id"] == job_id
            assert call_args["status"] == JobStatus.PENDING
            assert call_args["job_type"] == JobType.SCREENING
            assert call_args["options"] == options
            
            # Verify Timestamp (Edge Case: Must be UTC)
            assert isinstance(call_args["created_at"], datetime)
            assert call_args["created_at"].tzinfo == timezone.utc

    def test_get_history_pagination_defaults(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: Verify default pagination logic (skip=0, limit=20).
        """
        # Arrange
        mock_cursor = MagicMock()
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter([]) # Return empty list

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            # Act
            get_job_history()
            
            # Assert
            mock_jobs_collection.find.assert_called()
            mock_cursor.sort.assert_called_with("created_at", -1) # Descending order
            mock_cursor.skip.assert_called_with(0)
            mock_cursor.limit.assert_called_with(20) # Default limit

    def test_get_history_pagination_custom_values(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: Verify custom pagination inputs are respected.
        """
        mock_cursor = MagicMock()
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = iter([])

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            # Act
            get_job_history(limit=50, skip=10)
            
            # Assert
            mock_cursor.skip.assert_called_with(10)
            mock_cursor.limit.assert_called_with(50)

    def test_get_history_returns_pydantic_models(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: No data structure mismatches.
        Service must return ScreeningJobRunRecord objects, not raw dicts.
        """
        # Arrange - Mock raw DB data
        raw_doc = {
            "job_id": "job-abc-123",
            "job_type": "SCREENING",
            "status": "SUCCESS",
            "created_at": datetime(2026, 1, 19, 12, 0, 0, tzinfo=timezone.utc),
            "options": {},
            "result_summary": {"total_tickers": 100}
        }
        
        mock_cursor = MagicMock()
        # Mock the iterator behavior of the cursor
        mock_cursor.__iter__.return_value = iter([raw_doc])
        
        mock_jobs_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor

        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            # Act
            history = get_job_history()
            
            # Assert
            assert len(history) == 1
            assert isinstance(history[0], ScreeningJobRunRecord) # Type check
            assert history[0].job_id == "job-abc-123"
            assert history[0].status == JobStatus.SUCCESS

    def test_create_job_handles_db_errors_gracefully(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: Edge case handling (DB Failure).
        Should raise an exception if insertion fails.
        """
        from pymongo.errors import PyMongoError
        
        # Arrange
        mock_jobs_collection.insert_one.side_effect = PyMongoError("Connection failed")
        
        with patch("services.job_service.get_db_collections", return_value=mock_db_collections):
            # Act & Assert
            with pytest.raises(PyMongoError):
                create_job(job_type=JobType.SCREENING)