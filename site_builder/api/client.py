"""Shared MLB Stats API request plumbing."""

import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..constants import (
    API_BACKOFF_FACTOR,
    API_MAX_RETRIES,
    API_POOL_MAXSIZE,
    API_RATE_LIMIT,
    API_TIMEOUT,
)

BASE_URL = "https://statsapi.mlb.com/api/v1"
# The live feed (play-by-play) lives on the v1.1 API.
BASE_URL_V11 = "https://statsapi.mlb.com/api/v1.1"


class _RateLimiter:
    """Thread-safe limiter that paces calls to at most `rate` per second.

    Callers block in `acquire()` until their turn. Shared by every thread in
    both sync pipelines' ThreadPoolExecutors, so the *combined* request rate
    across all of them stays under the cap no matter how many workers exist.
    """

    def __init__(self, rate: float):
        self._interval = 1.0 / rate
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(self._next_slot, now)
            self._next_slot = start + self._interval
        wait = start - now
        if wait > 0:
            time.sleep(wait)


_rate_limiter = _RateLimiter(API_RATE_LIMIT)

# A requests.Session is not guaranteed thread-safe, so each worker thread gets
# its own. Reusing a Session across a thread's many requests keeps the TCP/TLS
# connection alive (HTTP keep-alive) instead of paying the ~0.15s connect cost
# on every call.
_thread_local = threading.local()


def _build_session() -> requests.Session:
    """Create a Session whose adapter pools connections and retries safely.

    Retry policy (429/502/503/504) with exponential backoff, jitter, and
    Retry-After support is delegated to urllib3's Retry rather than hand-rolled.
    Only idempotent GETs are retried.
    """
    session = requests.Session()
    retry = Retry(
        total=API_MAX_RETRIES,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        backoff_factor=API_BACKOFF_FACTOR,
        backoff_jitter=API_BACKOFF_FACTOR,
        respect_retry_after_header=True,
        raise_on_status=True,
    )
    adapter = HTTPAdapter(pool_maxsize=API_POOL_MAXSIZE, max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _build_session()
        _thread_local.session = session
    return session


def _request(url: str, timeout: int = API_TIMEOUT) -> requests.Response:
    """Rate-limited GET that reuses this thread's pooled, retrying Session.

    Raises on HTTP errors (after retries are exhausted). Shared by both
    get_json and get_text so every outbound call is paced, pooled, and retried
    the same way.
    """
    _rate_limiter.acquire()
    resp = _session().get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def get_json(url: str, timeout: int = API_TIMEOUT) -> dict:
    """GET *url* and return the parsed JSON body; raises on HTTP errors."""
    return _request(url, timeout).json()


def get_text(url: str, timeout: int = API_TIMEOUT) -> str:
    """GET *url* and return the raw text body; raises on HTTP errors.

    Used by scrapers (e.g. api/tjstats.py) that parse HTML rather than JSON,
    so they share the same pooling/retry/rate-limit plumbing as get_json.
    """
    return _request(url, timeout).text
