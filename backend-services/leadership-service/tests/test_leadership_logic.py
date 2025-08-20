# backend-services/leadership-service/tests/test_leadership_logic.py
import unittest
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path to import logic module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from leadership_logic import (
    check_is_small_to_mid_cap,
    check_is_early_stage,
    check_has_limited_float,
    check_yoy_eps_growth,
    check_positive_recent_earnings,
    check_accelerating_growth,
    check_consecutive_quarterly_growth,
    check_outperforms_in_rally,
    check_market_trend_context,
    evaluate_market_trend_impact
)

# --- Helper Functions for Mock Data Generation ---

def create_mock_financial_data(**overrides):
    """Creates a base dictionary of financial data that can be overridden for specific tests."""
    base_data = {
        'marketCap': 5_000_000_000,
        'sharesOutstanding': 100_000_000,
        'floatShares': 15_000_000,
        'ipoDate': (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d'),
        'quarterly_earnings': [{'Earnings': 1.0, 'Revenue': 1000}] * 6,
        'quarterly_financials': [{'Net Income': 100, 'Total Revenue': 1000}] * 6,
        'annual_earnings': [{'Earnings': 4.0}]
    }
    base_data.update(overrides)
    return base_data

def create_mock_price_data(performance_factor, length=50):
    """Creates mock stock and S&P 500 price data to simulate market conditions."""
    stock_data, sp500_data = [], []
    stock_price, sp500_price = 100.0, 4000.0

    for i in range(length):
        date_str = (datetime.now() - timedelta(days=length - 1 - i)).strftime('%Y-%m-%d')
        
        # Simulate a market rally (5% gain over 3 days) around day 25
        rally_multiplier = 1.05 if 25 <= i < 28 else 1.0
        
        stock_price *= (1.001 * performance_factor * rally_multiplier)
        sp500_price *= (1.001 * rally_multiplier)
        
        stock_data.append({'formatted_date': date_str, 'close': stock_price, 'high': stock_price * 1.01, 'low': stock_price * 0.99, 'volume': 100000})
        sp500_data.append({'formatted_date': date_str, 'close': sp500_price, 'high': sp500_price * 1.01, 'low': sp500_price * 0.99})
        
    return stock_data, sp500_data

def create_mock_index_data(trend='Bullish'):
    """Creates mock data for major market indices based on a trend scenario."""
    base_data = {
        '^GSPC': {'current_price': 4500, 'sma_50': 4400, 'sma_200': 4200, 'high_52_week': 4800, 'low_52_week': 4000},
        '^DJI': {'current_price': 35000, 'sma_50': 34000, 'sma_200': 32000, 'high_52_week': 38000, 'low_52_week': 30000},
        '^IXIC': {'current_price': 400, 'sma_50': 390, 'sma_200': 370, 'high_52_week': 420, 'low_52_week': 350}
    }
    if trend == 'Bearish':
        base_data['^GSPC']['current_price'] = 4300
        base_data['^DJI']['current_price'] = 33000
        base_data['^IXIC']['current_price'] = 380
    if trend == 'Neutral':
        base_data['^DJI']['current_price'] = 33000
    return base_data

# --- Test Suite ---

class TestLeadershipLogic(unittest.TestCase):

    def test_check_is_small_to_mid_cap(self):
        details = {}
        # Pass case
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=1_000_000_000), details)
        self.assertTrue(details['is_small_to_mid_cap'])
        # Fail case (too large)
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=20_000_000_000), details)
        self.assertFalse(details['is_small_to_mid_cap'])
        # Edge case (missing data)
        check_is_small_to_mid_cap(create_mock_financial_data(marketCap=None), details)
        self.assertFalse(details['is_small_to_mid_cap'])

    def test_check_is_early_stage(self):
        details = {}
        # Pass case
        recent_ipo = (datetime.now() - timedelta(days=2*365)).strftime('%Y-%m-%d')
        check_is_early_stage(create_mock_financial_data(ipoDate=recent_ipo), details)
        self.assertTrue(details['is_recent_ipo'])
        # Fail case
        old_ipo = (datetime.now() - timedelta(days=15*365)).strftime('%Y-%m-%d')
        check_is_early_stage(create_mock_financial_data(ipoDate=old_ipo), details)
        self.assertFalse(details['is_recent_ipo'])

    def test_check_has_limited_float(self):
        details = {}
        # Pass case (10% float)
        check_has_limited_float(create_mock_financial_data(floatShares=10_000_000), details)
        self.assertTrue(details['has_limited_float'])
        # Fail case (50% float)
        check_has_limited_float(create_mock_financial_data(floatShares=50_000_000), details)
        self.assertFalse(details['has_limited_float'])
        # Edge case (zero shares)
        check_has_limited_float(create_mock_financial_data(sharesOutstanding=0), details)
        self.assertFalse(details['has_limited_float'])

    def test_check_yoy_eps_growth(self):
        details = {}
        # Pass case (> 25% growth)
        earnings_pass = [{'Earnings': 1.0}] * 4 + [{'Earnings': 1.30}]
        check_yoy_eps_growth(create_mock_financial_data(quarterly_earnings=earnings_pass), details)
        self.assertTrue(details['has_strong_yoy_eps_growth'])
        self.assertEqual(details['yoy_eps_growth_level'], 'Standard Growth')
        # Fail case (< 25% growth)
        earnings_fail = [{'Earnings': 1.0}] * 4 + [{'Earnings': 1.10}]
        check_yoy_eps_growth(create_mock_financial_data(quarterly_earnings=earnings_fail), details)
        self.assertFalse(details['has_strong_yoy_eps_growth'])
        self.assertEqual(details['yoy_eps_growth_level'], 'Moderate Growth')
        # Edge case (insufficient data)
        check_yoy_eps_growth(create_mock_financial_data(quarterly_earnings=[{'Earnings': 1.0}] * 3), details)
        self.assertFalse(details['has_strong_yoy_eps_growth'])
        self.assertEqual(details['yoy_eps_growth_level'], 'Insufficient Data')

    def test_check_positive_recent_earnings(self):
        details = {}
        # Pass case
        check_positive_recent_earnings(create_mock_financial_data(), details)
        self.assertTrue(details['has_positive_recent_earnings'])
        # Fail case (negative annual earnings)
        check_positive_recent_earnings(create_mock_financial_data(annual_earnings=[{'Earnings': -0.5}]), details)
        self.assertFalse(details['has_positive_recent_earnings'])

    def test_check_accelerating_growth(self):
        details = {}
        # Pass case
        pass_earnings = [{'Earnings': 100, 'Revenue': 1000}, {'Earnings': 110, 'Revenue': 1100}, {'Earnings': 125, 'Revenue': 1250}, {'Earnings': 145, 'Revenue': 1450}]
        pass_financials = [{'Net Income': 50, 'Total Revenue': 1000}, {'Net Income': 66, 'Total Revenue': 1100}, {'Net Income': 100, 'Total Revenue': 1250}, {'Net Income': 159.5, 'Total Revenue': 1450}]
        check_accelerating_growth(create_mock_financial_data(quarterly_earnings=pass_earnings, quarterly_financials=pass_financials), details)
        self.assertTrue(details['has_accelerating_growth'])
        # Fail case
        fail_earnings = [{'Earnings': 100, 'Revenue': 1000}, {'Earnings': 120, 'Revenue': 1200}, {'Earnings': 130, 'Revenue': 1300}, {'Earnings': 135, 'Revenue': 1350}]
        check_accelerating_growth(create_mock_financial_data(quarterly_earnings=fail_earnings), details)
        self.assertFalse(details['has_accelerating_growth'])

    def test_check_consecutive_quarterly_growth(self):
        details = {}
        # Pass case (all rolling averages > 20%)
        pass_earnings = [{'Earnings': e} for e in [100, 130, 163, 212, 265, 345]]
        check_consecutive_quarterly_growth(create_mock_financial_data(quarterly_earnings=pass_earnings), details)
        self.assertTrue(details['has_consecutive_quarterly_growth'])
        # The calculated average growth is ~27.6%, which correctly falls into the 'Standard Growth' category (>20% but <35%)
        self.assertEqual(details['consecutive_quarterly_growth_level'], 'Standard Growth')
        # Fail case (one rolling average drops below 20%)
        fail_earnings = [{'Earnings': e} for e in [100, 130, 163, 170, 220, 280]]
        check_consecutive_quarterly_growth(create_mock_financial_data(quarterly_earnings=fail_earnings), details)
        self.assertFalse(details['has_consecutive_quarterly_growth'])

    def test_check_outperforms_in_rally(self):
        details = {}
        # Pass case (stock outperforms S&P by >1.5x)
        stock_pass, sp500_pass = create_mock_price_data(performance_factor=2.0)
        check_outperforms_in_rally(stock_pass, sp500_pass, details)
        self.assertTrue(details['outperforms_in_rally'])
        # Fail case (stock underperforms)
        stock_fail, sp500_fail = create_mock_price_data(performance_factor=0.5)
        check_outperforms_in_rally(stock_fail, sp500_fail, details)
        self.assertFalse(details['outperforms_in_rally'])
        # Edge case (no rally detected)
        _, no_rally_sp500 = create_mock_price_data(performance_factor=1.0)
        no_rally_sp500[25:28] = [{'close': 4100}] * 3 # Flatten the rally period
        check_outperforms_in_rally(stock_fail, no_rally_sp500, details)
        self.assertFalse(details['outperforms_in_rally'])

    def test_check_market_trend_context(self):
        details = {}
        # Bullish case
        check_market_trend_context(create_mock_index_data(trend='Bullish'), details)
        self.assertEqual(details['market_trend_context'], 'Bullish')
        # Bearish case
        check_market_trend_context(create_mock_index_data(trend='Bearish'), details)
        self.assertEqual(details['market_trend_context'], 'Bearish')
        # Neutral case
        check_market_trend_context(create_mock_index_data(trend='Neutral'), details)
        self.assertEqual(details['market_trend_context'], 'Neutral')
        # Edge case (missing index)
        check_market_trend_context({'^GSPC': {}}, details)
        self.assertEqual(details['market_trend_context'], 'Unknown')

if __name__ == '__main__':
    unittest.main()