import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from datetime import datetime, timezone, timedelta

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, price_cache, news_cache, PRICE_CACHE_TTL, NEWS_CACHE_TTL, init_db

class DataServiceCacheTest(unittest.TestCase):

    def setUp(self):
        # Use a test database for isolation
        app.config['TESTING'] = True
        self.app = app.test_client()
        self.db_client = MagicMock() # Mock the MongoClient
        
        # Patch MongoClient to return our mock client
        patch('app.MongoClient', return_value=self.db_client).start()
        
        # Mock the database and collections
        self.mock_db = MagicMock()
        self.db_client.stock_analysis = self.mock_db
        
        self.mock_price_cache = MagicMock()
        self.mock_news_cache = MagicMock()
        
        self.mock_db.price_cache = self.mock_price_cache
        self.mock_db.news_cache = self.mock_news_cache

        # Call init_db after patching MongoClient
        init_db()

        # Ensure indexes are created (mocked)
        self.mock_price_cache.create_index.return_value = None
        self.mock_news_cache.create_index.return_value = None

        # Patch the global variables in app.py after init_db has been called
        # This ensures that subsequent calls to price_cache and news_cache in app.py
        # refer to our mock objects.
        patch('app.price_cache', new=self.mock_price_cache).start()
        patch('app.news_cache', new=self.mock_news_cache).start()

        # Clear caches before each test (now using the mocked caches)
        self.mock_price_cache.delete_many({})
        self.mock_news_cache.delete_many({})

    def tearDown(self):
        patch.stopall() # Stop all patches

    @patch('app.yfinance_provider.get_stock_data')
    @patch('app.finnhub_provider.get_stock_data')
    def test_price_data_caching(self, mock_finnhub, mock_yfinance):
        ticker = "AAPL"
        finnhub_data = {"AAPL": {"price": 150.0}}
        yfinance_data = {"AAPL": {"price": 151.0}}

        # Mock cache misses initially
        self.mock_price_cache.find_one.return_value = None

        # Test Finnhub caching
        mock_finnhub.return_value = finnhub_data
        
        # First call: should hit external API and cache
        response = self.app.get(f'/data/{ticker}?source=finnhub')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, finnhub_data)
        mock_finnhub.assert_called_once_with(ticker)
        self.mock_price_cache.insert_one.assert_called_once()
        
        # Reset mocks for second call
        mock_finnhub.reset_mock()
        self.mock_price_cache.insert_one.reset_mock()

        # Mock cache hit for the second call
        self.mock_price_cache.find_one.return_value = {
            "_id": MagicMock(), # Add a mock _id
            "ticker": ticker,
            "source": "finnhub",
            "data": finnhub_data,
            "createdAt": datetime.now(timezone.utc)
        }

        # Second call: should hit cache, not external API
        response = self.app.get(f'/data/{ticker}?source=finnhub')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, finnhub_data)
        mock_finnhub.assert_not_called() # Ensure external API was NOT called
        self.mock_price_cache.insert_one.assert_not_called() # Ensure no new insert

        # Test Yfinance caching (similar logic)
        mock_yfinance.return_value = yfinance_data
        self.mock_price_cache.find_one.return_value = None # Reset for Yfinance first call
        self.mock_price_cache.insert_one.reset_mock()

        # First call for Yfinance
        response = self.app.get(f'/data/{ticker}?source=yfinance')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, yfinance_data)
        mock_yfinance.assert_called_once_with(ticker)
        self.mock_price_cache.insert_one.assert_called_once()

        # Reset mocks for second Yfinance call
        mock_yfinance.reset_mock()
        self.mock_price_cache.insert_one.reset_mock()

        # Mock cache hit for second Yfinance call
        self.mock_price_cache.find_one.return_value = {
            "_id": MagicMock(), # Add a mock _id
            "ticker": ticker,
            "source": "yfinance",
            "data": yfinance_data,
            "createdAt": datetime.now(timezone.utc)
        }

        # Second call for Yfinance
        response = self.app.get(f'/data/{ticker}?source=yfinance')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, yfinance_data)
        mock_yfinance.assert_not_called()
        self.mock_price_cache.insert_one.assert_not_called()

    @patch('app.marketaux_provider.get_news_for_ticker')
    def test_news_caching(self, mock_marketaux):
        ticker = "TSLA"
        news_data = [{"title": "TSLA news 1"}, {"title": "TSLA news 2"}]

        # Mock cache miss initially
        self.mock_news_cache.find_one.return_value = None

        mock_marketaux.return_value = news_data

        # First call: should hit external API and cache
        response = self.app.get(f'/news/{ticker}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, news_data)
        mock_marketaux.assert_called_once_with(ticker)
        self.mock_news_cache.insert_one.assert_called_once()

        # Reset mocks for second call
        mock_marketaux.reset_mock()
        self.mock_news_cache.insert_one.reset_mock()

        # Mock cache hit for the second call
        self.mock_news_cache.find_one.return_value = {
            "_id": MagicMock(), # Add a mock _id
            "ticker": ticker,
            "data": news_data,
            "createdAt": datetime.now(timezone.utc)
        }

        # Second call: should hit cache, not external API
        response = self.app.get(f'/news/{ticker}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, news_data)
        mock_marketaux.assert_not_called() # Ensure external API was NOT called
        self.mock_news_cache.insert_one.assert_not_called() # Ensure no new insert

    @patch('app.yfinance_provider.get_stock_data')
    def test_price_data_cache_expiration(self, mock_yfinance):
        ticker = "GOOG"
        old_data = {"GOOG": {"price": 100.0}}
        new_data = {"GOOG": {"price": 105.0}}

        # Simulate data in cache that is just about to expire
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=PRICE_CACHE_TTL + 1)
        self.mock_price_cache.find_one.return_value = {
            "_id": MagicMock(), # Add a mock _id
            "ticker": ticker,
            "source": "finnhub", # Source doesn't matter for expiration test, but needs to be present
            "data": old_data,
            "createdAt": expired_time
        }

        # Mock external API for fresh data
        mock_yfinance.return_value = new_data

        # First call: cache should be considered expired, so external API is called
        response = self.app.get(f'/data/{ticker}?source=yfinance')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, new_data)
        mock_yfinance.assert_called_once_with(ticker)
        self.mock_price_cache.insert_one.assert_called_once() # New data inserted

    @patch('app.marketaux_provider.get_news_for_ticker')
    def test_news_cache_expiration(self, mock_marketaux):
        ticker = "AMZN"
        old_news = [{"title": "Old AMZN news"}]
        new_news = [{"title": "New AMZN news"}]

        # Simulate data in cache that is just about to expire
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=NEWS_CACHE_TTL + 1)
        self.mock_news_cache.find_one.return_value = {
            "_id": MagicMock(), # Add a mock _id
            "ticker": ticker,
            "data": old_news,
            "createdAt": expired_time
        }

        # Mock external API for fresh news
        mock_marketaux.return_value = new_news

        # First call: cache should be considered expired, so external API is called
        response = self.app.get(f'/news/{ticker}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, new_news)
        mock_marketaux.assert_called_once_with(ticker)
        self.mock_news_cache.insert_one.assert_called_once() # New data inserted

# Latest Add: New test class for the cache clearing endpoint.
class DataServiceCacheClearTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()

        # We need to patch the global variables `price_cache` and `news_cache`
        # that are used by the `clear_cache` endpoint.
        self.price_cache_patcher = patch('app.price_cache', MagicMock())
        self.news_cache_patcher = patch('app.news_cache', MagicMock())
        self.init_db_patcher = patch('app.init_db', MagicMock())

        self.mock_price_cache = self.price_cache_patcher.start()
        self.mock_news_cache = self.news_cache_patcher.start()
        self.mock_init_db = self.init_db_patcher.start()

    def tearDown(self):
        self.price_cache_patcher.stop()
        self.news_cache_patcher.stop()
        self.init_db_patcher.stop()

    def test_clear_cache_success(self):
        """Tests successful cache clearing."""
        # Act
        response = self.app.post('/cache/clear')

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "All data service caches have been cleared."})
        
        # Verify that the drop method was called on each mock collection
        self.mock_price_cache.drop.assert_called_once()
        self.mock_news_cache.drop.assert_called_once()
        
        # Verify that the database is re-initialized after dropping
        self.mock_init_db.assert_called_once()

    def test_clear_cache_failure(self):
        """Tests failure during cache clearing."""
        # Arrange: Configure one of the mock drop methods to raise an exception
        self.mock_price_cache.drop.side_effect = Exception("Database connection failed")

        # Act
        response = self.app.post('/cache/clear')

        # Assert
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.json)
        self.assertEqual(response.json["error"], "Failed to clear caches.")
        
        # Even though it failed, the drop method was still called
        self.mock_price_cache.drop.assert_called_once()
        
        # In this failure path, the second drop is not called, and init_db is not called
        self.mock_news_cache.drop.assert_not_called()
        self.mock_init_db.assert_not_called()

if __name__ == '__main__':
    unittest.main()