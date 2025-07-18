# backend-services/analysis-service/tests/test_vcp_logic.py
import unittest
import numpy as np
from unittest.mock import patch

# Temporarily add the service directory to the path to import the new logic module
# This will be resolved by the execution environment (e.g., pytest)
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
        # Latest Add: This function now requires prices to check for recent selling pressure.
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
    @patch('vcp_logic.is_demand_dry')
    @patch('vcp_logic.is_correction_deep')
    @patch('vcp_logic.is_pivot_good')
    def test_run_vcp_screening_pass(self, mock_is_pivot_good, mock_is_correction_deep, mock_is_demand_dry):
        """Tests the case where all individual checks pass."""
        # Arrange: All checks return a "pass" condition.
        mock_is_pivot_good.return_value = True
        mock_is_correction_deep.return_value = False # is_deep returns False for a pass
        mock_is_demand_dry.return_value = True

        # Act
        vcp_pass_status, _, _ = run_vcp_screening([(0, 100, 10, 80)], [100], [10000])

        # Assert
        self.assertTrue(vcp_pass_status)
        mock_is_demand_dry.assert_called_once_with([(0, 100, 10, 80)], [100], [10000])

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


if __name__ == '__main__':
    unittest.main()