# backend-services/leadership-service/tests/test_helper_functions.py
import unittest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from helper_functions import analyze_ticker_leadership
from tests.mock_data_helpers import create_mock_financial_data, create_mock_price_data, create_mock_index_data

class TestAnalyzeTickerLeadershipLogic(unittest.TestCase):
    def setUp(self):
        """Set up common mock data for all tests."""
        self.mock_index_data = create_mock_index_data(trend='Bullish')
        self.mock_market_trends = [{'trend': 'Bullish'}] * 365
        self.mock_stock_data, _ = create_mock_price_data(performance_factor=1.5, length=300)
        self.mock_peers_data = {'industry': 'Test Industry', 'peers': ['PEER']}
        # Base financial data for peers and other non-target stocks
        self.mock_all_financial_data = {
            "PEER": create_mock_financial_data(marketCap=1e9) # Weak peer
        }

    def test_clear_pass_scenario_explosive_grower(self):
        """
        Unit Test: Validates a stock that clearly passes the 'Explosive Grower' profile
        and has supporting characteristics in other profiles.
        """
        # Arrange: This data passes all financial checks and is a small-cap recent IPO.
        financial_data = create_mock_financial_data(passing_data=True, marketCap=5e9, ipoDate='2022-01-01')
        all_financials = {**self.mock_all_financial_data, "TICKER": financial_data}

        # Act
        result = analyze_ticker_leadership(
            "TICKER", self.mock_index_data, self.mock_market_trends,
            financial_data, self.mock_stock_data, self.mock_peers_data, all_financials
        )

        # Assert
        self.assertTrue(result['passes'])
        self.assertIn('Explosive Grower', result['leadership_summary']['qualified_profiles'])
        self.assertIn('Qualifies as a Explosive Grower', result['leadership_summary']['message'])

    def test_fail_scenario_primary_pass_but_supporting_fail(self):
        """
        Unit Test: Validates a stock that passes one profile 100% but completely
        fails another (0% pass rate), resulting in an overall failure.
        """
        # Arrange: Passes 'Explosive Grower' but designed to fail all 'High-Potential Setup' checks
        financial_data = create_mock_financial_data(
            passing_data=True,         # Passes 'Explosive Grower'
            marketCap=50e9,            # Fails is_small_to_mid_cap
            ipoDate='2005-01-01',      # Fails is_recent_ipo
            floatShares=200_000_000    # Fails has_limited_float
        )
        all_financials = {**self.mock_all_financial_data, "TICKER": financial_data}

        # Act
        result = analyze_ticker_leadership(
            "TICKER", self.mock_index_data, self.mock_market_trends,
            financial_data, self.mock_stock_data, self.mock_peers_data, all_financials
        )

        # Assert
        self.assertFalse(result['passes'])
        self.assertIn('Explosive Grower', result['leadership_summary']['qualified_profiles']) # It still identifies the primary pass...
        self.assertIn('lacked supporting characteristics', result['leadership_summary']['message']) # ...but correctly states the overall failure reason.
        self.assertEqual(result['profile_details']['high_potential_setup']['passed_checks'], 0) # Confirm the 0% pass rate.

    def test_fail_scenario_no_primary_pass(self):
        """
        Unit Test: Validates a stock that has some good qualities but fails to
        achieve a 100% pass on any single profile.
        """
        # Arrange: This data fails at least one check in every profile.
        financial_data = create_mock_financial_data(
            passing_data=False,        # Fails 'Explosive Grower'
            marketCap=50e9,            # Fails 'High-Potential Setup'
            revenue_base=1000,
            earnings_base=100
        )
        
        # We need to create at least 3 stronger peers to ensure the ticker does not rank in the top 3.
        peers = ['PEER1', 'PEER2', 'PEER3', 'PEER4']
        self.mock_peers_data = {'industry': 'Test Industry', 'peers': peers}
        
        all_financials = { "TICKER": financial_data }
        for i, peer_ticker in enumerate(peers):
            all_financials[peer_ticker] = create_mock_financial_data(
                marketCap=(100 + i) * 1e9,
                revenue_base=5000 + (i * 100),
                earnings_base=500 + (i * 10),
                ticker=peer_ticker
            )

        # Create underperforming stock data to ensure the 'market_trend_impact' check fails.
        failing_stock_data, _ = create_mock_price_data(performance_factor=0.5, length=300)

        # Act
        result = analyze_ticker_leadership(
            "TICKER", self.mock_index_data, self.mock_market_trends,
            financial_data, failing_stock_data, self.mock_peers_data, all_financials
        )
        
        # Assert
        self.assertFalse(result['passes'])
        self.assertEqual(len(result['leadership_summary']['qualified_profiles']), 0)
        self.assertIn('Does not meet the criteria for any leadership profile', result['leadership_summary']['message'])

if __name__ == '__main__':
    unittest.main()