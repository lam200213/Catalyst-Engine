# backend-services/monitoring-service/app.py  
import requests
from flask import Flask, request, jsonify
import os
import logging
from logging.handlers import RotatingFileHandler


# --- 1. Initialize Flask App and Basic Config ---
app = Flask(__name__)
PORT = int(os.getenv("PORT", 3006))

# --- 2. Define Logging Setup Function ---
def setup_logging(app):
    """Configures comprehensive logging for the Flask app."""
    log_directory = "/app/logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # The filename is now specific to the service and in a dedicated folder.
    log_file = os.path.join(log_directory, "monitoring_service.log")

    # Create a rotating file handler to prevent log files from growing too large.
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)

    # Create a console handler for stdout
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Define the log format
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(log_formatter)
    console_handler.setFormatter(log_formatter)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False

    # Find and configure the loggers from the provider and helper modules
    # This ensures that log messages from background threads are captured correctly.
    module_loggers = [
        logging.getLogger('market_health_utils'),
        logging.getLogger('market_leaders'),
        logging.getLogger('helper_functions')
    ]
    
    for logger_instance in module_loggers:
        logger_instance.addHandler(file_handler)
        logger_instance.addHandler(console_handler)
        logger_instance.setLevel(logging.DEBUG)

    app.logger.info("Monitoring service logging initialized.")
# --- End of Logging Setup ---
setup_logging(app)

# --- 3. Import Project-Specific Modules ---
from market_health_utils import get_market_health
from market_leaders import get_market_leaders

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
        response_payload = {
            "market_overview": market_overview_data,
            "leaders_by_industry": {
                "leading_industries": leaders_data
            }
        }

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
        data = get_market_leaders()
        if not data:
            return jsonify({"message": "No market leader data available at the moment."}), 404

        # Contract: { leading_industries: string[], leading_stocks: [{ticker, percent_change_1m}] }
        return jsonify({"leading_industries": data}), 200
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
    Optional query: ?tickers=AAPL,MSFT,... for breadth universe.
    """
    try:
        tickers_param = request.args.get('tickers')
        universe = None
        if tickers_param:
            universe = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
        payload = get_market_health(universe=universe)
        return jsonify(payload), 200
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
    app.run(host='0.0.0.0', port=PORT)