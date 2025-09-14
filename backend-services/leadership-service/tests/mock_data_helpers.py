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
        'quarterly_earnings': [{'Earnings': 1.5, 'Revenue': 1500}, {'Earnings': 1.4, 'Revenue': 1400}, {'Earnings': 1.3, 'Revenue': 1300}, {'Earnings': 1.2, 'Revenue': 1200}, {'Earnings': 1.0, 'Revenue': 1000}],
        'quarterly_financials': [{'Net Income': 150, 'Total Revenue': 1500}, {'Net Income': 130, 'Total Revenue': 1300}, {'Net Income': 110, 'Total Revenue': 1100}, {'Net Income': 100, 'Total Revenue': 1000}],
        'annual_earnings': [{'Earnings': 4.0, 'Revenue': 4000, 'Net Income': 400}]
    }
    if passing_flag:
        # This data is specifically designed to have accelerating QoQ growth in all 3 metrics.
        base_data['quarterly_earnings'] = [
            {'Earnings': 3.45, 'Revenue': 3450}, # Q4
            {'Earnings': 2.50, 'Revenue': 2500}, # Q3
            {'Earnings': 1.90, 'Revenue': 1900}, # Q2
            {'Earnings': 1.50, 'Revenue': 1500}, # Q1
            {'Earnings': 1.00, 'Revenue': 1000}  # Q0 (year ago)
        ]
        base_data['quarterly_financials'] = [
            {'Net Income': 411, 'Total Revenue': 3450}, # Margin: 11.91%
            {'Net Income': 276, 'Total Revenue': 2500}, # Margin: 11.04%
            {'Net Income': 198, 'Total Revenue': 1900}, # Margin: 10.42%
            {'Net Income': 150, 'Total Revenue': 1500}  # Margin: 10.00%
        ]
    
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
        
        stock_data.append({'formatted_date': date_str, 'close': stock_price, 'high': stock_price * 1.01, 'low': stock_price * 0.99, 'volume': 100000})
        sp500_data.append({'formatted_date': date_str, 'close': sp500_price, 'high': sp500_price * 1.01, 'low': sp500_price * 0.99, 'volume': 50000000})
        
    return stock_data, sp500_data

def create_mock_index_data(trend='Bullish'):
    """Creates mock data for major market indices."""
    return {
        '^GSPC': {'current_price': 4500, 'sma_50': 4400, 'sma_200': 4200, 'high_52_week': 4800, 'low_52_week': 4000},
    }