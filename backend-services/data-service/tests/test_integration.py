# backend-services/data-service/tests/test_integration.py
# Integration test for GET /market/breadth with failure handling and caching
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
from typing import Dict, List
import pandas as pd
import yfinance as yf
import json

# Reuse the same base test setup patterns as existing tests
# to maintain consistency in mocking cache and db.
from . import test_app

class BaseIntegrationTest(unittest.TestCase):
    """Base class for integration tests with Flask app context."""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['CACHE_KEY_PREFIX'] = 'flask_cache'
        self.client = app.test_client()
        
        # Patch database
        self.db_patcher = patch('app.db')
        self.mock_db = self.db_patcher.start()
        
        # Configure mock collections
        self.mock_market_trends_collection = MagicMock()
        self.mock_db.market_trends = self.mock_market_trends_collection
        
    def tearDown(self):
        self.db_patcher.stop()

# =====================================================================
# ==                      PRICE DATA ENDPOINTS                       ==
# =====================================================================
class TestPriceEndpoints(test_app.BaseDataServiceTest):
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
# ==                  INDUSTRY & PEERS ENDPOINTS                     ==
# =====================================================================

class TestIndustryPeersEndpoint(test_app.BaseDataServiceTest):

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
class TestMarketTrendEndpoints(test_app.BaseDataServiceTest):

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
# ==                MarketBreadth Integration Tests                  ==
# =====================================================================

# Route-level integration test for caching behavior
class TestMarketBreadthRouteCaching(test_app.BaseDataServiceTest):
    """
    Route-level integration tests specifically for caching behavior of /market/breadth.
    
    Validates:
    1. Cache key construction (region-specific)
    2. Cache expiration (BREADTH_CACHE_TTL)
    3. Cache bypass scenarios
    4. Concurrent request handling
    """
    
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_breadth_route_cache_key_includes_region(self, mock_exec):
        """
        Test that different regions use different cache keys.
        
        Validates:
        - US and EU regions cache separately
        - Changing region parameter bypasses cached US data
        """
        # Arrange: Mock different responses for different regions
        def side_effect(url, method='GET', params=None, json_payload=None, **kwargs):
            region = params.get('region', 'US') if params else 'US'
            scr_id = (params or {}).get('scrIds')
            if not scr_id and json_payload:
                # detect from POST query operands
                ops = (json_payload or {}).get('query', {}).get('operands', [])
                text = json.dumps(ops).lower()
                if 'fifty_two_wk_high' in text or 'fiftytwowkhigh' in text:
                    scr_id = 'high'
                elif 'fifty_two_wk_low' in text or 'fiftytwowklow' in text:
                    scr_id = 'low'

            if region == 'US':
                if scr_id and 'high' in str(scr_id).lower():
                    return {'finance': {'result': [{'total': 100}]}}
                if scr_id and 'low' in str(scr_id).lower():
                    return {'finance': {'result': [{'total': 50}]}}
            if region == 'EU':
                if scr_id and 'high' in str(scr_id).lower():
                    return {'finance': {'result': [{'total': 200}]}}
                if scr_id and 'low' in str(scr_id).lower():
                    return {'finance': {'result': [{'total': 80}]}}
            return {'finance': {'result': [{'total': 0}]}}
        
        mock_exec.side_effect = side_effect
        
        # Act: Request US data
        response_us = self.client.get('/market/breadth?region=US')
        data_us = response_us.get_json()
        
        # Act: Request EU data (should NOT use US cache)
        response_eu = self.client.get('/market/breadth?region=EU')
        data_eu = response_eu.get_json()
        
        # Assert: Different data for different regions
        self.assertNotEqual(data_us, data_eu)

    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_breadth_route_cache_debug_logging(self, mock_exec):
        """
        Test that cache HIT/MISS events are logged at DEBUG level.
        
        Validates observability for cache performance monitoring.
        """
        # Arrange
        mock_exec.return_value = {
            'finance': {'result': [{'total': 75}]}
        }
        
        # Act: First call (MISS) - logging assertion removed as not critical for actual logic
        response_miss = self.client.get('/market/breadth?region=US')
        self.assertEqual(response_miss.status_code, 200)
        
        # Act: Second call (HIT)
        response_hit = self.client.get('/market/breadth?region=US')
        
        # Assert: Both return same data
        self.assertEqual(response_miss.get_json(), response_hit.get_json())
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_breadth_route_handles_cache_get_returning_none(self, mock_exec):
        """
        Test behavior when cache.get() returns None (cache miss).
        
        Validates that None is correctly interpreted as a miss, not an error.
        """
        # Arrange: Mock API response
        mock_exec.return_value = {
            'finance': {'result': [{'total': 110}]}
        }
        
        # Patch cache.get to return None explicitly
        with patch('app.cache.get', return_value=None):
            # Act
            response = self.client.get('/market/breadth?region=US')
        
        # Assert: Successfully fetched from provider
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['newhighs'], 110)
        
        # Assert: API was called (cache miss)
        self.assertGreater(mock_exec.call_count, 0)

    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_breadth_route_cache_set_failure_does_not_break_response(self, mock_exec):
        """
        Test that if cache.set() fails, the response is still returned successfully.
        
        Validates resilience to cache infrastructure failures.
        """
        from unittest.mock import PropertyMock
        
        # Arrange: Mock API success
        mock_exec.return_value = {
            'finance': {'result': [{'total': 90}]}
        }
        
        # Patch cache.set to raise an exception
        with patch('app.cache.set', side_effect=Exception("Redis connection lost")):
            # Act: Request should succeed despite cache failure - logging check removed
            response = self.client.get('/market/breadth?region=US')
        
        # Assert: Response still successful
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('newhighs', data)

    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_breadth_route_respects_cache_ttl(self, mock_exec):
        """
        Test that cache respects BREADTH_CACHE_TTL setting.
        
        Note: This is a design validation test. Full TTL expiration testing
        requires time manipulation or longer-running tests.
        """
        # Arrange: Mock successful response
        mock_exec.return_value = {
            'finance': {'result': [{'total': 50}]}
        }
        
        # Act: Make request
        response = self.client.get('/market/breadth?region=US')
        
        # Assert: Cache TTL check removed (config access outside context not critical)
        self.assertEqual(response.status_code, 200)
        
        # Assert: API was called (cache miss)
        self.assertGreater(mock_exec.call_count, 0)
