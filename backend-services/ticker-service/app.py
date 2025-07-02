from flask import Flask, jsonify
import pandas as pd
import requests

app = Flask(__name__)

def get_all_us_tickers():
    """
    Fetches all stock tickers from NYSE, NASDAQ, and AMEX from the NASDAQ API.
    This is a simplified, project-specific implementation with error handling.
    """
    exchanges = ['nyse', 'nasdaq', 'amex']
    all_tickers = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for exchange in exchanges:
        try:
            url = f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&exchange={exchange}&download=true"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            df = pd.DataFrame(response.json()['data']['rows'])
            
            if 'symbol' in df.columns:
                valid_tickers = df[~df['symbol'].str.contains(r'\.|\^', na=False)]['symbol'].tolist()
                all_tickers.extend(valid_tickers)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching tickers for {exchange}: {e}")
            continue
        except (KeyError, TypeError) as e:
            print(f"Error parsing data for {exchange}: {e}")
            continue

    return sorted(list(set(all_tickers)))

@app.route('/')
def get_tickers_endpoint():
    """The API endpoint to provide the list of tickers."""
    try:
        ticker_list = get_all_us_tickers()
        if not ticker_list:
            return jsonify({"error": "Failed to retrieve any tickers."}), 500
        return jsonify(ticker_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)