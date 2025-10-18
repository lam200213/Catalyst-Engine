# backend-services/monitoring-service/app.py  

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
    log_file = os.path.join(log_directory, "data_service.log")

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
        logging.getLogger('providers.yfin.yahoo_client'),
        logging.getLogger('providers.yfin.price_provider'),
        logging.getLogger('providers.yfin.financials_provider'),
        logging.getLogger('providers.yfin.market_leaders'),
        logging.getLogger('helper_functions')
    ]
    
    for logger_instance in module_loggers:
        logger_instance.addHandler(file_handler)
        logger_instance.addHandler(console_handler)
        logger_instance.setLevel(logging.DEBUG)

    app.logger.info("Data service logging initialized.")
# --- End of Logging Setup ---
setup_logging(app)

# --- 3. Import Project-Specific Modules ---
from market_health_utils import get_market_health
from market_leaders import get_market_leaders as get_leaders_data

@app.route('/market/leaders', methods=['GET'])
def market_leaders():
    """
    Provides a list of leading stocks grouped by industry.
    """
    logging.info("Request received for /market/leaders")
    try:
        data = get_leaders_data()
        if not data:
            return jsonify({"message": "No market leader data available at the moment."}), 404

        # Contract: { leading_industries: string[], leading_stocks: [{ticker, percent_change_1m}] }
        return jsonify({"leading_industries": data}), 200
    except Exception as e:
        logging.error(f"Failed to get market leaders: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/market/health', methods=['GET'])
def get_market_health_endpoint():
    """
    Returns a market health snapshot:
    - market_stage
    - market_correction_depth (percent from 52w high on ^GSPC)
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
        app.logger.error(f"Error in /market/health: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route('/watchlist/<string:user_id>', methods=['GET'])
def get_watchlist(user_id):
    # Existing watchlist logic
    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)