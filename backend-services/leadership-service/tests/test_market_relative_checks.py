# backend-services/leadership-service/tests/test_market_relative_checks.py
import unittest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from checks.market_relative_checks import *
from tests.mock_data_helpers import create_mock_price_data, create_mock_index_data

def create_mock_market_trends(pattern):
    """Helper to generate market trend data based on a pattern list."""
    # Base start date far enough in the past
    start_date = datetime.now() - timedelta(days=len(pattern))
    return [
        {'date': (start_date + timedelta(days=i)).strftime('%Y-%m-%d'), 'trend': trend}
        for i, trend in enumerate(pattern)
    ]

class TestMarketRelativeChecks(unittest.TestCase):
    def test_market_context_is_recovery_phase(self):
        """Test confirms recovery phase is correctly identified."""
        details = {}
        stock_data, _ = create_mock_price_data(1.5, length=365)
        index_data = create_mock_index_data()
        
        # This pattern has a clear turning point from Bearish to Bullish
        recovery_pattern = (['Bearish'] * 20) + (['Neutral'] * 5) + (['Bullish'] * 5)
        market_trends = create_mock_market_trends(recovery_pattern)
        
        # Make the stock hit a new high right after the turning point
        turning_point_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        idx_after_turn = next(i for i, d in enumerate(stock_data) if d['formatted_date'] > turning_point_date)
        stock_data[idx_after_turn]['high'] = 9999 # Force a new high
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends, details)
        
        result = details['market_trend_impact']
        self.assertTrue(result['is_recovery_phase'])
        self.assertIsNotNone(result['turning_point_date'])
        self.assertTrue(result['sub_results']['new_52_week_high_in_recovery']['pass'])

    def test_market_context_is_sustained_bull(self):
        """Test ensures a sustained bull market is not flagged as recovery."""
        details = {}
        stock_data, _ = create_mock_price_data(1.0, length=365)
        # Make stock hit a new high recently
        stock_data[-1]['high'] = max(d['high'] for d in stock_data) + 1
        index_data = create_mock_index_data()
        
        # This pattern has no preceding 'Bearish' trend
        bull_pattern = (['Neutral'] * 20) + (['Bullish'] * 10)
        market_trends = create_mock_market_trends(bull_pattern)
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends, details)
        
        result = details['market_trend_impact']
        self.assertFalse(result['is_recovery_phase'])
        self.assertIsNone(result['turning_point_date'])
        self.assertEqual(result['market_trend_context'], 'Bullish')
        self.assertTrue(result['sub_results']['new_52_week_high_last_20d']['pass'])

    def test_market_context_is_bearish(self):
        """Test ensures bearish context triggers shallow decline check."""
        details = {}
        stock_data, _ = create_mock_price_data(1.0, length=300)
        index_data = create_mock_index_data()

        # Simulate a shallow stock decline (5%) vs a deeper market decline (10%)
        stock_52w_high = max(d['high'] for d in stock_data)
        stock_data[-1]['close'] = stock_52w_high * 0.95 
        index_data['^GSPC']['current_price'] = index_data['^GSPC']['high_52_week'] * 0.90
        
        bear_pattern = (['Bullish'] * 20) + (['Neutral'] * 5) + (['Bearish'] * 5)
        market_trends = create_mock_market_trends(bear_pattern)
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends, details)
        
        result = details['market_trend_impact']
        self.assertFalse(result['is_recovery_phase'])
        self.assertEqual(result['market_trend_context'], 'Bearish')
        self.assertTrue(result['sub_results']['shallow_decline']['pass'])

    def test_insufficient_market_trend_data(self):
        """Test graceful failure when there's not enough trend data."""
        details = {}
        stock_data, _ = create_mock_price_data(1.0, length=300)
        index_data = create_mock_index_data()
        market_trends = create_mock_market_trends(['Bullish', 'Bearish']) # Only 2 days
        
        evaluate_market_trend_impact(stock_data, index_data, market_trends, details)
        
        result = details['market_trend_impact']
        self.assertFalse(result['pass'])
        self.assertIn("Market trends data is insufficient (requires >= 8 days).", result['message'])

if __name__ == '__main__':
    unittest.main()