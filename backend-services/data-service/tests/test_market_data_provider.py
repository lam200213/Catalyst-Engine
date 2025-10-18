# backend-services/data-service/tests/test_market_data_provider.py

import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, List

from app import app

# Reuse the same base test setup patterns as existing tests
# to maintain consistency in mocking cache and db.
from . import test_app

# Tests for market sector/industry and day_gainers endpoints, and 1m return batch.
# Also includes provider-level unit tests that mock raw inputs to validate parsing and thresholds.

class TestSectorIndustryEndpoint(test_app.BaseDataServiceTest):
    @patch('app.SectorIndustrySource')
    def test_sectors_industries_success_200(self, mock_source_cls):
        """GET /market/sectors/industries: success path and structure/type checks."""
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

    @patch('app.SectorIndustrySource')
    def test_sectors_industries_empty_404(self, mock_source_cls):
        """GET /market/sectors/industries: returns 404 when source returns empty mapping."""
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.return_value = {}
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/sectors/industries')
        self.assertEqual(resp.status_code, 404)
        self.assertIn("message", resp.json)
        self.assertIn("Could not retrieve sector/industry data.", resp.json["message"])

    @patch('app.SectorIndustrySource')
    def test_sectors_industries_exception_500(self, mock_source_cls):
        """GET /market/sectors/industries: security—generic 500 without leaking details."""
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.side_effect = RuntimeError("Backend failure")
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/sectors/industries')
        self.assertEqual(resp.status_code, 500)
        self.assertIn("error", resp.json)
        self.assertEqual(resp.json["error"], "Internal server error")


class TestDayGainersEndpoint(test_app.BaseDataServiceTest):
    @patch('app.DayGainersSource')
    def test_day_gainers_success_200(self, mock_source_cls):
        """GET /market/screener/day_gainers: success path and structure/type checks."""
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

    @patch('app.DayGainersSource')
    def test_day_gainers_empty_404(self, mock_source_cls):
        """GET /market/screener/day_gainers: returns 404 when source returns empty mapping."""
        mock_source = MagicMock()
        mock_source.get_industry_top_tickers.return_value = {}
        mock_source_cls.return_value = mock_source

        resp = self.client.get('/market/screener/day_gainers')
        self.assertEqual(resp.status_code, 404)
        self.assertIn("message", resp.json)
        self.assertIn("Could not retrieve day gainers data.", resp.json["message"])

    @patch('app.DayGainersSource')
    def test_day_gainers_exception_500(self, mock_source_cls):
        """GET /market/screener/day_gainers: security—generic 500 without leaking details."""
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

    @patch('providers.yfin.market_data_provider.yf.Ticker')
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

    @patch('providers.yfin.market_data_provider.yf.Ticker')
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

    @patch('providers.yfin.market_data_provider.yf.Ticker')
    def test_return_calculator_missing_close_column(self, mock_ticker_cls):
        """ReturnCalculator.one_month_change: missing 'Close' column returns None."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        df = pd.DataFrame({"Open": [1.0, 2.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        calc = ReturnCalculator()
        result = calc.one_month_change("MSFT")
        self.assertIsNone(result)

    @patch('providers.yfin.market_data_provider.yf.Ticker')
    def test_return_calculator_history_returns_empty(self, mock_ticker_cls):
        """ReturnCalculator.one_month_change: empty history returns None."""
        import pandas as pd
        from providers.yfin.market_data_provider import ReturnCalculator

        df = pd.DataFrame({"Close": []})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        calc = ReturnCalculator()
        result = calc.one_month_change("NVDA")
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
