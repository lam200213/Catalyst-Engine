# backend-services/leadership-service/tests/test_integration.py
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import requests

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

def mock_data_service_response(status_code=200, json_data=None, side_effect=None):
    """Helper to create mock responses for requests.get."""
    if side_effect:
        return MagicMock(side_effect=side_effect)
    
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json.return_value = json_data
    return mock_resp

class TestLeadershipScreening(unittest.TestCase):
    """
    TDD Test Suite for the Leadership Screening Endpoint.
    This suite is structured to directly validate the requirements from the test plan.
    """
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()

    def _get_mock_price_data(base_price=100.0, performance_factor=1.0, days=90):
        """Generates realistic price data that includes a market rally."""
        prices = []
        price = base_price
        for i in range(days):
            # Simulate a market rally (6% gain over 3 days) around day 60
            rally_multiplier = 1.02 if 60 <= i < 63 else 1.0
            price *= (1.001 * performance_factor * rally_multiplier)
            prices.append({'close': price, 'high': price * 1.01, 'low': price * 0.99, 'formatted_date': f'2025-01-{i+1:02d}'})
        return prices

    def _get_mock_financial_data(self, overrides={}):
        """Generates financial data with accelerating growth to pass all checks."""
        # Growth rates: 25%, 30%, 35%, 40%, 45%
        earnings = [100, 125, 162.5, 219.3, 307.1, 445.3]
        base_data = {
            'marketCap': 5_000_000_000, 'sharesOutstanding': 100_000_000,
            'floatShares': 15_000_000, 'ipoDate': '2020-01-01',
            'annual_earnings': [{'Earnings': 4.00}],
            'quarterly_earnings': [{'Earnings': e, 'Revenue': e * 10} for e in earnings],
            'quarterly_financials': [{'Net Income': e, 'Total Revenue': e * 10} for e in earnings],
        }
        base_data.update(overrides)
        return base_data

    @patch('app.requests.get')
    def test_leadership_endpoint_pass_scenario(self, mock_get):
        """
        Verifies the endpoint returns passes: true when all criteria are met.
        """
        # Arrange: Use side_effect to handle multiple, different API calls
        def side_effect(url, **kwargs):
            if 'financials/core/PASS-TICKER' in url:
                return mock_data_service_response(200, self._get_mock_financial_data())
            # Mock for market trend context checks
            if 'financials/core/^GSPC' in url or 'financials/core/^DJI' in url or 'financials/core/QQQ' in url:
                return mock_data_service_response(200, {'current_price': 4500, 'sma_50': 4400, 'sma_200': 4200})
            # Mock for rally check price data
            if 'data/PASS-TICKER' in url:
                return mock_data_service_response(200, _get_mock_price_data(performance_factor=1.02)) # Stock outperforms
            if 'data/^GSPC' in url:
                return mock_data_service_response(200, _get_mock_price_data()) # Market rally
            # Mocks for industry leadership check
            if 'industry/peers/PASS-TICKER' in url:
                return mock_data_service_response(200, {"industry": "Tech", "peers": ["MSFT"]})
            if 'financials/core/batch' in url:
                return mock_data_service_response(200, {"success": {"MSFT": {"totalRevenue": 1, "marketCap": 1, "netIncome": 1}, "PASS-TICKER": {"totalRevenue": 2, "marketCap": 2, "netIncome": 2}}})
            return mock_data_service_response(404, {"error": "URL Not Mocked"})
        mock_get.side_effect = side_effect

        # Act
        response = self.app.get('/leadership/PASS-TICKER')
        
        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertTrue(data['passes'], f"Expected passes to be True, but it was False. Details: {data.get('details')}")
        self.assertTrue(data['details']['is_small_to_mid_cap'])

    @patch('app.requests.get')
    def test_leadership_endpoint_fail_scenarios(self, mock_get):
        """
        Verifies the endpoint returns passes: false for single and multiple failures.
        """
        # --- Scenario 1: Fails a single criterion (Market Cap too large) ---
        mock_get.return_value = mock_data_service_response(
            status_code=200, 
            json_data=self._get_mock_financial_data({'marketCap': 20_000_000_000})
        )
        response_single_fail = self.app.get('/leadership/FAIL-SINGLE')
        data_single = response_single_fail.json
        
        self.assertEqual(response_single_fail.status_code, 200)
        self.assertFalse(data_single['passes'])
        self.assertFalse(data_single['details']['is_small_to_mid_cap'])
        self.assertTrue(data_single['details']['has_limited_float'])

        # --- Scenario 2: Fails multiple criteria ---
        mock_get.return_value = mock_data_service_response(
            status_code=200,
            json_data=self._get_mock_financial_data({
                'marketCap': 20_000_000_000,
                'ipoDate': '2005-01-01'
            })
        )
        response_multi_fail = self.app.get('/leadership/FAIL-MULTI')
        data_multi = response_multi_fail.json

        self.assertEqual(response_multi_fail.status_code, 200)
        self.assertFalse(data_multi['passes'])
        self.assertFalse(data_multi['details']['is_small_to_mid_cap'])
        self.assertFalse(data_multi['details']['is_recent_ipo'])

    @patch('app.requests.get')
    def test_leadership_endpoint_handles_data_service_500_error(self, mock_get):
        """
        Verifies the service returns a 502 Bad Gateway if the data-service fails.
        [Implements test plan requirement 2.1.3]
        """
        # Arrange
        mock_get.return_value = mock_data_service_response(status_code=500)
        
        # Act
        response = self.app.get('/leadership/ANYTICKER')

        # Assert
        self.assertEqual(response.status_code, 502)
        self.assertIn('error', response.json)
        self.assertIn('Failed to fetch data from data-service', response.json['error'])

    @patch('app.requests.get')
    def test_leadership_endpoint_handles_data_service_404_error(self, mock_get):
        """
        Verifies the service returns 502 for a non-existent ticker (404 from data-service).
        [Implements test plan requirement for non-existent ticker]
        """
        # Arrange
        mock_get.return_value = mock_data_service_response(status_code=404)

        # Act
        response = self.app.get('/leadership/NONEXISTENT')

        # Assert
        self.assertEqual(response.status_code, 502)
        self.assertIn('error', response.json)

    @patch('app.requests.get')
    def test_leadership_endpoint_handles_connection_error(self, mock_get):
        """
        Verifies the service returns 503 Service Unavailable on connection error.
        [Implements test plan requirement 2.1.3]
        """
        # Arrange
        mock_get.side_effect = requests.exceptions.ConnectionError("Service down")

        # Act
        response = self.app.get('/leadership/ANYTICKER')
        
        # Assert
        self.assertEqual(response.status_code, 503)
        self.assertIn('Service unavailable', response.json['error'])

    @patch('app.requests.get')
    def test_leadership_endpoint_handles_missing_data_key(self, mock_get):
        """
        Verifies the service doesn't crash and fails the check if a key is missing.
        [Implements test plan requirement 2.1.4]
        """
        # Arrange: Data is missing the 'marketCap' key
        mock_data = self._get_mock_financial_data()
        del mock_data['marketCap']
        mock_get.return_value = mock_data_service_response(status_code=200, json_data=mock_data)

        # Act
        response = self.app.get('/leadership/MISSINGKEY')
        
        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertFalse(data['passes'])
        self.assertFalse(data['details']['is_small_to_mid_cap'])

    def test_leadership_endpoint_handles_path_traversal_attack(self):
        """
        Verifies the service rejects malicious URLs.
        """
        # Act
        response = self.app.get('/leadership/../../etc/passwd')
        
        # Assert
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main()