# data-service/providers/yfinance_provider.py
import yfinance as yf
import pandas as pd

def get_stock_data(ticker: str) -> list | None:
    """
    Fetches historical stock data from Yahoo Finance using the yfinance library
    and formats it into the application's standard list-of-dictionaries format.

    Args:
        ticker: The stock symbol to fetch data for.

    Returns:
        A list of dictionaries with OHLCV data, or None if an error occurs.
    """
    try:
        # Create a Ticker object
        stock = yf.Ticker(ticker)
        
        # Get historical market data for the last year
        # yfinance returns a pandas DataFrame
        hist_df = stock.history(period="1y")
        
        # If the DataFrame is empty, the ticker might be invalid or delisted
        if hist_df.empty:
            print(f"No data found for ticker: {ticker}")
            return None
            
        # Reset index to make 'Date' a column instead of the index
        hist_df.reset_index(inplace=True)

        # Rename columns to match our standardized format where necessary
        # yfinance uses capitalized column names ('Open', 'High', etc.)
        hist_df.rename(columns={
            'Date': 'formatted_date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }, inplace=True)
        
        # 'Adj Close' is often available; we'll map it to 'adjclose'
        if 'Adj Close' in hist_df.columns:
            hist_df['adjclose'] = hist_df['Adj Close']
        else:
            # Fallback to 'close' if 'Adj Close' is not present
            hist_df['adjclose'] = hist_df['close']

        # Format the date to string 'YYYY-MM-DD'
        hist_df['formatted_date'] = hist_df['formatted_date'].dt.strftime('%Y-%m-%d')
        
        # Define the columns we need for our standard format
        required_columns = [
            'formatted_date', 'open', 'high', 'low', 'close', 'volume', 'adjclose'
        ]
        
        # Select only the required columns
        standardized_df = hist_df[required_columns]

        # Convert the DataFrame to the required list of dictionaries format
        return standardized_df.to_dict(orient='records')

    except Exception as e:
        print(f"Error fetching data from yfinance for {ticker}: {e}")
        return None