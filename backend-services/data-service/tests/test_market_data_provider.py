# backend-services/data-service/tests/test_market_data_provider.py

import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, List
import pandas as pd
import yfinance as yf

# Reuse the same base test setup patterns as existing tests
# to maintain consistency in mocking cache and db.
from . import test_app

# Tests for market sector/industry and day_gainers endpoints, and 1m return batch.
# Also includes provider-level unit tests that mock raw inputs to validate parsing and thresholds.

class TestSectorIndustryEndpoint(test_app.BaseDataServiceTest):
    # Correct patch path
    @patch('app.YahooSectorIndustrySource')
    def test_sectors_industries_success_200(self, mock_source_cls):
        """GET /market/sectors/industries: success path and structure/type checks."""
        # ensure cache is missed to prevent mock object serialization
        self.mock_cache.get.return_value = None
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.return_value = {
            "Semiconductors": ["NVDA", "AMD"],
            "Software": ["MSFT"]
        }
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/sectors/industries')
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        # Logical outcome + identifying keys
        self.assertIn("Semiconductors", data)
        self.assertIn("NVDA", data["Semiconductors"])
        # Type checks
        self.assertIsInstance(data, dict)
        for k, v in data.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, list)
            for s in v:
                self.assertIsInstance(s, str)

    # Correct patch path and add fallback test
    @patch('app.DayGainersSource')
    @patch('app.YahooSectorIndustrySource')
    def test_sectors_industries_fallback_on_empty(self, mock_sector_source_cls, mock_gainer_source_cls):
        """GET /market/sectors/industries: returns 200 with fallback data when primary source is empty."""
        self.mock_cache.get.return_value = None
        # Primary source returns empty
        mock_sector_source = MagicMock()
        mock_sector_source.get_industry_top_tickers.return_value = {}
        mock_sector_source_cls.return_value = mock_sector_source
        
        # Fallback source returns data
        fallback_data = {"From Gainers": ["GNR"]}
        mock_gainer_source = MagicMock()
        mock_gainer_source.get_industry_top_tickers.return_value = fallback_data
        mock_gainer_source_cls.return_value = mock_gainer_source

        resp = self.client.get('/market/sectors/industries')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json, fallback_data)

    # Correct patch path
    @patch('app.YahooSectorIndustrySource')
    def test_sectors_industries_exception_500(self, mock_source_cls):
        """GET /market/sectors/industries: security—generic 500 without leaking details."""
        self.mock_cache.get.return_value = None
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.side_effect = RuntimeError("Backend failure")
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/sectors/industries')
        self.assertEqual(resp.status_code, 500)
        self.assertIn("error", resp.json)
        self.assertEqual(resp.json["error"], "Internal server error")


class TestDayGainersEndpoint(test_app.BaseDataServiceTest):
    # Correct patch path
    @patch('app.DayGainersSource')
    def test_day_gainers_success_200(self, mock_source_cls):
        """GET /market/screener/day_gainers: success path and structure/type checks."""
        self.mock_cache.get.return_value = None
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.return_value = {
            "Consumer Electronics": ["AAPL"],
            "Software - Infrastructure": ["MSFT", "ORCL"]
        }
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/screener/day_gainers')
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertIn("Consumer Electronics", data)  # key identifying data
        self.assertIn("AAPL", data["Consumer Electronics"])  # logical result
        self.assertIsInstance(data, dict)
        for k, v in data.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, list)
            for s in v:
                self.assertIsInstance(s, str)

    # Correct patch path
    @patch('app.DayGainersSource')
    def test_day_gainers_empty_404(self, mock_source_cls):
        """GET /market/screener/day_gainers: returns 404 when source returns empty mapping."""
        self.mock_cache.get.return_value = None
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.return_value = {}
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/screener/day_gainers')
        self.assertEqual(resp.status_code, 404)
        self.assertIn("message", resp.json)
        self.assertIn("Could not retrieve day gainers data.", resp.json["message"])

    # Correct patch path
    @patch('app.DayGainersSource')
    def test_day_gainers_exception_500(self, mock_source_cls):
        """GET /market/screener/day_gainers: security—generic 500 without leaking details."""
        self.mock_cache.get.return_value = None
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.side_effect = ValueError("Bad parse")
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/screener/day_gainers')
        self.assertEqual(resp.status_code, 500)
        self.assertIn("error", resp.json)
        self.assertEqual(resp.json["error"], "Internal server error")

