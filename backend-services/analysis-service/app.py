# backend-services/analysis-service/app.py
import os
from flask import Flask, jsonify
import requests
import numpy as np

app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3003))

def detect_vcp(historical_data):
    """
    A simplified placeholder for VCP detection logic inspired by cookStock.py.
    A real implementation would be significantly more complex.
    """
    if not historical_data or not historical_data.get('c') or len(historical_data['c']) < 50:
        return {"detected": False, "message": "Not enough data for VCP analysis."}

    prices = historical_data['c']
    times = historical_data['t']

    # Mocking VCP detection for demonstration
    # This simulates finding a contraction in the last 20 days
    last_20_prices = prices[-20:]
    high_point = max(last_20_prices)
    low_point = min(last_20_prices)

    vcp_lines = [
        {"time": times[-20], "value": high_point},
        {"time": times[-1], "value": high_point},
        {"time": times[-20], "value": low_point},
        {"time": times[-1], "value": low_point},
    ]

    return {
        "detected": True,
        "message": "VCP analysis performed (mock data).",
        "vcpLines": vcp_lines,
        "buyPoints": [{"time": times[-2], "value": high_point * 1.01}], # Pivot breakout
        "sellPoints": [{"time": times[-2], "value": low_point * 0.99}] # Stop loss
    }

@app.route('/<ticker>')
async def analyze_ticker_endpoint(ticker):
    try:
        ticker = ticker.upper()
        # Fetch historical data from data-service
        hist_resp = requests.get(f"{DATA_SERVICE_URL}/data/historical-price/{ticker}")
        hist_resp.raise_for_status()
        historical_data = hist_resp.json()

        analysis_result = detect_vcp(historical_data)

        # Standardize the response payload
        return jsonify({
            "ticker": ticker,
            "analysis": analysis_result,
            "historicalData": historical_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
