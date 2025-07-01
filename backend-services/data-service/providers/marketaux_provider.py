# backend-services/data-service/providers/marketaux_provider.py
import os
import requests

# The base URL for the MarketAux API
MARKETAUX_API_URL = "https://api.marketaux.com/v1/news/all"

def get_news_for_ticker(ticker: str) -> list | None:
    """
    Fetches news articles for a specific ticker from the MarketAux API.

    Args:
        ticker: The stock symbol to fetch news for.

    Returns:
        A list of news article objects, or None if an error occurs.
    """
    api_key = os.getenv('MARKETAUX_API_KEY')
    if not api_key or api_key == 'YOUR_MARKETAUX_API_KEY':
        print("Error: MARKETAUX_API_KEY is not set or is invalid.")
        return None

    params = {
        'api_token': api_key,
        'symbols': ticker,
        'limit': 10,  # Limit to the 10 most recent articles
        'language': 'en'
    }

    try:
        response = requests.get(MARKETAUX_API_URL, params=params, timeout=10)
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()
        
        data = response.json()
        
        # The news articles are typically in the 'data' field
        return data.get('data', [])

    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from MarketAux for {ticker}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None