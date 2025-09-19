# backend-services/data-service/providers/yfin/yahoo_client.py
from curl_cffi import requests as cffi_requests
import threading
import logging
import random
from functools import wraps
import time
from curl_cffi import requests as cffi_requests
from curl_cffi.requests import errors as cffi_errors

session = cffi_requests.Session()
_YAHOO_CRUMB = None
_AUTH_LOCK = threading.Lock()

# Get a child logger
logger = logging.getLogger(__name__)

# A list of user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
]

# Proxies are now loaded from an environment variable for better configuration management.
import os # Add os import for environment variable access
PROXIES = [p.strip() for p in os.getenv("YAHOO_FINANCE_PROXIES", "").split(',') if p.strip()]

def _get_random_user_agent() -> str:
    """Returns a random user-agent from the list."""
    return random.choice(USER_AGENTS)

def _get_random_proxy() -> dict | None:
    """Returns a random proxy if available."""
    if not PROXIES:
        return None
    proxy_url = random.choice(PROXIES)
    return {"http": proxy_url, "https": proxy_url}

def _get_yahoo_auth():
    """
    Performs an initial request to Yahoo Finance to get the necessary
    cookies and the API 'crumb' for authenticated requests.
    This is thread-safe to prevent multiple requests in a concurrent environment.
    """
    global _YAHOO_CRUMB
    # Use a lock to ensure only one thread tries to get the crumb at a time
    with _AUTH_LOCK:
        # If another thread already got the crumb while this one was waiting, just return it
        if _YAHOO_CRUMB:
            return _YAHOO_CRUMB

        logger.debug("No auth crumb found. Fetching new one...")
        try:
            # The 'getcrumb' endpoint is a reliable way to get a valid crumb
            crumb_url = "https://query1.finance.yahoo.com/v1/test/getcrumb"
            headers = {'User-Agent': _get_random_user_agent()}
            proxy = _get_random_proxy()

            # The session object will automatically store the required cookies
            crumb_response = session.get(
                crumb_url,
                headers=headers,
                proxies=proxy,
                impersonate="chrome110",
                timeout=10
            )
            crumb_response.raise_for_status()
            _YAHOO_CRUMB = crumb_response.text
            logger.debug(f"Successfully fetched new crumb: {_YAHOO_CRUMB}")
            return _YAHOO_CRUMB
        except cffi_requests.errors.RequestsError as e:
            logger.critical(f"Failed to get Yahoo auth crumb: {e}")
            return None

def retry_on_failure(attempts=3, delay=2, backoff=2):
    """Decorator for robust HTTP requests with retries and backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = attempts, delay
            while mtries > 1:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Only retry on specific, retry-able errors
                    error_str = str(e).lower()
                    if "rate limited" in error_str or "could not resolve host" in error_str:
                        ticker = args[0] if args and isinstance(args[0], str) else 'N/A'
                        msg = f"Retrying {func.__name__} for {ticker} after error: {e}. Retries left: {mtries-1}"
                        logger.warning(msg)
                        # Add jitter (a small random delay) to prevent thundering herd problem
                        time.sleep(mdelay + random.uniform(0, 1))
                        mtries -= 1
                        mdelay *= backoff
                    else:
                        # Re-raise exceptions that are not transient (e.g., programming errors)
                        raise
            # Perform the final attempt outside the loop
            return func(*args, **kwargs)
        return wrapper
    return decorator

@retry_on_failure()
def execute_request(url, params=None):
    """
    Executes a request using the shared session, automatically handling
    authentication, headers, and proxies.
    """
    crumb = _get_yahoo_auth()
    if not crumb:
        raise cffi_errors.RequestsError("Could not execute request due to missing Yahoo crumb.")

    request_params = params.copy() if params else {}
    request_params['crumb'] = crumb
    
    headers = {
        "User-Agent": _get_random_user_agent()
    }
    
    response = session.get(url, params=request_params, headers=headers)
    response.raise_for_status() # Will raise an exception for 4xx/5xx status codes
    return response.json()