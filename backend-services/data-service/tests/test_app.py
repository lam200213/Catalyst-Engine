import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from datetime import date, datetime, timezone, timedelta
from app import app, price_cache, news_cache, PRICE_CACHE_TTL, NEWS_CACHE_TTL, init_db
from pymongo.errors import OperationFailure

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
        mock_financials_collection = MagicMock()
        
        # Simulate the conflict: the first call to create_index fails
        conflict_error = OperationFailure("Index conflict", code=85)
        mock_price_collection.create_index.side_effect = [
            conflict_error, # First call fails
            None            # Second call succeeds
        ]

        mock_db = MagicMock()
        mock_db.price_cache = mock_price_collection
        mock_db.news_cache = mock_news_collection
        mock_db.financials_cache = mock_financials_collection
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
        mock_financials_collection = MagicMock()
        # Simulate a different, unexpected database error
        other_error = OperationFailure("Some other error", code=12345)
        mock_price_collection.create_index.side_effect = other_error

        mock_db = MagicMock()
        mock_db.price_cache = mock_price_collection
        mock_db.financials_cache = mock_financials_collection
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

    @patch('app.yfinance_provider.get_stock_data')
    def test_batch_endpoint_success(self, mock_get_stock_data, mock_init_db):
        """
        Tests the /data/batch endpoint for successfully fetching data for a mix
        of cached and uncached tickers.
        """
        # --- Arrange ---
        # 1. Mock the data from the external provider for the uncached tickers
        uncached_ticker_data = {"formatted_date": "2025-07-21", "close": 200.0}
        mock_get_stock_data.return_value = {
            "UNCACHED": [uncached_ticker_data],
            "FAILED": None # Simulate a failure for one ticker
        }

        # 2. Mock the data found in the cache
        cached_ticker_data = {"formatted_date": "2025-07-21", "close": 100.0}
        cached_db_records = [
            {
                "ticker": "CACHED",
                "source": "yfinance",
                "data": [cached_ticker_data],
                "createdAt": datetime.now(timezone.utc)
            }
        ]
        # The 'find' method on a cursor returns an iterable
        self.mock_price_cache.find.return_value = cached_db_records

        # 3. Define the payload for the batch request
        request_payload = {
            'tickers': ['CACHED', 'UNCACHED', 'FAILED'],
            'source': 'yfinance'
        }

        # --- Act ---
        response = self.app.post('/data/batch', json=request_payload)

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        
        # Verify the structure and content of the response
        self.assertIn('success', response_data)
        self.assertIn('failed', response_data)
        self.assertEqual(response_data['failed'], ['FAILED'])
        
        # Check that the success list contains the correct data points
        self.assertIn('CACHED', response_data['success'])
        self.assertEqual(response_data['success']['CACHED'][0], cached_ticker_data)
        self.assertIn('UNCACHED', response_data['success'])
        self.assertEqual(response_data['success']['UNCACHED'][0], uncached_ticker_data)
        self.assertEqual(len(response_data['success']), 2)

        # Verify cache was queried for all tickers
        self.mock_price_cache.find.assert_called_once_with({
            'ticker': {'$in': ['CACHED', 'UNCACHED', 'FAILED']},
            'source': 'yfinance'
        })

        # Verify the data provider was only called for tickers NOT in the cache
        mock_get_stock_data.assert_called_once_with(['UNCACHED', 'FAILED'])
        
        # Verify that the newly fetched data was inserted into the cache
        self.mock_price_cache.insert_many.assert_called_once()

    def test_batch_endpoint_handles_empty_ticker_list(self, mock_init_db):
        """
        Ensures the system handles an empty ticker list gracefully and returns a
        valid, empty response.
        """
        # --- Arrange ---
        request_payload = {'tickers': [], 'source': 'yfinance'}

        # --- Act ---
        response = self.app.post('/data/batch', json=request_payload)

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(response_data['success'], [])
        self.assertEqual(response_data['failed'], [])
        
        # Ensure no database or external calls were made
        self.mock_price_cache.find.assert_not_called()

    def test_batch_endpoint_handles_invalid_input(self, mock_init_db):
        """
        Confirms that malformed requests are rejected with a 400 Bad Request.
        """
        # --- Arrange ---
        # Test case 1: Missing 'tickers' key
        payload1 = {'source': 'yfinance'}
        # Test case 2: 'tickers' is not a list
        payload2 = {'tickers': 'AAPL', 'source': 'yfinance'}
        # Test case 3: Empty payload
        payload3 = {}

        # --- Act & Assert ---
        for payload in [payload1, payload2, payload3]:
            with self.subTest(payload=payload):
                response = self.app.post('/data/batch', json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json)
        
        # Ensure no database or external calls were made
        self.mock_price_cache.find.assert_not_called()

    @patch('app.yfinance_provider.get_stock_data')
    def test_batch_endpoint_all_tickers_cached(self, mock_get_stock_data, mock_init_db):
        """
        Verifies that the external data provider is not called if all
        requested data is already in the cache.
        """
        # --- Arrange ---
        cached_records = [
            {"ticker": "AAPL", "source": "yfinance", "data": [{"close": 150}]},
            {"ticker": "MSFT", "source": "yfinance", "data": [{"close": 300}]}
        ]
        self.mock_price_cache.find.return_value = cached_records
        request_payload = {'tickers': ['AAPL', 'MSFT'], 'source': 'yfinance'}

        # --- Act ---
        response = self.app.post('/data/batch', json=request_payload)

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(len(response_data['success']), 2)
        self.assertEqual(response_data['failed'], [])
        
        # Crucially, the external provider should not have been called
        mock_get_stock_data.assert_not_called()
        
        # Verify the cache was queried
        self.mock_price_cache.find.assert_called_once_with({
            'ticker': {'$in': ['AAPL', 'MSFT']},
            'source': 'yfinance'
        })

