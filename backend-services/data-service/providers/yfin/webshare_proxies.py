# backend-services/data-service/providers/yfin/webshare_proxies.py
import logging
import os, time, json, random, threading
import urllib.request, urllib.error  # stdlib
from urllib.parse import urlencode

# Get a child logger
logger = logging.getLogger(__name__)
# thread-safe proxy list management
_PROXIES_LOCK = threading.RLock()

def _normalize_proxy_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    # Accept already formatted URLs
    if "@" in line and (line.startswith("http://") or line.startswith("https://")):
        return line
    # Accept raw ip:port:user:pass from Webshare download
    parts = line.split(":")
    if len(parts) >= 4:
        host, port, user, pwd = parts[0], parts[1], parts[2], ":".join(parts[3:])
        return f"http://{user}:{pwd}@{host}:{port}"
    # Accept bare host:port (no auth) – uncommon for Webshare but keep backward-compat
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    return line

def load_manual_and_file_proxies() -> list[str]:
    out: list[str] = []
    # From env var (comma-separated)
    env_raw = os.getenv("YAHOO_FINANCE_PROXIES", "")
    if env_raw:
        out.extend([_normalize_proxy_line(p) for p in env_raw.split(",") if p.strip()])
    # From optional file (one per line)
    file_path = os.getenv("YAHOO_FINANCE_PROXIES_FILE", "").strip()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                out.extend([_normalize_proxy_line(l) for l in f if l.strip()])
        except Exception as e:
            logger.warning(f"Failed reading proxies file '{file_path}': {e}")
    # De-duplicate while preserving order
    seen = set()
    dedup = []
    for p in out:
        if p and p not in seen:
            seen.add(p)
            dedup.append(p)
    return dedup

def _set_proxies(new_list: list[str]) -> None:
    global PROXIES
    with _PROXIES_LOCK:
        PROXIES = new_list
    logger.info(f"Proxy list updated, count={len(PROXIES)}")

def get_proxy_snapshot() -> list[str]:
    with _PROXIES_LOCK:
        return list(PROXIES)

def _parse_webshare_download_text(text: str) -> list[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return [_normalize_proxy_line(l) for l in lines]

def _fetch_webshare_via_download() -> list[str]:
    url = os.getenv("WEBSHARE_PROXY_DOWNLOAD_URL", "").strip()
    if not url:
        return []
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return _parse_webshare_download_text(body)
    except Exception as e:
        logger.warning(f"Webshare download fetch failed: {e}")
        return []

def _fetch_webshare_via_api() -> list[str]:
    api_key = os.getenv("WEBSHARE_API_KEY", "").strip()
    if not api_key:
        return []
    base = "https://proxy.webshare.io/api/v2/proxy/list/"
    params = {"mode": "direct"}  # return direct endpoints
    req = urllib.request.Request(f"{base}?{urlencode(params)}")
    req.add_header("Authorization", f"Token {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            results = data.get("results", [])
            out: list[str] = []
            for r in results:
                # Only include valid proxies when field is present
                if r.get("valid", True):
                    host = r.get("proxy_address")
                    port = r.get("port")
                    user = r.get("username", "")
                    pwd = r.get("password", "")
                    if host and port:
                        if user and pwd:
                            out.append(f"http://{user}:{pwd}@{host}:{port}")
                        else:
                            out.append(f"http://{host}:{port}")
            # Note: for paid tiers, paginate if needed (next in data.get("next"))
            return out
    except Exception as e:
        logger.warning(f"Webshare API fetch failed: {e}")
        return []

def _refresh_from_webshare_once() -> None:
    ws_list = _fetch_webshare_via_download() or _fetch_webshare_via_api()
    if not ws_list:
        return
    manual = load_manual_and_file_proxies()
    # Merge: Webshare first, then manual/file, preserving order and uniqueness
    merged = []
    seen = set()
    for p in ws_list + manual:
        if p and p not in seen:
            seen.add(p)
            merged.append(p)
    if merged:
        _set_proxies(merged)

def _start_webshare_refresher_thread() -> None:
    if not (os.getenv("WEBSHARE_PROXY_DOWNLOAD_URL") or os.getenv("WEBSHARE_API_KEY")):
        return
    interval = int(os.getenv("YF_PROXY_REFRESH_SECONDS", "900"))  # 15 minutes default
    def _worker():
        while True:
            try:
                _refresh_from_webshare_once()
            except Exception as e:
                logger.debug(f"Webshare refresh loop error: {e}")
            time.sleep(max(60, interval))
    t = threading.Thread(target=_worker, name="webshare-proxy-refresh", daemon=True)
    t.start()

PROXIES: list[str] = load_manual_and_file_proxies()
# kick off refresher if configured
_start_webshare_refresher_thread()
