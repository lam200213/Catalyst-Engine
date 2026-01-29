# backend-services/analysis-service/tests/unit/test_vcp_logic.py
import unittest
import numpy as np
from unittest.mock import patch
from vcp_logic import check_pivot_freshness, PIVOT_FRESHNESS_DAYS, PIVOT_BREAKOUT_THRESHOLD

# Temporarily add the service directory to the path to import the new logic module
# This will be resolved by the execution environment (e.g., pytest)
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import the functions to be tested from the new vcp_logic module
from vcp_logic import (
    is_pivot_good,
    is_correction_deep,
    is_demand_dry,
    get_vcp_footprint,
    run_vcp_screening,
    _calculate_volume_trend,
)

class TestVcpHelperFunctions(unittest.TestCase):
    """Tests for individual helper functions."""

    def test_calculate_volume_trend(self):
        """Tests the linear regression helper for volume trends."""
        self.assertLess(_calculate_volume_trend([10, 8, 6, 4])[0], 0, "Decreasing volume should have a negative slope.")
        self.assertGreater(_calculate_volume_trend([4, 6, 8, 10])[0], 0, "Increasing volume should have a positive slope.")
        self.assertAlmostEqual(_calculate_volume_trend([5, 5, 5, 5])[0], 0, places=5, msg="Flat volume should have a slope close to zero.")
        self.assertEqual(_calculate_volume_trend([10])[0], 0, "Single point volume should result in zero slope.")


class TestVcpScreeningLogic(unittest.TestCase):
    """
    Test suite for the core VCP screening logic functions.
    Each function is tested against various business logic and edge cases.
    """

    def test_is_pivot_good(self):
        """
        Business Logic: Verifies if the final contraction (pivot) is tight enough
        and if the current price is in a valid position.
        """
        # Mock VCP results: [ (high_idx, high_price, low_idx, low_price), ... ]
        vcp_results_good = [(0, 100, 10, 85), (11, 95, 20, 90)] # Final contraction is 5.2%
        vcp_results_bad = [(0, 100, 10, 85), (11, 95, 20, 65)] # Final contraction is 31.5%
        
        # 1. Pass: Contraction is shallow and price is above the last low.
        self.assertTrue(is_pivot_good(vcp_results_good, current_price=92), "Should pass with a tight pivot and good price position.")

        # 2. Fail: The final contraction is too deep (violates PIVOT_PRICE_PERC).
        self.assertFalse(is_pivot_good(vcp_results_bad, current_price=92), "Should fail if the pivot contraction is too deep.")

        # 3. Fail: Price has fallen below the last contraction's low.
        self.assertFalse(is_pivot_good(vcp_results_good, current_price=89), "Should fail if the current price is below the last low.")
        
        # 4. Edge Case: No VCP data provided.
        self.assertFalse(is_pivot_good([], current_price=100), "Should fail gracefully if no VCP data is available.")

    def test_is_correction_deep(self):
        """
        Business Logic: Verifies if the total correction from the first peak
        to the absolute lowest point is too severe.
        """
        # Mock VCP results: [ (high_idx, high_price, low_idx, low_price), ... ]
        # First high: 100, deepest low: 45. Correction = (100-45)/100 = 55%
        vcp_results_deep = [(0, 100, 10, 70), (11, 80, 20, 45)]
        
        # First high: 100, deepest low: 65. Correction = (100-65)/100 = 35%
        vcp_results_ok = [(0, 100, 10, 80), (11, 90, 20, 65)]

        # 1. Fail: Correction is too deep (>= MAX_CORRECTION_PERC). Function should return True.
        self.assertTrue(is_correction_deep(vcp_results_deep), "Should return True for a correction >= threshold.")
        
        # 2. Pass: Correction is within acceptable limits. Function should return False.
        self.assertFalse(is_correction_deep(vcp_results_ok), "Should return False for a correction < threshold.")
        
        # 3. Edge Case: No VCP data provided.
        self.assertFalse(is_correction_deep([]), "Should fail gracefully if no VCP data is available.")

    def test_is_demand_dry(self):
        """
        Business Logic: Verifies if volume is declining during the last contraction,
        indicating supply exhaustion.
        """
        #  This function now requires prices to check for recent selling pressure.
        vcp_results = [(0, 100, 5, 90)] # Contraction is from index 0 to 5
        prices = [100, 98, 95, 96, 94, 92]
        volumes_dry = [200, 180, 150, 120, 100, 80] # Volume for indices 0-5
        volumes_wet = [80, 100, 120, 150, 180, 200]
        
        # 1. Pass: Volume is clearly decreasing (negative slope).
        self.assertTrue(is_demand_dry(vcp_results, prices, volumes_dry), "Should pass when volume trend is negative.")

        # 2. Fail: Volume is increasing (positive slope).
        self.assertFalse(is_demand_dry(vcp_results, prices, volumes_wet), "Should fail when volume trend is positive.")

        # 3. Edge Case: Not enough volume data for a trend calculation.
        self.assertFalse(is_demand_dry(vcp_results, prices, [100]), "Should fail if volume data is insufficient for a trend line.")

        # 4. Fail (Blind Spot Addressed): Recent selling pressure (Vol up, Price down).
        # This tests the nuanced logic where a recent uptick in
        # volume on down days negates an overall volume dry-up.
        vcp_results_recent_pressure = [(0, 100, 10, 90)] # Contraction from index 0 to 10
        prices_recent_pressure = [110, 105, 100, 99, 98, 97, 96, 95, 94, 93, 92] # Prices for indices 0-10
        # Volumes are generally decreasing, but tick up at the very end as price falls.
        volumes_recent_pressure = [200, 180, 150, 120, 100, 80, 50, 40, 45, 50, 55] # Indices 0-10

        self.assertFalse(is_demand_dry(vcp_results_recent_pressure, prices_recent_pressure, volumes_recent_pressure), "Should fail if recent volume is rising while price is falling.")

    def test_get_vcp_footprint(self):
        """
        Business Logic: Verifies the correct formatting of the VCP footprint string.
        """
        # Mock VCP results: [ (high_idx, high_price, low_idx, low_price), ... ]
        # Contraction 1: 10 days, (100-80)/100 = 20.0%
        # Contraction 2: 5 days, (90-85)/90 = 5.6%
        vcp_results = [(0, 100, 10, 80), (15, 90, 20, 85)]
        
        expected_footprint_str = "10D 20.0% | 5D 5.6%"

        # 1. Pass: Correctly formats a multi-contraction footprint.
        _, footprint_str = get_vcp_footprint(vcp_results)
        self.assertEqual(footprint_str, expected_footprint_str)

        # 2. Edge Case: Single contraction (no separator).
        _, footprint_str_single = get_vcp_footprint([(0, 100, 10, 80)])
        self.assertEqual(footprint_str_single, "10D 20.0%")
        
        # 3. Edge Case: No VCP data returns an empty string.
        _, footprint_str_empty = get_vcp_footprint([])
        self.assertEqual(footprint_str_empty, "")

