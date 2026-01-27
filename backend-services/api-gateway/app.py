# backend-services/api-gateway/app.py
import os
import sys
import time
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS 
import requests

app = Flask(__name__)
PORT = int(os.getenv("PORT", 3000))

# Secure CORS Configuration
CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}})

# Service URLs
SERVICES = {
    "price": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "news": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "financials": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "industry": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "screen": os.getenv("SCREENING_SERVICE_URL", "http://screening-service:3002"),
    "analyze": os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:3003"),
    "tickers": os.getenv("TICKER_SERVICE_URL", "http://ticker-service:5001"),
    "cache": os.getenv("DATA_SERVICE_URL", "http://data-service:3001"),
    "jobs": os.getenv("SCHEDULER_SERVICE_URL", "http://scheduler-service:3004"),
    "leadership": os.getenv("LEADERSHIP_SERVICE_URL", "http://leadership-service:3005"),
    "monitor": os.getenv("MONITORING_SERVICE_URL", "http://monitoring-service:3006")
}

@app.route('/<service>/<path:path>', methods=['GET', 'POST', 'DELETE', 'PUT'])
@app.route('/<service>', methods=['GET', 'POST', 'DELETE', 'PUT'])
def gateway(service, path=""):
    """
    A gateway to forward requests. Supports JSON payloads and SSE streaming.
    """
    if service not in SERVICES:
        return jsonify({"error": "Service not found"}), 404

    # Security check
    if '..' in path:
        return jsonify({"error": "Malicious path detected"}), 400

    base_url = SERVICES[service]
    
    # Preserve full path for most services, special case for tickers
    if service == 'tickers':
        target_url = f"{SERVICES[service]}/tickers"
    else:
        target_url = f"{base_url.rstrip('/')}{request.path}"

    try:
        # --- 1. Identify Streaming Requests ---
        is_streaming_request = '/stream/' in request.path

        if request.method == 'POST':
            post_data = request.get_json() if request.is_json else None
            # Increase timeout for synchronous job triggering if needed, though they should be async
            timeout = 60 if service == 'jobs' else 45
            resp = requests.post(target_url, json=post_data, timeout=timeout)
        
        elif request.method == 'DELETE':
            resp = requests.delete(target_url, timeout=45)
            
        elif request.method == 'PUT':
            put_data = request.get_json() if request.is_json else None
            resp = requests.put(target_url, json=put_data, timeout=45)
            
        else:  # Default to GET
            query_params = dict(request.args)
            
            if service == 'monitor' and request.path.startswith('/monitor/market-health'):
                get_timeout = 60 
            else:
                get_timeout = 45  

            # --- 2. Forward Request (Conditional Streaming) ---
            req_kwargs = {'params': query_params, 'timeout': get_timeout}
            
            if is_streaming_request:
                req_kwargs['stream'] = True
                print(f"[Gateway] Forwarding STREAM request to {target_url} with timeout={get_timeout}", file=sys.stdout)

            start_time = time.time()
            resp = requests.get(target_url, **req_kwargs)
            
            if is_streaming_request:
                print(f"[Gateway] Connection established in {time.time() - start_time:.2f}s", file=sys.stdout)

        # --- 3. Handle Streaming Responses ---
        if is_streaming_request:
            # DEBUG: Log what we actually got from upstream
            c_type = resp.headers.get('Content-Type', '').lower()
            print(f"[Gateway] Stream Response: Status={resp.status_code}, Type={c_type}", file=sys.stdout)

            if resp.status_code == 200 and 'text/event-stream' in c_type:
                def generate():
                    # Iterate with a reasonable chunk size, not 1 byte, to reduce CPU overhead
                    # But small enough to allow immediate flushes of small events
                    for chunk in resp.iter_content(chunk_size=1024):
                        if chunk:
                            yield chunk

                headers = {
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                    'Connection': 'keep-alive'
                }
                return Response(stream_with_context(generate()), status=200, headers=headers)
            
            # GUARD RAIL: If we expected a stream but got something else (e.g. error HTML/JSON),
            # DO NOT fall through to json() buffering if it might be an infinite malformed stream.
            if resp.status_code != 200:
                 return Response(resp.content, status=resp.status_code, mimetype=c_type)

        # --- 4. Handle Standard JSON Responses ---
        try:
            json_data = resp.json()
        except requests.exceptions.JSONDecodeError:
            json_data = {"error": f"Non-JSON or empty response from {service}", "details": resp.text}
        
        return jsonify(json_data), resp.status_code

    except requests.exceptions.Timeout:
        print(f"Timeout connecting to {service} (Limit reached)", file=sys.stderr)
        return jsonify({"error": f"Timeout connecting to {service}"}), 504
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error to {service}: {e}", file=sys.stderr)
        return jsonify({"error": f"Service unavailable: {service}", "details": str(e)}), 503
    except requests.exceptions.RequestException as e:
        print(f"Error forwarding request to {service}: {e}", file=sys.stderr)
        return jsonify({"error": f"Error in {service} communication", "details": str(e)}), 502
    except Exception as e:
        print(f"An unexpected internal error occurred in the gateway: {e}", file=sys.stderr)
        return jsonify({"error": "An unexpected internal error occurred in the gateway", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)