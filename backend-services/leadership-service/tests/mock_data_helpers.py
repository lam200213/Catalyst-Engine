# backend-services/leadership-service/tests/mock_data_helpers.py
from datetime import datetime, timedelta

def create_mock_financial_data(**overrides):
    """
    Creates mock financial data. If passing_data=True, generates data guaranteed
    to pass accelerating growth checks for earnings, revenue, AND net margin.
    """
    passing_flag = overrides.pop('passing_data', False)
    base_data = {
        'marketCap': 5_000_000_000,
        'sharesOutstanding': 100_000_000,
        'floatShares': 50_000_000,
        'ipoDate': (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d'),
        # Data that fails accelerating growth
        'quarterly_earnings': [
            {'Earnings': 150, 'Revenue': 1500, 'Net Income': 150},
            {'Earnings': 140, 'Revenue': 1400, 'Net Income': 140},
            {'Earnings': 130, 'Revenue': 1300, 'Net Income': 130},
            {'Earnings': 120, 'Revenue': 1200, 'Net Income': 120},
            {'Earnings': 100, 'Revenue': 1000, 'Net Income': 100}
        ],
        'quarterly_financials': [
            {'Net Income': 150, 'Total Revenue': 1500},
            {'Net Income': 130, 'Total Revenue': 1300},
            {'Net Income': 110, 'Total Revenue': 1100},
            {'Net Income': 100, 'Total Revenue': 1000}
        ],
        'annual_earnings': [{'Earnings': 400, 'Revenue': 4000, 'Net Income': 400}]
    }
    if passing_flag:
        # This data is mathematically designed to pass all growth checks simultaneously.
        # 1. Consecutive QoQ EPS Growth: Rates are ~39%, 38%, 37%, 36%. All >20%.
        #    The average is >35%, satisfying the "High Growth" level check.
        # 2. Accelerating Growth (Earnings, Revenue, Margin)
        #    - Earnings Growth Rates (Q4vQ3, Q3vQ2, Q2vQ1): 38.9% > 38.2% > 36.8% (Accelerating)
        #    - Revenue Growth Rates: 20.0% > 15.0% > 10.0% (Accelerating)
        #    - Margin Growth Rates: 8.2% > 7.3% > 5.9% (Accelerating)
        base_data['quarterly_earnings'] = [
            {'Earnings': 3.57, 'Revenue': 2278, 'Net Income': 239}, # Q4 (Recent)
            {'Earnings': 2.57, 'Revenue': 1898, 'Net Income': 184}, # Q3
            {'Earnings': 1.86, 'Revenue': 1650, 'Net Income': 149}, # Q2
            {'Earnings': 1.36, 'Revenue': 1500, 'Net Income': 128}, # Q1
            {'Earnings': 1.00, 'Revenue': 1000, 'Net Income': 100}  # Q0 (Year Ago)
        ]
        base_data['quarterly_financials'] = [
            {'Net Income': 239, 'Total Revenue': 2278}, # Margin: 10.49%
            {'Net Income': 184, 'Total Revenue': 1898}, # Margin: 9.69%
            {'Net Income': 149, 'Total Revenue': 1650}, # Margin: 9.03%
            {'Net Income': 128, 'Total Revenue': 1500}  # Margin: 8.53%
        ]
        base_data['annual_earnings'] = [{'Earnings': 800, 'Revenue': 8000, 'Net Income': 850}]

    base_data.update(overrides)
    return base_data
def create_mock_price_data(performance_factor, length=50, **kwargs):
    """
    Creates mock price data. Simulates a strong market rally if passing_data=True,
    and ensures the stock's performance correctly reflects the performance_factor.
    """
    passing_flag = kwargs.get('passing_data', False)
    stock_data, sp500_data = [], []
    stock_price, sp500_price = 100.0, 4000.0

    for i in range(length):
        date_str = (datetime.now() - timedelta(days=length - 1 - i)).strftime('%Y-%m-%d')
        
        sp500_daily_change = 1.0005 # Base daily change

        sp500_price *= sp500_daily_change
        
        # Correctly apply the performance factor to the market's movement
        stock_daily_change = 1 + ((sp500_daily_change - 1) * performance_factor)
        stock_price *= stock_daily_change
        
        stock_data.append({
            'formatted_date': date_str, 
            'open': stock_price * 0.995,
            'close': stock_price, 
            'high': stock_price * 1.01, 
            'low': stock_price * 0.99, 
            'volume': 100000,
            'adjclose': stock_price
        })
        sp500_data.append({
            'formatted_date': date_str, 
            'open': sp500_price * 0.995,
            'close': sp500_price, 
            'high': sp500_price * 1.01, 
            'low': sp500_price * 0.99, 
            'volume': 50000000,
            'adjclose': sp500_price
        })
    return stock_data, sp500_data

def create_mock_index_data(trend='Bullish'):
    """Creates mock data for major market indices."""
    return {
        '^GSPC': {'current_price': 4500, 'sma_50': 4400, 'sma_200': 4200, 'high_52_week': 4800, 'low_52_week': 4000},
    }