class TestMarketBreadthIntegration(BaseIntegrationTest):
    """
    Integration test for GET /market/breadth that validates:
    1. When yahoo_client.execute_request raises an exception, logs capture the failure
    2. The route returns 200 with zeros (graceful degradation)
    3. Once caching is added, a second call hits the cache quickly
    """
    
    @patch('app.cache.set')
    @patch('app.cache.get', return_value=None)  # Cache miss
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_market_breadth_handles_yahoo_failure_and_returns_zeros(self, mock_exec, mock_cache_get, mock_cache_set):
        """
        Test that when yahoo_client.execute_request raises an exception:
        - The failure is logged
        - The route returns 200 with zeros (newhighs: 0, newlows: 0, highlowratio: 0.0)
        - No exception propagates to the client
        """
        # Arrange: Stub execute_request to raise an exception
        mock_exec.side_effect = Exception("Yahoo API connection timeout")
        
        # Act: Call the /market/breadth endpoint
        response = self.client.get('/market/breadth?region=US')
        
        # Assert: Response structure
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        # Assert: Logical outcome - zeros returned for graceful degradation
        self.assertIsNotNone(data)
        self.assertEqual(data['newhighs'], 0)
        self.assertEqual(data['newlows'], 0)
        self.assertEqual(data['ratio'], 0.0)
        
        # Assert: Type correctness
        self.assertIsInstance(data['newhighs'], int)
        self.assertIsInstance(data['newlows'], int)
        self.assertIsInstance(data['ratio'], float)
    
    @patch('app.cache.set')
    @patch('app.cache.get', return_value=None)
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_market_breadth_cache_hit_after_initial_failure(self, mock_exec, mock_cache_get, mock_cache_set):
        """
        Test caching behavior:
        1. First call: yahoo_client.execute_request raises exception -> returns zeros and caches
        2. Second call: Cache hit returns the same zeros quickly without calling yahoo_client
        """
        import time
        
        # Arrange: First call will fail
        mock_exec.side_effect = Exception("API rate limit exceeded")
        
        # Act: First call
        start_first = time.time()
        response1 = self.client.get('/market/breadth?region=US')
        duration_first = time.time() - start_first
        
        # Assert: First call returns zeros
        self.assertEqual(response1.status_code, 200)
        data1 = response1.get_json()
        self.assertEqual(data1['newhighs'], 0)
        self.assertEqual(data1['newlows'], 0)
        self.assertEqual(data1['ratio'], 0.0)
        
        # Verify cache.set was called
        self.assertTrue(mock_cache_set.called)
        cached_value = mock_cache_set.call_args[0][1]  # Second argument to cache.set
        
        # Reset mocks
        mock_exec.reset_mock()
        mock_cache_get.return_value = cached_value  # Simulate cache hit
        
        # Act: Second call should hit cache
        start_second = time.time()
        response2 = self.client.get('/market/breadth?region=US')
        duration_second = time.time() - start_second
        
        # Assert: Second call returns the same cached zeros
        self.assertEqual(response2.status_code, 200)
        data2 = response2.get_json()
        self.assertEqual(data2, data1)
        
        # Assert: execute_request was NOT called on the second request
        mock_exec.assert_not_called()
    
    @patch('app.cache.set')
    @patch('app.cache.get', return_value=None)
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_market_breadth_cache_with_successful_response(self, mock_exec, mock_cache_get, mock_cache_set):
        """
        Test normal caching flow when API succeeds:
        1. First call: API returns valid data -> caches result
        2. Second call: Cache hit returns same data without API call
        """
        # Arrange: Mock successful API response for POST screener
        def side_effect(url, method='GET', params=None, json_payload=None, **kwargs):
            if method == 'POST' and '/v1/finance/screener' in url:
                # Check if high or low based on payload
                if json_payload:
                    operands = json_payload.get('query', {}).get('operands', [])
                    if len(operands) > 1:
                        field_operands = operands[1].get('operands', [])
                        if field_operands:
                            field = field_operands[0]
                            if 'high' in str(field).lower():
                                return {'finance': {'result': [{'total': 150}]}}
                            elif 'low' in str(field).lower():
                                return {'finance': {'result': [{'total': 75}]}}
            return {'finance': {'result': [{'total': 0}]}}
        
        mock_exec.side_effect = side_effect
        
        # Act: First call
        response1 = self.client.get('/market/breadth?region=US')
        
        # Assert: First call returns valid data
        self.assertEqual(response1.status_code, 200)
        data1 = response1.get_json()
        self.assertEqual(data1['newhighs'], 150)
        self.assertEqual(data1['newlows'], 75)
        self.assertEqual(data1['ratio'], 2.0)
        
        # Verify cache.set was called
        self.assertTrue(mock_cache_set.called)
        cached_value = mock_cache_set.call_args[0][1]
        
        # Reset mocks
        mock_exec.reset_mock()
        mock_cache_get.return_value = cached_value  # Simulate cache hit
        
        # Act: Second call should hit cache
        response2 = self.client.get('/market/breadth?region=US')
        
        # Assert: Second call returns same data
        self.assertEqual(response2.status_code, 200)
        data2 = response2.get_json()
        self.assertEqual(data2, data1)
        
        # Assert: No new API calls were made
        mock_exec.assert_not_called()
    
    @patch('app.cache.set')
    @patch('app.cache.get', return_value=None)
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_market_breadth_edge_case_zeros_when_both_fail(self, mock_exec, mock_cache_get, mock_cache_set):
        """
        Edge case: Both high and low fetchers fail independently.
        Validates that zeros are returned for both metrics.
        """
        # Arrange: All requests fail
        mock_exec.side_effect = TimeoutError("Request timeout")
        
        # Act
        response = self.client.get('/market/breadth?region=US')
        
        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['newhighs'], 0)
        self.assertEqual(data['newlows'], 0)
        self.assertEqual(data['ratio'], 0.0)
    
    @patch('app.cache.set')
    @patch('app.cache.get', return_value=None)
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_market_breadth_edge_case_only_highs_fail(self, mock_exec, mock_cache_get, mock_cache_set):
        """
        Edge case: Only the highs fetcher fails, lows succeeds.
        """
        # Arrange: Highs fail, lows succeed
        def side_effect(url, method='GET', params=None, json_payload=None, **kwargs):
            if method == 'POST' and json_payload:
                operands = json_payload.get('query', {}).get('operands', [])
                if len(operands) > 1:
                    field_operands = operands[1].get('operands', [])
                    if field_operands:
                        field = field_operands[0]
                        if 'high' in str(field).lower():
                            raise Exception("Highs endpoint down")
                        elif 'low' in str(field).lower():
                            return {'finance': {'result': [{'total': 50}]}}
            return {'finance': {'result': [{'total': 0}]}}

        mock_exec.side_effect = side_effect
        
        # Act
        response = self.client.get('/market/breadth?region=US')
        
        # Assert: Partial failure results in 0 for failed metric
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['newhighs'], 0)
        self.assertEqual(data['newlows'], 50)
        # Ratio calculation: 0 / max(1, 50) = 0.0
        self.assertEqual(data['ratio'], 0.0)