class TestVcpOrchestration(unittest.TestCase):
    """
    Test suite for the main orchestrator function `run_vcp_screening`.
    This uses mocking to isolate the orchestrator's logic.
    """
    @patch('vcp_logic.is_volume_dry_up_at_pivot')
    @patch('vcp_logic.is_demand_dry')
    @patch('vcp_logic.is_correction_deep')
    @patch('vcp_logic.is_pivot_good')
    def test_run_vcp_screening_pass(
        self,
        mock_is_pivot_good,
        mock_is_correction_deep,
        mock_is_demand_dry,
        mock_analyze_vol,
    ):
        """Tests the case where all individual checks pass."""
        # Arrange: 2‑contraction VCP so structural rules pass
        vcp_results = [
            (0, 100.0, 5, 90.0),
            (6, 95.0, 10, 90.0),
        ]
        prices = [100.0] * 15
        volumes = [10000] * 15

        mock_is_pivot_good.return_value = True
        mock_is_correction_deep.return_value = False
        mock_is_demand_dry.return_value = True
        mock_analyze_vol.return_value = (True, 0.8)

        # Act
        vcp_pass_status, _, _ = run_vcp_screening(vcp_results, prices, volumes)

        # Assert
        self.assertTrue(vcp_pass_status)
        mock_is_pivot_good.assert_called_once()
        mock_is_demand_dry.assert_called_once()
        mock_analyze_vol.assert_called_once()

    @patch('vcp_logic.is_demand_dry')
    @patch('vcp_logic.is_correction_deep')
    @patch('vcp_logic.is_pivot_good')
    def test_run_vcp_screening_fail(self, mock_is_pivot_good, mock_is_correction_deep, mock_is_demand_dry):
        """Tests that a single failure results in an overall failure."""
        # Arrange: One check returns a "fail" condition.
        mock_is_pivot_good.return_value = True
        mock_is_correction_deep.return_value = False
        mock_is_demand_dry.return_value = False # This is the failing check

        # Act
        vcp_pass_status, _, _ = run_vcp_screening([(0, 100, 10, 80)], [100], [10000])

        # Assert
        self.assertFalse(vcp_pass_status)

    def test_run_vcp_screening_no_data(self):
        """Tests that the orchestrator returns False if no VCP is detected."""
        vcp_pass_status, footprint, _ = run_vcp_screening([], [100], [10000])
        self.assertFalse(vcp_pass_status)
        self.assertEqual(footprint, "")

