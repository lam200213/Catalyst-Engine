# backend-services/analysis-service/tests/unit/test_unit.py
import unittest
import os
import sys
from unittest.mock import patch

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import (
    prepare_historical_data,
    calculate_sma_series,
)

from vcp_logic import (
    find_one_contraction,
    find_volatility_contraction_pattern
)

# --- Test Data ---
def get_vcp_test_data():
    """Generates a predictable dataset known to contain VCPs."""
    prices = [100, 105, 102, 108, 104, 100, 103, 101, 98]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    historical_data = [{'formatted_date': d, 'open': p-1, 'high': p+1, 'low': p-1, 'close': p, 'volume': 1000, 'adjclose': p} for d, p in zip(dates, prices)]
    return historical_data, prices, dates
def get_flat_test_data():
    """Generates data with no volatility."""
    prices = [100] * 20
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    return prices, dates

def get_trend_test_data(up=True):
    """Generates data in a steady trend."""
    prices = [100 + i if up else 100 - i for i in range(20)]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    return prices, dates

def get_known_vcp_data_for_accuracy():
    """Returns a curated dataset for accuracy testing of pivot/stop-loss."""
    historical_prices = [
        {'formatted_date': '2024-01-01', 'close': 100.0}, {'formatted_date': '2024-01-02', 'close': 102.0},
        {'formatted_date': '2024-01-03', 'close': 101.0}, {'formatted_date': '2024-01-04', 'close': 103.0},
        {'formatted_date': '2024-01-05', 'close': 105.0}, # High 1 (105.0)
        {'formatted_date': '2024-01-06', 'close': 104.0}, {'formatted_date': '2024-01-07', 'close': 102.0},
        {'formatted_date': '2024-01-08', 'close': 100.0}, {'formatted_date': '2024-01-09', 'close': 98.0},
        {'formatted_date': '2024-01-10', 'close': 96.0}, # Low 1 (96.0)
        {'formatted_date': '2024-01-11', 'close': 97.0}, {'formatted_date': '2024-01-12', 'close': 99.0},
        {'formatted_date': '2024-01-13', 'close': 101.0}, {'formatted_date': '2024-01-14', 'close': 103.0},
        {'formatted_date': '2024-01-15', 'close': 104.0}, # High 2 (104.0)
        {'formatted_date': '2024-01-16', 'close': 103.0}, {'formatted_date': '2024-01-17', 'close': 101.0},
        {'formatted_date': '2024-01-18', 'close': 99.0}, {'formatted_date': '2024-01-19', 'close': 97.0},
        {'formatted_date': '2024-01-20', 'close': 95.0}, # Low 2 (95.0)
        {'formatted_date': '2024-01-21', 'close': 96.0}, {'formatted_date': '2024-01-22', 'close': 98.0},
        {'formatted_date': '2024-01-23', 'close': 100.0}, {'formatted_date': '2024-01-24', 'close': 102.0},
        {'formatted_date': '2024-01-25', 'close': 103.0}, # High 3 (103.0)
        {'formatted_date': '2024-01-26', 'close': 102.0}, {'formatted_date': '2024-01-27', 'close': 100.0},
        {'formatted_date': '2024-01-28', 'close': 98.0}, {'formatted_date': '2024-01-29', 'close': 96.0},
        {'formatted_date': '2024-01-30', 'close': 94.0}, # Low 3 (94.0)
        {'formatted_date': '2024-01-31', 'close': 95.0}, {'formatted_date': '2024-02-01', 'close': 97.0},
        {'formatted_date': '2024-02-02', 'close': 99.0}, {'formatted_date': '2024-02-03', 'close': 101.0},
        {'formatted_date': '2024-02-04', 'close': 103.0}, {'formatted_date': '2024-02-05', 'close': 105.0},
    ]
    expected_pivot = 103.0 * 1.01
    expected_stop_loss = 94.0 * 0.99
    return historical_prices, expected_pivot, expected_stop_loss

# --- Test Cases ---

class TestHelperFunctions(unittest.TestCase):
    """Tests for pure helper functions."""
    def test_prepare_data_success(self):
        raw_data, original_prices, original_dates = get_vcp_test_data()
        unsorted_raw_data = raw_data[::-1]
        prices, dates, sorted_data = prepare_historical_data(unsorted_raw_data)
        self.assertEqual(prices, original_prices)
        self.assertEqual(dates, original_dates)
        self.assertEqual(sorted_data[0]['formatted_date'], '2024-01-01')

    def test_prepare_data_empty_and_none(self):
        self.assertEqual(prepare_historical_data([]), ([], [], []))
        self.assertEqual(prepare_historical_data(None), ([], [], []))

    def test_calculate_sma_series_success(self):
        prices = [10, 20, 30, 40, 50]
        dates = [f"2024-01-0{i+1}" for i in range(5)]
        sma_series = calculate_sma_series(prices, dates, 3)
        self.assertEqual(len(sma_series), 3)
        self.assertAlmostEqual(sma_series[0]['value'], 20.0)
        self.assertEqual(sma_series[-1]['time'], '2024-01-05')

    def test_calculate_sma_series_insufficient_data(self):
        prices = [10, 20]
        dates = ["2024-01-01", "2024-01-02"]
        sma_series = calculate_sma_series(prices, dates, 5)
        self.assertEqual(sma_series, [])

class TestVCPAlgorithm(unittest.TestCase):
    """Tests for the core VCP detection algorithm."""
    def test_find_one_contraction_success(self):
        _, prices, _ = get_vcp_test_data()
        with patch('vcp_logic.COUNTER_THRESHOLD', 2):
            contraction = find_one_contraction(prices, 0)
            self.assertIsNotNone(contraction)
            self.assertEqual(contraction, (3, 108, 8, 98))

    def test_vcp_with_no_contractions(self):
        up_prices, _ = get_trend_test_data(up=True)
        down_prices, _ = get_trend_test_data(up=False)
        flat_prices, _ = get_flat_test_data()
        self.assertEqual(find_volatility_contraction_pattern(up_prices), [])
        self.assertEqual(find_volatility_contraction_pattern(down_prices), [])
        self.assertEqual(find_volatility_contraction_pattern(flat_prices), [])

class TestVCPAccuracy(unittest.TestCase):
    """Data-driven tests to ensure VCP calculations are accurate."""
    def test_vcp_pivot_and_stop_loss_calculation_accuracy(self):
        raw_prices, expected_pivot, expected_stop_loss = get_known_vcp_data_for_accuracy()
        prices, _, _ = prepare_historical_data(raw_prices)
        tolerance = 0.02
        vcp_results = find_volatility_contraction_pattern(prices)
        self.assertTrue(vcp_results, "No VCPs detected, but expected at least one.")
        
        last_high_price = vcp_results[-1][1]
        last_low_price = vcp_results[-1][3]
        calculated_pivot = last_high_price * 1.01
        calculated_stop_loss = last_low_price * 0.99

        pivot_diff = abs(calculated_pivot - expected_pivot) / expected_pivot
        self.assertTrue(pivot_diff <= tolerance)

        stop_loss_diff = abs(calculated_stop_loss - expected_stop_loss) / expected_stop_loss
        self.assertTrue(stop_loss_diff <= tolerance)

if __name__ == '__main__':
    unittest.main()
#  End of new consolidated unit test file.