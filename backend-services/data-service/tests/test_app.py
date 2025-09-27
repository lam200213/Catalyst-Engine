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

class BaseDataServiceTest(unittest.TestCase):
    """
    Base test class that sets up a test client and mocks external dependencies.
    - Mocks the Flask-Caching 'cache' object for controlled cache testing.
    - Mocks the persistent 'db' client for market trend storage tests.
    """
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

        # Patch the persistent database client (for market_trends)
        self.db_patcher = patch('app.db')
        self.mock_db = self.db_patcher.start()
        self.mock_market_trends_collection = MagicMock()
        self.mock_db.market_trends = self.mock_market_trends_collection

        # Patch the cache client used for all caching operations
        self.cache_patcher = patch('app.cache')
        self.mock_cache = self.cache_patcher.start()

    def tearDown(self):
        self.db_patcher.stop()
        self.cache_patcher.stop()
    # Helper method to create valid mock price data  
    def _create_valid_price_data(self, custom_data={}):
        """Creates a single, valid PriceDataItem dictionary."""
        default_data = {
            "formatted_date": "2025-09-24",
            "open": 150.0,
            "high": 152.0,
            "low": 149.5,
            "close": 151.75,
            "volume": 1000000,
            "adjclose": 151.75
        }
        default_data.update(custom_data)
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
        mock_get_stock_data.assert_called_once_with(ticker, start_date=None, period="1y")
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
        mock_get_stock_data.assert_called_once_with(ticker, start_date=None, period="1y")
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
            mock_get_stock_data.assert_called_once_with(ticker, start_date=None, period="1y")
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
        mock_get_stock_data.assert_called_once_with(ticker, start_date=expected_start_date, period=None)
        
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
        valid_cached_data = [self._create_valid_price_data({"close": 100.0})]
        valid_provider_data = [self._create_valid_price_data({"close": 200.0})]
        
        def cache_side_effect(key):
            if key == 'price_yfinance_CACHED':
                return valid_cached_data
            return None
        self.mock_cache.get.side_effect = cache_side_effect
        
        provider_data = {"UNCACHED": valid_provider_data, "FAILED": None}
        mock_get_stock_data.return_value = provider_data

        # --- Act ---
        response = self.client.post('/price/batch', json={'tickers': ['CACHED', 'UNCACHED', 'FAILED'], 'source': 'yfinance'})

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(data['success']['CACHED'], valid_cached_data)
        self.assertEqual(data['success']['UNCACHED'], valid_provider_data)
        self.assertIn('FAILED', data['failed'])
        mock_get_stock_data.assert_called_once_with(['UNCACHED', 'FAILED'], start_date=None, period='1y')
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
        mock_get_batch_financials.assert_called_once_with(tickers)
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

    def test_clear_cache_endpoint(self):
        """POST /cache/clear: Tests that the endpoint calls cache.clear()"""
        response = self.client.post('/cache/clear')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "All data service caches have been cleared."})
        self.mock_cache.clear.assert_called_once()


if __name__ == '__main__':
    unittest.main()