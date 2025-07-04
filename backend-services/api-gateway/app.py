# backend-services/api-gateway/app.py
import os
from flask import Flask, request, jsonify
from flask_cors import CORS 
import requests

app = Flask(__name__)

# Secure CORS Configuration: Only allow requests from the frontend's origin
# This replaces the overly permissive CORS(app)
CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}})

# Service URLs are now managed via environment variables
# These point to the internal Docker service names
SERVICES = {
    "data": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "news": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "screen": os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002"),
    "analyze": os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003"),
    "tickers": os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5000"),
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
    # The target service already knows its endpoint structure (e.g., /data/, /news/, /screen/)
    target_url = f"{SERVICES[service]}/{service}/{path}"
    
    # Special cases for services that have a root endpoint or handle their own path prefix
    if service == 'tickers': # Only tickers has a root endpoint
        target_url = f"{SERVICES[service]}/{path}"
    
    try:
        # Forward the request
        resp = requests.get(target_url, params=request.args, timeout=20)
        # Return the response from the target service, regardless of status code
        # The client can then handle different status codes (e.g., 404, 500)
        return jsonify(resp.json()), resp.status_code

    except requests.exceptions.Timeout:
        print(f"Timeout connecting to {service}")
        return jsonify({"error": f"Timeout connecting to {service}"}), 504 # Gateway Timeout
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error to {service}: {e}")
        return jsonify({"error": f"Service unavailable: {service}", "details": str(e)}), 503 # Service Unavailable
    except requests.exceptions.RequestException as e:
        # Catch any other request-related errors
        print(f"Error forwarding request to {service}: {e}")
        return jsonify({"error": f"Error in {service} communication", "details": str(e)}), 502 # Bad Gateway
    except Exception as e:
        # Catch any other unexpected errors in the gateway itself
        print(f"An unexpected internal error occurred in the gateway: {e}")
        return jsonify({"error": "An internal error occurred in the gateway", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)