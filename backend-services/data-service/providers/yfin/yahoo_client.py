# backend-services/data-service/providers/yfin/yahoo_client.py
from curl_cffi import requests as cffi_requests
import logging
from functools import wraps
from curl_cffi import requests as cffi_requests
from curl_cffi.requests import errors as cffi_errors
import os, time, json, random, threading
from typing import Optional, Dict, Any, List, Tuple

# Get a child logger
logger = logging.getLogger(__name__)

# Constants
_POOL_SIZE = int(os.getenv("YF_POOL_SIZE", "12"))
_TIMEOUT = int(os.getenv("YF_REQUEST_TIMEOUT", "12"))
_CRUMB_TTL_SECONDS = int(os.getenv("YF_CRUMB_TTL_SECONDS", "600"))

# simple health tracking and weighted pick
_ID_HEALTH = {}  # identity_id -> {'fail': int, 'cooldown_until': ts}

# A list of user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/92.0.902.67 Safari/537.36",
]

SUPPORTED_IMPERSONATE_PROFILES = [
    "chrome110", "chrome116", "chrome120",
    "firefox133", "firefox135", "edge101", 
    "safari153", "safari260", "chrome136"
]

# Proxies are now loaded from an environment variable for better configuration management.
PROXIES = [p.strip() for p in os.getenv("YAHOO_FINANCE_PROXIES", "").split(',') if p.strip()]
if PROXIES:
    logger.info(f"Successfully loaded {len(PROXIES)} proxies from environment.")
else:
    logger.warning("YAHOO_FINANCE_PROXIES environment variable not set or is empty. No proxies will be used.")

def _should_rotate(status_code: int, body_text: str) -> bool:
    if status_code in (401, 403, 429):
        return True
    t = (body_text or "").lower()
    return "too many requests" in t or "rate limit" in t

def _pick_profile() -> str:
    return random.choice(SUPPORTED_IMPERSONATE_PROFILES)

def _get_random_user_agent() -> str:
    """Returns a random user-agent from the list."""
    return random.choice(USER_AGENTS)

def _get_random_proxy() -> dict | None:
    """
    Returns a random proxy from the configured list if available or None to use the local IP.
    This ensures that even with proxies configured, some requests will use the direct connection.
    """
    proxy_choices = PROXIES + [None]
    chosen_proxy = random.choice(proxy_choices)
    if chosen_proxy is None:
        # logger.info("Using local IP address (no proxy for this request).")
        return None
    
    # logger.info(f"Using proxy: {chosen_proxy}")
    return {"http": chosen_proxy, "https": chosen_proxy}

