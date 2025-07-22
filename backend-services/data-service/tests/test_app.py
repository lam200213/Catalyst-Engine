import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from datetime import date, datetime, timezone, timedelta
from app import app, price_cache, news_cache, PRICE_CACHE_TTL, NEWS_CACHE_TTL, init_db
from pymongo.errors import OperationFailure
from app import app, init_db, PRICE_CACHE_TTL, NEWS_CACHE_TTL

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test class for the database initialization logic.
class TestDataServiceDbInit(unittest.TestCase):
    """
    Tests the init_db function, specifically its ability to handle
    index conflicts gracefully.
    """
    @patch('app.MongoClient')
    def test_init_db_handles_index_conflict(self, mock_mongo_client):
        """
        Verifies that if an index conflict occurs, the app drops the old
        index and successfully recreates it.
        """
        # --- Arrange ---
        mock_price_collection = MagicMock()
        mock_news_collection = MagicMock()
        
        # Simulate the conflict: the first call to create_index fails
        conflict_error = OperationFailure("Index conflict", code=85)
        mock_price_collection.create_index.side_effect = [
            conflict_error, # First call fails
            None            # Second call succeeds
        ]

        mock_db = MagicMock()
        mock_db.price_cache = mock_price_collection
        mock_db.news_cache = mock_news_collection
        mock_mongo_client.return_value.stock_analysis = mock_db

        # --- Act ---
        # Call the function we are testing
        init_db()

        # --- Assert ---
        # 1. The code should have tried to create the index, failed, and then dropped it.
        mock_price_collection.drop_index.assert_called_once()
        # 2. The code should have tried to create the index a second time.
        self.assertEqual(mock_price_collection.create_index.call_count, 2)

    @patch('app.MongoClient')
    def test_init_db_crashes_on_other_failures(self, mock_mongo_client):
        """
        Verifies that for any other database error, the app does not
        handle it and raises the exception, causing a crash.
        """
        # --- Arrange ---
        mock_price_collection = MagicMock()
        # Simulate a different, unexpected database error
        other_error = OperationFailure("Some other error", code=12345)
        mock_price_collection.create_index.side_effect = other_error

        mock_db = MagicMock()
        mock_db.price_cache = mock_price_collection
        mock_mongo_client.return_value.stock_analysis = mock_db

        # --- Act & Assert ---
        # Verify that the original error is re-raised, which would halt the app
        with self.assertRaises(OperationFailure):
            init_db()

# Test class for caching logic
@patch('app.init_db') # Patch init_db to prevent it from running in these tests
class TestDataServiceCacheLogic(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        
        # Patch the global collection variables for test isolation
        self.price_cache_patcher = patch('app.price_cache', MagicMock())
        self.news_cache_patcher = patch('app.news_cache', MagicMock())
        self.mock_price_cache = self.price_cache_patcher.start()
        self.mock_news_cache = self.news_cache_patcher.start()

    def tearDown(self):
        self.price_cache_patcher.stop()
        self.news_cache_patcher.stop()

    @patch('app.yfinance_provider.get_stock_data')
    def test_incremental_price_fetch(self, mock_get_stock_data, mock_init_db):
        """
        Tests that the service fetches only new data if recent data is in cache.
        """
        ticker = "AAPL"
        # Arrange: Simulate a cache hit with recent but not up-to-date data
        last_cached_date_str = (date.today() - timedelta(days=3)).strftime('%Y-%m-%d')
        last_cached_date_obj = date.fromisoformat(last_cached_date_str)
        
        cached_record = {
            "_id": "mock_id_123", "ticker": ticker, "source": "yfinance",
            "data": [{"formatted_date": last_cached_date_str, "close": 155.0}],
            "createdAt": datetime.now(timezone.utc) - timedelta(days=1)
        }
        self.mock_price_cache.find_one.return_value = cached_record
        mock_get_stock_data.return_value = [{"formatted_date": "2025-07-20", "close": 156.0}]

        # Act
        self.app.get(f'/data/{ticker}?source=yfinance')

        # Assert: The provider was called with the day AFTER the last cached date
        expected_start_date = last_cached_date_obj + timedelta(days=1)
        mock_get_stock_data.assert_called_once_with(ticker, start_date=expected_start_date)
        # Assert that the existing cache record was updated, not a new one inserted
        self.mock_price_cache.update_one.assert_called_once()
    
    @patch('app.yfinance_provider.get_stock_data')
    def test_price_cache_is_used_when_fresh(self, mock_get_stock_data, mock_init_db):
        """
        Verifies that if cache is fresh, the external provider is not called.
        """
        ticker = "MSFT"
        # Arrange: Data from yesterday, well within TTL
        fresh_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        fresh_record = {
            "_id": "mock_id_456", "ticker": ticker, "source": "yfinance",
            "data": [{"formatted_date": fresh_date, "close": 400.0}],
            "createdAt": datetime.now(timezone.utc)
        }
        self.mock_price_cache.find_one.return_value = fresh_record

        # Act
        response = self.app.get(f'/data/{ticker}?source=yfinance')

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, fresh_record['data'])
        mock_get_stock_data.assert_not_called() # Crucially, the provider was not hit

    @patch('app.yfinance_provider.get_stock_data')
    def test_data_not_found_from_provider_and_cache(self, mock_get_stock_data, mock_init_db):
        """
        Tests the scenario where the data provider returns None and no data is in cache,
        expecting a 404 Not Found response.
        """
        ticker = "GOOG"
        # Arrange: Simulate no data from provider and no data in cache
        mock_get_stock_data.return_value = None
        self.mock_price_cache.find_one.return_value = None

        # Act
        response = self.app.get(f'/data/{ticker}?source=yfinance')

        # Assert
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": f"Could not retrieve price data for {ticker} from yfinance."})
        mock_get_stock_data.assert_called_once_with(ticker, start_date=None)
    def test_clear_cache_endpoint(self, mock_init_db):
        """Tests that the POST /cache/clear endpoint works."""
        response = self.app.post('/cache/clear')
        self.assertEqual(response.status_code, 200)
        self.mock_price_cache.drop.assert_called_once()
        self.mock_news_cache.drop.assert_called_once()
        # The real init_db should be called after dropping
        mock_init_db.assert_called_once()
if __name__ == '__main__':
    unittest.main()