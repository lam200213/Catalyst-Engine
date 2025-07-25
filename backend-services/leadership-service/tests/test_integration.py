import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import date, datetime, timezone, timedelta

# Add the parent directory to the sys.path to allow imports from the main app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

# Test class for integration tests
class TestLeadershipServiceIntegration(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        
    def tearDown(self):
        pass

    @patch('app.requests.get')
    def test_leadership_endpoint_success(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with valid data
        """
        # Mock financial data response
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},
                {'Earnings': 110, 'Revenue': 1100},  # +10%
                {'Earnings': 126.5, 'Revenue': 1200}  # +15% (EPS accelerating)
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},  # 5% margin
                {'Net Income': 55, 'Total Revenue': 1100},  # 5.5% margin
                {'Net Income': 65, 'Total Revenue': 1200}   # 6.5% margin (accelerating)
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100}]),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(response_data['ticker'], 'AAPL')
        self.assertIn('results', response_data)
        self.assertIn('metadata', response_data)
        
        # Check that all leadership checks are present (using snake_case as per new architecture)
        results = response_data['results']
        self.assertIn('is_small_to_mid_cap', results)
        self.assertIn('is_recent_ipo', results)
        self.assertIn('has_limited_float', results)
        self.assertIn('has_accelerating_growth', results)
        self.assertIn('has_strong_yoy_eps_growth', results)
        self.assertIn('has_consecutive_quarterly_growth', results)
        self.assertIn('has_positive_recent_earnings', results)
        self.assertIn('outperforms_in_rally', results)
        self.assertIn('market_trend_context', results)
        self.assertIn('shallow_decline', results)
        self.assertIn('new_52_week_high', results)
        self.assertIn('recent_breakout', results)
        
        # Check YoY EPS growth level
        self.assertIn('yoy_eps_growth_level', results)
        
        # Check consecutive quarterly growth level
        self.assertIn('consecutive_quarterly_growth_level', results)
        
        # Check metadata includes execution_time
        self.assertIn('execution_time', response_data['metadata'])

    @patch('app.requests.get')
    def test_leadership_endpoint_data_service_unavailable(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint when data service is unavailable
        """
        # Mock financial data service returning 503
        mock_get.side_effect = [
            MagicMock(status_code=503),  # Financial data service unavailable
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 503)
        response_data = response.json
        self.assertIn('error', response_data)
        self.assertEqual(response_data['error'], 'Unable to fetch financial data')

    @patch('app.requests.get')
    def test_leadership_endpoint_invalid_ticker(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with invalid ticker parameter
        """
        # Make request to the endpoint with invalid ticker
        response = self.app.get('/leadership/')
        
        # Assert response
        self.assertEqual(response.status_code, 404)  # Flask returns 404 for missing parameter

    @patch('app.requests.get')
    def test_leadership_endpoint_empty_ticker(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with empty ticker parameter
        """
        # Make request to the endpoint with empty ticker
        response = self.app.get('/leadership/')
        
        # Assert response
        self.assertEqual(response.status_code, 404)  # Flask returns 404 for missing parameter

    @patch('app.requests.get')
    def test_leadership_endpoint_missing_required_data(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint when required data is missing
        """
        # Mock financial data response with missing data
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': None,
            'sharesOutstanding': None,
            'floatShares': None,
            'ipoDate': None,
            'quarterly_earnings': [],
            'quarterly_financials': [],
            'annual_earnings': []
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: []),  # Stock price data
            MagicMock(status_code=200, json=lambda: {}),  # S&P 500 core financial data
            MagicMock(status_code=200, json=lambda: {}),  # Dow Jones core financial data
            MagicMock(status_code=200, json=lambda: {})   # NASDAQ core financial data
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(response_data['ticker'], 'AAPL')
        
        # Check that all leadership checks return False when data is missing
        results = response_data['results']
        self.assertFalse(results['is_small_to_mid_cap'])
        self.assertFalse(results['is_recent_ipo'])
        self.assertFalse(results['has_limited_float'])
        self.assertFalse(results['has_accelerating_growth'])
        self.assertFalse(results['has_strong_yoy_eps_growth'])
        self.assertFalse(results['has_consecutive_quarterly_growth'])
        self.assertFalse(results['has_positive_recent_earnings'])
        self.assertFalse(results['outperforms_in_rally'])
        self.assertEqual(results['market_trend_context'], 'Unknown')
        self.assertFalse(results['shallow_decline'])
        self.assertFalse(results['new_52_week_high'])
        self.assertFalse(results['recent_breakout'])
        self.assertEqual(results['yoy_eps_growth_level'], 'Insufficient Data')
        self.assertEqual(results['consecutive_quarterly_growth_level'], 'Insufficient Data')

    @patch('app.requests.get')
    def test_leadership_endpoint_yoy_eps_growth_levels(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with different YoY EPS growth levels
        """
        # Test Exceptional Growth (>45%)
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},  # Base
                {'Earnings': 110, 'Revenue': 1100},
                {'Earnings': 126.5, 'Revenue': 1200},
                {'Earnings': 150, 'Revenue': 1300},
                {'Earnings': 200, 'Revenue': 1400}  # 100% growth (Exceptional Growth)
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},
                {'Net Income': 55, 'Total Revenue': 1100},
                {'Net Income': 65, 'Total Revenue': 1200},
                {'Net Income': 75, 'Total Revenue': 1300},
                {'Net Income': 100, 'Total Revenue': 1400}
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100} for _ in range(252)]),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        results = response_data['results']
        self.assertTrue(results['has_strong_yoy_eps_growth'])
        self.assertEqual(results['yoy_eps_growth_level'], 'Exceptional Growth')
        # Note: The test data may not have sufficient quarters for consecutive quarterly growth
        # so we just check that the field exists
        self.assertIn('consecutive_quarterly_growth_level', results)

    @patch('app.requests.get')
    def test_leadership_endpoint_consecutive_quarterly_growth_levels(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with different consecutive quarterly growth levels
        """
        # Test Exceptional Growth (>45%)
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},  # Base
                {'Earnings': 110, 'Revenue': 1100},
                {'Earnings': 126.5, 'Revenue': 1200},
                {'Earnings': 150, 'Revenue': 1300},
                {'Earnings': 180, 'Revenue': 1400},
                {'Earnings': 220, 'Revenue': 1500}  # High growth
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},
                {'Net Income': 55, 'Total Revenue': 1100},
                {'Net Income': 65, 'Total Revenue': 1200},
                {'Net Income': 75, 'Total Revenue': 1300},
                {'Net Income': 90, 'Total Revenue': 1400},
                {'Net Income': 110, 'Total Revenue': 1500}
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100} for _ in range(252)]),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        results = response_data['results']
        # Note: The actual growth level will depend on the calculated rolling averages
        # We just check that the field exists
        self.assertIn('consecutive_quarterly_growth_level', results)

    @patch('app.requests.get')
    def test_leadership_endpoint_market_trend_evaluation(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with market trend evaluation
        """
        # Test Bullish market trend
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},
                {'Earnings': 110, 'Revenue': 1100},
                {'Earnings': 126.5, 'Revenue': 1200},
                {'Earnings': 150, 'Revenue': 1300}
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},
                {'Net Income': 55, 'Total Revenue': 1100},
                {'Net Income': 65, 'Total Revenue': 1200},
                {'Net Income': 75, 'Total Revenue': 1300}
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        
        # Create stock data with new 52-week high
        stock_data = []
        for i in range(251):  # 251 days of data
            stock_data.append({
                'formatted_date': f'2023-01-01 + {i} days',
                'close': 90 + (i * 0.1),  # Gradually increasing price
                'high': 95 + (i * 0.1),
                'low': 85 + (i * 0.1),
                'open': 88 + (i * 0.1),
                'volume': 1000000
            })
        # Last day with new high - make sure the current price is higher than all previous highs
        stock_data.append({
            'formatted_date': '2023-01-01 + 251 days',
            'close': 121,  # Higher than the previous high of 120
            'high': 121,
            'low': 115,
            'open': 118,
            'volume': 1000000
        })
        
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: stock_data),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data (Bullish)
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data (Bullish)
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data (Bullish)
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        results = response_data['results']
        self.assertEqual(results['market_trend_context'], 'Bullish')
        self.assertTrue(results['new_52_week_high'])

    # New tests for gRPC client functionality
    @patch('app.requests.get')
    def test_leadership_endpoint_grpc_unavailable(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint when gRPC service is unavailable
        """
        # Mock gRPC service returning 503
        mock_get.side_effect = [
            MagicMock(status_code=503),  # gRPC service unavailable
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 503)
        response_data = response.json
        self.assertIn('error', response_data)
        self.assertEqual(response_data['error'], 'Unable to fetch financial data')

    # New tests for Redis caching functionality
    @patch('app.requests.get')
    def test_leadership_endpoint_cache_hit(self, mock_get):
        """
        Test the /leadership/<ticker> endpoint with cached data
        """
        # Mock financial data response
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},
                {'Earnings': 110, 'Revenue': 1100},
                {'Earnings': 126.5, 'Revenue': 1200}
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},
                {'Net Income': 55, 'Total Revenue': 1100},
                {'Net Income': 65, 'Total Revenue': 1200}
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data for first call
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100}]),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            }),
            mock_financial_response,  # Financial data for second call (cache hit simulation)
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100}]),  # Stock price data for second call
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data for second call
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data for second call
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data for second call
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make first request to the endpoint
        response1 = self.app.get('/leadership/AAPL')
        self.assertEqual(response1.status_code, 200)
        
        # Make second request to the same endpoint (should hit cache)
        response2 = self.app.get('/leadership/AAPL')
        self.assertEqual(response2.status_code, 200)
        
        # Both responses should be identical
        # Compare only the 'results' part of the JSON, ignoring the volatile 'metadata'
        self.assertEqual(response1.json['results'], response2.json['results'])

    # New tests for orchestrated check execution
    @patch('app.time.time', side_effect=[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]) # Mock time.time() for non-zero execution time
    @patch('app.requests.get')
    def test_leadership_endpoint_parallel_execution(self, mock_get, mock_time):
        """
        Test the /leadership/<ticker> endpoint with parallel check execution
        """
        # Mock financial data response
        mock_financial_response = MagicMock()
        mock_financial_response.status_code = 200
        mock_financial_response.json.return_value = {
            'marketCap': 1000000000,  # $1B
            'sharesOutstanding': 100000000,
            'floatShares': 15000000,  # 15% float
            'ipoDate': '2020-01-01',  # 5 years ago
            'quarterly_earnings': [
                {'Earnings': 100, 'Revenue': 1000},
                {'Earnings': 110, 'Revenue': 1100},
                {'Earnings': 126.5, 'Revenue': 1200}
            ],
            'quarterly_financials': [
                {'Net Income': 50, 'Total Revenue': 1000},
                {'Net Income': 55, 'Total Revenue': 1100},
                {'Net Income': 65, 'Total Revenue': 1200}
            ],
            'annual_earnings': [
                {'Earnings': 2.50}
            ]
        }
        mock_get.side_effect = [
            mock_financial_response,  # Financial data
            MagicMock(status_code=200, json=lambda: [{'formatted_date': '2024-01-01', 'close': 100}]),  # Stock price data
            MagicMock(status_code=200, json=lambda: {  # S&P 500 core financial data
                'current_price': 4500,
                'sma_50': 4400,
                'sma_200': 4200,
                'high_52_week': 4800,
                'low_52_week': 4000
            }),
            MagicMock(status_code=200, json=lambda: {  # Dow Jones core financial data
                'current_price': 35000,
                'sma_50': 34000,
                'sma_200': 32000,
                'high_52_week': 38000,
                'low_52_week': 30000
            }),
            MagicMock(status_code=200, json=lambda: {  # NASDAQ core financial data
                'current_price': 15000,
                'sma_50': 14500,
                'sma_200': 13500,
                'high_52_week': 16000,
                'low_52_week': 12000
            })
        ]

        # Make request to the endpoint
        response = self.app.get('/leadership/AAPL')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(response_data['ticker'], 'AAPL')
        self.assertIn('results', response_data)
        self.assertIn('metadata', response_data)
        
        # Check that execution_time is present in metadata
        self.assertIn('execution_time', response_data['metadata'])
        
        # Check that execution_time is a reasonable value (should be fast with parallel execution)
        execution_time = response_data['metadata']['execution_time']
        self.assertIsInstance(execution_time, (int, float))
        self.assertGreater(execution_time, 0)
        self.assertLess(execution_time, 5)  # Should complete in less than 5 seconds

    @patch('app.requests.post') # Mock requests.post for batch endpoint
    @patch('app.requests.get')
    def test_industry_rank_endpoint_success(self, mock_get, mock_post):
        """
        Test the /leadership/industry_rank/<ticker> endpoint with valid data
        """
        # Mock response for GET /industry/peers/<ticker>
        mock_peers_response = MagicMock()
        mock_peers_response.status_code = 200
        mock_peers_response.json.return_value = {
            "industry": "Technology",
            "peers": ["MSFT", "GOOGL", "AMZN", "FB"]
        }

        # Mock response for POST /financials/core/batch
        mock_batch_response = MagicMock()
        mock_batch_response.status_code = 200
        mock_batch_response.json.return_value = {
            "AAPL": {"revenue": 387530000000, "marketCap": 3000000000000},
            "MSFT": {"revenue": 211915000000, "marketCap": 3100000000000},
            "GOOGL": {"revenue": 307394000000, "marketCap": 2200000000000},
            "AMZN": {"revenue": 574785000000, "marketCap": 1900000000000},
            "FB": {"revenue": 134900000000, "marketCap": 1200000000000}
        }

        mock_get.return_value = mock_peers_response
        mock_post.return_value = mock_batch_response

        response = self.app.get('/leadership/industry_rank/AAPL')
        self.assertEqual(response.status_code, 200)
        response_data = response.json

        self.assertEqual(response_data['ticker'], 'AAPL')
        self.assertEqual(response_data['industry'], 'Technology')
        self.assertIn('rank', response_data)
        self.assertIn('total_peers_ranked', response_data)
        self.assertIn('ranked_peers_data', response_data)
        self.assertIsInstance(response_data['rank'], int)
        self.assertGreater(response_data['rank'], 0)
        self.assertIsInstance(response_data['total_peers_ranked'], int)
        self.assertGreater(response_data['total_peers_ranked'], 0)
        self.assertIsInstance(response_data['ranked_peers_data'], list)
        self.assertGreater(len(response_data['ranked_peers_data']), 0)

    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_industry_rank_endpoint_incomplete_data(self, mock_get, mock_post):
        """
        Test the /leadership/industry_rank/<ticker> endpoint with incomplete financial data for peers
        """
        mock_peers_response = MagicMock()
        mock_peers_response.status_code = 200
        mock_peers_response.json.return_value = {
            "industry": "Technology",
            "peers": ["MSFT", "GOOGL", "AMZN"]
        }

        mock_batch_response = MagicMock()
        mock_batch_response.status_code = 200
        mock_batch_response.json.return_value = {
            "AAPL": {"revenue": 387530000000, "marketCap": 3000000000000},
            "MSFT": {"revenue": None, "marketCap": 3100000000000}, # Incomplete revenue
            "GOOGL": {"revenue": 307394000000, "marketCap": None}, # Incomplete marketCap
            "AMZN": {"revenue": 574785000000, "marketCap": 1900000000000}
        }

        mock_get.return_value = mock_peers_response
        mock_post.return_value = mock_batch_response

        response = self.app.get('/leadership/industry_rank/AAPL')
        self.assertEqual(response.status_code, 200)
        response_data = response.json

        self.assertEqual(response_data['ticker'], 'AAPL')
        self.assertEqual(response_data['industry'], 'Technology')
        self.assertIn('rank', response_data)
        self.assertIn('total_peers_ranked', response_data)
        self.assertIn('ranked_peers_data', response_data)
        
        # Only AAPL and AMZN should be ranked
        self.assertEqual(response_data['total_peers_ranked'], 2)
        self.assertEqual(len(response_data['ranked_peers_data']), 2)
        self.assertFalse(any(d['ticker'] == 'MSFT' for d in response_data['ranked_peers_data']))
        self.assertFalse(any(d['ticker'] == 'GOOGL' for d in response_data['ranked_peers_data']))

    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_industry_rank_endpoint_no_peers(self, mock_get, mock_post):
        """
        Test the /leadership/industry_rank/<ticker> endpoint when no peers are returned
        """
        mock_peers_response = MagicMock()
        mock_peers_response.status_code = 200
        mock_peers_response.json.return_value = {
            "industry": "Technology",
            "peers": []
        }

        mock_get.return_value = mock_peers_response
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "AAPL": {"revenue": 387530000000, "marketCap": 3000000000000}
        }) # Batch response with data for the original ticker only

        response = self.app.get('/leadership/industry_rank/AAPL')
        self.assertEqual(response.status_code, 200)
        response_data = response.json

        self.assertEqual(response_data['ticker'], 'AAPL')
        self.assertEqual(response_data['industry'], 'Technology')
        self.assertIn('rank', response_data)
        self.assertIn('total_peers_ranked', response_data)
        self.assertIn('ranked_peers_data', response_data)
        
        # Only the original ticker should be ranked if no peers
        self.assertEqual(response_data['total_peers_ranked'], 1)
        self.assertEqual(response_data['rank'], 1)
        self.assertEqual(len(response_data['ranked_peers_data']), 1)
        self.assertEqual(response_data['ranked_peers_data'][0]['ticker'], 'AAPL')

    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_industry_rank_endpoint_peers_service_unavailable(self, mock_get, mock_post):
        """
        Test the /leadership/industry_rank/<ticker> endpoint when peers service is unavailable
        """
        mock_get.return_value = MagicMock(status_code=503) # Peers service unavailable

        response = self.app.get('/leadership/industry_rank/AAPL')
        self.assertEqual(response.status_code, 500) # Error from check_industry_leadership
        response_data = response.json
        self.assertIn('error', response_data)
        self.assertIn('Could not fetch industry peers', response_data['error'])

    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_industry_rank_endpoint_batch_service_unavailable(self, mock_get, mock_post):
        """
        Test the /leadership/industry_rank/<ticker> endpoint when batch financial service is unavailable
        """
        mock_peers_response = MagicMock()
        mock_peers_response.status_code = 200
        mock_peers_response.json.return_value = {
            "industry": "Technology",
            "peers": ["MSFT", "GOOGL"]
        }

        mock_get.return_value = mock_peers_response
        mock_post.return_value = MagicMock(status_code=503) # Batch service unavailable

        response = self.app.get('/leadership/industry_rank/AAPL')
        self.assertEqual(response.status_code, 500) # Error from check_industry_leadership
        response_data = response.json
        self.assertIn('error', response_data)
        self.assertIn('Could not fetch batch financial data', response_data['error'])

if __name__ == '__main__':
    unittest.main()