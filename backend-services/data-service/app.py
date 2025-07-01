# data-service/app.py
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Import provider modules, including the new marketaux_provider
from providers import yfinance_provider, finnhub_provider, marketaux_provider

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

@app.route('/data/<string:ticker>', methods=['GET'])
def get_data(ticker: str):
    """
    Main data endpoint for historical price data.
    Fetches stock data from a specified source (finnhub or yfinance).
    Defaults to 'finnhub' if no source is provided.
    
    Query Params:
        source (str): 'finnhub' or 'yfinance'.
    """
    # Get the data source from the query parameter, defaulting to finnhub
    source = request.args.get('source', 'finnhub').lower()

    data = None
    if source == 'yfinance':
        data = yfinance_provider.get_stock_data(ticker)
    elif source == 'finnhub':
        data = finnhub_provider.get_stock_data(ticker)
    else:
        return jsonify({"error": "Invalid data source specified. Use 'finnhub' or 'yfinance'."}), 400

    if data is not None:
        return jsonify(data)
    else:
        return jsonify({"error": f"Could not retrieve price data for {ticker} from {source}."}), 404

@app.route('/news/<string:ticker>', methods=['GET'])
def get_news(ticker: str):
    """
    News data endpoint.
    Fetches news articles for a given ticker from MarketAux.
    """
    try:
        news_data = marketaux_provider.get_news_for_ticker(ticker)
        
        if news_data is not None:
            return jsonify(news_data)
        else:
            return jsonify({"error": f"Could not retrieve news for {ticker}."}), 404

    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500


if __name__ == '__main__':
    # Get port from environment or default to 3001
    port = int(os.environ.get('PORT', 3001))
    app.run(host='0.0.0.0', port=port)