class TestReturnBatchEndpoint(test_app.BaseDataServiceTest):
    @patch('app.ReturnCalculator')
    def test_return_1m_batch_success_mix(self, mock_calc_cls):
        """POST /data/return/1m/batch: mixed results and type checks."""
        # Arrange
        payload = {"tickers": ["AAPL", "MSFT", "BROKEN"]}
        mock_calc = MagicMock()
        # Map return values: float for AAPL, None for MSFT, exception for BROKEN -> becomes None in response
        def side_effect(symbol):
            if symbol == "AAPL":
                return 3.21
            if symbol == "MSFT":
                return None
            if symbol == "BROKEN":
                raise RuntimeError("Provider failed")

        mock_calc.one_month_change.side_effect = side_effect
        mock_calc_cls.return_value = mock_calc

        # Act
        resp = self.client.post('/data/return/1m/batch', json=payload)

        # Assert
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        # Assert identifying data (keys) and logical outcomes (values)
        self.assertSetEqual(set(data.keys()), {"AAPL", "MSFT", "BROKEN"})
        self.assertIsInstance(data["AAPL"], float)
        self.assertEqual(data["AAPL"], 3.21)
        self.assertIsNone(data["MSFT"])  # intentionally None is allowed
        self.assertIsNone(data["BROKEN"])  # exception -> None at endpoint

    def test_return_1m_batch_invalid_payload(self):
        """POST /data/return/1m/batch: invalid payloads return 400."""
        bad_payloads = [
            {},  # missing 'tickers'
            {"tickers": "not-a-list"},  # wrong type
            {"tickers": []},  # empty list is treated as invalid in current implementation
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                resp = self.client.post('/data/return/1m/batch', json=payload)
                self.assertEqual(resp.status_code, 400)
                self.assertIn("error", resp.json)

    def test_return_1m_batch_security_long_strings(self):
        """POST /data/return/1m/batch: ensure long/malicious tickers do not break."""
        # Not validated by route, but should return cleanly with None values
        long_ticker = "A" * 1024
        payload = {"tickers": [long_ticker]}
        with patch('app.ReturnCalculator') as mock_calc_cls:
            mock_calc = MagicMock()
            mock_calc.one_month_change.return_value = None
            mock_calc_cls.return_value = mock_calc

            resp = self.client.post('/data/return/1m/batch', json=payload)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(long_ticker, resp.json)
            self.assertIsNone(resp.json[long_ticker])

    def test_return_1m_batch_get_method_not_allowed(self):
        """GET /data/return/1m/batch: surfaces route-method discrepancy (only POST implemented)."""
        resp = self.client.get('/data/return/1m/batch')
        self.assertEqual(resp.status_code, 405)  # Method Not Allowed


class TestReturnSingleRouteDiscrepancy(test_app.BaseDataServiceTest):
    def test_single_return_route_misconfigured(self):
        """
        GET /data/return/1m/<ticker> is not registered in app.py.
        The current route is '/data/return/1m/' without a <ticker> param,
        so calling '/data/return/1m/AAPL' should 404.
        """
        resp = self.client.get('/data/return/1m/AAPL')
        self.assertEqual(resp.status_code, 404)


# Provider-level unit tests for requirement 12 and 13:
# - Mock raw yfinance responses, not just final outputs.
# - Threshold tests: history length < 2 returns None; length == 2 computes a float.


class TestProviderParsingAndThresholds(test_app.BaseDataServiceTest):
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_day_gainers_parsing_raw_json_and_limit(self, mock_execute_request):
        """DayGainersSource: mock raw screener JSON and enforce per-industry limit."""
        from providers.yfin.market_data_provider import DayGainersSource

        # Mock the response from the direct API call
        mock_execute_request.return_value = {
            "finance": {
                "result": [
                    {
                        "quotes": [
                            {"symbol": "AAPL", "industry": "Consumer Electronics"},
                            {"symbol": "SONY", "industry": "Consumer Electronics"},
                            {"symbol": "MSFT", "industry": "Software - Infrastructure"},
                            {"symbol": None, "industry": "Consumer Electronics"},   # ignored
                            {"symbol": "NVDA", "industry": None},                   # ignored
                        ]
                    }
                ]
            }
        }

        source = DayGainersSource()
        data = source.get_industry_top_tickers(per_industry_limit=1)
        # Enforce limit = 1
        self.assertIn("Consumer Electronics", data)
        self.assertEqual(data["Consumer Electronics"], ["AAPL"])
        self.assertIn("Software - Infrastructure", data)
        self.assertEqual(data["Software - Infrastructure"], ["MSFT"])
        # Types
        self.assertIsInstance(data, dict)
        for k, v in data.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, list)
            for s in v:
                self.assertIsInstance(s, str)

    @patch('providers.yfin.market_data_provider.price_provider.get_stock_data')
    def test_return_calculator_threshold_below_two_returns_none(self, mock_ticker_cls):
        """ReturnCalculator.one_month_change: len(closes) < 2 fails gracefully."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        # History with only one 'Close' value -> below threshold
        df = pd.DataFrame({"Close": [100.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        calc = ReturnCalculator()
        result = calc.one_month_change("AAPL")
        self.assertIsNone(result)

    @patch('providers.yfin.market_data_provider.price_provider.get_stock_data')
    def test_return_calculator_threshold_exact_two_passes(self, mock_ticker_cls):
        """ReturnCalculator.one_month_change: len(closes) == 2 computes percentage."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        # Start=100, End=110 => 10% -> rounded(10.0, 2) = 10.0
        df = pd.DataFrame({"Close": [100.0, 110.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        calc = ReturnCalculator()
        result = calc.one_month_change("AAPL")
        self.assertIsInstance(result, float)
        self.assertEqual(result, 10.0)

    @patch('providers.yfin.market_data_provider.price_provider.get_stock_data')
    def test_return_calculator_missing_close_column(self, mock_get_stock_data):
        """ReturnCalculator.one_month_change: missing 'Close' column returns None."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        mock_get_stock_data.return_value = [
            {'open': 1.0, 'formatted_date': '2025-01-01'}, 
            {'open': 2.0, 'formatted_date': '2025-01-02'}
        ]

        calc = ReturnCalculator()
        result = calc.one_month_change("MSFT")
        self.assertIsNone(result)

    @patch('providers.yfin.market_data_provider.price_provider.get_stock_data')
    def test_return_calculator_history_returns_empty(self, mock_get_stock_data):
        """ReturnCalculator.one_month_change: empty history returns None."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        mock_get_stock_data.return_value = []

        calc = ReturnCalculator()
        result = calc.one_month_change("NVDA")
        self.assertIsNone(result)

class TestProviderLogic(test_app.BaseDataServiceTest):
    """Unit tests for provider-level business logic, independent of Flask routes."""

    @patch('providers.yfin.market_data_provider.yf.Industry')
    @patch('providers.yfin.market_data_provider.yahoo_client.execute_request')
    def test_yahoo_sector_source_parsing_and_dedup(self, mock_search, mock_industry_cls):
        """YahooSectorIndustrySource: Test symbol parsing and list merging/deduplication."""
        from providers.yfin.market_data_provider import YahooSectorIndustrySource

        # Arrange
        mock_industry_instance = MagicMock()
        # Table with 'name' column needing parsing, no 'symbol' column
        perf_df = pd.DataFrame({"name": ["NVIDIA (NVDA)", "AMD (AMD)", "Intel Corp"]})
        # Table with overlapping and new symbols
        growth_df = pd.DataFrame({"symbol": ["GOOG", "NVDA"]})
        
        mock_industry_instance.top_performing_companies = perf_df
        mock_industry_instance.top_growth_companies = growth_df
        mock_industry_cls.return_value = mock_industry_instance
        
        # Mock the fallback search for 'Intel Corp'
        mock_search.return_value = {"quotes": [{"symbol": "INTC", "quoteType": "EQUITY"}]}

        # Act
        source = YahooSectorIndustrySource(sector_keys=['technology']) # Force one sector
        # Mock the discovery part to simplify
        source._discover_sector_keys = lambda: ['technology']
        # Mock Sector to return a dummy industries DataFrame
        with patch('providers.yfin.market_data_provider.yf.Sector') as mock_sector_cls:
            mock_sector_instance = MagicMock()
            mock_sector_instance.industries = pd.DataFrame(index=['semiconductors'])
            mock_sector_cls.return_value = mock_sector_instance
            
            result = source.get_industry_top_tickers(per_industry_limit=5)

        # Assert
        self.assertIn("semiconductors", result)
        # Expected order: perf_df symbols first, then unique growth_df symbols
        # NVDA, AMD from perf_df
        # INTC from search fallback on perf_df
        # GOOG from growth_df (NVDA is a duplicate and should be ignored)
        expected_tickers = ["NVDA", "AMD", "INTC", "GOOG"]
        self.assertEqual(result["semiconductors"], expected_tickers)

    @patch('providers.yfin.market_data_provider.price_provider.get_stock_data')
    def test_return_calculator_logic(self, mock_get_price_data):
        """ReturnCalculator.one_month_change: Test various data scenarios."""
        from providers.yfin.market_data_provider import ReturnCalculator
        from datetime import date, timedelta

        today = date.today()
        calc = ReturnCalculator()

        # Case 1: len(series) < 2 -> None
        mock_get_price_data.return_value = [
            {'close': 100.0, 'formatted_date': (today - timedelta(days=5)).strftime('%Y-%m-%d')}
        ]
        self.assertIsNone(calc.one_month_change("TICK1"))

        # Case 2: len(series) == 2 -> Correct calculation
        mock_get_price_data.return_value = [
            {'close': 100.0, 'formatted_date': (today - timedelta(days=30)).strftime('%Y-%m-%d')},
            {'close': 110.0, 'formatted_date': (today - timedelta(days=2)).strftime('%Y-%m-%d')}
        ]
        self.assertEqual(calc.one_month_change("TICK2"), 10.0)

        # Case 3: Empty data -> None
        mock_get_price_data.return_value = []
        self.assertIsNone(calc.one_month_change("TICK3"))

        # Case 4: None data -> None
        mock_get_price_data.return_value = None
        self.assertIsNone(calc.one_month_change("TICK4"))

        # Case 5: Today's partial bar is correctly excluded
        mock_get_price_data.return_value = [
            {'close': 100.0, 'formatted_date': (today - timedelta(days=30)).strftime('%Y-%m-%d')},
            {'close': 110.0, 'formatted_date': (today - timedelta(days=2)).strftime('%Y-%m-%d')},
            {'close': 999.0, 'formatted_date': today.strftime('%Y-%m-%d')} # This should be ignored
        ]
        self.assertEqual(calc.one_month_change("TICK5"), 10.0)

if __name__ == '__main__':
    unittest.main()
