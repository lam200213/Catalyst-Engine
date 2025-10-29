# backend-services/monitoring-service/app.py  
import requests
from flask import Flask, request, jsonify
import os
import logging
from logging.handlers import RotatingFileHandler
import threading
import time

# --- 1. Initialize Flask App and Basic Config ---
app = Flask(__name__)
PORT = int(os.getenv("PORT", 3006))
MONITORING_SERVICE_URL = os.getenv("MONITORING_SERVICE_URL", "http://monitoring-service:3006")

# --- 2. Define Logging Setup Function ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handlers (console + rotating file), built once
    handlers = []

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    log_directory = "/app/logs"
    os.makedirs(log_directory, exist_ok=True)
    log_file = os.path.join(log_directory, "monitoring_service.log")

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    app.logger.setLevel(log_level)
    app.logger.propagate = False
    
    # Clear existing handlers to avoid duplication
    for h in list(app.logger.handlers):
        app.logger.removeHandler(h)

    # Attach the handlers to app.logger
    for h in handlers:
        app.logger.addHandler(h)

    # prevent werkzeug from duplicating to root/stdout
    werk = logging.getLogger("werkzeug")
    werk.propagate = False
    for h in list(werk.handlers):
        if isinstance(h, logging.StreamHandler):
            werk.removeHandler(h)

    # Module loggers that should emit through the same handlers
    module_names = [
        "market_health_utils",
        "market_leaders",
        "helper_functions",
    ]
    for name in module_names:
        module_loggers = logging.getLogger(name)
        module_loggers.setLevel(log_level)
        module_loggers.propagate = False
        # Clear existing handlers
        for h in list(module_loggers.handlers):
            module_loggers.removeHandler(h)
        # Attach shared handlers
        for h in handlers:
            module_loggers.addHandler(h)

    app.logger.info("Monitoring service logging initialized.")
# --- End of Logging Setup ---
setup_logging(app)

# --- 3. Import Project-Specific Modules ---
from market_health_utils import get_market_health
from market_leaders import get_market_leaders
from helper_functions import (
    validate_market_overview,
    validate_market_leaders,
    compose_market_health_response,
)

# Prewarm market health on startup to avoid first-user 504
def _prewarm_market_health():
    try:
        delay = int(os.getenv("MONITOR_PREWARM_DELAY_SEC", "3"))
        timeout = int(os.getenv("MONITOR_PREWARM_TIMEOUT_SEC", "55"))
        time.sleep(delay)
        # Call the service locally to build caches
        url = f"{MONITORING_SERVICE_URL}/monitor/market-health"
        requests.get(url, timeout=timeout)
        app.logger.info("Prewarm for /monitor/market-health completed.")
    except Exception as e:
        app.logger.warning(f"Prewarm failed: {e}")

@app.route('/monitor/market-health', methods=['GET'])
def get_aggregated_market_health():
    """
    Orchestrates calls to internal logic functions to build the complete
    payload for the frontend's market health page.
    """
    app.logger.info("Request received for aggregated /monitor/market-health")
    try:
        # 1. Get market overview data
        market_overview_data = get_market_health()

        # 2. Get market leaders data
        leaders_data = get_market_leaders() # This returns a list of industries

        # 3. Assemble the final response payload according to the contract
        # The contract expects leaders_by_industry: { leading_industries: [...] }
        response_payload = compose_market_health_response(
            validate_market_overview(market_overview_data),
            validate_market_leaders(leaders_data),
        )

        return jsonify(response_payload), 200

    except requests.exceptions.RequestException as re:
        app.logger.error(f"Failed to connect to a downstream service: {re}", exc_info=True)
        return jsonify({"error": "Failed to fetch data from a dependency service."}), 503
    except Exception as e:
        app.logger.error(f"An unexpected error occurred in /monitor/market-health: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred"}), 500

@app.route('/monitor/internal/leaders', methods=['GET'])
def market_leaders():
    """
    Provides a list of leading stocks grouped by industry.
    """
    app.logger.info("Request received for /monitor/internal/leaders")
    try:
        leaders = get_market_leaders()  # returns {"leading_industries": [...]}
        return jsonify(validate_market_leaders(leaders)), 200
    except Exception as e:
        app.logger.error(f"Failed to get market leaders: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/monitor/internal/health', methods=['GET'])
def get_market_health_endpoint():
    """
    Returns a market health snapshot:
    - market_stage
    - correction_depth_percent (percent from 52w high on ^GSPC)
    - high_low_ratio
    - new_highs, new_lows (explicit counts)
    """
    try:
        overview = get_market_health()  # returns dict with expected keys
        return jsonify(validate_market_overview(overview)), 200
    except Exception as e:
        app.logger.error(f"Error in /monitor/internal/health: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/watchlist/<string:user_id>', methods=['GET'])
def get_watchlist(user_id):
    # Existing watchlist logic
    pass

@app.route('/health', methods=['GET'])
def health_check():
    """Standard health check endpoint."""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    setup_logging(app)
    threading.Thread(target=_prewarm_market_health, daemon=True).start()  # Latest Add
    app.run(host="0.0.0.0", port=PORT)