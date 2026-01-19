# backend-services/scheduler-service/tests/conftest.py

import sys
import os
import pytest
from unittest.mock import MagicMock

# Ensure the app and shared modules are in the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

@pytest.fixture
def mock_db_collections():
    """
    Mocks the database collections tuple returned by db.get_db_collections().
    Structure: (results, jobs, trend_survivors, vcp_survivors, leadership_survivors, ticker_status)
    """
    mock_results = MagicMock()
    mock_jobs = MagicMock() # Index 1: screening_jobs collection
    mock_trend = MagicMock()
    mock_vcp = MagicMock()
    mock_leadership = MagicMock()
    mock_status = MagicMock()
    
    return (mock_results, mock_jobs, mock_trend, mock_vcp, mock_leadership, mock_status)

@pytest.fixture
def mock_jobs_collection(mock_db_collections):
    """Convenience fixture to access the jobs collection mock directly."""
    return mock_db_collections[1]