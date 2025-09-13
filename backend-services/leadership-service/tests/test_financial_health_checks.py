# Latest Add:
# backend-services/leadership-service/tests/test_financial_health_checks.py
import unittest
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import logic module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from checks.financial_health_checks import *
from tests.mock_data_helpers import create_mock_financial_data

class TestFinancialHealthChecks(unittest.TestCase):

    def test_check_is_small_to_mid_cap(self):
        details = {}
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=1_000_000_000), details)
        self.assertTrue(details['is_small_to_mid_cap']['pass'])
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=20_000_000_000), details)
        self.assertFalse(details['is_small_to_mid_cap']['pass'])
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=None), details)
        self.assertFalse(details['is_small_to_mid_cap']['pass'])

    def test_check_is_early_stage(self):
        details = {}
        recent_ipo = (datetime.now() - timedelta(days=2*365)).strftime('%Y-%m-%d')
        check_is_early_stage(create_mock_financial_data(ipoDate=recent_ipo), details)
        self.assertTrue(details['is_recent_ipo']['pass'])
        old_ipo = (datetime.now() - timedelta(days=15*365)).strftime('%Y-%m-%d')
        check_is_early_stage(create_mock_financial_data(ipoDate=old_ipo), details)
        self.assertFalse(details['is_recent_ipo']['pass'])

    def test_check_has_limited_float(self):
        details = {}
        check_has_limited_float(create_mock_financial_data(floatShares=50_000_000), details)
        self.assertTrue(details['has_limited_float']['pass'], "Should pass for 50M shares")
        check_has_limited_float(create_mock_financial_data(floatShares=150_000_000), details)
        self.assertFalse(details['has_limited_float']['pass'], "Should fail for 150M shares")
        check_has_limited_float(create_mock_financial_data(floatShares=None), details)
        self.assertFalse(details['has_limited_float']['pass'])

    def test_check_yoy_eps_growth(self):
        details = {}
        earnings_pass = [{'Earnings': 1.0}] * 4 + [{'Earnings': 0.75}] # 33% growth
        check_yoy_eps_growth(create_mock_financial_data(quarterly_earnings=earnings_pass), details)
        self.assertTrue(details['has_strong_yoy_eps_growth']['pass'])
        self.assertEqual(details['has_strong_yoy_eps_growth']['yoy_eps_growth_level'], 'Standard Growth')
        
        earnings_fail = [{'Earnings': 1.0}] * 4 + [{'Earnings': 0.9}] # 11% growth
        check_yoy_eps_growth(create_mock_financial_data(quarterly_earnings=earnings_fail), details)
        self.assertFalse(details['has_strong_yoy_eps_growth']['pass'])

    def test_check_positive_recent_earnings(self):
        details = {}
        check_positive_recent_earnings(create_mock_financial_data(passing_data=True), details)
        self.assertTrue(details['has_positive_recent_earnings']['pass'])
        check_positive_recent_earnings(create_mock_financial_data(annual_earnings=[{'Earnings': -0.5}]), details)
        self.assertFalse(details['has_positive_recent_earnings']['pass'])

    def test_check_accelerating_growth(self):
        details = {}
        check_accelerating_growth(create_mock_financial_data(passing_data=True), details)
        self.assertTrue(details['has_accelerating_growth']['pass'], details['has_accelerating_growth']['message'])
        
        # Test fail case
        check_accelerating_growth(create_mock_financial_data(passing_data=False), details)
        self.assertFalse(details['has_accelerating_growth']['pass'])

    def test_check_consecutive_quarterly_growth(self):
        details = {}
        check_consecutive_quarterly_growth(create_mock_financial_data(passing_data=True), details)
        self.assertTrue(details['has_consecutive_quarterly_growth']['pass'])
        self.assertEqual(details['has_consecutive_quarterly_growth']['growth_level'], 'High Growth')

if __name__ == '__main__':
    unittest.main()