# backend-services/leadership-service/tests/test_industry_peer_checks.py
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from checks.industry_peer_checks import check_industry_leadership, analyze_industry_leadership

class TestIndustryPeerChecks(unittest.TestCase):

    def test_analyze_industry_leadership_wrapper(self):
        """
        Tests the analyze_industry_leadership wrapper to ensure it validates
        peer contracts and correctly filters the all_financial_data map.
        """
        details = {}
        
        # --- Scenario 1: Valid data ---
        peers_data_raw = {"industry": "Software", "peers": ["PEER1"]}
        all_financials = {
            "TICKER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000, "ticker": "TICKER"},
            "PEER1": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000, "ticker": "PEER1"},
            "UNRELATED": {"annual_earnings": [{"Revenue": 100, "Net Income": 10}], "marketCap": 1000, "ticker": "UNRELATED"}
        }
        
        analyze_industry_leadership("TICKER", peers_data_raw, all_financials, details)
        result = details['is_industry_leader']
        
        self.assertTrue(result['pass'])
        self.assertEqual(result['rank'], 1)
        # Asserts that the 'UNRELATED' ticker was correctly excluded from the ranking.
        self.assertEqual(result['total_peers_ranked'], 2)

        # --- Scenario 2: Invalid peer data contract ---
        details = {}
        invalid_peers_raw = {"industry": "Hardware", "peers": "NOT_A_LIST"} # Violates contract
        
        analyze_industry_leadership("TICKER", invalid_peers_raw, all_financials, details)
        result = details['is_industry_leader']
        
        self.assertFalse(result['pass'])
        self.assertIn("Invalid peer data structure", result['message'])

    def test_check_industry_leadership(self):
        details = {}
        # Pass case: Ticker is a leader (rank 1)
        peers_data = {"industry": "Tech"}
        batch_data = {
            "LEADER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "MIDDLE": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000},
            "LAGGARD": {"annual_earnings": [{"Revenue": 200, "Net Income": 20}], "marketCap": 2000},
        }
        check_industry_leadership("LEADER", peers_data, batch_data, details)
        self.assertTrue(details['is_industry_leader']['pass'])
        self.assertEqual(details['is_industry_leader']['rank'], 1)

        # Pass case: Ticker is #3, which still passes the criteria
        check_industry_leadership("LAGGARD", peers_data, batch_data, details)
        self.assertTrue(details['is_industry_leader']['pass'])
        self.assertEqual(details['is_industry_leader']['rank'], 3)
        
        # Add a 4th company to test a failing rank
        batch_data_with_fourth = batch_data.copy()
        batch_data_with_fourth["NEWBIE"] = {"annual_earnings": [{"Revenue": 100, "Net Income": 10}], "marketCap": 1000}
        check_industry_leadership("NEWBIE", peers_data, batch_data_with_fourth, details)
        self.assertFalse(details['is_industry_leader']['pass'])
        self.assertEqual(details['is_industry_leader']['rank'], 4)

    def test_handles_incomplete_and_missing_data(self):
        details = {}
        peers_data = {"industry": "Retail"}
        
        # Data with missing keys and None values
        batch_data = {
            "TICKER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "PEER_NO_MCAP": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": None},
            "PEER_NO_REV": {"annual_earnings": [{"Net Income": 20}], "marketCap": 2000},
            "PEER_EMPTY": {}
        }

        check_industry_leadership("TICKER", peers_data, batch_data, details)
        result = details['is_industry_leader']
        
        # The logic should filter out the 3 bad peers and only rank the valid one.
        self.assertTrue(result['pass'])
        self.assertEqual(result['rank'], 1)
        self.assertEqual(result['total_peers_ranked'], 1)

    def test_handles_no_valid_data_for_ranking(self):
        details = {}
        peers_data = {"industry": "Pharma"}
        batch_data = { "TICKER": {"annual_earnings": [], "marketCap": None} } # No valid data at all
        
        check_industry_leadership("TICKER", peers_data, batch_data, details)
        result = details['is_industry_leader']
        
        self.assertFalse(result['pass'])
        self.assertIn("No complete financial data available", result['message'])

if __name__ == '__main__':
    unittest.main()