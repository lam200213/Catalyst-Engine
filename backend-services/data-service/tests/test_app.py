import unittest
from unittest.mock import patch, MagicMock, ANY
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

# Test Class for Market Trend Endpoints
@patch('app.init_db')
class TestMarketTrendEndpoints(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        self.market_trends_patcher = patch('app.market_trends', MagicMock())
        self.mock_market_trends = self.market_trends_patcher.start()

    def tearDown(self):
        self.market_trends_patcher.stop()

    def _generate_mock_price_data(self, base_date_str, num_days, final_price=None):
        """
        Helper to generate time-series data for mocking.
        Optionally sets a specific price for the final day.
        """
        base_date = datetime.strptime(base_date_str, '%Y-%m-%d')
        data = []
        for i in range(num_days):
            price = 100 + i
            if i == num_days - 1 and final_price is not None:
                price = final_price
            data.append({
                'formatted_date': (base_date - timedelta(days=num_days - 1 - i)).strftime('%Y-%m-%d'),
                'close': price,
                'high': price + 2, # Mock high price
                'low': price - 2   # Mock low price
            })
        return data


    @patch('app.yfinance_provider.get_stock_data')
    def test_calculate_market_trend_success(self, mock_get_stock_data, mock_init_db):
        """
        Tests the on-demand calculation of market trends, ensuring it correctly
        processes historical data to determine the trend.
        """
        # --- Arrange ---
        calc_date = "2025-08-25"
        # Generate 300 days of data to safely accommodate 200-day SMA and 252-day (52-week) rolling windows.
        mock_history = self._generate_mock_price_data(calc_date, 300)
        
        # The provider returns data for all 3 indices
        mock_get_stock_data.return_value = {
            '^GSPC': mock_history,
            '^DJI': mock_history,
            '^IXIC': mock_history,
        }
        
        # --- Act ---
        response = self.app.post('/market-trend/calculate', json={'dates': [calc_date]})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(len(data['trends']), 1)
        self.assertEqual(data['trends'][0]['date'], calc_date)
        # All indices are above their 50-day SMA in this mock data
        self.assertEqual(data['trends'][0]['trend'], 'Bullish') 
        
        # Verify it was stored in the database via upsert
        self.mock_market_trends.update_one.assert_called_once()
        call_args, _ = self.mock_market_trends.update_one.call_args
        self.assertEqual(call_args[0], {'date': calc_date}) # The query filter
        self.assertIn('trend', call_args[1]['$set']) # The update document
        
    @patch('app.yfinance_provider.get_stock_data')
    def test_calculate_market_trend_bearish_scenario(self, mock_get_stock_data, mock_init_db):
        """
        Tests that the endpoint correctly identifies a Bearish trend when the
        current price is below the 50-day SMA.
        """
        # --- Arrange ---
        calc_date = "2025-08-25"
        # Generate 300 days of data. Historical prices are high, SMA will be high. Final price is 50.
        mock_history = self._generate_mock_price_data(calc_date, 300, final_price=50)

        mock_get_stock_data.return_value = {
            '^GSPC': mock_history,
            '^DJI': mock_history,
            '^IXIC': mock_history,
        }
        
        # --- Act ---
        response = self.app.post('/market-trend/calculate', json={'dates': [calc_date]})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('trends', data)
        self.assertEqual(len(data['trends']), 1)
        self.assertEqual(data['trends'][0]['date'], calc_date)
        # With the final price well below the historical average, the trend should be Bearish.
        self.assertEqual(data['trends'][0]['trend'], 'Bearish')

    @patch('app.yfinance_provider.get_stock_data')
    def test_calculate_market_trend_handles_non_trading_day(self, mock_get_stock_data, mock_init_db):
        """
        Tests that the endpoint gracefully handles a date for which no price data
        is available (e.g., a weekend or holiday).
        """
        # --- Arrange ---
        trading_day = "2025-08-25"
        non_trading_day = "2025-08-24" # Assume this is a Sunday
        
        # Generate sufficient historical data for calculations on the trading day.
        mock_history = self._generate_mock_price_data(trading_day, 300)
        # Explicitly remove the non-trading day from the mock history to ensure it's not found.
        mock_history_filtered = [d for d in mock_history if d['formatted_date'] != non_trading_day]
        
        mock_get_stock_data.return_value = {
            '^GSPC': mock_history_filtered,
            '^DJI': mock_history_filtered,
            '^IXIC': mock_history_filtered,
        }
        
        # --- Act ---
        # Request both a valid and an invalid date
        response = self.app.post('/market-trend/calculate', json={'dates': [trading_day, non_trading_day]})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        
        # One date should succeed
        self.assertEqual(len(data['trends']), 1)
        self.assertEqual(data['trends'][0]['date'], trading_day)
        
        # The non-trading day should be in the failed list
        self.assertEqual(len(data['failed_dates']), 1)
        self.assertIn(non_trading_day, data['failed_dates'])
        
        # Ensure the database was still updated for the successful date
        self.mock_market_trends.update_one.assert_called_once()

    def test_calculate_market_trend_invalid_payload(self, mock_init_db):
        """
        Tests that the endpoint returns a 400 Bad Request for various invalid payloads.
        """
        invalid_payloads = [
            {},                     # Empty payload
            {"dates": "not-a-list"}, # 'dates' is not a list
            {"wrong_key": []}       # Missing 'dates' key
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.app.post('/market-trend/calculate', json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json)

    def test_get_market_trends_with_range(self, mock_init_db):
        """
        Tests retrieval of market trends using a date range via GET /market-trends.
        """
        # Arrange
        mock_trend_data = [
            {"date": "2025-08-25", "trend": "Bullish"},
            {"date": "2025-08-26", "trend": "Neutral"}
        ]
        # Simulate the find query returning a cursor. The endpoint implementation
        # now rebuilds the list, so we must mock the cursor's return value.
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [
            {"date": "2025-08-25", "trend": "Bullish", "details": {}}, # Mock full document
            {"date": "2025-08-26", "trend": "Neutral", "details": {}}
        ]
        self.mock_market_trends.find.return_value = mock_cursor

        # Act
        response = self.app.get('/market-trends?start_date=2025-08-25&end_date=2025-08-26')

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, mock_trend_data)
        # Verify the database was queried with the correct date range filter
        self.mock_market_trends.find.assert_called_once_with(
            {"date": {"$gte": "2025-08-25", "$lte": "2025-08-26"}}, 
            {'_id': 0}
        )

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
        self.app.get(f'/price/{ticker}?source=yfinance')

        # Assert: The provider was called with the day AFTER the last cached date
        expected_start_date = last_cached_date_obj + timedelta(days=1)
        mock_get_stock_data.assert_called_once_with(ticker, start_date=expected_start_date, period=None)
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
        response = self.app.get(f'/price/{ticker}?source=yfinance')

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
        response = self.app.get(f'/price/{ticker}?source=yfinance')

        # Assert
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": f"Could not retrieve price data for {ticker} from yfinance."})
        mock_get_stock_data.assert_called_once_with(ticker, start_date=None, period="1y")

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
        Tests the /price/batch endpoint for successfully fetching data for a mix
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
        response = self.app.post('/price/batch', json=request_payload)

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
        # including the default arguments for a batch miss.
        mock_get_stock_data.assert_called_once_with(['UNCACHED', 'FAILED'], start_date=None, period='1y')
        
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
        response = self.app.post('/price/batch', json=request_payload)

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
                response = self.app.post('/price/batch', json=payload)
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
        response = self.app.post('/price/batch', json=request_payload)

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
    def test_get_core_financials_uses_cache_when_fresh(self, mock_get_core_financials, mock_init_db):
        """Tests that the provider is not called if fresh data exists in the financials cache."""
        ticker = "NVDA"
        # Arrange: Create a mock record as if it were stored in MongoDB
        mock_financial_data = {'marketCap': 3000000000000, 'ipoDate': '1999-01-22'}
        fresh_record = {
            "_id": "mock_financial_id_123",
            "ticker": ticker,
            "data": mock_financial_data,
            "createdAt": datetime.now(timezone.utc) # Fresh timestamp
        }
        self.mock_financials_cache.find_one.return_value = fresh_record

        # Act
        response = self.app.get(f'/financials/core/{ticker}')

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, mock_financial_data)
        # Crucially, assert the external provider was NOT called
        mock_get_core_financials.assert_not_called()
        # Assert that the TTL was refreshed on cache hit
        self.mock_financials_cache.update_one.assert_called_once()

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
        mock_get_batch_core_financials.assert_called_once_with(tickers, ANY)

    @patch('app.yfinance_provider.get_batch_core_financials')
    def test_batch_financials_missing_data_contract_fields(self, mock_get_batch_core_financials, mock_init_db):
        """Test that missing data contract fields are handled with default values."""
        tickers = ["GOOG", "AMZN"]
        self.mock_financials_cache.find_one.return_value = None
        
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
        mock_get_batch_core_financials.assert_called_once_with(tickers + ["FAIL"], ANY)

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