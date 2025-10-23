# backend-services/data-service/tests/test_app.py
import unittest
from unittest.mock import patch, MagicMock, ANY
from datetime import date, timedelta
from app import app
import pandas as pd
from pydantic import ValidationError, TypeAdapter
from typing import List
# Make sure the shared models are importable for testing
from shared.contracts import CoreFinancials, PriceDataItem
from helper_functions import cache_covers_request

class BaseDataServiceTest(unittest.TestCase):
    """
    Base test class that sets up a test client and mocks external dependencies.
    - Mocks the Flask-Caching 'cache' object for controlled cache testing.
    - Mocks the persistent 'db' client for market trend storage tests.
    """
    def setUp(self):
        app.config['TESTING'] = True
        app.config['CACHE_KEY_PREFIX'] = 'flask_cache_'
        self.client = app.test_client()

        # Patch the persistent database client (for market_trends)
        self.db_patcher = patch('app.db')
        self.mock_db = self.db_patcher.start()
        self.mock_market_trends_collection = MagicMock()
        self.mock_db.market_trends = self.mock_market_trends_collection

        # Patch the cache client used for all caching operations
        self.cache_patcher = patch('app.cache')
        self.mock_cache = self.cache_patcher.start()
        # The app uses `cache.cache._write_client`, so we must mock that specific path.
        self.mock_redis_client = self.mock_cache.cache._write_client = MagicMock()


    def tearDown(self):
        self.db_patcher.stop()
        self.cache_patcher.stop()
    # Helper method to create valid mock price data  
    def _create_valid_price_data(self, overrides=None, day_offset=0):
        """Creates a single, valid PriceDataItem dictionary."""
        target_date = (date.today() - timedelta(days=day_offset)).strftime('%Y-%m-%d')
        default_data = {
            "formatted_date": target_date,
            "open": 150.0,
            "high": 152.0,
            "low": 149.5,
            "close": 151.75,
            "volume": 1000000,
            "adjclose": 151.75
        }
        if overrides:
            # Ensure overrides is a dictionary before updating
            if isinstance(overrides, dict):
                default_data.update(overrides)
        return default_data

    # Helper method to create valid mock financials data
    def _create_valid_financials_data(self, ticker, overrides=None):
        """Helper to create a dictionary with valid core financials data."""
        data = {
            "ticker": ticker,
            "marketCap": 2500000000000.0,
            "sharesOutstanding": 5000000000.0,
            "floatShares": 0,
            "ipoDate": None,
            "annual_earnings": [{
                "Earnings": 4.0, "Revenue": 50000000000.0, "Net Income": 20000000000.0
            }],
            "quarterly_earnings": [{
                "Earnings": 1.0, "Revenue": 12000000000.0, "Net Income": 5000000000.0
            }],
            "quarterly_financials": [{
                "Net Income": 5000000000.0, "Total Revenue": 12000000000.0
            }]
        }
        if overrides:
            data.update(overrides)
        return data
    
    def _create_mock_index_data(self, ticker="^GSPC"):
            """Creates a mock data dictionary for a market index."""
            return {
                "ticker": ticker,
                "current_price": 4500.0,
                "sma_50": 4400.0,
                "sma_200": 4200.0,
                "high_52_week": 4600.0,
                "low_52_week": 3800.0,
            }

