# backend-services/leadership-service/tests/test_industry_peer_checks.py
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from checks.industry_peer_checks import check_industry_leadership

class TestIndustryPeerChecks(unittest.TestCase):

    def test_check_industry_leadership(self):
        details = {}
        # Pass case: Ticker is a leader (rank 1)
        peers_data = {"industry": "Tech"}
        batch_data = {
            "TICKER": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "PEER1": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000},
            "PEER2": {"annual_earnings": [{"Revenue": 200, "Net Income": 20}], "marketCap": 2000},
        }
        check_industry_leadership("TICKER", peers_data, batch_data, details)
        self.assertTrue(details['is_industry_leader']['pass'])
        self.assertEqual(details['is_industry_leader']['rank'], 1)

        # Fail case: Ticker is not a leader (rank 3)
        details = {}
        batch_data_fail = {
            "TICKER": {"annual_earnings": [{"Revenue": 200, "Net Income": 20}], "marketCap": 2000},
            "PEER1": {"annual_earnings": [{"Revenue": 1000, "Net Income": 100}], "marketCap": 10000},
            "PEER2": {"annual_earnings": [{"Revenue": 500, "Net Income": 50}], "marketCap": 5000},
        }
        check_industry_leadership("TICKER", peers_data, batch_data_fail, details)
        self.assertTrue(details['is_industry_leader']['pass']) # Rank 3 still passes
        self.assertEqual(details['is_industry_leader']['rank'], 3)

if __name__ == '__main__':
    unittest.main()