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
    evaluate_market_trend_impact,
    check_industry_leadership
)

# --- Helper Functions for Mock Data Generation ---

def create_mock_financial_data(**overrides):
    """Creates a base dictionary of financial data that can be overridden for specific tests."""
    base_data = {
        'marketCap': 5_000_000_000,
        'sharesOutstanding': 100_000_000,
        'floatShares': 15_000_000,
        'ipoDate': (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d'),
        # Data is newest to oldest
        'quarterly_earnings': [{'Earnings': 1.5, 'Revenue': 1500}, {'Earnings': 1.4, 'Revenue': 1400}, {'Earnings': 1.3, 'Revenue': 1300}, {'Earnings': 1.2, 'Revenue': 1200}, {'Earnings': 1.0, 'Revenue': 1000}],
        'quarterly_financials': [{'Net Income': 150, 'Total Revenue': 1500}, {'Net Income': 130, 'Total Revenue': 1300}, {'Net Income': 110, 'Total Revenue': 1100}, {'Net Income': 100, 'Total Revenue': 1000}],
        'annual_earnings': [{'Earnings': 4.0, 'Revenue': 4000, 'Net Income': 400}]
    }
    base_data.update(overrides)
    return base_data

def create_mock_price_data(performance_factor, length=50):
    """Creates mock stock and S&P 500 price data to simulate market conditions."""
    stock_data, sp500_data = [], []
    stock_price, sp500_price = 100.0, 4000.0

    for i in range(length):
        date_str = (datetime.now() - timedelta(days=length - 1 - i)).strftime('%Y-%m-%d')
        
        rally_multiplier = 1.05 if 25 <= i < 28 else 1.0
        
        # Using additive change to avoid multiplication issues
        sp500_change = (sp500_price * 0.001) * rally_multiplier
        stock_change = (stock_price * 0.001) * performance_factor * rally_multiplier
        
        stock_price += stock_change
        sp500_price += sp500_change
        
        stock_data.append({'formatted_date': date_str, 'close': stock_price, 'high': stock_price * 1.01, 'low': stock_price * 0.99, 'volume': 100000})
        sp500_data.append({'formatted_date': date_str, 'close': sp500_price, 'high': sp500_price * 1.01, 'low': sp500_price * 0.99, 'volume': 50000000})
        
    return stock_data, sp500_data

def create_mock_index_data(trend='Bullish'):
    """Creates mock data for major market indices based on a trend scenario."""
    base_data = {
        '^GSPC': {'current_price': 4500, 'sma_50': 4400, 'sma_200': 4200, 'high_52_week': 4800, 'low_52_week': 4000},
        '^DJI': {'current_price': 35000, 'sma_50': 34000, 'sma_200': 32000, 'high_52_week': 38000, 'low_52_week': 30000},
        '^IXIC': {'current_price': 14000, 'sma_50': 13500, 'sma_200': 13000, 'high_52_week': 15000, 'low_52_week': 12000}
    }
    if trend == 'Bearish':
        base_data['^GSPC']['current_price'], base_data['^GSPC']['sma_50'] = 4300, 4400
        base_data['^DJI']['current_price'], base_data['^DJI']['sma_50'] = 33000, 34000
        base_data['^IXIC']['current_price'], base_data['^IXIC']['sma_50'] = 13000, 13500
    if trend == 'Neutral':
        base_data['^GSPC']['current_price'], base_data['^GSPC']['sma_50'] = 4500, 4400
        base_data['^DJI']['current_price'], base_data['^DJI']['sma_50'] = 33000, 34000 # One index is bearish
        base_data['^IXIC']['current_price'], base_data['^IXIC']['sma_50'] = 14000, 13500
    return base_data

# --- Test Suite ---

class TestLeadershipLogic(unittest.TestCase):

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
        check_has_limited_float(create_mock_financial_data(floatShares=10_000_000), details)
        self.assertTrue(details['has_limited_float']['pass'])
        check_has_limited_float(create_mock_financial_data(floatShares=50_000_000), details)
        self.assertFalse(details['has_limited_float']['pass'])
        check_has_limited_float(create_mock_financial_data(sharesOutstanding=0), details)
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
        self.assertEqual(details['has_strong_yoy_eps_growth']['yoy_eps_growth_level'], 'Moderate Growth')

    def test_check_positive_recent_earnings(self):
        details = {}
        check_positive_recent_earnings(create_mock_financial_data(), details)
        self.assertTrue(details['has_positive_recent_earnings']['pass'])
        check_positive_recent_earnings(create_mock_financial_data(annual_earnings=[{'Earnings': -0.5}]), details)
        self.assertFalse(details['has_positive_recent_earnings']['pass'])

    def test_check_accelerating_growth(self):
        details = {}
        pass_earnings = [{'Earnings': 1.45, 'Revenue': 1450}, {'Earnings': 1.25, 'Revenue': 1250}, {'Earnings': 1.10, 'Revenue': 1100}, {'Earnings': 1.0, 'Revenue': 1000}]
        pass_financials = [{'Net Income': 159.5, 'Total Revenue': 1450}, {'Net Income': 125, 'Total Revenue': 1250}, {'Net Income': 100, 'Total Revenue': 1100}, {'Net Income': 80, 'Total Revenue': 1000}]
        check_accelerating_growth(create_mock_financial_data(quarterly_earnings=pass_earnings, quarterly_financials=pass_financials), details)
        self.assertTrue(details['has_accelerating_growth']['pass'])
        
        fail_earnings = [{'Earnings': 1.35}, {'Earnings': 1.30}, {'Earnings': 1.20}, {'Earnings': 1.0}]
        check_accelerating_growth(create_mock_financial_data(quarterly_earnings=fail_earnings, quarterly_financials=pass_financials), details)
        self.assertFalse(details['has_accelerating_growth']['pass'])

    def test_check_consecutive_quarterly_growth(self):
        details = {}
        pass_earnings = [{'Earnings': 3.45}, {'Earnings': 2.65}, {'Earnings': 2.12}, {'Earnings': 1.63}, {'Earnings': 1.30}]
        check_consecutive_quarterly_growth(create_mock_financial_data(quarterly_earnings=pass_earnings), details)
        self.assertTrue(details['has_consecutive_quarterly_growth']['pass'])
        self.assertEqual(details['has_consecutive_quarterly_growth']['growth_level'], 'Standard Growth')
        
        fail_earnings = [{'Earnings': 2.80}, {'Earnings': 2.20}, {'Earnings': 1.70}, {'Earnings': 1.63}, {'Earnings': 1.30}]
        check_consecutive_quarterly_growth(create_mock_financial_data(quarterly_earnings=fail_earnings), details)
        self.assertFalse(details['has_consecutive_quarterly_growth']['pass'])

    def test_check_outperforms_in_rally(self):
        details = {}
        stock_pass, sp500_pass = create_mock_price_data(performance_factor=2.0)
        check_outperforms_in_rally(stock_pass, sp500_pass, details)
        self.assertTrue(details['outperforms_in_rally']['pass'])
        
        stock_fail, sp500_fail = create_mock_price_data(performance_factor=0.5)
        check_outperforms_in_rally(stock_fail, sp500_fail, details)
        self.assertFalse(details['outperforms_in_rally']['pass'])

    def test_check_market_trend_context(self):
        details = {}
        check_market_trend_context(create_mock_index_data(trend='Bullish'), details)
        self.assertEqual(details['market_trend_context']['trend'], 'Bullish')
        check_market_trend_context(create_mock_index_data(trend='Bearish'), details)
        self.assertEqual(details['market_trend_context']['trend'], 'Bearish')
        check_market_trend_context(create_mock_index_data(trend='Neutral'), details)
        self.assertEqual(details['market_trend_context']['trend'], 'Neutral')

    def test_evaluate_market_trend_impact(self):
        details = {}
        stock_data, _ = create_mock_price_data(1, length=300)
        index_data = create_mock_index_data()

        # Bearish: shallow decline pass
        stock_data[-1]['close'] = stock_data[-1]['high'] * 0.95 # 5% decline
        index_data['^GSPC']['current_price'] = index_data['^GSPC']['high_52_week'] * 0.90 # 10% decline
        evaluate_market_trend_impact(stock_data, index_data, 'Bearish', [], details)
        self.assertTrue(details['market_trend_impact']['sub_results']['shallow_decline']['pass'])

        # Bullish: new 52-week high pass
        stock_data[-1]['close'] = max(d['high'] for d in stock_data) + 1
        evaluate_market_trend_impact(stock_data, index_data, 'Bullish', [], details)
        self.assertTrue(details['market_trend_impact']['sub_results']['new_52_week_high']['pass'])

        # Recovery: recent breakout pass
        stock_data[-1]['close'] = stock_data[-2]['close'] * 1.10 # 10% price jump
        stock_data[-1]['volume'] = stock_data[-2]['volume'] * 2.0 # 100% volume jump
        market_trends = [{'status': 'Bearish'}] * 4 + [{'status': 'Neutral'}]
        evaluate_market_trend_impact(stock_data, index_data, 'Neutral', market_trends, details)
        self.assertTrue(details['market_trend_impact']['is_recovery_phase'])
        self.assertTrue(details['market_trend_impact']['sub_results']['recent_breakout']['pass'])

    def test_check_industry_leadership(self):
        # Pass case: Ticker is a leader (rank 1)
        peers_data = {"industry": "Tech"}
        batch_data = {
            "TICKER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "PEER1": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000},
            "PEER2": {"annual_earnings": [{"Revenue": 200, "Net Income": 20}], "marketCap": 2000},
        }
        result = check_industry_leadership("TICKER", peers_data, batch_data)
        self.assertEqual(result['rank'], 1)

        # Fail case: Ticker is not a leader (rank 3)
        batch_data_fail = {
            "TICKER": {"annual_earnings": [{"Revenue": 200, "Net Income": 20}], "marketCap": 2000},
            "PEER1": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "PEER2": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000},
        }
        result_fail = check_industry_leadership("TICKER", peers_data, batch_data_fail)
        self.assertEqual(result_fail['rank'], 3)
        
        # Edge case: No peers found
        result_no_peers = check_industry_leadership("TICKER", {"industry": "Tech"}, {"TICKER": batch_data["TICKER"]})
        self.assertEqual(result_no_peers['rank'], 1)
        self.assertEqual(result_no_peers['total_peers_ranked'], 1)

if __name__ == '__main__':
    unittest.main()