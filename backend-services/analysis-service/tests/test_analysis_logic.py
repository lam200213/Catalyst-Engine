import unittest
import sys
import os

# Add the parent directory to the path to allow importing app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import find_volatility_contraction_pattern, prepare_historical_data # Assuming this is the main VCP analysis function

def get_known_vcp_data():
    """
    Returns a curated historical price dataset representing a known VCP,
    along with its pre-calculated expected pivot and stop-loss points.
    """
    historical_prices = [
        {'formatted_date': '2024-01-01', 'close': 100.0},
        {'formatted_date': '2024-01-02', 'close': 102.0},
        {'formatted_date': '2024-01-03', 'close': 101.0},
        {'formatted_date': '2024-01-04', 'close': 103.0},
        {'formatted_date': '2024-01-05', 'close': 105.0}, # High 1 (105.0)
        {'formatted_date': '2024-01-06', 'close': 104.0},
        {'formatted_date': '2024-01-07', 'close': 102.0},
        {'formatted_date': '2024-01-08', 'close': 100.0},
        {'formatted_date': '2024-01-09', 'close': 98.0},
        {'formatted_date': '2024-01-10', 'close': 96.0}, # Low 1 (96.0)
        {'formatted_date': '2024-01-11', 'close': 97.0},
        {'formatted_date': '2024-01-12', 'close': 99.0},
        {'formatted_date': '2024-01-13', 'close': 101.0},
        {'formatted_date': '2024-01-14', 'close': 103.0},
        {'formatted_date': '2024-01-15', 'close': 104.0}, # High 2 (104.0)
        {'formatted_date': '2024-01-16', 'close': 103.0},
        {'formatted_date': '2024-01-17', 'close': 101.0},
        {'formatted_date': '2024-01-18', 'close': 99.0},
        {'formatted_date': '2024-01-19', 'close': 97.0},
        {'formatted_date': '2024-01-20', 'close': 95.0}, # Low 2 (95.0)
        {'formatted_date': '2024-01-21', 'close': 96.0},
        {'formatted_date': '2024-01-22', 'close': 98.0},
        {'formatted_date': '2024-01-23', 'close': 100.0},
        {'formatted_date': '2024-01-24', 'close': 102.0},
        {'formatted_date': '2024-01-25', 'close': 103.0}, # High 3 (103.0)
        {'formatted_date': '2024-01-26', 'close': 102.0},
        {'formatted_date': '2024-01-27', 'close': 100.0},
        {'formatted_date': '2024-01-28', 'close': 98.0},
        {'formatted_date': '2024-01-29', 'close': 96.0},
        {'formatted_date': '2024-01-30', 'close': 94.0}, # Low 3 (94.0)
        {'formatted_date': '2024-01-31', 'close': 95.0},
        {'formatted_date': '2024-02-01', 'close': 97.0},
        {'formatted_date': '2024-02-02', 'close': 99.0},
        {'formatted_date': '2024-02-03', 'close': 101.0},
        {'formatted_date': '2024-02-04', 'close': 103.0},
        {'formatted_date': '2024-02-05', 'close': 105.0}, # Breakout
    ]
    # Based on this simplified dataset, the last contraction is High 3 (103.0) and Low 3 (94.0)
    expected_pivot = 103.0 * 1.01
    expected_stop_loss = 94.0 * 0.99
    return historical_prices, expected_pivot, expected_stop_loss

class TestVCPAnalysisLogic(unittest.TestCase):
    """
    Unit tests for the VCP analysis logic in the analysis-service.
    """

    def test_vcp_pivot_and_stop_loss_calculation(self):
        """
        Tests that the VCP analysis correctly identifies the pivot point
        and stop-loss within an acceptable tolerance.
        """
        # 1. Arrange: Prepare test data and expected outcomes
        raw_prices, expected_pivot, expected_stop_loss = get_known_vcp_data()
        
        # Prepare data using the utility function
        prices, dates, _ = prepare_historical_data(raw_prices)
        
        tolerance = 0.02  # 2% tolerance

        # 2. Act: Execute the VCP analysis function
        # find_volatility_contraction_pattern returns a list of contractions
        # Each contraction is (high_idx, high_price, low_idx, low_price)
        vcp_results = find_volatility_contraction_pattern(prices)

        self.assertTrue(vcp_results, "No VCPs detected, but expected at least one.")
        
        # Extract the last contraction for pivot and stop-loss calculation
        # This aligns with the app.py logic for buyPoints/sellPoints
        last_high_idx, last_high_price, last_low_idx, last_low_price = vcp_results[-1]

        # Calculate pivot and stop-loss based on the logic in app.py
        calculated_pivot = last_high_price * 1.01
        calculated_stop_loss = last_low_price * 0.99

        # 3. Assert: Verify results within tolerance
        # Check pivot point
        pivot_diff = abs(calculated_pivot - expected_pivot) / expected_pivot
        self.assertTrue(
            pivot_diff <= tolerance,
            f"Pivot point out of tolerance. Expected: {expected_pivot}, Got: {calculated_pivot} (Diff: {pivot_diff:.2%})"
        )

        # Check stop-loss
        stop_loss_diff = abs(calculated_stop_loss - expected_stop_loss) / expected_stop_loss
        self.assertTrue(
            stop_loss_diff <= tolerance,
            f"Stop-loss out of tolerance. Expected: {expected_stop_loss}, Got: {calculated_stop_loss} (Diff: {stop_loss_diff:.2%})"
        )

if __name__ == '__main__':
    unittest.main()