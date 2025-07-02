# data-service/providers/finnhub_provider.py
import finnhub
import os
import datetime as dt
import time

def get_stock_data(ticker: str) -> list | None:
    """
    Fetches historical stock data from Finnhub and transforms it
    into the application's standard list-of-dictionaries format.

    Args:
        ticker: The stock symbol to fetch data for.

    Returns:
        A list of dictionaries with OHLCV data, or None if an error occurs.
    """
    try:
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is not set in environment.")
            
        finnhub_client = finnhub.Client(api_key=api_key)
        
        # Calculate timestamps for the last year
        end_ts = int(time.time())
        start_ts = int((dt.datetime.now() - dt.timedelta(days=365)).timestamp())

        # Fetch candle data from Finnhub
        res = finnhub_client.stock_candles(ticker, 'D', start_ts, end_ts)
        print(f"Finnhub API response for {ticker}: {res}")

        # Finnhub returns 'no_data' in the 's' field on failure.
        if res.get('s') == 'no_data' or 'c' not in res:
            return None

        # Transform Finnhub's response (dictionary of lists) into our standard format.
        # This is the crucial transformation step.
        standardized_data = []
        for i in range(len(res['c'])):
            standardized_data.append({
                "high": res['h'][i],
                "low": res['l'][i],
                "open": res['o'][i],
                "close": res['c'][i],
                "volume": res['v'][i],
                "adjclose": res['c'][i], # Finnhub doesn't provide a separate adjusted close in this call.
                "formatted_date": dt.datetime.fromtimestamp(res['t'][i]).strftime('%Y-%m-%d')
            })
            
        return standardized_data
        
    except Exception as e:
        print(f"Error fetching data from Finnhub for {ticker}: {e}")
        return None