# Latest Add: backend-services/monitoring-service/data_fetcher.py
import os, logging, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
DATA_SERVICE_URL = os.getenv("DATA_SERVICE_URL", "http://data-service:3001")

# A per-process shared Session is standard for connection pooling 
# and is thread-safe for typical request flows; 
# it reduces latency and resource use versus creating a Session per call.
def _session():
    s = requests.Session()
    retry = Retry(
        total=4, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "HEAD", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

# Keep the session per-process to leverage connection pooling.
_session_singleton = _session()

# --- for market_leader ---
def get_sector_industry_map(timeout=60):
    url = f"{DATA_SERVICE_URL}/market/sectors/industries"
    r = _session_singleton.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}

def get_day_gainers_map(limit=200, timeout=60):
    # Screener variant that returns industry -> [tickers] mapping
    url = f"{DATA_SERVICE_URL}/market/screener/day_gainers?limit={limit}"
    r = _session_singleton.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}

def post_returns_1m_batch(tickers, timeout=30):
    if not tickers:
        return {}
    url = f"{DATA_SERVICE_URL}/data/return/1m/batch"
    r = _session_singleton.post(url, json={"tickers": tickers}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # Expect dict: { "TICK": float_or_null, ... }
    return data if isinstance(data, dict) else {t: None for t in tickers}

def get_52w_highs(timeout=60):
    # Screener returns a list of quote dicts
    url = f"{DATA_SERVICE_URL}/market/screener/52w_highs"
    r = _session_singleton.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []
# --- for market_health_utils ---
def post_price_batch(tickers, period="2y", source="yfinance", timeout=60):
    url = f"{DATA_SERVICE_URL}/price/batch"
    payload = {"tickers": tickers, "source": source, "period": period}
    r = _session_singleton.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}

def get_price_single(ticker, source="yfinance", timeout=30):
    url = f"{DATA_SERVICE_URL}/price/{ticker}?source={source}"
    r = _session_singleton.get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    return r.json()

def get_breadth(timeout=20):
    url = f"{DATA_SERVICE_URL}/market/breadth"
    r = _session_singleton.get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and any(k in item for k in ("new_highs", "new_lows", "high_low_ratio")):
                return item
    return None
