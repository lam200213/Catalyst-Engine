# backend-services/ticker-service/stub-ticker-service.py

# This is a stub ticker service that returns a small, predictable list for fast testing
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/tickers')
def get_tickers_endpoint():
    # Return a small, predictable list for fast testing
    return jsonify(['AAPL', 'MSFT', 'TSLA', 'NVDA', 'GOOG'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)