# =====================================================================
# ==                      PRICE DATA ENDPOINTS                       ==
# =====================================================================
class TestPriceEndpoints(BaseDataServiceTest):
    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_output_conforms_to_contract(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests that the endpoint's JSON output strictly conforms to the PriceDataItem contract."""
        # --- Arrange ---
        ticker = "CONTRACT"
        self.mock_cache.get.return_value = None
        # This data perfectly matches the PriceDataItem contract
        provider_data = [self._create_valid_price_data()]
        mock_get_stock_data.return_value = provider_data
        PriceDataListValidator = TypeAdapter(List[PriceDataItem])

        # --- Act ---
        response = self.client.get(f'/price/{ticker}')
        response_data = response.json

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        try:
            # Validate that the actual JSON response conforms to the Pydantic model.
            # This is the core of the producer contract test.
            PriceDataListValidator.validate_python(response_data)
        except ValidationError as e:
            self.fail(f"The /price/<ticker> endpoint produced a JSON response that violates the PriceDataItem contract: {e}")

    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_handles_invalid_provider_data(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests graceful failure when provider data violates the contract."""
        # --- Arrange ---
        ticker = "INVALID"
        self.mock_cache.get.return_value = None
        # This data violates the contract ('volume' is a string, not an int)
        provider_data = [{
            "formatted_date": "2025-09-24", "open": 150.0, "high": 152.0,
            "low": 149.5, "close": 151.75, "volume": "a-million"
        }]
        mock_get_stock_data.return_value = provider_data

        # --- Act ---
        response = self.client.get(f'/price/{ticker}')

        # --- Assert ---
        # The service should catch the ValidationError in the helper and return an error status,
        # not crash or return malformed data.
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.json)
        self.assertIn("Could not retrieve valid price data", response.json['error'])

    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_provider_failure(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests a graceful 404 response when the provider fails."""
        # --- Arrange ---
        ticker = "FAIL"
        self.mock_cache.get.return_value = None
        mock_get_stock_data.return_value = None # Simulate provider returning no data

        # --- Act ---
        response = self.client.get(f'/price/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json)
        self.assertIn(f"Could not retrieve price data for {ticker}", response.json['error'])
        # Add ANY for the executor argument
        mock_get_stock_data.assert_called_once_with(ticker, ANY, start_date=None, period="1y")
        self.mock_cache.set.assert_not_called()

    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_handles_empty_cache_gracefully(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests full fetch if cached data is an empty list."""
        # --- Arrange ---
        ticker = "GOOG"
        # Simulate a scenario where a previous fetch failed and cached an empty list
        self.mock_cache.get.return_value = []
        provider_data = [self._create_valid_price_data()]
        mock_get_stock_data.return_value = provider_data
        
        # --- Act ---
        response = self.client.get(f'/price/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, provider_data)
        # It should ignore the empty cache and perform a full fetch
        mock_get_stock_data.assert_called_once_with(ticker, ANY, start_date=None, period="1y")
        self.mock_cache.set.assert_called_once_with(f"price_yfinance_{ticker}", provider_data, timeout=ANY)

    def test_get_price_handles_path_traversal(self):
        """GET /price/<ticker>: Tests rejection of malicious path traversal input."""
        response = self.client.get('/price/../../etc/passwd')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)
        self.assertIn('Invalid ticker format', response.json['error'])

        @patch('app.yf_price_provider.get_stock_data')
        def test_get_price_success_full_cache_miss(self, mock_get_stock_data):
            """GET /price/<ticker>: Tests a full fetch when no cache exists."""
            # --- Arrange ---
            ticker = "AAPL"
            self.mock_cache.get.return_value = None
            provider_data = [{"formatted_date": "2025-09-20", "close": 150.0}]
            mock_get_stock_data.return_value = provider_data

            # --- Act ---
            response = self.client.get(f'/price/{ticker}')

            # --- Assert ---
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, provider_data)
            self.mock_cache.get.assert_called_once_with(f"price_yfinance_{ticker}")
            mock_get_stock_data.assert_called_once_with(ticker, ANY, start_date=None, period="1y")
            self.mock_cache.set.assert_called_once_with(f"price_yfinance_{ticker}", provider_data, timeout=ANY)

    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_success_incremental_fetch(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests incremental fetch when recent data is cached."""
        # --- Arrange ---
        ticker = "MSFT"
        last_cached_date_str = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        last_cached_date_obj = date.fromisoformat(last_cached_date_str)
        
        cached_data = [self._create_valid_price_data({"formatted_date": last_cached_date_str})]
        self.mock_cache.get.return_value = cached_data

        new_data_from_provider = [self._create_valid_price_data({"formatted_date": (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')})]
        mock_get_stock_data.return_value = new_data_from_provider

        # --- Act ---
        response = self.client.get(f'/price/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        expected_combined_data = cached_data + new_data_from_provider
        self.assertEqual(response.json, expected_combined_data)
        
        expected_start_date = last_cached_date_obj + timedelta(days=1)
        mock_get_stock_data.assert_called_once_with(ticker, ANY, start_date=expected_start_date, period=None)
        
        self.mock_cache.set.assert_called_once_with(f"price_yfinance_{ticker}", expected_combined_data, timeout=ANY)

    @patch('app.yf_price_provider.get_stock_data')
    def test_get_price_success_current_cache_hit(self, mock_get_stock_data):
        """GET /price/<ticker>: Tests a full cache hit when data is current."""
        # --- Arrange ---
        ticker = "NVDA"
        current_date_str = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        cached_data = [self._create_valid_price_data({"formatted_date": current_date_str})]
        self.mock_cache.get.return_value = cached_data

        # --- Act ---
        response = self.client.get(f'/price/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, cached_data)
        mock_get_stock_data.assert_not_called()
        self.mock_cache.set.assert_not_called()

    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_success_with_cache_mix(self, mock_get_stock_data):
        """POST /price/batch: Tests a mix of cached and uncached tickers."""
        # --- Arrange ---
        valid_cached_data = [self._create_valid_price_data({"close": 100.0}, day_offset=1)]
        valid_provider_data = [self._create_valid_price_data({"close": 200.0})]
        
        def cache_side_effect(key):
            if key == 'price_yfinance_CACHED':
                return valid_cached_data
            return None
        self.mock_cache.get.side_effect = cache_side_effect
        
        # mock_get_stock_data must handle single and batch calls.
        # It now returns a dictionary mapping ticker to data.
        def provider_side_effect(tickers, executor, start_date=None, period=None):
            if tickers == ['UNCACHED', 'FAILED']:
                 return {"UNCACHED": valid_provider_data, "FAILED": None}
            return {} # Default empty response
        mock_get_stock_data.side_effect = provider_side_effect

        # --- Act ---
        response = self.client.post('/price/batch', json={'tickers': ['CACHED', 'UNCACHED', 'FAILED'], 'source': 'yfinance'})

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(data['success']['CACHED'], valid_cached_data)
        self.assertEqual(data['success']['UNCACHED'], valid_provider_data)
        self.assertIn('FAILED', data['failed'])
        mock_get_stock_data.assert_called_once_with(['UNCACHED', 'FAILED'], ANY, start_date=None, period='1y')
        self.mock_cache.set.assert_called_once_with('price_yfinance_UNCACHED', valid_provider_data, timeout=ANY)
    
    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_all_tickers_cached(self, mock_get_stock_data):
        """POST /price/batch: Tests when all tickers are found in the cache."""
        # --- Arrange ---
        self.mock_cache.get.return_value = [self._create_valid_price_data()]

        # --- Act ---
        response = self.client.post('/price/batch', json={'tickers': ['AAPL', 'MSFT'], 'source': 'yfinance'})

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('AAPL', data['success'])
        self.assertIn('MSFT', data['success'])
        self.assertEqual(len(data['failed']), 0)
        mock_get_stock_data.assert_not_called()

    
    def test_batch_price_handles_empty_ticker_list(self):
        """POST /price/batch: Tests behavior with an empty ticker list."""
        response = self.client.post('/price/batch', json={'tickers': [], 'source': 'yfinance'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"success": {}, "failed": []})

    def test_batch_price_invalid_payload(self):
        """POST /price/batch: Tests rejection of invalid request bodies."""
        for payload in [{}, {'tickers': 'not-a-list'}, {'source': 'yfinance'}]:
            with self.subTest(payload=payload):
                response = self.client.post('/price/batch', json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json)

# =====================================================================
# ==                BATCH PRICE LOGIC & EDGE CASES                   ==
# =====================================================================
class TestBatchPriceLogic(BaseDataServiceTest):
    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_explicit_start_date_precedence(self, mock_get_stock_data):
        """POST /price/batch: Tests that `start_date` overrides any existing cache."""
        # --- Arrange ---
        ticker = "AAPL"
        # Simulate a rich cache with 20 days of data
        cached_data = [self._create_valid_price_data(day_offset=i) for i in range(20)]
        self.mock_cache.get.return_value = cached_data

        # The provider will return only 5 days of data
        start_date_str = (date.today() - timedelta(days=4)).strftime('%Y-%m-%d')
        start_date_obj = date.fromisoformat(start_date_str)
        provider_data = {"AAPL": [self._create_valid_price_data(day_offset=i) for i in range(5)]}
        mock_get_stock_data.return_value = provider_data

        # --- Act ---
        # Request data with an explicit start_date, which should ignore the cache.
        response = self.client.post('/price/batch', json={
            'tickers': [ticker],
            'source': 'yfinance',
            'start_date': start_date_str
        })

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        # The provider should be called with the explicit start date
        mock_get_stock_data.assert_called_once_with([ticker], ANY, start_date=start_date_obj, period=None)
        # The response should contain exactly the 5 days from the provider, not the 20 from cache
        self.assertEqual(len(response.json['success'][ticker]), 5)
        # The cache should be updated with the newly fetched data
        self.mock_cache.set.assert_called_once_with(f"price_yfinance_{ticker}", provider_data[ticker], timeout=ANY)

    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_incremental_merge_on_stale_cache(self, mock_get_stock_data):
        """POST /price/batch: Tests correct incremental fetch and merge for a stale cache."""
        # --- Arrange ---
        ticker = "MSFT"
        # Simulate a cache that is stale by 5 days
        cached_data = [self._create_valid_price_data(day_offset=i + 5) for i in range(10)]
        self.mock_cache.get.return_value = cached_data
        last_cached_date = date.fromisoformat(sorted(cached_data, key=lambda x: x['formatted_date'])[-1]['formatted_date'])

        # Provider will return the 5 days of "new" data
        new_data = [self._create_valid_price_data(day_offset=i) for i in range(5)]
        mock_get_stock_data.return_value = new_data
        
        # --- Act ---
        # Make a request with no period or start_date, relying on incremental logic
        response = self.client.post('/price/batch', json={'tickers': [ticker], 'source': 'yfinance'})

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        # Provider should be called starting from the day after the last cached date
        expected_start_date = last_cached_date + timedelta(days=1)
        mock_get_stock_data.assert_called_once_with(ticker, ANY, start_date=expected_start_date, period=None)
        
        # Response should contain the merged and de-duplicated data
        response_data = response.json['success'][ticker]
        self.assertEqual(len(response_data), 15) # 10 from cache + 5 new
        
        # Verify no duplicate dates
        response_dates = [item['formatted_date'] for item in response_data]
        self.assertEqual(len(response_dates), len(set(response_dates)))
        
        # Verify cache is updated with the full, merged list
        self.mock_cache.set.assert_called_once_with(f"price_yfinance_{ticker}", response_data, timeout=ANY)

    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_handles_invalid_source(self, mock_get_stock_data):
        """POST /price/batch: Tests that an unknown 'source' is rejected and makes no network calls."""
        # --- Act ---
        response = self.client.post('/price/batch', json={
            'tickers': ['AAPL'],
            'source': 'invalid_source' # This source is not 'yfinance' or 'finnhub'
        })
        
        # --- Assert ---
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)
        self.assertIn("Invalid data source", response.json['error'])
        # Crucially, assert that no attempt was made to fetch data from any provider
        mock_get_stock_data.assert_not_called()

# =====================================================================
# ==               PRICE CACHE COVERAGE & STAMPEDE                   ==
# =====================================================================
class TestPriceCacheCoverage(BaseDataServiceTest):

    @patch('app.yf_price_provider.get_stock_data')
    def test_cache_period_honor_and_stampede_guard(self, mock_get_stock_data):
        """
        Tests period-aware cache coverage and request deduplication.
        Case A: Requesting longer period triggers refetch.
        Case B: Requesting shorter period uses cache.
        Stampede: Duplicate tickers in one request are fetched once.
        """
        # --- Arrange ---
        # 1. Setup mock data for different periods
        one_year_data = [self._create_valid_price_data(overrides={"close": 100 + i}, day_offset=365 - i) for i in range(365)]
        two_year_data = [self._create_valid_price_data(overrides={"close": 200 + i}, day_offset=730 - i) for i in range(730)]

        # Mock the provider to return 2-year data when called
        mock_get_stock_data.return_value = {"GSPC": two_year_data}

        # --- Act & Assert: Case A (Cache miss on longer period) ---
        # Simulate cache having 1-year data
        self.mock_cache.get.return_value = one_year_data
        
        # Request 2 years of data. This should be a cache miss due to insufficient coverage.
        resp1 = self.client.post('/price/batch', json={'tickers': ['GSPC'], 'source': 'yfinance', 'period': '2y'})
        
        self.assertEqual(resp1.status_code, 200)
        # Provider should have been called once to fetch the new 2-year data
        mock_get_stock_data.assert_called_once_with(['GSPC'], ANY, start_date=None, period='2y')
        # Cache should have been updated with the 2-year data
        self.mock_cache.set.assert_called_once_with('price_yfinance_GSPC', two_year_data, timeout=ANY)

        # --- Act & Assert: Subsequent calls are cache hits ---
        # Reset mocks for the next stage
        mock_get_stock_data.reset_mock()
        self.mock_cache.set.reset_mock()
        
        # Now, simulate the cache having the full 2-year data
        self.mock_cache.get.return_value = two_year_data
        
        # Requesting 2 years again should now be a cache hit
        resp2 = self.client.post('/price/batch', json={'tickers': ['GSPC'], 'source': 'yfinance', 'period': '2y'})
        self.assertEqual(resp2.status_code, 200)
        mock_get_stock_data.assert_not_called()
        self.mock_cache.set.assert_not_called()

        # --- Act & Assert: Case B (Cache hit on shorter period) ---
        # Requesting 1 year when 2 years are cached should also be a cache hit
        resp3 = self.client.post('/price/batch', json={'tickers': ['GSPC'], 'source': 'yfinance', 'period': '1y'})
        self.assertEqual(resp3.status_code, 200)
        mock_get_stock_data.assert_not_called()
        self.mock_cache.set.assert_not_called()

        # --- Act & Assert: Stampede Guard (Deduplication) ---
        self.mock_cache.get.return_value = None # Ensure a cache miss for this part
        mock_get_stock_data.reset_mock()
        mock_get_stock_data.return_value = {"AAPL": one_year_data, "MSFT": one_year_data}
        
        # Send a request with duplicate tickers
        self.client.post('/price/batch', json={'tickers': ['AAPL', 'MSFT', 'AAPL'], 'source': 'yfinance', 'period': '1y'})
        
        # The provider should only be called with the UNIQUE set of tickers
        mock_get_stock_data.assert_called_once()
        call_args = mock_get_stock_data.call_args[0][0]
        self.assertCountEqual(call_args, ['AAPL', 'MSFT'])


class TestCacheCoversRequestHelper(BaseDataServiceTest):
    
    @patch('pandas_market_calendars.get_calendar')
    def test_trading_day_aware_coverage(self, mock_get_calendar):
        """Unit test for the cache_covers_request helper with trading day awareness."""
        # --- Arrange ---
        nyse_today = pd.Timestamp.now(tz='America/New_York').normalize()
        # Create a mock schedule of the last 300 trading days
        mock_schedule = pd.DataFrame(index=pd.bdate_range(end=nyse_today, periods=300))
        mock_calendar = MagicMock()
        mock_calendar.schedule.return_value = mock_schedule
        mock_get_calendar.return_value = mock_calendar

        first_trading_day_1y_ago = mock_schedule.index[-252]
        
        # --- Act & Assert: Edge Cases ---
        # Case 1: Cache starts exactly on the required first trading day -> Should PASS
        cached_data_perfect = [{'formatted_date': first_trading_day_1y_ago.strftime('%Y-%m-%d')}]
        self.assertTrue(cache_covers_request(cached_data_perfect, "1y", None))

        # Case 2: Cache starts one BUSINESS day after the required first trading day -> Should FAIL
        next_trading_day = (first_trading_day_1y_ago + pd.tseries.offsets.BDay(1)).strftime('%Y-%m-%d')
        cached_data_short = [{'formatted_date': next_trading_day}]
        self.assertFalse(cache_covers_request(cached_data_short, "1y", None))

        # Case 3a: Cache has just under the required bar count -> Should FAIL
        cached_data_bars_fail = [{'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')} for d in range(251)]
        self.assertFalse(cache_covers_request(cached_data_bars_fail, "1y", None), "Should fail with 251 bars for a 1y period.")

        # Case 3b: Cache has exactly the required bar count -> Should PASS by bar count
        cached_data_bars_pass = [{'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')} for d in range(252)]
        self.assertTrue(cache_covers_request(cached_data_bars_pass, "1y", None), "Should pass with 252 bars for a 1y period.")

        # Case 3c: Over-threshold row-count should PASS (e.g., 253 bars for 1y)
        cached_data_over = [
            {'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')}
            for d in range(253)
        ]
        self.assertTrue(cache_covers_request(cached_data_over, "1y", None))

        # Case 3d: Order invariance with exactly threshold bars (252) should PASS
        cached_data_exact = [
            {'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')}
            for d in range(252)
        ]
        # Shuffle to ensure order does not affect coverage
        from random import shuffle
        shuffle(cached_data_exact)
        self.assertTrue(cache_covers_request(cached_data_exact, "1y", None))

        # Case 3e: Duplicates: 251 unique + 1 duplicate.
        # Current implementation counts total rows (including duplicates), so this will PASS.
        # If the intended behavior is to ignore duplicates, change the expectation to False
        # and update cache_covers_request to de-duplicate by date before counting.
        unique_251 = [
            {'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')}
            for d in range(1, 252)
        ]  # 251 unique dates (skip 0 so we can duplicate it below)
        duplicate_one = {'formatted_date': (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')}
        cached_data_dupe = unique_251 + [duplicate_one]  # total len = 252, but with one duplicate date
        self.assertTrue(cache_covers_request(cached_data_dupe, "1y", None))

        # Case 3f: Malformed entry resilience: one malformed among otherwise valid bars.
        # With current logic (invalid entries ignored; row-count with small grace), this should PASS.
        cached_data_malformed = [
            {'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')}
            for d in range(253)
        ]
        cached_data_malformed[125] = {'formatted_date': None}  # inject one malformed row
        self.assertTrue(cache_covers_request(cached_data_malformed, "1y", None))

        # Case 3g: req_start precedence: even with many bars, start-only bound should be enforced.
        # Set req_start to one day BEFORE the cache's first date → Should FAIL.
        many_bars = [
            {'formatted_date': (date.today() - timedelta(days=d)).strftime('%Y-%m-%d')}
            for d in range(300)
        ]
        first_cache_date = date.fromisoformat(many_bars[-1]['formatted_date'])
        req_start_prior = (first_cache_date - timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertFalse(cache_covers_request(many_bars, "1y", req_start_prior))

# =====================================================================
# ==                   CORE FINANCIALS ENDPOINTS                     ==
# =====================================================================
class TestFinancialsEndpoints(BaseDataServiceTest):
    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_output_conforms_to_contract(self, mock_get_core_financials):
        """GET /financials/core/<ticker>: Tests that the JSON output strictly conforms to the CoreFinancials contract."""
        # --- Arrange ---
        ticker = "GOODDATA"
        self.mock_cache.get.return_value = None
        # This data perfectly matches the CoreFinancials contract
        provider_data = self._create_valid_financials_data(ticker)
        mock_get_core_financials.return_value = provider_data
        
        # --- Act ---
        response = self.client.get(f'/financials/core/{ticker}')
        response_data = response.json
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        try:
            # Validate that the actual JSON response conforms to the Pydantic model.
            CoreFinancials.model_validate(response_data)
        except ValidationError as e:
            self.fail(f"The /financials/core/<ticker> endpoint produced a JSON response that violates the CoreFinancials contract: {e}")

    @patch('app.yf_financials_provider.get_batch_core_financials')
    def test_batch_financials_contract_enforcement(self, mock_get_batch_financials):
        """POST /financials/core/batch: Tests contract cleaning and rejection of invalid data."""
        # --- Arrange ---
        tickers = ["GOOD", "CLEAN_ME", "INVALID"]
        self.mock_cache.get.return_value = None
        
        mock_get_batch_financials.return_value = {
            # Valid data
            "GOOD": self._create_valid_financials_data("GOOD"),
            # Data with an optional field set to None, which is valid.
            "CLEAN_ME": self._create_valid_financials_data("CLEAN_ME", {"marketCap": None}),
            # Data missing a required key ('annual_earnings'), which should cause validation to fail.
            "INVALID": {"ticker": "INVALID", "quarterly_earnings": []}
        }
        
        # --- Act ---
        response = self.client.post('/financials/core/batch', json={'tickers': tickers})
        data = response.json
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        
        # 1. Test the successfully processed tickers
        self.assertIn("GOOD", data['success'])
        self.assertIn("CLEAN_ME", data['success'])
        
        # 2. Test that the cleaning logic worked as expected for CLEAN_ME
        self.assertEqual(data['success']['CLEAN_ME']['marketCap'], 0)
        
        # 3. Test that the invalid ticker was correctly identified and failed
        self.assertIn("INVALID", data['failed'])
        self.assertNotIn("INVALID", data['success'])

    @patch('app.yf_financials_provider.get_batch_core_financials')
    def test_batch_financials_missing_data_contract_fields(self, mock_get_batch_financials):
        """POST /financials/core/batch: Tests graceful handling of missing keys from provider."""
        # --- Arrange ---
        tickers = ["GOOD", "MISSING_KEY"]
        self.mock_cache.get.return_value = None
        
        missing_key_data = self._create_valid_financials_data("MISSING_KEY")
        del missing_key_data['marketCap'] # Pydantic will default this to None

        mock_get_batch_financials.return_value = {
            "GOOD": self._create_valid_financials_data("GOOD"),
            "MISSING_KEY": missing_key_data
        }
        
        # --- Act ---
        response = self.client.post('/financials/core/batch', json={'tickers': tickers})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json['success']
        # Check that the service correctly defaulted the missing field to 0
        self.assertEqual(data["MISSING_KEY"]["marketCap"], 0)
        self.assertIn("GOOD", data)

    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_success_cache_miss(self, mock_get_core_financials):
        """GET /financials/core/<ticker>: Tests a cache miss for a decorator-cached endpoint."""
        # --- Arrange ---
        ticker = "AAPL"
        provider_data = self._create_valid_financials_data(ticker)
        mock_get_core_financials.return_value = provider_data
        self.mock_cache.get.return_value = None

        # --- Act ---
        response = self.client.get(f'/financials/core/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ticker'], provider_data['ticker'])
        self.assertEqual(response.json['annual_earnings'], provider_data['annual_earnings'])
        mock_get_core_financials.assert_called_once_with(ticker)

    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_success_cache_hit(self, mock_get_core_financials):
        """GET /financials/core/<ticker>: Tests a cache hit for a decorator-cached endpoint."""
        # --- Arrange ---
        ticker = "AAPL"
        cached_data = self._create_valid_financials_data(ticker)
        self.mock_cache.get.return_value = cached_data
        
        # --- Act ---
        response = self.client.get(f'/financials/core/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ticker'], cached_data['ticker'])
        self.assertEqual(response.json['annual_earnings'], cached_data['annual_earnings'])
        mock_get_core_financials.assert_not_called()

    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_for_index_success(self, mock_get_financials):
        """GET /financials/core/:ticker - Tests the happy path for a market index."""
        # --- Arrange ---
        self.mock_cache.get.return_value = None
        mock_data = self._create_mock_index_data(ticker="^GSPC")
        mock_get_financials.return_value = mock_data

        # --- Act ---
        response = self.client.get('/financials/core/^GSPC')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ticker'], '^GSPC')
        self.assertIn('current_price', response.json)
        self.assertNotIn('marketCap', response.json)
        self.mock_cache.set.assert_called_once_with('financials_^GSPC', mock_data, timeout=ANY)

    # New test case for cache hit on index
    def test_get_core_financials_for_index_cache_hit(self):
        """GET /financials/core/:ticker - Tests a cache hit for a market index."""
        # --- Arrange ---
        mock_data = self._create_mock_index_data(ticker="^DJI")
        self.mock_cache.get.return_value = mock_data

        # --- Act ---
        response = self.client.get('/financials/core/^DJI')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ticker'], '^DJI')
        self.assertEqual(response.json['current_price'], 4500.0)
        self.mock_cache.get.assert_called_once_with('financials_^DJI')


    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_not_found(self, mock_get_core_financials):
        """GET /financials/core/<ticker>: Tests 404 response for a non-existent ticker."""
        # --- Arrange ---
        ticker = "NONEXISTENT"
        mock_get_core_financials.return_value = None
        self.mock_cache.get.return_value = None

        # --- Act ---
        response = self.client.get(f'/financials/core/{ticker}')

        # --- Assert ---
        self.assertEqual(response.status_code, 404)
        mock_get_core_financials.assert_called_once_with(ticker)

    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_gracefully_handles_incomplete_data(self, mock_get_core_financials):
        """GET /financials/core/<ticker>: Ensures incomplete provider data is handled."""
        # --- Arrange ---
        ticker = "INCOMPLETE"
        provider_data = self._create_valid_financials_data(ticker)

        del provider_data['marketCap']
        mock_get_core_financials.return_value = provider_data
        self.mock_cache.get.return_value = None
        
        # --- Act ---
        response = self.client.get(f'/financials/core/{ticker}')
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['marketCap'], 0)

    def test_get_core_financials_handles_path_traversal_attack(self):
        """GET /financials/core/<ticker>: Tests rejection of malicious input."""
        response = self.client.get('/financials/core/../../etc/passwd')
        self.assertEqual(response.status_code, 400)
        

    @patch('app.yf_financials_provider.get_batch_core_financials')
    def test_batch_financials_success(self, mock_get_batch_financials):
        """POST /financials/core/batch: Tests successful retrieval and caching."""
        # --- Arrange ---
        tickers = ["AAPL", "MSFT", "FAILED"]
        self.mock_cache.get.return_value = None 
        
        mock_get_batch_financials.return_value = {
            "AAPL": self._create_valid_financials_data("AAPL"),
            "MSFT": self._create_valid_financials_data("MSFT"),
            "FAILED": None
        }
        
        # --- Act ---
        response = self.client.post('/financials/core/batch', json={'tickers': tickers})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn("AAPL", data['success'])
        self.assertIn("MSFT", data['success'])
        self.assertIn("FAILED", data['failed'])
        mock_get_batch_financials.assert_called_once_with(tickers, ANY)
        self.assertEqual(self.mock_cache.set.call_count, 2)


    @patch('app.yf_financials_provider.get_batch_core_financials')
    def test_batch_financials_handles_bad_data_types(self, mock_get_batch_financials):
        """POST /financials/core/batch: Tests that non-numeric contract fields are defaulted to 0."""
        # --- Arrange ---
        tickers = ["BAD_DATA"]
        self.mock_cache.get.return_value = None
        
        mock_get_batch_financials.return_value = {
            "BAD_DATA": self._create_valid_financials_data("BAD_DATA", {"totalRevenue": "invalid", "Net Income": None})
        }
        
        # --- Act ---
        response = self.client.post('/financials/core/batch', json={'tickers': tickers})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json['success']
        self.assertEqual(data["BAD_DATA"]["totalRevenue"], 0)
        self.assertEqual(data["BAD_DATA"]["Net Income"], 0)

    def test_batch_financials_handles_empty_ticker_list(self):
        """POST /financials/core/batch: Tests behavior with an empty ticker list."""
        response = self.client.post('/financials/core/batch', json={'tickers': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"success": {}, "failed": []})

    
    def test_batch_financials_invalid_payload(self):
        """POST /financials/core/batch: Tests rejection of invalid request bodies."""
        for payload in [{}, {'tickers': 'not-a-list'}]:
            with self.subTest(payload=payload):
                response = self.client.post('/financials/core/batch', json=payload)
                self.assertEqual(response.status_code, 400)

    @patch('app.yf_financials_provider.get_core_financials')
    def test_get_core_financials_invalid_cache_data(self, mock_get_financials):
        """GET /financials/core/:ticker - Tests refetch when cached data is invalid."""
        # --- Arrange ---
        # Use a self-contained, explicit dictionary for the invalid cached data.
        invalid_cached_data = {
            "ticker": "AAPL", "marketCap": "this-is-an-invalid-string", "totalRevenue": 1,
            "netIncome": 1, "sharesOutstanding": 1, "floatShares": 1,
            "annual_earnings": [], "quarterly_earnings": [],
            "quarterly_financials": [], "firstTradeDate": "1980-12-12"
        }
        self.mock_cache.get.return_value = invalid_cached_data
        
        # This is the raw data our mock provider will return.
        valid_refetched_data = self._create_valid_financials_data("AAPL")
        mock_get_financials.return_value = valid_refetched_data
        
        # This is the data AFTER the app validates and cleans it. We must replicate the
        # logic of `validate_and_prepare_financials` to create the exact expected result.
        validated_model = CoreFinancials.model_validate(valid_refetched_data)
        expected_data = validated_model.model_dump(by_alias=True)
        
        # Replicate the cleaning/defaulting step from the helper function
        expected_data['totalRevenue'] = expected_data.get('totalRevenue') if isinstance(expected_data.get('totalRevenue'), (int, float)) else 0
        expected_data['Net Income'] = expected_data.get('Net Income') if isinstance(expected_data.get('Net Income'), (int, float)) else 0
        expected_data['marketCap'] = expected_data.get('marketCap') if isinstance(expected_data.get('marketCap'), (int, float)) else 0

        # --- Act ---
        response = self.client.get('/financials/core/AAPL')
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        # Verify it's the valid, refetched, and cleaned data
        self.assertEqual(response.json, expected_data)
        # Verify a refetch was triggered
        mock_get_financials.assert_called_once_with('AAPL')
        # Assert that the CACHED data matches the cleaned, validated object.
        self.mock_cache.set.assert_called_once_with('financials_AAPL', expected_data, timeout=ANY)


# =====================================================================
# ==                        NEWS ENDPOINTS                           ==
# =====================================================================

class TestNewsEndpoint(BaseDataServiceTest):
    
    @patch('app.get_news_cached')
    def test_get_news_success_cache_miss(self, mock_get_news):
        """GET /news/<ticker>: Tests cache miss for the news endpoint."""
        ticker = "TSLA"
        provider_data = [{"title": "Big News"}]
        mock_get_news.return_value = provider_data
        self.mock_cache.get.return_value = None

        response = self.client.get(f'/news/{ticker}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, provider_data)
        mock_get_news.assert_called_once_with(ticker)

    @patch('app.get_news_cached')
    def test_get_news_success_cache_hit(self, mock_get_news_cached):
        """GET /news/<ticker>: Tests cache hit for the news endpoint."""
        # This test verifies the route correctly calls the cached function and returns its data.
        # It tests the "outcome" of a cache hit by mocking the function that encapsulates the cache logic.
        ticker = "TSLA"
        cached_data = [{"title": "Old News"}]
        mock_get_news_cached.return_value = cached_data

        response = self.client.get(f'/news/{ticker}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, cached_data)
        mock_get_news_cached.assert_called_once_with(ticker)

# =====================================================================
# ==                  INDUSTRY & PEERS ENDPOINTS                     ==
# =====================================================================

class TestIndustryPeersEndpoint(BaseDataServiceTest):

    @patch('app.finnhub_provider.get_company_peers_and_industry')
    def test_industry_peers_endpoint_with_real_cache(self, mock_get_peers):
        """
        Tests that the /industry/peers endpoint correctly caches its response.
        """
        # Temporarily stop the global cache mock from the base class to test the real cache decorator
        self.cache_patcher.stop()
        
        # Need to get the real cache object from the app context
        from app import cache
        cache.clear() # Ensure a clean slate for the test

        try:
            # --- Arrange ---
            ticker = 'AAPL'
            mock_peer_data = {'industry': 'Technology', 'peers': ['MSFT', 'GOOG']}
            mock_get_peers.return_value = mock_peer_data

            # --- Act ---
            # First call: should be a cache MISS, calling the provider
            response1 = self.client.get(f'/industry/peers/{ticker}')
            # Second call: should be a cache HIT, provider should not be called again
            response2 = self.client.get(f'/industry/peers/{ticker}')

            # --- Assert ---
            self.assertEqual(response1.status_code, 200)
            self.assertEqual(response1.json, mock_peer_data)
            self.assertEqual(response2.status_code, 200)
            self.assertEqual(response2.json, mock_peer_data)

            # The crucial assertion: prove the provider was only called ONCE for two requests.
            mock_get_peers.assert_called_once_with(ticker)
        
        finally:
            # Restart the patcher to not interfere with other tests
            self.cache_patcher.start()

    @patch('app.get_industry_peers_cached')
    def test_get_industry_peers_success_cache_miss(self, mock_get_industry_peers_cached):
        """GET /industry/peers/<ticker>: Tests cache miss."""
        ticker = "GOOGL"
        provider_data = {"industry": "Tech", "peers": ["MSFT", "AAPL"]}
        mock_get_industry_peers_cached.return_value = provider_data

        response = self.client.get(f'/industry/peers/{ticker}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, provider_data)
        mock_get_industry_peers_cached.assert_called_once_with(ticker)

    @patch('app.get_industry_peers_cached')
    def test_get_industry_peers_success_cache_hit(self, mock_get_industry_peers_cached):
        """GET /industry/peers/<ticker>: Tests cache hit."""
        ticker = "GOOGL"
        cached_data = {"industry": "Tech", "peers": ["MSFT", "AAPL"]}
        mock_get_industry_peers_cached.return_value = cached_data

        response = self.client.get(f'/industry/peers/{ticker}')

        self.assertEqual(response.status_code, 200)
        mock_get_industry_peers_cached.assert_called_once_with(ticker)

    @patch('app.get_industry_peers_cached')
    def test_get_industry_peers_not_found(self, mock_get_industry_peers_cached):
        """GET /industry/peers/<ticker>: Tests 404 for non-existent ticker."""
        ticker = "NONEXISTENT"
        mock_get_industry_peers_cached.return_value = None

        response = self.client.get(f'/industry/peers/{ticker}')

        self.assertEqual(response.status_code, 404)

    def test_get_industry_peers_invalid_ticker_format(self):
        """GET /industry/peers/<ticker>: Tests rejection of invalid ticker format."""
        response = self.client.get('/industry/peers/!@#$')
        self.assertEqual(response.status_code, 400)

# =====================================================================
# ==                  MARKET TREND ENDPOINTS (DB)                    ==
# =====================================================================
class TestMarketTrendEndpoints(BaseDataServiceTest):

    def _generate_mock_price_data(self, base_date_str, num_days, trend='up'):
        base_date = date.fromisoformat(base_date_str)
        data = []
        for i in range(num_days):
            price_mod = i if trend == 'up' else -i
            data.append({
                'formatted_date': (base_date - timedelta(days=num_days - 1 - i)).strftime('%Y-%m-%d'),
                'close': 100 + price_mod, 'high': 102 + price_mod, 'low': 98 + price_mod
            })
        return data

    @patch('app.yf_price_provider.get_stock_data')
    @patch('pandas_market_calendars.get_calendar')
    def test_calculate_market_trend_success(self, mock_get_calendar, mock_get_stock_data):
        """POST /market-trend/calculate: Tests successful calculation and storage."""
        # --- Arrange ---
        calc_date = "2025-08-25"
        mock_nyse = MagicMock()
        mock_nyse.schedule.return_value.index = pd.to_datetime([calc_date])
        mock_get_calendar.return_value = mock_nyse
        
        mock_history = self._generate_mock_price_data(calc_date, 300, trend='up')
        mock_get_stock_data.return_value = {'^GSPC': mock_history, '^DJI': mock_history, '^IXIC': mock_history}
        
        # --- Act ---
        response = self.client.post('/market-trend/calculate', json={'dates': [calc_date]})
        
        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['trends'][0]['date'], calc_date)
        self.assertEqual(response.json['trends'][0]['trend'], 'Bullish')
        self.mock_db.market_trends.update_one.assert_called_once()

    
    @patch('app.yf_price_provider.get_stock_data')
    @patch('pandas_market_calendars.get_calendar')
    def test_calculate_market_trend_bearish_scenario(self, mock_get_calendar, mock_get_stock_data):
        """POST /market-trend/calculate: Tests a bearish market scenario."""
        calc_date = "2025-08-25"
        mock_nyse = MagicMock()
        mock_nyse.schedule.return_value.index = pd.to_datetime([calc_date])
        mock_get_calendar.return_value = mock_nyse
        
        mock_history = self._generate_mock_price_data(calc_date, 300, trend='down')
        mock_get_stock_data.return_value = {'^GSPC': mock_history, '^DJI': mock_history, '^IXIC': mock_history}
        
        response = self.client.post('/market-trend/calculate', json={'dates': [calc_date]})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['trends'][0]['trend'], 'Bearish')

    
    @patch('pandas_market_calendars.get_calendar')
    def test_calculate_market_trend_handles_non_trading_day(self, mock_get_calendar):
        """POST /market-trend/calculate: Tests that non-trading days are handled."""
        non_trading_date = "2025-08-24" # A Sunday
        mock_nyse = MagicMock()
        mock_nyse.schedule.return_value.index = pd.to_datetime([]) # No valid days
        mock_get_calendar.return_value = mock_nyse
        
        response = self.client.post('/market-trend/calculate', json={'dates': [non_trading_date]})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['trends']), 0)
        self.assertIn(non_trading_date, response.json['failed_dates'])

    
    def test_calculate_market_trend_invalid_payload(self):
        """POST /market-trend/calculate: Tests rejection of invalid payloads."""
        response = self.client.post('/market-trend/calculate', json={'dates': 'not-a-list'})
        self.assertEqual(response.status_code, 400)

    def test_get_market_trends_with_range(self):
        """GET /market-trends: Tests retrieval of stored trends within a date range."""
        # --- Arrange ---
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [{"date": "2025-08-25"}, {"date": "2025-08-26"}]
        self.mock_db.market_trends.find.return_value = mock_cursor

        # --- Act ---
        response = self.client.get('/market-trends?start_date=2025-08-25&end_date=2025-08-26')

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json), 2)
        self.mock_db.market_trends.find.assert_called_once_with(
            {"date": {"$gte": "2025-08-25", "$lte": "2025-08-26"}}, 
            {'_id': 0}
        )
        
