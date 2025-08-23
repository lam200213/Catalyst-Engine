# backend-services/leadership-service/data_fetcher.py 

import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

# --- Create a shared requests Session for connection pooling and retries ---
session = requests.Session()

# Define the retry strategy
retry_strategy = Retry(
    total=3,  # Total number of retries
    backoff_factor=1,  # Wait 1s, 2s, 4s between retries
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
    allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
)

# Mount the retry strategy to the session
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)
# --- End of shared session configuration ---

# --- Helper functions for data fetching ---
def fetch_financial_data(ticker):
    """
    Fetch financial data from data service, handling errors gracefully.
    Returns a tuple of (data, status_code).
    """
    try:
        financials_url = f"{DATA_SERVICE_URL}/financials/core/{ticker}"
        financials_response = session.get(financials_url, timeout=10)
        
        financials_response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            
        return financials_response.json(), 200
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Could not fetch financial data for {ticker}: {e}")
        return None, getattr(e.response, 'status_code', 503)

def fetch_price_data(ticker):
    """Fetch price data from data service"""
    try:
        # Fetch stock price data
        stock_url = f"{DATA_SERVICE_URL}/price/{ticker}"
        stock_response = session.get(stock_url, timeout=10) 
        stock_response.raise_for_status()
            
        stock_data = stock_response.json()
        return stock_data
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching price data for {ticker} after retries: {e}")
        return None

def fetch_index_data():
    """Fetch major index data from data service"""
    # Fetch data for all three major indices for market trend context
    indices = ['^GSPC', '^DJI', '^IXIC']
    index_data = {}
    for index in indices:
        try:
            url = f"{DATA_SERVICE_URL}/financials/core/{index}"
            response = session.get(url, timeout=10)
            response.raise_for_status()
            index_data[index] = response.json()
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error fetching index data for {index} after retries: {e}")
            index_data[index] = {}
            
    return index_data

def fetch_peer_data(ticker):
    """Fetches industry and peer list from the data-service."""
    try:
        peers_url = f"{DATA_SERVICE_URL}/industry/peers/{ticker}"
        response = session.get(peers_url, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch industry peers for {ticker}", status_code)

def fetch_batch_financials(tickers):
    """Fetches core financial data for a list of tickers in a single batch."""
    try:
        batch_url = f"{DATA_SERVICE_URL}/financials/core/batch"
        payload = {"tickers": tickers, "metrics": ["revenue", "marketCap", "netIncome"]}
        response = session.post(batch_url, json=payload, timeout=40)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch batch financial data", status_code)
    
def fetch_market_trends():
    """Fetches historical market trend data."""
    try:
        trends_url = f"{DATA_SERVICE_URL}/market-trends"
        response = session.get(trends_url, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch market trends data", status_code)

# --- End of helper functions ---