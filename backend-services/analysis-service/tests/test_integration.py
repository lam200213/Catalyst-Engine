# backend-services/analysis-service/tests/test_integration.py
import unittest
import numpy as np
import requests
import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

# --- Test Data Helpers ---
def get_vcp_test_data():
    """Generates a predictable dataset known to contain VCPs."""
    prices = [100, 105, 102, 108, 104, 100, 103, 101, 98]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    historical_data = [{'formatted_date': d, 'open': p-1, 'high': p+1, 'low': p-1, 'close': p, 'volume': 1000, 'adjclose': p} for d, p in zip(dates, prices)]
    return historical_data

def generate_pivot_test_data(vcp_present=True, low_vol_date_index=None, equal_volumes=False):
    """Generates structured data for testing low-volume pivot detection."""
    prices = [100, 105, 102, 108, 104, 100, 103, 101, 98, 99, 100]
    volumes = [500, 600, 450, 700, 550, 400, 300, 250, 200, 220, 240]

    if not vcp_present:
        prices = [100 - i for i in range(len(prices))]
    if low_vol_date_index is not None and vcp_present:
        volumes[low_vol_date_index] = 50
    if equal_volumes:
        for i in range(3, 9): volumes[i] = 100

    return [{
        "formatted_date": f"2025-01-{(i+1):02d}", "close": float(p), "volume": int(v),
        "open": float(p - 1), "high": float(p + 1), "low": float(p - 1), "adjclose": float(p)
    } for i, (p, v) in enumerate(zip(prices, volumes))]

# --- Test Cases ---

