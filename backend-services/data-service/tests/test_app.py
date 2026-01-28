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

    # helper to advance a date by one trading day
    def _next_weekday(self, d):
        # weekend-only (Sat/Sun) adjustment; no holiday awareness
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

# =====================================================================
# ==                BATCH PRICE LOGIC & EDGE CASES                   ==
# =====================================================================
class TestBatchPriceLogic(BaseDataServiceTest):
    @patch('app.yf_price_provider.get_stock_data')
    def test_batch_price_incremental_merge_is_sorted_and_provider_wins_on_overlap(self, mock_get_stock_data):
        """
        POST /price/batch:
        - Cache exists but stale -> incremental fetch path
        - Provider returns overlapping dates (same formatted_date as cache)
        Expected:
        - Final merged list is sorted by formatted_date ascending
        - No duplicate formatted_date
        - Provider value overwrites cache on overlapping formatted_date
        """
        ticker = "MSFT"

        # Cache with unsorted order + duplicate date in cache
        cached_data = [
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-10", "close": 110.0}),
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-08", "close": 108.0}),
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-09", "close": 109.0}),
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-10", "close": 999.0}),  # duplicate in cache
        ]
        self.mock_cache.get.return_value = cached_data

        # Provider returns unsorted data + overlap on 2026-01-10 with a different close
        provider_data = [
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-13", "close": 113.0}),
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-10", "close": 555.0}),  # overlap (provider should win)
            self._create_valid_price_data(overrides={"formatted_date": "2026-01-12", "close": 112.0}),
        ]
        mock_get_stock_data.return_value = provider_data

        resp = self.client.post('/price/batch', json={'tickers': [ticker], 'source': 'yfinance'})
        self.assertEqual(resp.status_code, 200)

        out = resp.json['success'][ticker]

        # 1) Deduped by formatted_date
        dates = [row["formatted_date"] for row in out]
        self.assertEqual(len(dates), len(set(dates)))

        # 2) Sorted ascending
        self.assertEqual(dates, sorted(dates))

        # 3) Provider wins on overlap (2026-01-10 should have close=555.0)
        row_0110 = next(r for r in out if r["formatted_date"] == "2026-01-10")
        self.assertEqual(row_0110["close"], 555.0)

        # 4) Cache updated with the final merged list
        self.mock_cache.set.assert_called_once() 

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
        # Provider should be called starting from the trade day after the last cached date 
        expected_start_date = self._next_weekday(last_cached_date + timedelta(days=1))
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

class TestipelineResilience(BaseDataServiceTest):

    @patch("app.yf_price_provider.get_stock_data")
    def test_price_batch_provider_none_returns_failed_not_500(self, mock_get_stock_data):
        """
        Week 9 Plan 1: one bad ticker should not crash the batch.
        Provider returns None for that ticker (e.g., missing timestamp).
        Expected: HTTP 200, ticker is listed in failed.
        """
        self.mock_cache.get.return_value = None
        mock_get_stock_data.return_value = {"BADTICK": None}

        resp = self.client.post("/price/batch", json={
            "tickers": ["BADTICK"],
            "source": "yfinance",
            "period": "1y",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertIn("BADTICK", resp.json.get("failed", []))
        self.assertNotIn("BADTICK", resp.json.get("success", {}))

if __name__ == '__main__':
    unittest.main()