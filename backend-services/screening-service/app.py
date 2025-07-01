# backend-services/screening-service/app.py
import os
from flask import Flask, jsonify
import requests

app = Flask(__name__)

DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")
PORT = int(os.getenv("PORT", 3002))

def apply_screening_criteria(ticker, fundamentals, historical_data):
    """
    Applies the 8 SEPA screening criteria.
    This is a simplified implementation based on available data.
    """
    if not fundamentals or not historical_data or not historical_data.get('c'):
        return {"passes": False, "reason": "Insufficient data for screening."}

    price_data = historical_data['c']
    current_price = price_data[-1] if price_data else 0
    
    # Simplified Criteria checks
    # 1 & 5: Price > 50, 150, 200 MA
    ma_50 = sum(price_data[-50:]) / 50 if len(price_data) > 50 else 0
    ma_150 = sum(price_data[-150:]) / 150 if len(price_data) > 150 else 0
    ma_200 = sum(price_data[-200:]) / 200 if len(price_data) > 200 else 0
    
    passes_ma = current_price > ma_150 and current_price > ma_200 and current_price > ma_50

    # 2: 150 MA > 200 MA
    passes_ma_order = ma_150 > ma_200 if ma_150 and ma_200 else False

    # 3: 200 MA trending up for at least 1 month
    ma_200_month_ago = sum(price_data[-230:-30]) / 200 if len(price_data) > 230 else 0
    passes_ma_trend = ma_200 > ma_200_month_ago if ma_200 and ma_200_month_ago else False
    
    # 6 & 7: Price position relative to 52-week high/low
    low_52_week = min(price_data)
    high_52_week = max(price_data)
    passes_price_position = (current_price > (low_52_week * 1.3)) and (current_price > (high_52_week * 0.75))

    # Combine all checks
    all_passes = all([passes_ma, passes_ma_order, passes_ma_trend, passes_price_position])

    return {
        "passes": all_passes,
        "reason": "Meets all quantitative criteria." if all_passes else "Failed one or more criteria."
    }

@app.route('/<ticker>')
async def screen_ticker_endpoint(ticker):
    try:
        ticker = ticker.upper()
        # Fetch required data from data-service
        fund_resp = requests.get(f"{DATA_SERVICE_URL}/data/fundamentals/{ticker}")
        hist_resp = requests.get(f"{DATA_SERVICE_URL}/data/historical-price/{ticker}")
        
        fund_resp.raise_for_status()
        hist_resp.raise_for_status()
        
        fundamentals = fund_resp.json()
        historical_data = hist_resp.json()
        
        result = apply_screening_criteria(ticker, fundamentals, historical_data)
        
        return jsonify({"ticker": ticker, **result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
