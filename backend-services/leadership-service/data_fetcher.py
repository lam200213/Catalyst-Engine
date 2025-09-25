# backend-services/leadership-service/data_fetcher.py 
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask 
import pandas as pd 
from datetime import datetime, timedelta
import pandas_market_calendars as mcal

app = Flask(__name__)

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

def fetch_batch_financials(tickers):
    """Fetches core financial data for a list of tickers in a single batch."""
    try:
        batch_url = f"{DATA_SERVICE_URL}/financials/core/batch"
        payload = {"tickers": tickers, "metrics": ["revenue", "marketCap", "netIncome"]}
        response = session.post(batch_url, json=payload, timeout=4000)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch batch financial data", status_code)

def fetch_price_data(ticker):
    """Fetch price data from data service"""
    try:
        # Fetch stock price data
        stock_url = f"{DATA_SERVICE_URL}/price/{ticker}"
        stock_response = session.get(stock_url, timeout=10) 
        stock_response.raise_for_status()
            
        stock_data = stock_response.json()
        return stock_data, 200
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching price data for {ticker} after retries: {e}")
        return None, getattr(e.response, 'status_code', 503)

def fetch_batch_price_data(tickers):
    """Fetches price data for a list of tickers in a single batch."""
    try:
        batch_url = f"{DATA_SERVICE_URL}/price/batch"
        # The source is hardcoded to yfinance as it's the default and required provider for this service
        payload = {"tickers": tickers, "source": "yfinance"}
        response = session.post(batch_url, json=payload, timeout=40) # Increased timeout for potentially large batches
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        return None, (f"Could not fetch batch price data", status_code)

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
    
def get_last_n_workdays(n_days=8):
    """Calculates the last N US business days, starting with the oldest date and ending with the most recent one."""
    nyse = mcal.get_calendar('NYSE')
    # Anchor the calculation to yesterday to ensure the trading day has completed.
    end_date = datetime.now().date() - timedelta(days=1)
    
    # Go back far enough to ensure we capture n_days even with holidays. A 10-day buffer is safe.
    start_date = end_date - timedelta(days=n_days + 10) 
    
    # Get the schedule of valid trading days up to and including yesterday.
    schedule = nyse.schedule(start_date=start_date, end_date=end_date)
    
    # The schedule's index contains the datetime objects of valid market days.
    # We format them and take the last n_days from the list.
    trading_days = schedule.index.strftime('%Y-%m-%d').tolist()
    
    return trading_days[-n_days:]

def fetch_market_trends(n_days=8):
    """
    Ensures the last n workdays of market trend data are available.
    It fetches what exists, identifies what's missing, and requests
    on-demand calculation for the missing days.
    order: oldest-to-newest
    """
    try:
        # 1. Determine the required dates 
        required_dates = get_last_n_workdays(n_days)
        
        # 2. Ask data-service for the trends it already has for this period
        start_date, end_date = required_dates[0], required_dates[-1]
        trends_url = f"{DATA_SERVICE_URL}/market-trends?start_date={start_date}&end_date={end_date}"
        response = session.get(trends_url, timeout=10)
        response.raise_for_status()
        existing_trends = response.json()
        
        existing_dates = {trend['date'] for trend in existing_trends}
        
        # 3. Identify which dates are missing
        missing_dates = [d for d in required_dates if d not in existing_dates]
        
        calculated_trends = []
        # 4. If there are missing dates, ask data-service to calculate them
        if missing_dates:
            calc_url = f"{DATA_SERVICE_URL}/market-trend/calculate"
            payload = {"dates": missing_dates}
            calc_response = session.post(calc_url, json=payload, timeout=30)
            calc_response.raise_for_status()
            calculated_trends = calc_response.json().get("trends", [])

        # 5. Combine existing and newly calculated trends
        all_trends = existing_trends + calculated_trends
        
        # Sort and ensure we only return data for the required dates in the correct order
        trend_map = {trend['date']: trend for trend in all_trends}
        final_trends = [trend_map[date] for date in required_dates if date in trend_map]
        
        return final_trends, None

    except requests.exceptions.RequestException as e:
        status_code = getattr(e.response, 'status_code', 503)
        app.logger.error(f"Failed to fetch or calculate market trends: {e}")
        return None, (f"Could not fetch market trends data", status_code)

# --- End of helper functions ---