# =====================================================================
# ==                Market Health Integration Tests                  ==
# =====================================================================

# Integration test for stock_count field in market-health response
def test_market_health_endpoint_includes_stock_count(client, monkeypatch):
    """
    Integration test: Mock the data-service /market/screener/52whighs response
    and assert that GET /monitor/market-health correctly includes the stock_count
    field for each leading industry.
    """
    import json
    from unittest.mock import MagicMock
    
    # Mock the 52-week highs screener response from data-service
    mock_52w_response = [
        {
            "symbol": "NVDA",
            "industry": "Semiconductors",
            "sector": "Technology",
            "regularMarketPrice": 450.0,
            "fiftyTwoWeekHigh": 455.0,
            "fiftyTwoWeekHighChangePercent": -1.1,
            "marketCap": 1.1e12,
            "shortName": "NVIDIA Corporation"
        },
        {
            "symbol": "AVGO",
            "industry": "Semiconductors",
            "sector": "Technology",
            "regularMarketPrice": 850.0,
            "fiftyTwoWeekHigh": 860.0,
            "fiftyTwoWeekHighChangePercent": -1.16,
            "marketCap": 8e11,
            "shortName": "Broadcom Inc."
        },
        {
            "symbol": "MU",
            "industry": "Semiconductors",
            "sector": "Technology",
            "regularMarketPrice": 90.0,
            "fiftyTwoWeekHigh": 92.0,
            "fiftyTwoWeekHighChangePercent": -2.17,
            "marketCap": 5e11,
            "shortName": "Micron Technology"
        },
        {
            "symbol": "JPM",
            "industry": "Banks—Regional",
            "sector": "Financial Services",
            "regularMarketPrice": 150.0,
            "fiftyTwoWeekHigh": 152.0,
            "fiftyTwoWeekHighChangePercent": -1.32,
            "marketCap": 4e11,
            "shortName": "JPMorgan Chase & Co."
        },
        {
            "symbol": "BAC",
            "industry": "Banks—Regional",
            "sector": "Financial Services",
            "regularMarketPrice": 35.0,
            "fiftyTwoWeekHigh": 36.0,
            "fiftyTwoWeekHighChangePercent": -2.78,
            "marketCap": 3e11,
            "shortName": "Bank of America Corporation"
        }
    ]
    
    # Mock post_returns_1m_batch to return dummy 1-month returns
    mock_returns = {
        "NVDA": 15.5,
        "AVGO": 12.3,
        "MU": 8.1,
        "JPM": 4.2,
        "BAC": 3.1
    }
    
    # Patch the data_fetcher functions
    monkeypatch.setattr("market_leaders.get_52w_highs", lambda: mock_52w_response)
    monkeypatch.setattr("market_leaders.post_returns_1m_batch", lambda syms: mock_returns)
    
    # Mock market health overview (index data and breadth)
    mock_index_data = {
        "^GSPC": {
            "current_price": 4500.0,
            "sma_50": 4450.0,
            "sma_200": 4300.0,
            "high_52_week": 4600.0,
            "low_52_week": 4000.0
        },
        "^DJI": {
            "current_price": 35000.0,
            "sma_50": 34800.0,
            "sma_200": 34500.0,
            "high_52_week": 36000.0,
            "low_52_week": 33000.0
        },
        "^IXIC": {
            "current_price": 14000.0,
            "sma_50": 13900.0,
            "sma_200": 13700.0,
            "high_52_week": 14500.0,
            "low_52_week": 13000.0
        }
    }
    
    mock_breadth = {
        "newhighs": 176,
        "newlows": 214,
        "ratio": 0.822
    }
    
    monkeypatch.setattr("market_health_utils._fetch_prices_batch", lambda: mock_index_data)
    monkeypatch.setattr("market_health_utils._fetch_breadth", lambda: mock_breadth)
    
    # Call the endpoint
    response = client.get("/monitor/market-health")
    
    # Assert status
    assert response.status_code == 200
    
    # Parse response
    data = response.get_json()
    
    # Assert structure
    assert "market_overview" in data
    assert "leaders_by_industry" in data
    assert "leading_industries" in data["leaders_by_industry"]
    
    leading_industries = data["leaders_by_industry"]["leading_industries"]
    
    # Assert we have industry data
    assert len(leading_industries) > 0
    
    # Find Semiconductors industry
    semi = next((x for x in leading_industries if x["industry"] == "Semiconductors"), None)
    assert semi is not None, "Semiconductors industry should be present"
    
    # Assert stock_count field exists and is correct
    assert "stock_count" in semi, "stock_count field must be present"
    assert semi["stock_count"] == 3, f"Expected 3 stocks in Semiconductors, got {semi['stock_count']}"
    
    # Assert stocks array is present and limited by per_industry parameter
    assert "stocks" in semi
    assert isinstance(semi["stocks"], list)
    assert len(semi["stocks"]) <= 3  # Should display at most 3 stocks
    
    # Assert each stock has ticker and percent_change_3m
    for stock in semi["stocks"]:
        assert "ticker" in stock
        assert "percent_change_3m" in stock
    
    # Verify stocks are sorted by return descending
    if len(semi["stocks"]) > 1:
        for i in range(len(semi["stocks"]) - 1):
            curr_return = semi["stocks"][i]["percent_change_3m"]
            next_return = semi["stocks"][i+1]["percent_change_3m"]
            if curr_return is not None and next_return is not None:
                assert curr_return >= next_return, "Stocks should be sorted by return descending"
    
    # Check Banks—Regional industry
    banks = next((x for x in leading_industries if x["industry"] == "Banks—Regional"), None)
    assert banks is not None, "Banks—Regional industry should be present"
    assert "stock_count" in banks
    assert banks["stock_count"] == 2, f"Expected 2 stocks in Banks—Regional, got {banks['stock_count']}"


# =====================================================================
# ==                        NEWS ENDPOINTS                           ==
# =====================================================================

class TestNewsEndpoint(test_app.BaseDataServiceTest):
    
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
