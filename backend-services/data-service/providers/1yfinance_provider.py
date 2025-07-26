
# backend-services/data-service/providers/yfinance_provider.py
import yfinance as yf
import datetime as dt
import sys
import pandas as pd

# Latest Add: Refactored entire file to use the yfinance library

def get_stock_data(ticker_symbol: str, start_date: dt.date = None) -> list | None:
    """
    Fetches historical stock data using the yfinance library.
    """
    print(f"YFINANCE_PROVIDER: Fetching price data for {ticker_symbol}")
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # Determine the period for the history call
        if start_date:
            history_df = ticker.history(start=start_date, auto_adjust=True)
        else:
            history_df = ticker.history(period="1y", auto_adjust=True)

        if history_df.empty:
            return None

        # Reset index to make 'Date' a column and format it
        history_df.reset_index(inplace=True)
        history_df['formatted_date'] = history_df['Date'].dt.strftime('%Y-%m-%d')
        
        # Rename columns to match our application's standard format
        history_df.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume'
        }, inplace=True)

        # Select and convert to the required list-of-dictionaries format
        return history_df[['formatted_date', 'open', 'high', 'low', 'close', 'volume']].to_dict('records')

    except Exception as e:
        # Improved error logging for better visibility
        sys.stderr.write(f"--- YFINANCE_PROVIDER ERROR in get_stock_data for {ticker_symbol} ---\n")
        sys.stderr.write(f"    Exception Type: {type(e).__name__}\n")
        sys.stderr.write(f"    Exception Details: {str(e)}\n")
        sys.stderr.flush()
        return None

def get_core_financials(ticker_symbol: str) -> dict | None:
    """
    Fetches core financial data using the yfinance library.
    """
    print(f"YFINANCE_PROVIDER: Fetching core financials for {ticker_symbol}")
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # The .info dictionary contains most of what we need
        info = ticker.info

        if not info or info.get('trailingEps') is None: # A good check for a valid ticker
             return None

        # Helper to transform yfinance quarterly earnings format
        def _transform_yf_earnings(yf_earnings_df):
            if yf_earnings_df is None or yf_earnings_df.empty:
                return []
            df = yf_earnings_df.reset_index()
            df.rename(columns={'index': 'date', 'Revenue': 'Revenue', 'Earnings': 'Earnings'}, inplace=True)
            return df.to_dict('records')

        data = {
            'marketCap': info.get('marketCap'),
            'sharesOutstanding': info.get('sharesOutstanding'),
            'floatShares': info.get('floatShares'),
            'ipoDate': dt.datetime.fromtimestamp(info['ipoDate']).strftime('%Y-%m-%d') if 'ipoDate' in info else None,
            'annual_earnings': _transform_yf_earnings(ticker.earnings),
            'quarterly_earnings': _transform_yf_earnings(ticker.quarterly_earnings),
            'quarterly_financials': _transform_yf_earnings(ticker.quarterly_financials)
        }
        return data

    except Exception as e:
        # Improved error logging
        sys.stderr.write(f"--- YFINANCE_PROVIDER ERROR in get_core_financials for {ticker_symbol} ---\n")
        sys.stderr.write(f"    Exception Type: {type(e).__name__}\n")
        sys.stderr.write(f"    Exception Details: {str(e)}\n")
        sys.stderr.flush()
        return None