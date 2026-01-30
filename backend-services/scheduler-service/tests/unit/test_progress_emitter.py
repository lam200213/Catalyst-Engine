# backend-services/scheduler-service/tests/unit/test_progress_emitter.py

import pytest
from unittest.mock import patch, ANY
from datetime import datetime, timezone
from shared.contracts import JobStatus

# Expected to fail until services/progress_emitter.py is created
try:
    from services.progress_emitter import emit_progress
except ImportError:
    pass

@pytest.mark.unit
class TestProgressEmitter:
    
    def test_emit_progress_atomic_update(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement:
        1. Updates 'status', 'step_current', 'updated_at' via $set.
        2. Appends a new log entry via $push.
        """
        job_id = "job-123"
        message = "Analyzing trend..."
        step_curr = 2
        step_tot = 5
        
        with patch("services.progress_emitter.get_db_collections", return_value=mock_db_collections):
            # Act
            emit_progress(
                job_id=job_id,
                message=message,
                step_current=step_curr,
                step_total=step_tot,
                step_name="trend"
            )
            
            # Assert
            mock_jobs_collection.update_one.assert_called_once()
            args = mock_jobs_collection.update_one.call_args[0]
            
            # Check Query
            assert args[0] == {"job_id": job_id}
            
            # Check Update Operators
            update_op = args[1]
            assert "$set" in update_op
            assert "$push" in update_op
            
            # Verify Set Fields
            assert update_op["$set"]["status"] == JobStatus.RUNNING
            assert update_op["$set"]["step_current"] == step_curr
            assert isinstance(update_op["$set"]["updated_at"], datetime)
            
            # Verify Push (Log Entry)
            log_entry = update_op["$push"]["progress_log"]
            # If using $each/$slice, the structure is slightly deeper
            if "$each" in log_entry:
                entry_data = log_entry["$each"][0]
            else:
                entry_data = log_entry
                
            assert entry_data["message"] == message
            assert entry_data["step"] == step_curr

    def test_emit_progress_caps_log_size(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: The progress log should not grow indefinitely.
        It must use $slice (e.g., -100) to keep only the most recent entries.
        """
        with patch("services.progress_emitter.get_db_collections", return_value=mock_db_collections):
            emit_progress(
                job_id="job-cap-test",
                message="Log entry",
                step_current=1,
                step_total=10,
                step_name="test"
            )
            
            update_op = mock_jobs_collection.update_one.call_args[0][1]
            push_op = update_op["$push"]["progress_log"]
            
            # Must use Mongo's $slice modifier
            assert "$slice" in push_op
            assert push_op["$slice"] == -100  # Keep last 100
            assert "$each" in push_op # Required when using modifiers like $slice

    def test_emit_progress_handles_completion(self, mock_db_collections, mock_jobs_collection):
        """
        Requirement: If status is explicitly passed as SUCCESS, it should update the status field.
        """
        with patch("services.progress_emitter.get_db_collections", return_value=mock_db_collections):
            emit_progress(
                job_id="job-done",
                message="Done",
                step_current=5,
                step_total=5,
                step_name="finalize",
                status=JobStatus.SUCCESS
            )
            
            update_op = mock_jobs_collection.update_one.call_args[0][1]
            assert update_op["$set"]["status"] == JobStatus.SUCCESS
            assert "completed_at" in update_op["$set"] # Should optionally set completion time