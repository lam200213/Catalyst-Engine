# backend-services/leadership-service/tests/test_market_relative_checks.py
import unittest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from checks.market_relative_checks import *
from tests.mock_data_helpers import create_mock_price_data, create_mock_index_data

class TestMarketRelativeChecks(unittest.TestCase):

    def test_check_outperforms_in_rally(self):
        details = {}
        stock_pass, sp500_pass = create_mock_price_data(performance_factor=2.0, passing_data=True)
        check_outperforms_in_rally(stock_pass, sp500_pass, details)
        self.assertTrue(details['outperforms_in_rally']['pass'], details['outperforms_in_rally']['message'])
        
        stock_fail, sp500_fail = create_mock_price_data(performance_factor=0.5, passing_data=True)
        check_outperforms_in_rally(stock_fail, sp500_fail, details)
        self.assertFalse(details['outperforms_in_rally']['pass'])

    def test_evaluate_market_trend_impact(self):
        details = {}
        stock_data, _ = create_mock_price_data(1, length=300)
        index_data = create_mock_index_data()

        # Scenario 1: Bearish market, stock has a shallow decline
        stock_data[-1]['close'] = max(d['high'] for d in stock_data) * 0.95 
        index_data['^GSPC']['current_price'] = index_data['^GSPC']['high_52_week'] * 0.90
        market_trends_bearish = [{'date': '...', 'trend': 'Neutral'}] * 7 + [{'date': '...', 'trend': 'Bearish'}]
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends_bearish, details)
        self.assertEqual(details['market_trend_impact']['market_trend_context'], 'Bearish')
        self.assertTrue(details['market_trend_impact']['sub_results']['shallow_decline']['pass'])

        # Scenario 2: Bullish market, stock hits a new 52-week high
        details = {} 
        stock_data[-1]['close'] = max(d['high'] for d in stock_data) + 1 
        market_trends_bullish = [{'date': '...', 'trend': 'Bullish'}] * 8
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends_bullish, details)
        self.assertEqual(details['market_trend_impact']['market_trend_context'], 'Bullish')
        self.assertTrue(details['market_trend_impact']['sub_results']['new_high_last_20d']['pass'])

if __name__ == '__main__':
    unittest.main()