# backend-services/monitoring-service/tests/db/test_mongo_connect.py
"""
Test suite for database/mongo_client.py
Following TDD principles - these tests should be written BEFORE implementation
"""

import pytest
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import os
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
from database.mongo_client import (
    connect,
    DEFAULT_USER_ID,
)

# ============================================================================
# TEST: Connection and Initialization
# ============================================================================

class TestConnection:
    """Test database connection functionality"""
    
    def test_connect_returns_client_and_db(self, mock_mongo_client):
        """Verify connect() returns both client and database handle"""
        mock_client, mock_db = mock_mongo_client
        
        with patch('database.mongo_client.MongoClient', return_value=mock_client):
            client, db = connect()
            
            assert client is not None, "Client should not be None"
            assert db is not None, "Database handle should not be None"
            assert client == mock_client, "Should return the MongoDB client"
    
    def test_connect_uses_env_variables(self):
        """Verify connection uses MONGO_URI and MONITOR_DB from environment"""
        test_url = "mongodb://testhost:27017/"
        test_db = "test_stock_analysis"

        # Explicitly exercise the test branch: ENV=test + TEST_DB_NAME set
        with patch.dict(
            os.environ,
            {"MONGO_URI": test_url, "TEST_DB_NAME": test_db, "ENV": "test"},
            clear=False,
        ):
            with patch("database.mongo_client.MongoClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                client, db = connect()

                # Verify MongoClient was called with correct URL
                mock_client_class.assert_called_once_with(test_url)
                # Verify correct database was selected
                mock_client.__getitem__.assert_called_once_with(test_db)

    def test_connect_handles_connection_failure(self):
        """Verify proper error handling when connection fails"""
        with patch(
            "database.mongo_client.MongoClient",
            side_effect=ConnectionFailure("Connection failed"),
        ):
            with pytest.raises(ConnectionFailure):
                connect()
    
    def test_connect_with_missing_env_variables(self):
        """
        Verify behavior when environment variables are missing under pytest:
        safety guard should raise RuntimeError instead of using a prod DB.
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch("database.mongo_client.MongoClient") as mock_client_class:
                with pytest.raises(RuntimeError):
                    connect()

            # Guard should prevent any attempt to open a client
            mock_client_class.assert_not_called()

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