# Tests for the /financials/core endpoint
@patch('app.init_db')
class TestFinancialsEndpoint(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        self.financials_cache_patcher = patch('app.financials_cache', MagicMock())
        self.mock_financials_cache = self.financials_cache_patcher.start()

    def tearDown(self):
        self.financials_cache_patcher.stop()

    @patch('app.yfinance_provider.get_core_financials')
    def test_get_core_financials_endpoint(self, mock_get_core_financials, mock_init_db):
        """Test the happy path for the /financials/core/:ticker endpoint."""
        self.mock_financials_cache.find_one.return_value = None
        mock_get_core_financials.return_value = {
            'marketCap': 2500000000,
            'sharesOutstanding': 100000000,
            'floatShares': 80000000,
            'ipoDate': '2020-01-01',
            'quarterly_earnings': [{'date': '3Q2024', 'revenue': 5000, 'earnings': 1000}],
            'quarterly_financials': [{'date': '3Q2024', 'eps': 1.25}]
        }
        response = self.app.get('/financials/core/AAPL')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['marketCap'], 2500000000)

    @patch('app.yfinance_provider.get_core_financials')
    def test_get_core_financials_for_non_existent_ticker(self, mock_get_core_financials, mock_init_db):
        """Test the endpoint returns 404 for a ticker with no data."""
        self.mock_financials_cache.find_one.return_value = None
        mock_get_core_financials.return_value = None
        response = self.app.get('/financials/core/NONEXISTENTTICKER')
        self.assertEqual(response.status_code, 404)

    @patch('app.yfinance_provider.get_core_financials')
    def test_get_core_financials_with_incomplete_provider_data(self, mock_get_core_financials, mock_init_db):
        """Test graceful degradation when provider is missing a key."""
        self.mock_financials_cache.find_one.return_value = None
        mock_get_core_financials.return_value = {'marketCap': 2500000000} # Missing ipoDate
        response = self.app.get('/financials/core/AAPL')
        self.assertEqual(response.status_code, 200)
        self.assertIn('marketCap', response.json)
        self.assertIsNone(response.json.get('ipoDate'))

    def test_get_core_financials_handles_path_traversal_attack(self, mock_init_db):
        """Test endpoint rejects malicious input."""
        response = self.app.get('/financials/core/../../etc/passwd')
        self.assertEqual(response.status_code, 400)

if __name__ == '__main__':
    unittest.main()