class TestAnalysisEndpoint(unittest.TestCase):
    """Tests for the /analyze endpoint, covering success, errors, and edge cases."""
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_analyze_success_path(self, mock_get):
        raw_data = get_vcp_test_data()
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: raw_data,
            content=json.dumps(raw_data).encode('utf-8')
        )
        response = self.app.get('/analyze/AAPL')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['ticker'], 'AAPL')
        self.assertIn('vcp_pass', json_data)
        self.assertIn('vcpFootprint', json_data)
        self.assertIn('chart_data', json_data)

    @patch('app.requests.get')
    def test_analyze_data_contract_violation_for_required_field(self, mock_get):
        """
        Consumer Test: Verifies a 502 error if the upstream payload
        violates the data contract by missing a REQUIRED field ('formatted_date').
        """
        # Arrange: Create a payload missing the required 'formatted_date' field.
        invalid_payload = [
            {'formatted_date': '2024-01-01', 'close': 100.5},
            {'close': 101.5} # Missing 'formatted_date'
        ]
        mock_get.return_value = MagicMock(
            status_code=200,
            content=json.dumps(invalid_payload).encode('utf-8')
        )

        # Act
        response = self.app.get('/analyze/CONTRACTVIOLATION')

        # Assert: Pydantic validation should fail and return a 502.
        self.assertEqual(response.status_code, 502)
        json_data = response.get_json()
        self.assertIn("Invalid data structure", json_data['error'])
        self.assertIn("Field required", json_data['details'])

    @patch('app.requests.get')
    def test_analyze_data_with_unusable_records(self, mock_get):
        """
        Consumer Test: Verifies a 404 error if the upstream payload is
        schema-valid but all records are unusable (e.g., missing 'close' price).
        """
        # Arrange: Payload where all records are missing the optional 'close' field.
        unusable_payload = [
            {'formatted_date': '2024-01-01', 'open': 100},
            {'formatted_date': '2024-01-02', 'open': 101}
        ]
        mock_get.return_value = MagicMock(
            status_code=200,
            content=json.dumps(unusable_payload).encode('utf-8')
        )

        # Act
        response = self.app.get('/analyze/UNUSABLEDATA')

        # Assert: The service should filter records, find no data, and return 404.
        self.assertEqual(response.status_code, 404)
        json_data = response.get_json()
        self.assertIn("No price data available", json_data['error'])

    @patch('app.requests.get')
    def test_analyze_data_service_404_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404, json=lambda: {'error': 'Ticker not found'})
        response = self.app.get('/analyze/FAKETICKER')
        self.assertEqual(response.status_code, 502)
        self.assertIn('Invalid or non-existent ticker', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_data_service_connection_error(self, mock_get):
        """Tests the endpoint's handling of a connection error when calling the data-service."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Service unavailable")
        response = self.app.get('/analyze/ANYTICKER')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Service unavailable', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_with_no_price_data(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
            content=b'[]'
        )
        response = self.app.get('/analyze/NEWTICKER')
        self.assertEqual(response.status_code, 404)
        self.assertIn('No price data available', response.get_json()['error'])
    
    @patch('app.requests.get')
    def test_endpoint_handles_numpy_types(self, mock_get):
        """Ensures the endpoint can correctly serialize NumPy data types."""
        mock_data = [
            {'formatted_date': '2024-01-01', 'close': 100.0, 'open': 99, 'high': 101, 'low': 99, 'volume': 1000, 'adjclose': 100.0},
            {'formatted_date': '2024-01-02', 'close': 101.0, 'open': 100, 'high': 102, 'low': 100, 'volume': 1000, 'adjclose': 101.0},
            {'formatted_date': '2024-01-03', 'close': 102.0, 'open': 101, 'high': 103, 'low': 101, 'volume': 1000, 'adjclose': 102.0},
            {'formatted_date': '2024-01-04', 'close': 103.0, 'open': 102, 'high': 104, 'low': 102, 'volume': 1000, 'adjclose': 103.0}
        ]
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_data,
            content=json.dumps(mock_data).encode('utf-8')
        )
        with patch('app.find_volatility_contraction_pattern') as mock_vcp:
            mock_vcp.return_value = [(3, np.float64(103.0), 0, np.float64(100.0))]
            response = self.app.get('/analyze/TESTTICKER')
            self.assertEqual(response.status_code, 200)
            json_response = response.get_json()
            self.assertIsInstance(json_response['chart_data']['buyPoints'][0]['value'], float)

class TestLowVolumePivotFeature(unittest.TestCase):
    """
    Integration tests for the low-volume pivot date feature, ensuring it's
    correctly identified and returned within the /analyze endpoint's response.
    """
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_pivot_found_successfully(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=True, low_vol_date_index=6)
        expected_date = "2025-01-07"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: test_data,
            content=json.dumps(test_data).encode('utf-8')
        )
        response = self.app.get('/analyze/PIVOT')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['chart_data']['lowVolumePivotDate'], expected_date)

    @patch('app.requests.get')
    def test_pivot_is_none_when_no_vcp_detected(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=False)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: test_data,
            content=json.dumps(test_data).encode('utf-8')
        )
        response = self.app.get('/analyze/NOVCP')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json_data['chart_data']['detected'])
        self.assertIsNone(json_data['chart_data']['lowVolumePivotDate'])

    @patch('app.requests.get')
    def test_pivot_is_deterministic_with_equal_volumes(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=True, equal_volumes=True)
        expected_date = "2025-01-04"
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: test_data,
            content=json.dumps(test_data).encode('utf-8')
        )
        response = self.app.get('/analyze/EQUALVOL')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json_data['chart_data']['detected'])
        self.assertEqual(json_data['chart_data']['lowVolumePivotDate'], expected_date)

class TestVolumeTrendLineFeature(unittest.TestCase):
    """
    Integration tests for the volume trend line feature, ensuring it's
    correctly calculated and returned in the /analyze endpoint's response.
    """
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_volume_trend_line_is_calculated(self, mock_get):
        """1. Business Logic: Verifies the trend line is returned for a valid VCP."""
        test_data = generate_pivot_test_data(vcp_present=True)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: test_data,
            content=json.dumps(test_data).encode('utf-8')
        )

        response = self.app.get('/analyze/TREND')
        json_data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn('volumeTrendLine', json_data['chart_data'])
        trend_line = json_data['chart_data']['volumeTrendLine']
        self.assertIsInstance(trend_line, list)
        self.assertEqual(len(trend_line), 2, "Trend line should consist of a start and end point.")
        self.assertIn('time', trend_line[0])
        self.assertIn('value', trend_line[0])

    @patch('app.requests.get')
    def test_volume_trend_line_is_empty_when_no_vcp(self, mock_get):
        """2. Edge Case: Verifies the trend line is an empty list when no VCP is found."""
        test_data = generate_pivot_test_data(vcp_present=False)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: test_data,
            content=json.dumps(test_data).encode('utf-8')
        )
        response = self.app.get('/analyze/NOTREND')
        json_data = response.get_json()
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('volumeTrendLine', json_data['chart_data'])
        self.assertEqual(json_data['chart_data']['volumeTrendLine'], [])


class TestResponseStructure(unittest.TestCase):
    """Tests for the new VCP screening response format."""
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_analyze_returns_screening_format(self, mock_get):
        """
        Verifies the /analyze endpoint returns the new screening format 
        with vcp_pass and vcpFootprint keys at the top level.
        """
        # Arrange: Mock a successful response from the data-service
        # Using a helper from existing tests to generate predictable data
        mock_data = generate_pivot_test_data(vcp_present=True)
        mock_get.return_value = MagicMock(
            status_code=200, 
            json=lambda: mock_data,
            content=json.dumps(mock_data).encode('utf-8')
        )

        # Act: Call the endpoint
        response = self.app.get('/analyze/AAPL')
        json_data = response.get_json()

        # Assert: Check for the new required top-level keys
        self.assertEqual(response.status_code, 200)
        self.assertIn('vcp_pass', json_data)
        self.assertIn('vcpFootprint', json_data)
        self.assertIn('chart_data', json_data)
        
        # Verify the type of the new keys
        self.assertIsInstance(json_data['vcp_pass'], bool)
        self.assertIsInstance(json_data['vcpFootprint'], str)

class TestVCPEvaluationModes(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        # Use a helper to generate predictable test data
        self.mock_price_data = generate_pivot_test_data(vcp_present=True)
        self.mock_price_data_content = json.dumps(self.mock_price_data).encode('utf-8')

    @patch('app.requests.get')
    @patch('app.run_vcp_screening')
    def test_analyze_full_evaluation_returns_detailed_results(self, mock_run_vcp_screening, mock_get):
        """
        Tests that the default 'full' mode returns a detailed breakdown of every VCP check.
        """
        # --- Arrange ---
        # Mock the data-service to return valid price data
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self.mock_price_data,
            content=self.mock_price_data_content
        )

        # Mock the orchestrator to return a "fail" status with detailed results
        # This simulates a ticker that passes some checks but fails others.
        mock_run_vcp_screening.return_value = (
            False, # Overall vcp_pass
            "10D 20.0% | 5D 15.0%", # vcpFootprint
            { # The new detailed breakdown
                "is_pivot_good": True,
                "is_correction_deep": False, # This check passes (is_deep is False)
                "is_demand_dry": False # This check fails
            }
        )

        # --- Act ---
        # Call the endpoint without the 'mode' parameter to test the default
        response = self.app.get('/analyze/FAILING_TICKER')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertIn('vcp_pass', json_data)
        self.assertFalse(json_data['vcp_pass'])
        self.assertIn('vcp_details', json_data, "Response should contain the detailed check results.")
        self.assertEqual(json_data['vcp_details']['is_pivot_good'], True)
        self.assertEqual(json_data['vcp_details']['is_demand_dry'], False)

    # Ensure that ?mode=fast stops processing on the first failure and returns a lean response.
    @patch('app.requests.get')
    @patch('vcp_logic.is_pivot_good')
    @patch('vcp_logic.is_correction_deep')
    @patch('vcp_logic.is_demand_dry') # Mock the individual checks
    def test_analyze_fail_fast_mode_halts_on_first_failure(self, mock_is_demand_dry, mock_is_correction_deep, mock_is_pivot_good, mock_get):
        """
        Tests that 'fast' mode halts execution on the first check failure.
        """
        # --- Arrange ---
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self.mock_price_data,
            content=self.mock_price_data_content
        )

        # Mock the VCP checks so the first one fails
        mock_is_pivot_good.return_value = False # This is the first check, it will fail.
        mock_is_correction_deep.return_value = False # Should not be called
        mock_is_demand_dry.return_value = True # Should not be called

        # --- Act ---
        # Call the endpoint explicitly with mode=fast
        response = self.app.get('/analyze/FAILING_TICKER?mode=fast')
        json_data = response.get_json()

        # --- Assert ---
        self.assertEqual(response.status_code, 200)
        self.assertIn('vcp_pass', json_data)
        self.assertFalse(json_data['vcp_pass'])
        self.assertNotIn('vcp_details', json_data, "Fast mode should not return detailed results.")

        # Crucially, assert that the logic halted after the first failure
        mock_is_pivot_good.assert_called_once()
        mock_is_correction_deep.assert_not_called()
        mock_is_demand_dry.assert_not_called()

class TestBatchAnalysisEndpoint(unittest.TestCase):
    """Tests for the new /analyze/batch endpoint."""
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.post')
    def test_batch_analysis_success(self, mock_post):
        """Business Logic: Verifies a successful batch run with mixed pass/fail tickers."""
        # Arrange: Mock data for two tickers, one that will pass, one that will fail
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "success": {
                    "VCP_PASS": generate_pivot_test_data(vcp_present=True),
                    "VCP_FAIL": generate_pivot_test_data(vcp_present=False)
                }
            }
        )
        payload = {"tickers": ["VCP_PASS", "VCP_FAIL"]}
        
        # Act
        response = self.app.post('/analyze/batch', data=json.dumps(payload), content_type='application/json')
        json_data = response.get_json()

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(json_data, list)
        self.assertEqual(len(json_data), 1) # Only the passing ticker should be returned
        self.assertEqual(json_data[0]['ticker'], 'VCP_PASS')
        self.assertTrue(json_data[0]['vcp_pass'])
        self.assertIn('vcpFootprint', json_data[0])

    def test_batch_analysis_empty_ticker_list(self):
        """Edge Case: Verifies an empty ticker list returns a 200 OK with an empty list."""
        payload = {"tickers": []}
        response = self.app.post('/analyze/batch', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_batch_analysis_invalid_payload(self):
        """Edge Case: Verifies malformed payloads return a 400 Bad Request."""
        # Missing 'tickers' key
        response1 = self.app.post('/analyze/batch', data=json.dumps({"data": []}), content_type='application/json')
        self.assertEqual(response1.status_code, 400)
        
        # 'tickers' is not a list
        response2 = self.app.post('/analyze/batch', data=json.dumps({"tickers": "AAPL"}), content_type='application/json')
        self.assertEqual(response2.status_code, 400)

    @patch('app.requests.post')
    def test_batch_analysis_data_service_502_error(self, mock_post):
        """Error Handling: Verifies a data-service error is handled gracefully."""
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        payload = {"tickers": ["AAPL"]}
        response = self.app.post('/analyze/batch', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 502)
        self.assertIn("Failed to retrieve batch data", response.get_json()['error'])

    @patch('app.requests.post')
    def test_batch_analysis_data_service_connection_error(self, mock_post):
        """Error Handling: Verifies a connection error to data-service returns 503."""
        mock_post.side_effect = requests.exceptions.RequestException("Connection refused")
        payload = {"tickers": ["AAPL"]}
        response = self.app.post('/analyze/batch', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertIn("Error connecting to data-service", response.get_json()['error'])
    
    @patch('app._process_ticker_analysis')
    @patch('app.requests.post')
    def test_batch_individual_ticker_failure_does_not_crash(self, mock_post, mock_process):
        """Resilience: Ensures an error in one ticker's analysis doesn't halt the whole batch."""
        # Arrange
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "success": {
                    "GOOD": generate_pivot_test_data(vcp_present=True),
                    "BAD": generate_pivot_test_data(vcp_present=True) 
                }
            }
        )
        # Mock the processing function to fail for one ticker but succeed for another
        mock_process.side_effect = [
            {"ticker": "GOOD", "vcp_pass": True, "vcpFootprint": "10W..."}, # Successful result for GOOD
            Exception("Unexpected processing error") # Simulate a crash for BAD
        ]
        
        payload = {"tickers": ["GOOD", "BAD"]}

        # Act
        response = self.app.post('/analyze/batch', data=json.dumps(payload), content_type='application/json')
        json_data = response.get_json()

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(json_data), 1) # Only the good result should be present
        self.assertEqual(json_data[0]['ticker'], "GOOD")

if __name__ == '__main__':
    unittest.main()