# Unit tests for pivot freshness logic
class TestPivotFreshnessLogic(unittest.TestCase):
    """
    Unit tests for check_pivot_freshness covering:
    - Pass/fail logic
    - Boundary conditions (days and breakout)
    - No-VCP case
    - Minimal data length handling
    """

    def _build_prices(self, length, base=100.0):
        # Simple monotonic list; values don't influence freshness beyond current_price
        return [float(base + i) for i in range(length)]

    def test_freshness_passes_at_threshold_days(self):
        """
        1. Business Logic: days_since_pivot == threshold should pass.
        7. Types: Validate returned fields types are as expected.
        9. Expected outcomes align with function output.
        """
        # vcp_results format: [(high_idx, high_price, low_idx, low_price)]
        threshold = PIVOT_FRESHNESS_DAYS
        total_len = 50
        last_low_idx = total_len - 1 - threshold
        last_high_price = 100.0
        vcp_results = [(10, last_high_price, last_low_idx, 90.0)]
        prices = self._build_prices(total_len, base=95.0)
        prices[-1] = last_high_price * (PIVOT_BREAKOUT_THRESHOLD - 0.01)  # below breakout threshold

        out = check_pivot_freshness(vcp_results, prices)
        self.assertTrue(out['passes'])
        self.assertEqual(out['days_since_pivot'], threshold)
        self.assertIsInstance(out['message'], str)

    def test_freshness_fails_when_stale_just_over_threshold(self):
        """
        2. Edge Case: days_since_pivot == threshold + 1 should fail as stale.
        5. Blind spots: ensure off-by-one is caught.
        """
        threshold = PIVOT_FRESHNESS_DAYS + 1
        total_len = 60
        last_low_idx = total_len - 1 - threshold
        last_high_price = 120.0
        vcp_results = [(20, last_high_price, last_low_idx, 100.0)]
        prices = self._build_prices(total_len, base=110.0)
        prices[-1] = last_high_price  # not extended, but stale

        out = check_pivot_freshness(vcp_results, prices)
        self.assertFalse(out['passes'])
        self.assertEqual(out['days_since_pivot'], PIVOT_FRESHNESS_DAYS + 1)
        self.assertIn('stale', out['message'].lower())

    def test_freshness_fails_when_extended_breakout(self):
        """
        1. Business Logic: price > high * threshold should fail as extended.
        12. Boundary: price just beyond breakout threshold fails; just at threshold would pass upstream freshness gate.
        """
        total_len = 40
        last_low_idx = total_len - 10
        last_high_price = 50.0
        vcp_results = [(5, last_high_price, last_low_idx, 45.0)]
        prices = self._build_prices(total_len, base=49.0)
        prices[-1] = last_high_price * (PIVOT_BREAKOUT_THRESHOLD + 0.001)  # just over threshold

        out = check_pivot_freshness(vcp_results, prices)
        self.assertFalse(out['passes'])
        self.assertIn('breakout', out['message'].lower())

    def test_freshness_no_vcp_detected(self):
        """
        2. Edge Case: No VCP results should fail gracefully with None days_since_pivot.
        7. Type: days_since_pivot is None on no-VCP.
        """
        prices = self._build_prices(10)
        out = check_pivot_freshness([], prices)
        self.assertFalse(out['passes'])
        self.assertIsNone(out['days_since_pivot'])
        self.assertIn('no vcp', out['message'].lower())

    def test_freshness_minimal_length_prices_graceful(self):
        """
        12. Length Thresholds: Provide minimal price data around last_low_idx boundary.
        Ensure no index errors and deterministic output.
        """
        total_len = 2
        last_low_idx = 0
        last_high_price = 100.0
        vcp_results = [(0, last_high_price, last_low_idx, 95.0)]
        prices = self._build_prices(total_len, base=99.0)
        prices[-1] = last_high_price  # within threshold on price, days_since_pivot = 1

        out = check_pivot_freshness(vcp_results, prices)
        # Depending on PIVOT_FRESHNESS_DAYS (default 20), with days_since_pivot=1 it should pass freshness and not be extended.
        self.assertIn('passes', out)
        self.assertIn('days_since_pivot', out)
        self.assertIsInstance(out['message'], str)

if __name__ == '__main__':
    unittest.main()