@patch('app.init_db')
class TestIndustryPeersEndpoint(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        self.industry_cache_patcher = patch('app.industry_cache', MagicMock())
        self.mock_industry_cache = self.industry_cache_patcher.start()

    def tearDown(self):
        self.industry_cache_patcher.stop()

    @patch('app.finnhub_provider.get_company_peers_and_industry')
    def test_get_industry_peers_cache_hit(self, mock_get_industry_peers, mock_init_db):
        """Test the /industry/peers/:ticker endpoint with a cache hit."""
        ticker = "AAPL"
        cached_data = {
            "_id": "mock_id_789", # Add a mock _id
            "ticker": ticker,
            "data": {"industry": "Technology", "peers": ["MSFT", "GOOGL"]},
            "createdAt": datetime.now(timezone.utc)
        }
        self.mock_industry_cache.find_one.return_value = cached_data

        response = self.app.get(f'/industry/peers/{ticker}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, cached_data['data'])
        mock_get_industry_peers.assert_not_called()
        self.mock_industry_cache.update_one.assert_called_once()

    @patch('app.finnhub_provider.get_company_peers_and_industry')
    def test_get_industry_peers_cache_miss(self, mock_get_industry_peers, mock_init_db):
        """Test the /industry/peers/:ticker endpoint with a cache miss."""
        ticker = "AAPL"
        self.mock_industry_cache.find_one.return_value = None
        mock_get_industry_peers.return_value = {"industry": "Technology", "peers": ["MSFT", "GOOGL"]}

        response = self.app.get(f'/industry/peers/{ticker}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"industry": "Technology", "peers": ["MSFT", "GOOGL"]})
        mock_get_industry_peers.assert_called_once_with(ticker)
        self.mock_industry_cache.insert_one.assert_called_once()

    @patch('app.finnhub_provider.get_company_peers_and_industry')
    def test_get_industry_peers_data_not_found(self, mock_get_industry_peers, mock_init_db):
        """Test the /industry/peers/:ticker endpoint when provider returns no data."""
        ticker = "NONEXISTENT"
        self.mock_industry_cache.find_one.return_value = None
        mock_get_industry_peers.return_value = None

        response = self.app.get(f'/industry/peers/{ticker}')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Data not found for ticker"})
        mock_get_industry_peers.assert_called_once_with(ticker)
        self.mock_industry_cache.insert_one.assert_not_called()

    def test_get_industry_peers_invalid_ticker_format(self, mock_init_db):
        """Test the /industry/peers/:ticker endpoint rejects invalid ticker format."""
        response = self.app.get('/industry/peers/../../etc/passwd')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json, {"error": "Invalid ticker format"})

@patch('app.init_db')
class TestBatchFinancialsEndpoint(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        # Patch financials_cache even if not directly used by this endpoint, for consistency
        self.financials_cache_patcher = patch('app.financials_cache', MagicMock())
        self.mock_financials_cache = self.financials_cache_patcher.start()

    def tearDown(self):
        self.financials_cache_patcher.stop()

    @patch('app.yfinance_provider.get_batch_core_financials')
    def test_batch_financials_success(self, mock_get_batch_core_financials, mock_init_db):
        """Test the POST /financials/core/batch endpoint for successful data retrieval and contract enforcement."""
        tickers = ["AAPL", "MSFT"]
        mock_get_batch_core_financials.return_value = {
            "AAPL": {
                "totalRevenue": 383285000000,
                "netIncome": 96995000000,
                "marketCap": 3000000000000,
                "otherField": "value1"
            },
            "MSFT": {
                "totalRevenue": 211915000000,
                "netIncome": 72361000000,
                "marketCap": 2500000000000,
                "anotherField": "value2"
            }
        }
        
        response = self.app.post('/financials/core/batch', json={'tickers': tickers})
        self.assertEqual(response.status_code, 200)
        data = response.json['success']
        
        self.assertIn("AAPL", data)
        self.assertEqual(data["AAPL"]["totalRevenue"], 383285000000)
        self.assertEqual(data["AAPL"]["netIncome"], 96995000000)
        self.assertEqual(data["AAPL"]["marketCap"], 3000000000000)
        self.assertEqual(data["AAPL"]["otherField"], "value1")

        self.assertIn("MSFT", data)
        self.assertEqual(data["MSFT"]["totalRevenue"], 211915000000)
        self.assertEqual(data["MSFT"]["netIncome"], 72361000000)
        self.assertEqual(data["MSFT"]["marketCap"], 2500000000000)
        self.assertEqual(data["MSFT"]["anotherField"], "value2")
        
        self.assertEqual(response.json['failed'], [])
        mock_get_batch_core_financials.assert_called_once_with(tickers)

    @patch('app.yfinance_provider.get_batch_core_financials')
    def test_batch_financials_missing_data_contract_fields(self, mock_get_batch_core_financials, mock_init_db):
        """Test that missing data contract fields are handled with default values."""
        tickers = ["GOOG", "AMZN"]
        mock_get_batch_core_financials.return_value = {
            "GOOG": {
                "totalRevenue": 100000000000,
                "otherField": "value3"
            },
            "AMZN": {
                "netIncome": 5000000000,
                "marketCap": "not_a_number", # Invalid type
                "anotherField": "value4"
            },
            "FAIL": None # Simulate a failed ticker
        }
        
        response = self.app.post('/financials/core/batch', json={'tickers': tickers + ["FAIL"]})
        self.assertEqual(response.status_code, 200)
        data = response.json['success']
        failed = response.json['failed']

        self.assertIn("GOOG", data)
        self.assertEqual(data["GOOG"]["totalRevenue"], 100000000000)
        self.assertEqual(data["GOOG"]["netIncome"], 0) # Defaulted
        self.assertEqual(data["GOOG"]["marketCap"], 0) # Defaulted
        self.assertEqual(data["GOOG"]["otherField"], "value3")

        self.assertIn("AMZN", data)
        self.assertEqual(data["AMZN"]["totalRevenue"], 0) # Defaulted
        self.assertEqual(data["AMZN"]["netIncome"], 5000000000)
        self.assertEqual(data["AMZN"]["marketCap"], 0) # Defaulted due to invalid type
        self.assertEqual(data["AMZN"]["anotherField"], "value4")
        
        self.assertIn("FAIL", failed)
        self.assertEqual(len(failed), 1)
        mock_get_batch_core_financials.assert_called_once_with(tickers + ["FAIL"])

    def test_batch_financials_empty_ticker_list(self, mock_init_db):
        """Test handling of an empty ticker list."""
        response = self.app.post('/financials/core/batch', json={'tickers': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"success": {}, "failed": []})

    def test_batch_financials_invalid_payload(self, mock_init_db):
        """Test handling of invalid request payloads."""
        # Missing 'tickers'
        response = self.app.post('/financials/core/batch', json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)

        # 'tickers' not a list
        response = self.app.post('/financials/core/batch', json={'tickers': "AAPL"})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)