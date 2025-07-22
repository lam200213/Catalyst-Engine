# backend-services/api-gateway/app.py
import os
from flask import Flask, request, jsonify
from flask_cors import CORS 
import requests

app = Flask(__name__)
PORT = int(os.getenv("PORT", 3000))

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
    "tickers": os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001"),
    "cache": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "jobs": os.getenv("SCHEDULER_SERVICE_URL", "http://scheduler-service:3004"),
}

@app.route('/<service>/<path:path>', methods=['GET', 'POST'])
@app.route('/<service>', methods=['GET', 'POST'])
def gateway(service, path=""):
    """
    A simple gateway to forward requests to the appropriate backend service.
    """
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    # Security check to prevent path traversal
    if '..' in path:
        return jsonify({"error": "Malicious path detected"}), 400

    # Construct the full URL for the target service
    # The target service already knows its endpoint structure (e.g., /data/, /news/, /screen/)
    # Handle the specific path for the jobs service, as it doesn't follow the /service/path pattern.
    if service == 'jobs':
        target_url = f"{SERVICES[service]}/{service}/{path}"
    elif service == 'cache' and path == 'clear':
        target_url = f"{SERVICES[service]}/cache/clear"
    elif service == 'tickers':
        # Route to the /tickers endpoint
        target_url = f"{SERVICES[service]}/tickers"
    else:
        target_url = f"{SERVICES[service]}/{service}/{path}"

    try:
        # Conditional logic to handle POST vs. GET requests
        if request.method == 'POST':
            # Only attempt to forward a JSON body if one is present in the request.
            post_data = request.get_json() if request.is_json else None
            # Set a much longer timeout specifically for the 'jobs' service
            timeout = 6000 if service == 'jobs' else 20
            resp = requests.post(target_url, json=post_data, timeout=timeout)
        else:  # Default to GET
            # Convert Flask's ImmutableMultiDict to a standard dict for consistent mocking and forwarding.
            query_params = dict(request.args)
            resp = requests.get(target_url, params=query_params, timeout=20)

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
    app.run(host='0.0.0.0', port=PORT)