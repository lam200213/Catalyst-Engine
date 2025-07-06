# backend-services/analysis-service/tests/test_integration.py
import unittest
import numpy as np
import requests
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

# --- Test Data Helpers ---
def get_vcp_test_data():
    """Generates a predictable dataset known to contain VCPs."""
    prices = [100, 105, 102, 108, 104, 100, 103, 101, 98]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(prices))]
    historical_data = [{'formatted_date': d, 'close': p} for d, p in zip(dates, prices)]
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
        "open": float(p - 1), "high": float(p + 1), "low": float(p - 1),
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
        mock_get.return_value = MagicMock(status_code=200, json=lambda: raw_data)
        response = self.app.get('/analyze/AAPL')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['ticker'], 'AAPL')
        self.assertIn('analysis', json_data)

    @patch('app.requests.get')
    def test_analyze_data_service_404(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404, json=lambda: {'error': 'Ticker not found'})
        response = self.app.get('/analyze/FAKETICKER')
        self.assertEqual(response.status_code, 502)
        self.assertIn('Invalid or non-existent ticker', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_data_service_503(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Service unavailable")
        response = self.app.get('/analyze/ANYTICKER')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Service unavailable', response.get_json()['error'])

    @patch('app.requests.get')
    def test_analyze_with_empty_price_data(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        response = self.app.get('/analyze/NEWTICKER')
        self.assertEqual(response.status_code, 404)
        self.assertIn('No price data available', response.get_json()['error'])
    
    @patch('app.requests.get')
    def test_endpoint_handles_numpy_types(self, mock_get):
        """Ensures the endpoint can correctly serialize NumPy data types."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {'formatted_date': '2024-01-01', 'close': 100.0},
            {'formatted_date': '2024-01-02', 'close': 101.0},
            {'formatted_date': '2024-01-03', 'close': 102.0},
            {'formatted_date': '2024-01-04', 'close': 103.0}
        ]
        with patch('app.find_volatility_contraction_pattern') as mock_vcp:
            mock_vcp.return_value = [(3, np.float64(103.0), 0, np.float64(100.0))]
            response = self.app.get('/analyze/TESTTICKER')
            self.assertEqual(response.status_code, 200)
            json_response = response.get_json()
            self.assertIsInstance(json_response['analysis']['buyPoints'][0]['value'], float)

class TestLowVolumePivotEndpoint(unittest.TestCase):
    """Tests for the low-volume pivot date feature in the /analyze endpoint."""
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_pivot_found_successfully(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=True, low_vol_date_index=6)
        expected_date = "2025-01-07"
        mock_get.return_value = MagicMock(status_code=200, json=lambda: test_data)
        response = self.app.get('/analyze/PIVOT')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json_data['analysis']['lowVolumePivotDate'], expected_date)

    @patch('app.requests.get')
    def test_no_vcp_detected(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=False)
        mock_get.return_value = MagicMock(status_code=200, json=lambda: test_data)
        response = self.app.get('/analyze/NOVCP')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json_data['analysis']['detected'])
        self.assertIsNone(json_data['analysis']['lowVolumePivotDate'])

    @patch('app.requests.get')
    def test_equal_volumes_is_deterministic(self, mock_get):
        test_data = generate_pivot_test_data(vcp_present=True, equal_volumes=True)
        expected_date = "2025-01-04"
        mock_get.return_value = MagicMock(status_code=200, json=lambda: test_data)
        response = self.app.get('/analyze/EQUALVOL')
        json_data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json_data['analysis']['detected'])
        self.assertEqual(json_data['analysis']['lowVolumePivotDate'], expected_date)

class TestVolumeTrendLine(unittest.TestCase):
    """Tests for the volume trend line feature in the /analyze endpoint."""
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.get')
    def test_volume_trend_line_is_calculated(self, mock_get):
        """1. Business Logic: Verifies the trend line is returned for a valid VCP."""
        test_data = generate_pivot_test_data(vcp_present=True)
        mock_get.return_value = MagicMock(status_code=200, json=lambda: test_data)

        response = self.app.get('/analyze/TREND')
        json_data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertIn('volumeTrendLine', json_data['analysis'])
        trend_line = json_data['analysis']['volumeTrendLine']
        self.assertIsInstance(trend_line, list)
        self.assertEqual(len(trend_line), 2)
        self.assertIn('time', trend_line[0])
        self.assertIn('value', trend_line[0])

    @patch('app.requests.get')
    def test_volume_trend_line_is_empty_when_no_vcp(self, mock_get):
        """2. Edge Case: Verifies the trend line is an empty list when no VCP is found."""
        test_data = generate_pivot_test_data(vcp_present=False)
        mock_get.return_value = MagicMock(status_code=200, json=lambda: test_data)

        response = self.app.get('/analyze/NOTREND')
        json_data = response.get_json()
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('volumeTrendLine', json_data['analysis'])
        self.assertEqual(json_data['analysis']['volumeTrendLine'], [])


if __name__ == '__main__':
    unittest.main()
# Latest Add: End of new consolidated integration test file.