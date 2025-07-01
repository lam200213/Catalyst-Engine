# backend-services/api-gateway/app.py
import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Service URLs are now managed via environment variables
# These point to the internal Docker service names
SERVICES = {
    "screen": os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002"),
    "analyze": os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003"),
    "tickers": os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5000")
}

@app.route('/<service>/<path:path>', methods=['GET'])
@app.route('/<service>', methods=['GET'])
def gateway(service, path=""):
    """
    A simple gateway to forward requests to the appropriate backend service.
    """
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    # Construct the full URL for the target service
    target_url = f"{SERVICES[service]}/{path}"
    
    try:
        # Forward the request
        resp = requests.get(target_url, params=request.args, timeout=20)
        resp.raise_for_status() # Raise an exception for bad status codes
        
        # Return the response from the target service
        return jsonify(resp.json()), resp.status_code

    except requests.exceptions.RequestException as e:
        print(f"Error forwarding request to {service}: {e}")
        return jsonify({"error": f"Error connecting to {service}", "details": str(e)}), 502 # Bad Gateway
    except Exception as e:
        return jsonify({"error": "An internal error occurred in the gateway", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