# =====================================================================
# ==                      SYSTEM ENDPOINTS                           ==
# =====================================================================
class TestSystemEndpoints(BaseDataServiceTest):

    def test_clear_cache_all(self):
        """POST /cache/clear: Tests clearing all caches with an empty payload or 'all'."""
        for payload in [{}, {'type': 'all'}]:
            with self.subTest(payload=payload):
                self.mock_redis_client.scan.return_value = (0, [b'flask_cache_key1', b'flask_cache_key2'])
                response = self.client.post('/cache/clear', json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Cleared 2 entries", response.json['message'])
                # Assert scan is called with the service-wide prefix
                self.mock_redis_client.scan.assert_called_with(cursor=0, match='flask_cache_*', count=1000)
                # Assert delete is called on the keys found by scan
                self.mock_redis_client.delete.assert_called_with(b'flask_cache_key1', b'flask_cache_key2')
                self.mock_cache.clear.assert_not_called() # Should not use the old method
                self.mock_redis_client.reset_mock()

    def test_clear_cache_specific_type_success(self):
        """POST /cache/clear: Tests clearing a specific cache type successfully."""
        cache_type_to_clear = 'industry'
        # redis-py returns keys as bytes. Note the multiple patterns for 'industry'.
        redis_keys = [b'flask_cache_peers_NVDA', b'flask_cache_day_gainers_US']
        # Simulate scan finding keys for one of the patterns
        self.mock_redis_client.scan.return_value = (0, redis_keys)
        
        response = self.client.post('/cache/clear', json={'type': cache_type_to_clear})
        
        self.assertEqual(response.status_code, 200)
        # Message should reflect the total from all patterns
        self.assertIn(f"Cleared {len(redis_keys)} entries from the '{cache_type_to_clear}' cache.", response.json['message'])
        self.assertEqual(response.json['keys_deleted'], len(redis_keys))
        
        # Check correct patterns were used
        self.assertIn('flask_cache_peers_*', [call.kwargs['match'] for call in self.mock_redis_client.scan.call_args_list])
        self.assertIn('flask_cache_day_gainers_*', [call.kwargs['match'] for call in self.mock_redis_client.scan.call_args_list])
        self.mock_redis_client.delete.assert_called_with(*redis_keys)
        self.mock_cache.clear.assert_not_called()

    def test_clear_cache_specific_type_no_keys_found(self):
        """POST /cache/clear: Tests clearing a specific cache type when no keys are found."""
        cache_type_to_clear = 'news'
        self.mock_redis_client.scan.return_value = (0, []) # No keys found
        
        response = self.client.post('/cache/clear', json={'type': cache_type_to_clear})
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cleared 0 entries", response.json['message'])
        self.assertEqual(response.json['keys_deleted'], 0)
        self.mock_redis_client.scan.assert_called_with(cursor=0, match='flask_cache_news_*', count=1000)
        self.mock_redis_client.delete.assert_not_called()

    def test_clear_cache_invalid_type(self):
        """POST /cache/clear: Tests request with an invalid cache type."""
        response = self.client.post('/cache/clear', json={'type': 'invalid_type'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json)
        self.assertIn("Invalid cache type 'invalid_type'", response.json['error'])

if __name__ == '__main__':
    unittest.main()