# identity structure and pool
class _Identity:
    def __init__(self):
        self.lock = threading.RLock()
        self.session = None
        self.crumb: Optional[str] = None
        self.expiry: float = 0.0
        self.profile: Optional[str] = None
        self.proxy: Optional[Dict[str, str]] = None
        self._bootstrap()

    def _bootstrap(self):
        self.profile = _pick_profile()
        self.proxy = _get_random_proxy()
        self.session = cffi_requests.Session(impersonate=self.profile)

    def ensure_crumb(self) -> Optional[str]:
        now = time.time()
        if self.crumb and now < self.expiry:
            return self.crumb
        with self.lock:
            # re-check after acquiring lock
            if self.crumb and time.time() < self.expiry:
                return self.crumb
            reason = "expired" if self.crumb else "missing"
            return self._refresh_crumb_locked(reason)

    def rotate_and_refresh(self, reason: str) -> Optional[str]:
        with self.lock:
            self.profile = _pick_profile()
            self.proxy = _get_random_proxy()
            self.session = cffi_requests.Session(impersonate=self.profile)
            return self._refresh_crumb_locked(reason)

    def _refresh_crumb_locked(self, reason: str = "initial") -> Optional[str]:
        headers = {"User-Agent": _get_random_user_agent()}
        try:
            resp = self.session.get(
                "https://query1.finance.yahoo.com/v1/test/getcrumb",
                headers=headers,
                proxies=self.proxy,
                impersonate=self.profile,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            self.crumb = (resp.text or "").strip()
            self.expiry = time.time() + _CRUMB_TTL_SECONDS
            logger.debug(f"Yahoo crumb refreshed ({reason}), profile={self.profile}, proxy={'on' if self.proxy else 'off'}")
            return self.crumb
        except Exception as e:
            logger.warning(f"Failed to refresh Yahoo crumb ({reason}): {e}")
            self.crumb = None
            self.expiry = 0.0
            return None

_POOL_LOCK = threading.RLock()
_ID_POOL: List[_Identity] = []

_POOL_READY = False  # readiness reflects a successfully built pool
def is_pool_ready() -> bool:
    return _POOL_READY and bool(_ID_POOL)

# init-on-import, mark ready only when pool successfully builds
def init_pool(size: int = _POOL_SIZE):
    global _ID_POOL, _POOL_READY
    with _POOL_LOCK:
        if _POOL_READY and _ID_POOL:
            return
        try:
            # build a fresh local pool first
            local_pool = [_Identity() for _ in range(max(1, size))]
            # opportunistic crumb prime; failures are tolerated
            for ident in local_pool:
                try:
                    ident.ensure_crumb()
                except Exception:
                    pass
            # publish pool only after success
            _ID_POOL = local_pool
            _POOL_READY = True  # success path only
            logger.info(f"Yahoo client pool initialized size={len(_ID_POOL)}")
        except Exception as e:
            logger.warning(f"Yahoo client pool init failed: {e}")

def _identity_weight(ident: _Identity) -> float:
    h = _ID_HEALTH.get(id(ident), {})
    if h and time.time() < h.get('cooldown_until', 0):
        return 0.01
    fail = h.get('fail', 0)
    return 1.0 / (1 + fail)

def _choose_identity() -> _Identity:
    # Per-request random identity
    with _POOL_LOCK:
        if not _ID_POOL:
            return _Identity()
        weights = [_identity_weight(ident) for ident in _ID_POOL]
        # normalize
        s = sum(weights) or 1.0
        probs = [w / s for w in weights]
        return random.choices(_ID_POOL, weights=probs, k=1)[0]

def _mark_failure(ident: _Identity):
    rec = _ID_HEALTH.setdefault(id(ident), {'fail': 0, 'cooldown_until': 0})
    rec['fail'] += 1
    # cooldown grows with failures
    rec['cooldown_until'] = time.time() + min(60, 2 ** rec['fail'])

# rotate-aware retry decorator
# the functions wrapped by it must accept or ignore _chosen_identity
def retry_on_failure(attempts: int = 3, delay: float = 0.3, backoff: float = 2.0):
    def deco(func):
        @wraps(func)  # preserve function metadata
        def wrapper(*args, **kwargs):
            last_exc = None
            wait = delay
            for i in range(max(1, attempts)):
                ident = _choose_identity()
                try:
                    return func(*args, _chosen_identity=ident, **kwargs)
                except Exception as e:
                    last_exc = e
                    # rotate identity then backoff
                    try:
                        ident.rotate_and_refresh(reason=f"retry_{i+1}")
                    except Exception:
                        pass
                    time.sleep(wait)
                    wait *= backoff
            raise last_exc
        return wrapper
    return deco

# public helper for yfinance compatibility
def get_yf_session():
    """
    Returns a curl_cffi Session from a randomly chosen identity.
    Each provider call should fetch a session fresh to maximize rotation.
    """
    ident = _choose_identity()
    # Ensure crumb readiness for first call paths that might need cookies
    try:
        ident.ensure_crumb()
    except Exception:
        pass
    return ident.session  # yfinance can accept requests-like session

def _execute_json_once(url: str, *, method: str = "GET", params: dict | None = None,
                 json_payload: dict | None = None, _chosen_identity: _Identity | None = None) -> dict:
    """
    Unified JSON transport API.
    Perform a GET to Yahoo endpoints with active rotation and return parsed JSON.
    On 401/403/429 or phrases like 'Too Many Requests', rotates identity and retries once.
    """
    ident = _chosen_identity or _choose_identity()
    crumb = ident.ensure_crumb()
    if not crumb:
        # try a rotate immediately
        crumb = ident.rotate_and_refresh("no_crumb")
        if not crumb:
            raise cffi_errors.RequestsError("Failed to obtain Yahoo crumb")

    merged = dict(params or {})
    # Yahoo chart endpoints often accept crumb in params; keep consistent
    merged["crumb"] = crumb

    headers = {"User-Agent": _get_random_user_agent()}
    func = ident.session.post if method.upper() == "POST" else ident.session.get
    try:
        resp = func(
            url,
            params=merged,
            json=json_payload if method.upper() == "POST" else None,
            headers=headers,
            proxies=ident.proxy,
            impersonate=ident.profile,
            timeout=_TIMEOUT,
        )
        body_preview = (resp.text or "")[:256]
        if not (200 <= resp.status_code < 300):
            logger.warning(f"[yf] {resp.status_code} url={url} host={resp.url.split('//')[1].split('/')[0]} params={params} body[:256]={body_preview}")
            resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _mark_failure(ident)
        logger.debug(f"execute_json failure for {url}: {e}")
        raise
    
@retry_on_failure(attempts=3, delay=3, backoff=2)
def execute_request(url: str, *, method: str = "GET", params: dict | None = None,
                 json_payload: dict | None = None, _chosen_identity: _Identity | None = None) -> dict:
    """
    Unified JSON transport API.
    Perform a GET to Yahoo endpoints with active rotation and return parsed JSON.
    On 401/403/429 or phrases like 'Too Many Requests', rotates identity and retries once.
    """
    return _execute_json_once(url, method=method, params=params, json_payload=json_payload, _chosen_identity=_chosen_identity)
