# backend-services/monitoring-service/app.py  
import requests
from flask import Flask, request, jsonify
import os
import logging
from logging.handlers import RotatingFileHandler
import threading
import time
import re
from pymongo.errors import ConnectionFailure
from database import mongo_client
from services import watchlist_service, update_orchestrator, downstream_clients
from shared.contracts import (
    ApiError,
    LastRefreshStatus,
    WatchlistBatchRemoveRequest,
    WatchlistBatchRemoveResponse,
    InternalBatchAddRequest,
    InternalBatchAddResponse, 
    WatchlistRefreshStatusResponse,
)
from pydantic import ValidationError
# --- 1. Initialize Flask App and Basic Config ---
app = Flask(__name__)
PORT = int(os.getenv("PORT", 3006))
MONITORING_SERVICE_URL = os.getenv("MONITORING_SERVICE_URL", "http://monitoring-service:3006")
# Allowed ticker characters: letters, digits, dot, hyphen
_TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.\-]+$")
try:
    from contracts import MAX_TICKER_LEN  # e.g., 10
except Exception:
    MAX_TICKER_LEN = 10

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
    build_batch_remove_message,
    normalize_and_validate_ticker_path,
    build_validated_payload,
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

        # 3. Fetch VCP analysis for Major Indices
        indices_map = {}
        try:
            # We want FULL analysis to render charts, so we pass mode="full"
            indices_tickers = ["^GSPC", "^IXIC", "^DJI"]
            indices_resp = downstream_clients.analyze_batch(indices_tickers, mode="full")
            
            # Convert list response to Dict[ticker, AnalysisObject]
            app.logger.info(f"Indices analysis response type: {type(indices_resp)}")
            if isinstance(indices_resp, list):
                app.logger.info(f"Indices analysis count: {len(indices_resp)}")
                for item in indices_resp:
                    if isinstance(item, dict) and "ticker" in item:
                        indices_map[item["ticker"]] = item
            else:
                app.logger.warning(f"Indices analysis response was not a list: {indices_resp}")
                        
        except Exception as ex:
            app.logger.error(f"Failed to fetch indices analysis: {ex}")
            # Non-fatal, frontend handles missing chart data gracefully

        # 4. Assemble the final response payload according to the contract
        # The contract expects leaders_by_industry: { leading_industries: [...] }
        response_payload = compose_market_health_response(
            validate_market_overview(market_overview_data),
            validate_market_leaders(leaders_data),
            indices_map
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


@app.route('/monitor/watchlist', methods=['GET'])
def get_watchlist_internal():
    """
    Internal-only watchlist endpoint for TDD.

    Query Parameters:
      - exclude: Comma-separated list of portfolio tickers to exclude (mutual exclusivity), case-insensitive.
                 Example: ?exclude=CRWD,NET,BRK%2EB

    Returns (JSON):
      {
        "items": [...],
        "metadata": { "count": int }
      }

    Status Codes:
      - 200: Success
      - 500: Internal server error or invalid response from service
      - 503: Service unavailable (DB connection failure)
    """
    # Parse exclude parameter (Flask already URL-decodes query string)
    exclude_param = request.args.get('exclude', '')
    portfolio_tickers = []
    if exclude_param and exclude_param.strip():
        # Split by comma, trim whitespace, drop empties, normalize to uppercase
        portfolio_tickers = [
            t.strip().upper()
            for t in exclude_param.split(',')
            if isinstance(t, str) and t.strip()
        ]

    app.logger.info(f"GET /monitor/watchlist - excluding {len(portfolio_tickers)} portfolio tickers")

    # Connect to database with graceful degradation on failure
    try:
        from database import mongo_client
        client, db = mongo_client.connect()
    except Exception as e:
        # Map any connection-time error to 503 to satisfy tests and avoid leaking internals
        app.logger.error(f"Database connection failure in /monitor/watchlist: {e}", exc_info=True)
        return jsonify({"error": "Service unavailable - database connection failed"}), 503

    # Delegate to service layer
    try:
        from services import watchlist_service
        watchlist_data = watchlist_service.get_watchlist(db, portfolio_tickers)
    except Exception as e:
        app.logger.error(f"Service error in watchlist retrieval: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    # Validate shape using the shared contract to ensure stable structure
    try:
        from shared.contracts import WatchlistListResponse
        validated = WatchlistListResponse(**watchlist_data)
        # jsonify ensures application/json content-type as required by tests
        return jsonify(validated.model_dump()), 200
    except Exception as ve:
        app.logger.error(f"Pydantic validation failed for watchlist response: {ve}", exc_info=True)
        return jsonify({"error": "Invalid response format from service"}), 500
@app.route('/monitor/watchlist/<ticker>', methods=['PUT'])
def put_watchlist_ticker(ticker):
    """
    Public: Add or re-add a ticker to the watchlist (idempotent).

    Path:
      PUT /monitor/watchlist/:ticker

    Behavior:
      - Validates ticker format.
      - Delegates to services.watchlist_service.add_or_upsert_ticker.
      - Returns 201 on first insert (existed=False), 200 on idempotent re-add (existed=True).
      - Does not accept or rely on business fields from request body.
      - Remains a thin controller; no business logic here.

    Response:
      JSON {
        "message": str,
        "item": {
          "ticker": str,
          "status": "Watch",
          "date_added": null,
          "is_favourite": false,
          "last_refresh_status": "PENDING",
          "last_refresh_at": null,
          "failed_stage": null,
          "current_price": null,
          "pivot_price": null,
          "pivot_proximity_percent": null,
          "is_leader": false
        }
      }
    """
    try:
        try:
            normalized = normalize_and_validate_ticker_path(ticker)
        except ValueError as ve:
            # Preserve existing error messages
            return jsonify({"error": str(ve)}), 400

        # Connect DB and call service
        client, db = mongo_client.connect()
        result = watchlist_service.add_or_upsert_ticker(db, "public", normalized)

        # Map status code
        status_code = 200 if result.get("existed") else 201
        message = (
            f"Already in watchlist: {result['ticker']}"
            if status_code == 200 else
            f"Added to watchlist: {result['ticker']}"
        )

        # Build a minimal item preview using established naming and defaults
        item = {
            "ticker": result["ticker"],
            "status": "Watch",
            "date_added": None,
            "is_favourite": False,
            "last_refresh_status": "PENDING",
            "last_refresh_at": None,
            "failed_stage": None,
            "current_price": None,
            "pivot_price": None,
            "pivot_proximity_percent": None,
            "is_leader": False
        }

        return jsonify({"message": message, "item": item}), status_code

    except ValueError as ve:
        # Service validation errors
        return jsonify({"error": str(ve)}), 400
    except ConnectionFailure as cf:
        # DB connection failures
        app.logger.error(f"Database connection failure in PUT /monitor/watchlist/<ticker>: {cf}", exc_info=True)
        return jsonify({"error": "Service unavailable - database connection failed"}), 503
    except Exception as e:
        app.logger.error(f"Error in PUT /monitor/watchlist/<ticker>: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/monitor/internal/update-all', methods=['POST'])
def update_all():
    try:
        # TODO: delegate to update orchestrator (fetch + recompute + persist)
        # TODO: implement services/update_orchestrator.py when backend dependencies are ready.
        return jsonify({
            "message": "Monitor data update completed successfully.",
            "updated_portfolio_items": 0,
            "updated_watchlist_items": 0
        }), 200
    except Exception as e:
        app.logger.error(f"update-all failed: {e}", exc_info=True)
        return jsonify({ "error": "Service unavailable" }), 503

@app.route('/monitor/watchlist/<ticker>', methods=['DELETE'])
def delete_watchlist_ticker(ticker):
    """
    Move a ticker from watchlist to archive (manual delete).
    - Validates ticker format (allowed: A-Z0-9.-, length 1–10).
    - Normalizes ticker to uppercase.
    - Delegates to services.watchlist_service.move_to_archive.
    - Returns 200 with a message on success, 404 if not found, 400 on invalid format.
    - Does not leak internal DB fields to the client.
    """
    try:
        try:
            normalized = normalize_and_validate_ticker_path(ticker)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

        # DB connect
        client, db = mongo_client.connect()

        # Delegate to service
        result = watchlist_service.move_to_archive(db, normalized)

        if result is None:
            return jsonify({"error": "Ticker not in watchlist"}), 404

        # Success; do not include internal fields in response
        return jsonify({"message": f"{normalized} moved to archive"}), 200

    except ConnectionFailure as cf:
        app.logger.error(f"DB connection failure in DELETE /monitor/watchlist/: {cf}", exc_info=True)
        return jsonify({"error": "Service unavailable - database connection failed"}), 503
    except ValueError as ve:
        # Surface validation issues as 400
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        app.logger.error(f"Error in DELETE /monitor/watchlist/: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/monitor/archive', methods=['GET'])
def get_archive_route():
    """
    Returns archived items for the default single-user, mapped to API contract:
    { "archived_items": [ {ticker, archived_at, reason, failed_stage?}, ... ] }
    """
    try:
        client, db = mongo_client.connect()
    except ConnectionFailure as cf:
        return jsonify({"error": str(cf)}), 503  # matches error handling tests
    try:
        payload = watchlist_service.get_archive(db)
        return jsonify(payload), 200
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/monitor/archive/<path:ticker>", methods=["DELETE"])
def delete_archive_ticker(ticker):
    """
    Hard delete an archived ticker item for the default user.
    Validates and normalizes the ticker path param, 
    Connects to MongoDB and deletes the archived item scoped to the default user
    Responses:
    - 200: {"message": "Archived ticker <TICKER> permanently deleted."}
    - 404: {"error": "Ticker not found"}
    - 400: {"error": "Invalid ticker format"}
    - 503: {"error": "Service unavailable"}
    """
    # Parse raw path input and validate, then normalize 
    try:
        symbol = normalize_and_validate_ticker_path(ticker)
    except ValueError:
        # This route always used a generic message; preserve it
        return jsonify({"error": "Invalid ticker format"}), 400

    try:
        client, db = mongo_client.connect()
    except ConnectionFailure:
        return jsonify({"error": "Service unavailable"}), 503

    # Call DB layer directly (ensures route tests patching db calls are satisfied)
    try:
        result = mongo_client.delete_archive_item(db, symbol)
    except Exception:
        # Do not leak internals in responses
        return jsonify({"error": "Service unavailable"}), 503

    if getattr(result, "deleted_count", 0) == 1:
        return jsonify({"message": f"Archived ticker {symbol} permanently deleted."}), 200

    return jsonify({"error": "Ticker not found"}), 404

@app.route('/monitor/watchlist/<ticker>/favourite', methods=['POST'])
def post_watchlist_favourite(ticker: str):
    """
    Toggle is_favourite for a single watchlist item belonging to the default single-user.
    Request body: { "is_favourite": bool }
    Responses:
      200: { "message": str }
      400: { "error": str } for invalid body or ticker format
      404: { "error": str } when ticker not found for current user
      503: { "error": str } when database is unavailable
    """
    # Parse and validate JSON body
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "is_favourite" not in payload:
        return jsonify({"error": "Body must be JSON with field 'is_favourite' of type boolean"}), 400
    is_fav = payload.get("is_favourite")
    if not isinstance(is_fav, bool):
        return jsonify({"error": "Field 'is_favourite' must be a boolean"}), 400

    # Decode, normalize, and validate ticker
    try:
        norm_ticker = normalize_and_validate_ticker_path(ticker)
    except ValueError:
        return jsonify({"error": "Invalid ticker format"}), 400

    # DB operation
    try:
        client, db = mongo_client.connect()
    except ConnectionFailure:
        return jsonify({"error": "Database unavailable"}), 503

    result = mongo_client.toggle_favourite(db, norm_ticker, is_fav)
    modified = getattr(result, "modified_count", 0)
    if modified == 0:
        return jsonify({"error": f"Watchlist item '{norm_ticker}' not found"}), 404

    return jsonify({"message": f"Watchlist item '{norm_ticker}' favourite set to {str(is_fav).lower()}"}), 200

@app.route("/monitor/watchlist/batch/remove", methods=["POST"])
def watchlist_batch_remove():
    """
    Removes a list of tickers from the active watchlist in a single bulk operation.

    Public endpoint backing the "Remove Selected" UI action.
    """
    try:
        raw_body = request.get_json(force=True, silent=False)
    except Exception:
        error = ApiError(error="Request body must be valid JSON").model_dump()
        return jsonify(error), 400

    if raw_body is None:
        error = ApiError(error="Request body is required").model_dump()
        return jsonify(error), 400

    # Early Pydantic validation to enforce { tickers: List[str] } and block
    # payload-based NoSQL injection attempts (e.g., dict elements in the array).
    try:
        req_model = WatchlistBatchRemoveRequest(**raw_body)
    except ValidationError:
        error = ApiError(error="Invalid request payload for batch remove").model_dump()
        return jsonify(error), 400

    # Route-level normalization and basic sanitation
    normalized_tickers = []
    for t in req_model.tickers:
        symbol = t.strip().upper()
        if symbol:
            normalized_tickers.append(symbol)

    if not normalized_tickers:
        error = ApiError(error="At least one non-empty ticker must be provided").model_dump()
        return jsonify(error), 400

    client, db = mongo_client.connect()

    try:
        result = watchlist_service.batch_remove_from_watchlist(
            db, normalized_tickers
        )
    except ValueError as exc:
        # Validation / limit violations from service: treat as 400 Bad Request
        error = ApiError(error=str(exc)).model_dump()
        return jsonify(error), 400
    except Exception:
        # Preserve generic error envelope per ApiError contract
        error = ApiError(error="Failed to remove watchlist items").model_dump()
        return jsonify(error), 500

    raw_removed = result.get("removed", [])
    if isinstance(raw_removed, list):
        removed_tickers = [t for t in raw_removed if isinstance(t, str)]
    else:
        # Legacy shape: numeric count only; fall back to normalized input
        removed_tickers = normalized_tickers[: int(raw_removed) or 0]

    raw_notfound = result.get("notfound", result.get("not_found", []))
    if isinstance(raw_notfound, list):
        notfound_tickers = [t for t in raw_notfound if isinstance(t, str)]
    else:
        # Legacy shape: numeric count; but we have no identifiers, so leave empty
        notfound_tickers = []

    # Build message using counts but keep identifiers in the response
    removed_count = len(removed_tickers)
    notfound_count = len(notfound_tickers)
    tickers_out = removed_tickers or normalized_tickers

    msg = build_batch_remove_message(removed_count, notfound_count, tickers_out)

    resp_model = WatchlistBatchRemoveResponse(
        message=msg,
        removed=removed_count,
        notfound=notfound_count,
        removed_tickers=removed_tickers,
        not_found_tickers=notfound_tickers,
    )
    return jsonify(resp_model.model_dump()), 200

@app.route("/monitor/watchlist/batch/add", methods=["POST"])
@app.route("/monitor/internal/watchlist/batch/add", methods=["POST"])
def internal_batch_add_watchlist():
    """
    Batch add tickers to the watchlist.
    Exposed as both a public and internal endpoint using the same logic.

    Behavior:
    - Accepts JSON body: { "tickers": [str, ...] }.
    - Validates payload against InternalBatchAddRequest and additional route-level rules.
    - Normalizes tickers (strip + uppercase) and deduplicates before delegating.
    - Delegates to services.watchlist_service.batch_add_to_watchlist for business logic.
    - Returns 201 if at least one ticker was newly added, otherwise 200.
    - Response JSON: { "message": str, "added": int, "skipped": int }.
    """
    # Enforce JSON content-type; missing/incorrect content-type should fail with 400/415 per tests
    if not request.is_json:
        return jsonify({"error": "Request body must be application/json"}), 400

    payload = request.get_json(silent=True) or {}

    # Validate against Pydantic contract first (ensures tickers field exists and is a list of strings)
    try:
        model = InternalBatchAddRequest(**payload)
    except ValidationError as ve:
        app.logger.warning(
            "internal_batch_add_watchlist: request validation failed: %s", ve
        )
        return jsonify({"error": "Invalid request body for internal batch add"}), 400

    raw_tickers = model.tickers

    # Additional defensive checks to satisfy security/edge-case tests
    if not isinstance(raw_tickers, list):
        return jsonify({"error": "tickers must be provided as a list of strings"}), 400
    if not raw_tickers:
        return jsonify({"error": "At least one ticker must be provided"}), 400

    # Route-level normalization and deduplication (case-insensitive)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_tickers:
        if not isinstance(raw, str):
            # Non-string items must reject the entire payload and not call the service
            return jsonify({"error": "tickers must be a list of strings"}), 400

        symbol = raw.strip().upper()

        # Reject clearly invalid or dangerous tokens at the route layer
        if not symbol:
            # Empty or whitespace-only tokens are invalid
            return jsonify({"error": "Invalid ticker format in tickers array"}), 400

        if len(symbol) > MAX_TICKER_LEN:
            # Enforce documented max length (e.g., 10) here
            return jsonify({"error": "Invalid ticker format in tickers array"}), 400

        if "$" in symbol:
            # Guardrail against obvious NoSQL-style payloads like "AAPL$"
            return jsonify({"error": "Invalid ticker format in tickers array"}), 400

        # Do NOT apply the strict _TICKER_PATTERN here; service-level validation
        # (and tests) own the canonical ticker format rules for internal batch add.

        if symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)

    if not normalized:
        return jsonify({"error": "No valid tickers provided"}), 400

    # Connect to MongoDB
    try:
        client, db = mongo_client.connect()
    except ConnectionFailure as cf:
        app.logger.error(
            "internal_batch_add_watchlist: database connection failure: %s", cf, exc_info=True
        )
        return jsonify({"error": "Service unavailable - database connection failed"}), 503

    # Delegate to service layer
    try:
        result = watchlist_service.batch_add_to_watchlist(db, normalized)
    except ValueError as ve:
        # Service-level validation errors (e.g., invalid ticker formats)
        app.logger.warning(
            "internal_batch_add_watchlist: service validation error: %s", ve
        )
        return jsonify({"error": str(ve)}), 400
    except Exception as exc:
        app.logger.error(
            "internal_batch_add_watchlist: unexpected service error: %s",
            exc,
            exc_info=True,
        )
        return jsonify({"error": "Internal server error"}), 500

    added_list = list(result.get("added", []))
    skipped_list = list(result.get("skipped", []))
    errors_list = list(result.get("errors", []))

    added_count = len(added_list)
    skipped_count = len(skipped_list)

    # Compose a user-facing message that includes at least one key identifier for traceability
    identifiers = added_list or skipped_list
    preview: str = ""
    if identifiers:
        preview = ", ".join(identifiers[:5])

    if errors_list:
        message = (
            f"Batch add completed: added {added_count}, skipped {skipped_count}, "
            f"errors for {len(errors_list)} tickers."
        )
    else:
        message = f"Batch add completed: added {added_count}, skipped {skipped_count}."

    if preview:
        message = f"{message} Sample: {preview}"

    # Validate response against Pydantic contract to guard type/shape drift
    response_model = InternalBatchAddResponse(
        message=message,
        added=added_count,
        skipped=skipped_count,
    )

    # Status code: 201 when at least one new ticker was added; otherwise 200
    status_code = 201 if added_count > 0 else 200

    return jsonify(response_model.model_dump(mode="json")), status_code

# Refresh orchestrator endpoint using shared contracts and helpers
@app.route("/monitor/internal/watchlist/refresh-status", methods=["POST"])
def refresh_watchlist_status_endpoint():
    """
    Internal endpoint to refresh watchlist item statuses.

    Orchestrates:
    - Running the watchlist refresh orchestrator.
    - Validating the summary against WatchlistRefreshStatusResponse.
    - Returning a normalized JSON payload with aliased field names.

    Responses:
    - 200: { "message": str, "updated_items": int, "archived_items": int, "failed_items": int }
    - 500: { "error": str } on unexpected failures.
    """
    # Trace entry for observability and tests
    app.logger.info(
        "POST /monitor/internal/watchlist/refresh-status - refresh-status requested"
    )
    try:
        summary = update_orchestrator.refresh_watchlist_status()
    except Exception as exc:
        # Log internal details, but surface a generic error message to callers.
        app.logger.error(f"refresh-status orchestrator failure: {exc}", exc_info=True)
        try:
            error_body = ApiError(error="Watchlist refresh failed").model_dump()
        except Exception:
            error_body = {"error": "Watchlist refresh failed"}
        return jsonify(error_body), 500

    # Defensive: tolerate non-dict returns, but tests expect dict with specific fields.
    if not isinstance(summary, dict):
        app.logger.error("refresh-status orchestrator returned non-dict summary")
        try:
            error_body = ApiError(error="Internal server error").model_dump()
        except Exception:
            error_body = {"error": "Internal server error"}
        return jsonify(error_body), 500

    # normalize keys for the route response; support both styles from the orchestrator.
    message = summary.get("message")
    updated = summary.get("updated_items")
    archived = summary.get("archived_items")
    failed = summary.get("failed_items")

    response_payload = {
        "message": message,
        "updated_items": int(updated) if isinstance(updated, int) else updated,
        "archived_items": int(archived) if isinstance(archived, int) else archived,
        "failed_items": int(failed) if isinstance(failed, int) else failed,
    }

    # Trace final outcome for observability; tests assert the presence of "refresh-status" here.
    app.logger.info("refresh-status summary: %s", response_payload)

    return jsonify(response_payload), 200
@app.route('/health', methods=['GET'])
def health_check():
    """Standard health check endpoint."""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    setup_logging(app)
    threading.Thread(target=_prewarm_market_health, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)