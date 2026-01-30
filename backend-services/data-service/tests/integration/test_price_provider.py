# backend-services/data-service/tests/unit/test_price_provider.py
import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
import os
import sys
from curl_cffi.requests import errors as cffi_errors
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from providers.yfin import price_provider
from tests.common.test_fixtures import make_chart_payload

class TestYFinancePriceProvider(unittest.TestCase):
    """Tests for the yfinance price data provider."""

    def setUp(self):
        """Set up a ThreadPoolExecutor for tests."""
        self.executor = ThreadPoolExecutor(max_workers=1)

    def tearDown(self):
        """Shutdown the ThreadPoolExecutor."""
        self.executor.shutdown(wait=True)

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    @patch('providers.yfin.price_provider.is_ticker_delisted', return_value=True)
    def test_get_stock_data_skips_single_delisted_ticker(self, mock_is_delisted, mock_fetch):
        """
        Tests that get_stock_data (single mode) skips API calls for a delisted ticker.
        """
        # --- Act ---
        result = price_provider.get_stock_data('DELISTED', self.executor, period="1y")

        # --- Assert ---
        self.assertIsNone(result)
        mock_is_delisted.assert_called_once_with('DELISTED')
        mock_fetch.assert_not_called()

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    @patch('providers.yfin.price_provider.is_ticker_delisted')
    def test_get_stock_data_filters_delisted_in_batch(self, mock_is_delisted, mock_fetch):
        """
        Tests that get_stock_data (batch mode) filters out delisted tickers.
        """
        # --- Arrange ---
        # Mock is_ticker_delisted to return True only for 'BADD'
        mock_is_delisted.side_effect = lambda ticker: ticker == 'BADD'
        # Mock the actual fetcher to return simple data
        mock_fetch.return_value = [{"close": 100}]

        # --- Act ---
        results = price_provider.get_stock_data(['GOOD1', 'BADD', 'GOOD2'], self.executor, period="1y")

        # --- Assert ---
        # Check that the delisted check was called for all tickers
        self.assertEqual(mock_is_delisted.call_count, 3)
        
        # Check that the API fetch was only called for the good tickers
        self.assertEqual(mock_fetch.call_count, 2)
        
        # Verify the final result dictionary does not contain the delisted ticker
        self.assertIn('GOOD1', results)
        self.assertIn('GOOD2', results)
        self.assertNotIn('BADD', results)


    def _get_mock_yahoo_response(self):
        return {
            'chart': {
                'result': [{
                    'timestamp': [1672531200, 1672617600],
                    'indicators': {
                        'quote': [{'open': [100, 102], 'high': [105, 106], 'low': [99, 101], 'close': [102, 105], 'volume': [10000, 12000]}],
                        'adjclose': [{'adjclose': [101, 104]}]
                    }
                }]
            }
        }

    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_get_single_ticker_data_success(self, mock_execute_request):
        """Tests a successful fetch and transformation for a single ticker."""
        # --- Arrange ---
        mock_execute_request.return_value = self._get_mock_yahoo_response()

        # --- Act ---
        data = price_provider._get_single_ticker_data('AAPL', period="1y")

        # --- Assert ---
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['formatted_date'], '2023-01-01')
        self.assertEqual(data[0]['close'], 102)
        self.assertEqual(data[1]['volume'], 12000)

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_get_single_ticker_data_api_404(self, mock_execute_request, mock_mark_delisted):
        """Tests that a 404 response correctly marks the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=404)
        mock_execute_request.side_effect = cffi_errors.RequestsError("404 Error", response=mock_response)

        # --- Act ---
        result = price_provider._get_single_ticker_data('DELISTED', period="1y")

        # --- Assert ---
        self.assertIsNone(result) # The function should return None on failure
        mock_mark_delisted.assert_called_once_with('DELISTED', "Yahoo Finance API call failed with status 404 for chart data.")

    @patch('providers.yfin.price_provider.mark_ticker_as_delisted')
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_provider_does_not_mark_delisted_on_other_http_errors(self, mock_execute_request, mock_mark_delisted):
        """Tests that a non-404 HTTP error does NOT mark the ticker as delisted."""
        # --- Arrange ---
        mock_response = MagicMock(status_code=500)
        mock_execute_request.side_effect = cffi_errors.RequestsError("500 Server Error", response=mock_response)

        # --- Act ---
        data = price_provider._get_single_ticker_data('SERVERERROR', period="1y")

        # --- Assert ---
        self.assertIsNone(data)
        mock_mark_delisted.assert_not_called()
            
    @patch('providers.yfin.price_provider.yahoo_client.execute_request')
    def test_ticker_sanitization(self, mock_execute_request):
        """Tests that ticker symbols are correctly sanitized."""
        # --- Arrange ---
        mock_execute_request.return_value = self._get_mock_yahoo_response()
        dirty_ticker = 'BRK/A  '
        expected_sanitized_ticker = 'BRK-A'

        # --- Act ---
        price_provider._get_single_ticker_data(dirty_ticker, period="1y")

        # --- Assert ---
        mock_execute_request.assert_called_once()
        request_url = mock_execute_request.call_args[0][0]
        self.assertIn(expected_sanitized_ticker, request_url)
        self.assertNotIn(dirty_ticker, request_url)

    @patch('providers.yfin.price_provider._get_single_ticker_data')
    def test_get_stock_data_batch_with_failures(self, mock_get_single):
        """Tests the batch function with a mix of successful and failed tickers."""
        # --- Arrange ---
        def side_effect(ticker, start_date=None, period=None, interval="1d"): # Correct signature
            if ticker == 'AAPL':
                return [{"close": 150}]
            elif ticker == 'FAIL':
                # The function is expected to handle its own exceptions and return None on failure
                raise Exception("API failure")
            return None
        mock_get_single.side_effect = side_effect

        # --- Act ---
        results = price_provider.get_stock_data(['AAPL', 'FAIL', 'NONE'], self.executor, period="1y")

        # --- Assert ---
        self.assertIn('AAPL', results)
        self.assertEqual(results['AAPL'], [{"close": 150}])
        self.assertIn('FAIL', results)
        self.assertIsNone(results['FAIL'])
        self.assertIn('NONE', results)
        self.assertIsNone(results['NONE'])

    def test_transform_yahoo_response_missing_timestamp_returns_none(self):
        """
        Week 9 Plan 1: chart.result[0].timestamp may be missing for delisted/stale tickers.
        Expected: transform returns None (no exception).
        """
        bad = make_chart_payload(include_timestamp=False)
        out = price_provider._transform_yahoo_response(bad, "NOTS")
        self.assertIsNone(out)

    @patch("providers.yfin.price_provider.yahoo_client.execute_request")
    def test_get_single_ticker_data_missing_timestamp_returns_none(self, mock_execute_request):
        """
        Week 9 Plan 1: _get_single_ticker_data should not crash on missing timestamp.
        Expected: returns None, does not mark delisted (not a 404).
        """
        mock_execute_request.return_value = make_chart_payload(include_timestamp=False)
        out = price_provider._get_single_ticker_data("NOTS", period="1y")
        self.assertIsNone(out)

    def test_transform_yahoo_response_missing_result_returns_none(self):
        bad = {"chart": {"result": []}}
        out = price_provider._transform_yahoo_response(bad, "EMPTY")
        self.assertIsNone(out)

    # Test for the "No Market Sessions" symptom (empty timestamp)
    def test_transform_yahoo_response_handles_missing_timestamp_gracefully(self):
        """
        Simulates the scenario where a query window covers only non-trading days (e.g., Sat-Sun).
        Yahoo often returns a valid structure but without the 'timestamp' key.
        The provider should catch the KeyError and return None.
        """
        # A payload structure often seen when no data is available in the range
        empty_window_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "USD", "symbol": "NTLA"},
                        "indicators": {
                            "quote": [{}],
                            "adjclose": [{}]
                        }
                        # 'timestamp' is missing here
                    }
                ],
                "error": None
            }
        }
        
        # Act
        result = price_provider._transform_yahoo_response(empty_window_payload, "NTLA")
        
        # Assert
        self.assertIsNone(result)

    def test_plan_incremental_never_starts_on_weekend(self):
        from datetime import date
        from helper_functions import plan_incremental_price_fetch

        # Simulate cache last bar on Friday
        cached = [{"formatted_date": "2026-01-23", "close": 100, "open": 100, "high": 101, "low": 99, "volume": 1, "adjclose": 100}]

        plan = plan_incremental_price_fetch(
            cached_data=cached,
            req_period=None,
            req_start=None,
            today=date(2026, 1, 28),  # Wednesday
            validate_fn=lambda data, _t: data,
            covers_fn=lambda _data, _p, _s: True,
        )

        self.assertEqual(plan["action"], "fetch_incremental")
        self.assertEqual(plan["start_date"].isoformat(), "2026-01-26")  # Monday, not weekend

    @patch("helper_functions.get_trading_calendar")
    def test_plan_incremental_holiday_aware_returns_cache_when_last_bar_is_previous_session(self, mock_get_cal):
        import helper_functions
        from datetime import date
        from helper_functions import plan_incremental_price_fetch

        # Ensure helper_functions internal calendar cache does not leak across tests
        helper_functions._TRADING_CAL = None

        # Mock NYSE calendar: for Tue 2026-01-20, the previous trading day is Fri 2026-01-16
        mock_calendar = MagicMock()
        # Add columns to dataframe to ensure .empty is False (pandas checks size=rows*cols)
        mock_calendar.schedule.return_value = pd.DataFrame(index=pd.to_datetime(["2026-01-16"]), columns=["market_open"])
        mock_get_cal.return_value = mock_calendar

        cached = [{
            "formatted_date": "2026-01-16",
            "close": 100,
            "open": 100,
            "high": 101,
            "low": 99,
            "volume": 1,
            "adjclose": 100
        }]

        plan = plan_incremental_price_fetch(
            cached_data=cached,
            req_period=None,
            req_start=None,
            today=date(2026, 1, 20),  # Tuesday; Monday is a market holiday (MLK Day)
            validate_fn=lambda data, _t: data,
            covers_fn=lambda _data, _p, _s: True,
        )

        self.assertEqual(plan["action"], "return_cache")
        self.assertIsNone(plan["start_date"])

    @patch("providers.yfin.price_provider.yahoo_client.execute_request")
    @patch("helper_functions.get_trading_calendar")
    def test_get_single_ticker_data_incremental_period2_uses_previous_trading_day(self, mock_get_cal, mock_execute_request):
        import helper_functions

        helper_functions._TRADING_CAL = None

        mock_calendar = MagicMock()
        # Add columns to dataframe to ensure .empty is False
        mock_calendar.schedule.return_value = pd.DataFrame(index=pd.to_datetime(["2026-01-23"]), columns=["market_open"])
        mock_get_cal.return_value = mock_calendar

        mock_execute_request.return_value = make_chart_payload(include_timestamp=False)

        with patch.dict(os.environ, {"YF_TODAY_OVERRIDE": "2026-01-26"}):
            out = price_provider._get_single_ticker_data(
                "NTLA",
                start_date=dt.date(2026, 1, 22),  # Thursday
                interval="1d",
            )

        self.assertIsNone(out)

        params = mock_execute_request.call_args.kwargs["params"]
        p1 = dt.datetime.fromtimestamp(int(params["period1"])).date().isoformat()
        p2 = dt.datetime.fromtimestamp(int(params["period2"])).date().isoformat()

        self.assertEqual(p1, "2026-01-22")
        self.assertEqual(p2, "2026-01-23")  # Friday, previous trading day

    @patch("providers.yfin.price_provider.yahoo_client.execute_request")
    @patch("helper_functions.get_trading_calendar")
    def test_get_single_ticker_data_weekend_window_clamps_to_previous_trading_day(self, mock_get_cal, mock_execute_request):
        import helper_functions

        helper_functions._TRADING_CAL = None

        mock_calendar = MagicMock()
        # Add columns to dataframe to ensure .empty is False
        mock_calendar.schedule.return_value = pd.DataFrame(index=pd.to_datetime(["2026-01-23"]), columns=["market_open"])
        mock_get_cal.return_value = mock_calendar

        mock_execute_request.return_value = make_chart_payload(include_timestamp=False)

        with patch.dict(os.environ, {"YF_TODAY_OVERRIDE": "2026-01-26"}):
            out = price_provider._get_single_ticker_data(
                "NTLA",
                start_date=dt.date(2026, 1, 24),  # Saturday
                interval="1d",
            )

        self.assertIsNone(out)

        params = mock_execute_request.call_args.kwargs["params"]
        p1 = dt.datetime.fromtimestamp(int(params["period1"])).date().isoformat()
        p2 = dt.datetime.fromtimestamp(int(params["period2"])).date().isoformat()

        # start_date is clamped to last completed session (Friday)
        self.assertEqual(p1, "2026-01-23")
        self.assertEqual(p2, "2026-01-23")

    @patch("pandas_market_calendars.get_calendar")
    @patch("helper_functions.previous_trading_day")
    def test_cache_covers_request_uses_previous_trading_day_as_anchor_end(self, mock_prev_trading_day, mock_get_calendar):
        from datetime import date
        from helper_functions import cache_covers_request

        # Force anchor_end to be previous_trading_day(today), not calendar yesterday
        mock_prev_trading_day.return_value = date(2026, 1, 16)

        mock_nyse = MagicMock()

        # Must not be "empty" in pandas; include a column to avoid rows*cols == 0
        mock_nyse.schedule.return_value = pd.DataFrame(
            index=pd.to_datetime(["2025-01-01"]),
            columns=["market_open"]
        )

        mock_get_calendar.return_value = mock_nyse

        # Use <252 unique dates so we do NOT take the row-count fast path.
        # Also make cache_end_dt later than 2026-01-16 so anchor_end should be 2026-01-16.
        cached_data = [
            {"formatted_date": "2025-01-01"},
            {"formatted_date": "2026-01-20"},
        ]

        result = cache_covers_request(cached_data, "1y", None)

        # Assert that calendar schedule was built using anchor_end = previous trading day
        self.assertTrue(mock_get_calendar.called)

        _, kwargs = mock_nyse.schedule.call_args
        self.assertEqual(kwargs["end_date"], date(2026, 1, 16))

        # Optional: keep assertion on return value stable (with our mock schedule, should be True)
        self.assertTrue(result)

    def test_transform_yahoo_response_timestamp_exists_but_values_contain_none(self):
        """
        Messy-but-valid Yahoo payload:
        - timestamp exists
        - OHLC/adjclose arrays contain None values
        Expected: transform does not crash; returns list with N items; None values preserved.
        """
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [1672531200, 1672617600, 1672704000],  # 2023-01-01, 02, 03
                    "indicators": {
                        "quote": [{
                            "open":   [100, None, 102],
                            "high":   [105, 106, None],
                            "low":    [99,  None, 101],
                            "close":  [102, None, 105],
                            "volume": [10000, None, 12000],
                        }],
                        "adjclose": [{
                            "adjclose": [101, None, 104]
                        }]
                    }
                }],
                "error": None
            }
        }

        out = price_provider._transform_yahoo_response(payload, "MESSY")
        self.assertIsNotNone(out)
        self.assertEqual(len(out), 3)

        # Spot-check the "None bar" survives transformation
        self.assertEqual(out[1]["formatted_date"], "2023-01-02")
        self.assertIsNone(out[1]["open"])
        self.assertIsNone(out[1]["close"])
        self.assertIsNone(out[1]["adjclose"])
        self.assertIsNone(out[1]["volume"])

    def test_transform_yahoo_response_timestamp_exists_but_arrays_mismatched_lengths_returns_none(self):
        """
        Messy-but-valid structure but inconsistent lengths:
        - timestamp has 3 items
        - OHLC arrays have only 2 items
        Expected: IndexError is caught and transform returns None.
        """
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [1672531200, 1672617600, 1672704000],
                    "indicators": {
                        "quote": [{
                            "open":   [100, 101],          # shorter than timestamps
                            "high":   [105, 106],
                            "low":    [99, 100],
                            "close":  [102, 103],
                            "volume": [10000, 11000],
                        }],
                        "adjclose": [{
                            "adjclose": [101, 102]         # shorter than timestamps
                        }]
                    }
                }],
                "error": None
            }
        }

        out = price_provider._transform_yahoo_response(payload, "MISMATCH")
        self.assertIsNone(out)